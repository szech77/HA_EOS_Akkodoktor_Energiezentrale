"""go-e local HTTP API v2 contracts over real loopback HTTP requests."""
from contextlib import contextmanager
from datetime import timedelta
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import json
from threading import Thread
from unittest.mock import patch
from urllib.parse import parse_qs,urlsplit

import pytest

from custom_components.eos_energiezentrale.energy.drivers import WALLBOX_DRIVERS
from custom_components.eos_energiezentrale.energy.contracts import PluginContractError,UnsupportedFeature
from custom_components.eos_energiezentrale.energy.plugins.goe_http_v2 import GoEAPIError
from custom_components.eos_energiezentrale.energy.vehicle_limits import charging_profile
from test_energy import NOW


class API(ThreadingHTTPServer):
    daemon_threads=True
    def __init__(self):
        super().__init__(('127.0.0.1',0),Handler)
        self.data={'car':3,'err':0,'frc':1,'alw':False,'amp':6,'ama':32,'adi':False,
                   'cbl':32,'var':22,'psm':2,'pnp':3,'fsp':False,'mca':6,
                   'nrg':[230,231,229,0,0.,0.,0.,0.,0.,0.,0.,0.],
                   'pha':[True,True,True,False,False,False]}
        self.requests=[];self.writes=[]
        self.reject=set();self.ignore=set();self.pending={};self.delay=0
        # Status reads that keep alw=false (modelStatus 22) after a release with sua on.
        self.simulate=0
        # Next status reads answered with an error, as a slow charger would.
        self.fail_status=0;self.fail_after_write=0
        self.redirect=self.bad_json=self.meter_down=self.down=False


class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        self.server.requests.append(self.path)
        target=urlsplit(self.path);query=parse_qs(target.query)
        if self.server.redirect:
            self.send_response(302);self.send_header('Location','/trap');self.end_headers();return
        if self.server.down or self.server.meter_down and 'nrg' in query.get('filter',[''])[0]:
            self.send_error(503);return
        if target.path=='/api/status' and self.server.fail_status:
            self.server.fail_status-=1
            self.send_error(503);return
        if target.path=='/api/status':
            for key,(value,count) in tuple(self.server.pending.items()):
                if count==0:
                    self.server.data[key]=value
                    del self.server.pending[key]
                else: self.server.pending[key]=(value,count-1)
            keys=query.get('filter',[''])[0].split(',')
            body={key:self.server.data[key] for key in keys if key in self.server.data}
        elif target.path=='/api/set':
            changes={key:json.loads(value[0]) for key,value in query.items()}
            self.server.fail_status,self.server.fail_after_write=self.server.fail_status+self.server.fail_after_write,0
            self.server.writes.append(changes)
            body={key:'denied' if key in self.server.reject else True for key in changes}
            for key,value in changes.items():
                if key in self.server.reject or key in self.server.ignore: continue
                if self.server.delay and key=='amp': self.server.pending[key]=(value,self.server.delay)
                else: self.server.data[key]=value
                if key=='frc':
                    self.server.data['alw']=value==2
                    if value==1 and self.server.data['car']==2: self.server.data['car']=3
                    if value==2 and self.server.data.get('sua') is True and self.server.simulate:
                        # The charger first simulates unplugging, then allows charging.
                        self.server.data.update(alw=False,modelStatus=22)
                        self.server.pending.update(alw=(True,self.server.simulate),modelStatus=(3,self.server.simulate))
        else:
            self.send_error(404);return
        raw=b'invalid' if self.server.bad_json else json.dumps(body).encode()
        self.send_response(200);self.send_header('Content-Type','application/json')
        self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)


@contextmanager
def api(**params):
    with API() as server:
        thread=Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
        url=f'http://127.0.0.1:{server.server_port}'
        driver=WALLBOX_DRIVERS['goe_http_v2'](None,{'url':url,**params})
        try: yield driver,server
        finally: server.shutdown();thread.join(timeout=2)


def test_discovery_and_native_api_v2_units_need_no_ha_entities():
    with api() as (driver,server):
        server.data['nrg'][11]=4140.5
        sample=driver.read({},NOW)
        assert (sample.watts,sample.status,sample.phases,sample.maximum,sample.step)==(4140.5,'connected',3,32,1)
        assert sample.sample==NOW and sample.nominal_voltage==230
        assert not any(driver.ids.values()) and not server.writes
        assert 'v2' in driver.info.name and driver.features.optional_connection
        assert all(path.startswith('/api/status?filter=') for path in server.requests)


@pytest.mark.parametrize('car,status',[(0,'unknown'),(1,'disconnected'),(2,'charging'),(3,'connected'),
                                     (4,'connected'),(5,'error'),(6,'unknown'),(None,'unknown')])
def test_vehicle_states_are_distinguished_from_unavailable_meter_values(car,status):
    with api() as (driver,server):
        server.data['car']=car
        assert driver.read({},NOW).status==status


def test_cable_adapter_and_hardware_limits_are_reported_to_eos():
    with api(phase_switching=True) as (driver,server):
        server.data['adi']=True
        sample=driver.read({},NOW)
        assert sample.maximum==16 and sample.max_phases==3
        profile=charging_profile(sample,driver,{'max_current_a':32},{'phase_auto':True},True)
        assert profile[0:2]==(11040,1380) and profile[3]
        server.data.update(adi=False,cbl=13)
        assert driver.read({},NOW).maximum==13
        server.data.update(var=11,cbl=32)
        assert driver.read({},NOW).maximum==16
        server.data['car']=1;server.data['cbl']=0
        sample=driver.read({},NOW)
        profile=charging_profile(sample,driver,{'max_current_a':32},{'phase_auto':True},False)
        assert sample.watts==0 and profile[2:]==((0.,),False)


@pytest.mark.parametrize('key,value',[('cbl',None),('ama',None),('var',255),('mca',8),('mca',None)])
def test_unknown_limits_never_become_a_guessed_charging_capability(key,value):
    with api() as (driver,server):
        server.data[key]=value
        assert driver.read({},NOW).maximum is None
        with pytest.raises(PluginContractError): driver.charge(16,driver.read({},NOW))
        assert not server.writes


def test_charging_sets_current_before_permission_and_waits_for_readback():
    with api() as (driver,server),patch('custom_components.eos_energiezentrale.energy.plugins.goe_http_v2.sleep'):
        server.delay=2
        driver.charge(16,driver.read({},NOW))
        assert server.writes==[{'amp':16},{'frc':2}]
        assert server.data['amp']==16 and server.data['alw']
        count=len(server.requests)
        driver.charge(16,driver.read({},NOW))
        assert len(server.writes)==2 and len(server.requests)>count
        driver.pause(driver.read({},NOW))
        assert server.writes[-1]=={'frc':1} and not server.data['alw']


def test_fresh_lower_limit_or_disconnected_car_prevents_new_enable():
    with api() as (driver,server):
        sample=driver.read({},NOW)
        server.data['adi']=True
        with pytest.raises(GoEAPIError): driver.charge(32,sample)
        assert {'frc':2} not in server.writes and {'amp':32} not in server.writes
        server.data['car']=1
        with pytest.raises(GoEAPIError): driver.charge(6,sample)
        assert all('amp' not in command for command in server.writes)


def test_fractional_or_out_of_bounds_current_is_rejected_before_network_access():
    with api() as (driver,server):
        sample=driver.read({},NOW);server.requests.clear()
        for amps in (5,33,6.5,float('nan')):
            with pytest.raises(PluginContractError): driver.charge(amps,sample)
        assert not server.requests and not server.writes


def test_device_rejection_does_not_enable_and_stop_is_confirmed_independently():
    with api() as (driver,server):
        server.reject.add('amp')
        with pytest.raises(GoEAPIError): driver.charge(16,driver.read({},NOW))
        assert {'frc':2} not in server.writes and server.writes[-1]=={'frc':1}
        server.reject.add('frc')
        with pytest.raises(GoEAPIError): driver.pause(driver.read({},NOW))


def test_success_acknowledgement_without_readback_is_not_a_confirmed_command():
    with api() as (driver,server):
        server.ignore.add('amp')
        ticks=iter(index*.5 for index in range(100))
        with patch('custom_components.eos_energiezentrale.energy.plugins.goe_http_v2.monotonic',side_effect=lambda:next(ticks)), \
                patch('custom_components.eos_energiezentrale.energy.plugins.goe_http_v2.sleep'):
            with pytest.raises(GoEAPIError): driver.charge(16,driver.read({},NOW))
        assert {'frc':2} not in server.writes and server.writes[-1]=={'frc':1}


def test_offline_or_malformed_telemetry_is_unknown_and_independent_pause_still_works():
    with api() as (driver,server):
        server.meter_down=True
        sample=driver.read({},NOW)
        assert sample.status=='unavailable' and sample.watts is None
        driver.pause(sample)
        assert server.data['frc']==1
        server.meter_down=False;server.data['nrg']=None
        assert driver.read({},NOW).watts is None
        driver.pause(sample)
        server.bad_json=True
        assert driver.read({},NOW).status=='unavailable'
        with pytest.raises(GoEAPIError): driver.pause(sample)


def test_errors_and_unknown_permission_do_not_allow_charging():
    with api() as (driver,server):
        sample=driver.read({},NOW)
        server.data['err']=13
        assert driver.read({},NOW).status=='error'
        with pytest.raises(GoEAPIError): driver.charge(6,sample)
        assert {'frc':2} not in server.writes
        server.data['alw']=None
        assert driver.read({},NOW).status=='unavailable'


def test_phases_are_derived_from_api_and_switching_is_explicitly_opt_in():
    with api() as (driver,server):
        assert not driver.features.phase_switching
        with pytest.raises(UnsupportedFeature): driver.phase(1,driver.read({},NOW))
        assert not server.writes
    with api(phase_switching=True) as (driver,server):
        server.data['pha']=[True,False,False,False,False,False]
        server.data['nrg'][:3]=[230,0,0];server.data['pnp']=1
        sample=driver.read({},NOW)
        assert sample.max_phases==sample.phases==1 and not driver.features.phase_switching
        server.data['pha']=[True,True,False,False,False,False]
        assert driver.read({},NOW).phases is None


def test_phase_switch_requires_pause_two_new_zero_samples_and_reported_phase():
    with api(phase_switching=True) as (driver,server), \
            patch('custom_components.eos_energiezentrale.energy.plugins.goe_http_v2.datetime') as clock:
        sample=driver.read({},NOW)
        clock.now.return_value=NOW
        assert not driver.phase(1,sample)
        assert server.writes==[{'frc':1}]
        clock.now.return_value=NOW+timedelta(seconds=1)
        assert not driver.phase(1,sample)
        clock.now.return_value=NOW+timedelta(seconds=3)
        assert not driver.phase(1,sample)
        assert {'psm':1} not in server.writes
        clock.now.return_value=NOW+timedelta(seconds=4)
        assert not driver.phase(1,sample)
        assert server.writes[-1]=={'psm':1}
        with pytest.raises(GoEAPIError): driver.charge(6,sample)
        assert not driver.phase(1,sample)  # pnp still reports the old hardware phase.
        server.data.update(pnp=1,fsp=True)
        assert driver.phase(1,sample)
        assert driver.phase_requested is None
        driver.charge(6,driver.read({},NOW+timedelta(seconds=4)))
        assert server.writes[-1]=={'frc':2}


def test_current_measurement_prevents_phase_switch_despite_zero_watt_reading():
    with api(phase_switching=True) as (driver,server), \
            patch('custom_components.eos_energiezentrale.energy.plugins.goe_http_v2.datetime') as clock:
        sample=driver.read({},NOW)
        for second in (0,1,5,10):
            clock.now.return_value=NOW+timedelta(seconds=second)
            server.data['nrg'][4]=6.
            assert not driver.phase(1,sample)
        assert all('psm' not in command for command in server.writes)


def test_single_phase_vehicle_can_charge_in_three_phase_station_mode():
    with api() as (driver,server):
        server.data.update(pnp=1,psm=2)
        sample=driver.read({},NOW)
        assert sample.phases==3
        driver.charge(6,sample)
        assert server.writes==[{'frc':2}]


def test_unconfirmed_phase_switch_times_out_without_enabling_the_vehicle():
    with api(phase_switching=True) as (driver,server):
        sample=driver.read({},NOW)
        driver.phase_requested=(1,0)
        server.data['psm']=1
        with patch('custom_components.eos_energiezentrale.energy.plugins.goe_http_v2.monotonic',return_value=46):
            with pytest.raises(GoEAPIError,match='phase switch'):
                driver.phase(1,sample)
        assert {'frc':2} not in server.writes
        driver.pause(sample)
        assert driver.phase_requested is None and server.data['frc']==1


def test_the_same_direct_wallbox_cannot_be_assigned_to_two_vehicles():
    from custom_components.eos_energiezentrale.const import DEFAULTS
    from custom_components.eos_energiezentrale.energy.fleet import vehicle_options
    with api() as (driver,server):
        rows=[{'id':f'car{index}','resource':f'ev{index}','wallbox_type':'goe_http_v2',
               'wallbox_parameters':{'url':driver.url}} for index in (2,3)]
        with pytest.raises(ValueError,match='shared'):
            vehicle_options({**DEFAULTS,'vehicles':json.dumps(rows)})
        assert not server.requests


def test_redirects_are_not_followed_and_error_messages_do_not_expose_private_responses():
    with api() as (driver,server):
        server.redirect=True
        assert driver.read({},NOW).status=='unavailable'
        with pytest.raises(GoEAPIError) as error: driver.pause(driver.read({},NOW))
        assert not any('/trap' in path for path in server.requests)
        assert driver.url not in str(error.value)


@pytest.mark.parametrize('params',[{'url':'http://user:password@charger.local'},
    {'url':'http://charger.local/api'},{'url':'http://charger.local:0'},
    {'url':'http://charger.local','nominal_voltage':0},{'phase_switching':'true'}])
def test_invalid_parameters_are_rejected_without_network_access(params):
    with patch('socket.create_connection') as connect,pytest.raises(ValueError):
        WALLBOX_DRIVERS['goe_http_v2'](None,params)
    connect.assert_not_called()


def test_the_chargers_own_decision_is_logged_on_each_change_and_kept_for_diagnostics(caplog):
    with api() as (driver,server):
        server.data.update(modelStatus=4,acs=0,lmo=3,sua=False,fwv='60.3')
        caplog.set_level('INFO','custom_components.eos_energiezentrale.energy.plugins.goe_http_v2')
        driver.read({},NOW)
        driver.read({},NOW)
        assert driver.charger_status=={'car':{'code':3,'name':'WaitCar'},'force':{'code':1,'name':'Off'},
            'allowed':False,'reason':{'code':4,'name':'NotChargingBecauseForceStateOff'},
            'access_control':{'code':0,'name':'Open'},'logic_mode':{'code':3,'name':'Default'},
            'error':0,'simulate_unplugging_always':False,'firmware':'60.3'}
        # The charger allows charging, but the vehicle does not take current: one new entry with the reason.
        server.data.update(frc=2,alw=True,modelStatus=3)
        server.data['nrg'][11]=1234.5
        driver.read({},NOW)
        server.data['amp']=10
        driver.read({},NOW)
        entries=[record.getMessage() for record in caplog.records if 'go-e charger status' in record.getMessage()]
        assert len(entries)==2 and 'ChargingBecauseForceStateOn' in entries[1] and '"WaitCar"' in entries[1]
        # Neither measurements, currents nor addresses are logged.
        assert not any(text in '\n'.join(entries) for text in ('1234','127.0.0.1','"amp"'))


def test_an_older_firmware_without_reason_codes_still_controls_normally():
    with api() as (driver,server):
        assert driver.read({},NOW).status=='connected'
        assert driver.charger_status['reason'] is None and driver.charger_status['firmware'] is None
        server.data['fwv']='<script>'
        driver.read({},NOW)
        assert driver.charger_status['firmware'] is None


@contextmanager
def stalled_vehicle(**params):
    """Charging is released, but the vehicle reports a finished session and takes no power."""
    clock = [1000.]
    with api(**params) as (driver, server), \
            patch('custom_components.eos_energiezentrale.energy.plugins.goe_http_v2.monotonic', lambda: clock[0]), \
            patch('custom_components.eos_energiezentrale.energy.plugins.goe_http_v2.sleep'):
        server.data.update(car=4, frc=2, alw=True, amp=16, sua=False)
        yield driver, server, clock


def charge_at(driver, clock, seconds):
    clock[0] = 1000. + seconds
    driver.charge(16, driver.read({}, NOW))


def test_a_released_vehicle_that_reports_complete_is_restarted_at_most_twice_by_simulated_unplugging(caplog):
    caplog.set_level('INFO', 'custom_components.eos_energiezentrale.energy.plugins.goe_http_v2')
    with stalled_vehicle(simulate_unplugging=True) as (driver, server, clock):
        for seconds in (0, 30, 59):
            charge_at(driver, clock, seconds)
        assert not server.writes
        charge_at(driver, clock, 60)
        # The charger's own setting is enabled and confirmed, then the session is restarted.
        assert server.writes == [{'sua': True}, {'frc': 1}, {'frc': 2}]
        assert server.data['sua'] is True and server.data['alw']
        assert any('go-e simulated unplugging' in record.getMessage() and 'enabled' in record.getMessage()
                   for record in caplog.records)
        assert any('attempt 1 of 2' in record.getMessage() and 'Complete' in record.getMessage() for record in caplog.records)
        # Still not charging: one more restart after another full minute, then no more in this session.
        charge_at(driver, clock, 120)
        assert len(server.writes) == 3
        for seconds in (180, 600, 3600):
            charge_at(driver, clock, seconds)
        assert server.writes[3:] == [{'frc': 1}, {'frc': 2}]
        # After charging or unplugging, a new stall gets new attempts; the setting is already on.
        server.data['car'] = 2
        driver.read({}, NOW)
        server.data['car'] = 4
        charge_at(driver, clock, 4000)
        charge_at(driver, clock, 4060)
        assert server.writes[5:] == [{'frc': 1}, {'frc': 2}]


def test_simulated_unplugging_is_opt_in():
    with stalled_vehicle() as (driver, server, clock):
        assert driver.unplugging is False
        for seconds in (0, 60, 3600):
            charge_at(driver, clock, seconds)
        assert not server.writes


@pytest.mark.parametrize('change', [{'car': 2}, {'nrg': [230, 231, 229, 0, 0., 0., 0., 0., 0., 0., 0., 1500.]}])
def test_a_charging_unplugged_or_power_drawing_vehicle_is_never_unplugged(change):
    with stalled_vehicle(simulate_unplugging=True) as (driver, server, clock):
        server.data.update(change)
        for seconds in (0, 60, 3600):
            charge_at(driver, clock, seconds)
        assert not server.writes


def test_the_stall_must_last_without_interruption():
    with stalled_vehicle(simulate_unplugging=True) as (driver, server, clock):
        charge_at(driver, clock, 0)
        server.data['nrg'] = [230, 231, 229, 0, 0., 0., 0., 0., 0., 0., 0., 1500.]
        charge_at(driver, clock, 40)
        server.data['nrg'] = [230, 231, 229, 0, 0., 0., 0., 0., 0., 0., 0., 0.]
        charge_at(driver, clock, 70)
        charge_at(driver, clock, 129)
        assert not server.writes
        charge_at(driver, clock, 130)
        assert server.writes == [{'sua': True}, {'frc': 1}, {'frc': 2}]


def test_a_failed_restart_stops_charging_and_is_not_repeated():
    with stalled_vehicle(simulate_unplugging=True) as (driver, server, clock):
        server.reject.add('sua')
        charge_at(driver, clock, 0)
        with pytest.raises(GoEAPIError):
            charge_at(driver, clock, 60)
        assert server.writes[-1] == {'frc': 1} and not server.data['alw']
        server.reject.clear()
        server.data.update(frc=2, alw=True)
        writes = len(server.writes)
        charge_at(driver, clock, 200)
        assert len(server.writes) == writes


def test_the_unplugging_setting_can_only_be_switched_on():
    with api() as (driver, server):
        with pytest.raises(ValueError):
            driver._set(sua=False)
        assert not server.writes


def hold_at(driver, clock, seconds):
    clock[0] = 1000. + seconds
    driver.hold(16, driver.read({}, NOW))


def test_an_unchanged_release_is_watched_while_the_controller_only_holds_it():
    with stalled_vehicle(simulate_unplugging=True) as (driver, server, clock):
        for seconds in (0, 30, 59):
            hold_at(driver, clock, seconds)
        assert not server.writes
        hold_at(driver, clock, 60)
        assert server.writes == [{'sua': True}, {'frc': 1}, {'frc': 2}]
        hold_at(driver, clock, 600)
        assert len(server.writes) == 3


def test_holding_a_charging_vehicle_needs_no_extra_request():
    with stalled_vehicle(simulate_unplugging=True) as (driver, server, clock):
        server.data['car'] = 2
        server.data['nrg'] = [230, 231, 229, 0, 0., 0., 0., 0., 0., 0., 0., 3500.]
        state = driver.read({}, NOW)
        count = len(server.requests)
        driver.hold(16, state)
        assert len(server.requests) == count and not server.writes


def test_a_failed_restart_while_holding_stops_charging():
    with stalled_vehicle(simulate_unplugging=True) as (driver, server, clock):
        server.reject.add('frc')
        hold_at(driver, clock, 0)
        with pytest.raises(GoEAPIError):
            hold_at(driver, clock, 60)
        assert server.writes[0] == {'sua': True} and server.writes[-1] == {'frc': 1}


def test_plugins_cannot_bypass_the_hold_contract():
    from custom_components.eos_energiezentrale.energy.plugin_registry import validate_class
    from custom_components.eos_energiezentrale.energy.plugins.goe_http_v2 import GoEHTTPv2

    class Bypass(GoEHTTPv2):
        def hold(self, amps, state): pass

    class WrongSignature(GoEHTTPv2):
        def _hold(self, amps): pass

    for plugin in (Bypass, WrongSignature):
        with pytest.raises(PluginContractError):
            validate_class(plugin)
    assert validate_class(GoEHTTPv2) is GoEHTTPv2


def test_a_release_during_the_chargers_simulated_unplugging_is_confirmed_without_pausing():
    with stalled_vehicle(simulate_unplugging=True) as (driver, server, clock):
        server.simulate = 6
        charge_at(driver, clock, 0)
        charge_at(driver, clock, 60)
        # The restart is accepted although charging is not yet allowed during the simulation.
        assert server.writes == [{'sua': True}, {'frc': 1}, {'frc': 2}]
        assert server.data['frc'] == 2
        # With sua on, every later release passes the simulation as well, without a pause.
        server.data.update(frc=1, alw=False)
        driver.charge(16, driver.read({}, NOW))
        assert server.writes[-1] == {'frc': 2} and {'frc': 1} not in server.writes[3:]


def test_a_slow_status_answer_while_confirming_is_retried():
    with api() as (driver, server), patch('custom_components.eos_energiezentrale.energy.plugins.goe_http_v2.sleep'):
        state = driver.read({}, NOW)
        server.fail_after_write = 2
        driver.charge(16, state)
        assert server.writes == [{'amp': 16}, {'frc': 2}] and server.data['alw']


def test_a_release_that_stays_disallowed_without_simulation_is_still_a_failure():
    with api() as (driver, server):
        server.ignore.add('frc')
        ticks = iter(index * .5 for index in range(200))
        with patch('custom_components.eos_energiezentrale.energy.plugins.goe_http_v2.monotonic', side_effect=lambda: next(ticks)), \
                patch('custom_components.eos_energiezentrale.energy.plugins.goe_http_v2.sleep'):
            with pytest.raises(GoEAPIError):
                driver.charge(16, driver.read({}, NOW))
        assert server.writes[-1] == {'frc': 1}


def test_a_stop_is_never_confirmed_by_a_simulated_unplugging():
    with api() as (driver, server):
        server.data.update(frc=2, alw=True, modelStatus=22)
        server.ignore.add('frc')
        ticks = iter(index * .5 for index in range(200))
        with patch('custom_components.eos_energiezentrale.energy.plugins.goe_http_v2.monotonic', side_effect=lambda: next(ticks)), \
                patch('custom_components.eos_energiezentrale.energy.plugins.goe_http_v2.sleep'):
            with pytest.raises(GoEAPIError):
                driver.pause(driver.read({}, NOW))


def test_a_simulated_unplugging_longer_than_a_normal_confirmation_does_not_fail_the_release():
    with api() as (driver, server):
        server.data.update(sua=True, modelStatus=4)
        server.simulate = 1000  # Still simulating when the confirmation ends.
        ticks = iter(index * .5 for index in range(400))
        with patch('custom_components.eos_energiezentrale.energy.plugins.goe_http_v2.monotonic', side_effect=lambda: next(ticks)), \
                patch('custom_components.eos_energiezentrale.energy.plugins.goe_http_v2.sleep'):
            driver.charge(16, driver.read({}, NOW))
        assert server.writes == [{'amp': 16}, {'frc': 2}]
        assert server.data['frc'] == 2 and server.data['modelStatus'] == 22


def test_a_released_vehicle_waiting_without_power_is_restarted_like_a_finished_one():
    with stalled_vehicle(simulate_unplugging=True) as (driver, server, clock):
        server.data['car'] = 3
        charge_at(driver, clock, 0)
        charge_at(driver, clock, 60)
        assert server.writes == [{'sua': True}, {'frc': 1}, {'frc': 2}]


def test_a_completed_phase_switch_allows_one_more_restart():
    with stalled_vehicle(simulate_unplugging=True, phase_switching=True) as (driver, server, clock):
        driver.unplug_attempts = 2
        driver.phase_requested = (1, 0.)
        server.data.update(frc=1, alw=False, psm=1, pnp=1, fsp=True)
        with patch('custom_components.eos_energiezentrale.energy.plugins.goe_http_v2.datetime') as now:
            now.now.return_value = NOW
            assert driver.phase(1, driver.read({}, NOW))
        assert driver.unplug_attempts == 1 and driver.stalled_since is None


@pytest.mark.parametrize('model,car,error,reason', [
    (2, 3, 0, 'access_control'), (27, 3, 0, 'load_management'), (24, 4, 0, 'min_pause'), (5, 3, 0, 'charger_logic'),
    (3, 4, 0, 'vehicle_complete'), (3, 3, 0, 'vehicle_waiting'), (3, 3, 7, 'charger_error'), (None, 3, 0, 'vehicle_waiting'),
    (3, 2, 0, None),
])
def test_the_chargers_own_reason_explains_an_idle_release(model, car, error, reason):
    with api() as (driver, server):
        server.data.update(car=car, err=error, frc=2, alw=True)
        if model is not None:
            server.data['modelStatus'] = model
        driver.read({}, NOW)
        assert driver.idle_reason() == reason


@pytest.mark.parametrize('model', [23, 24, 29])
def test_a_release_held_by_the_chargers_own_timed_reason_is_confirmed(model):
    with api() as (driver, server):
        ticks = iter(index * .5 for index in range(400))
        with patch('custom_components.eos_energiezentrale.energy.plugins.goe_http_v2.monotonic', side_effect=lambda: next(ticks)), \
                patch('custom_components.eos_energiezentrale.energy.plugins.goe_http_v2.sleep'):
            # Not the simulation: the charger holds the accepted release for another timed reason.
            server.ignore.add('frc')
            server.data.update(frc=2, alw=False, modelStatus=model)
            driver._set(frc=2)
        assert server.writes[-1] == {'frc': 2}


def test_access_control_never_confirms_a_release():
    with api() as (driver, server):
        server.ignore.add('frc')
        server.data.update(frc=2, alw=False, modelStatus=2)
        ticks = iter(index * .5 for index in range(400))
        with patch('custom_components.eos_energiezentrale.energy.plugins.goe_http_v2.monotonic', side_effect=lambda: next(ticks)), \
                patch('custom_components.eos_energiezentrale.energy.plugins.goe_http_v2.sleep'):
            with pytest.raises(GoEAPIError):
                driver._set(frc=2)


def test_an_unplugged_vehicle_is_never_unplugged():
    with stalled_vehicle(simulate_unplugging=True) as (driver, server, clock):
        server.data['car'] = 1
        for seconds in (0, 60, 3600):
            hold_at(driver, clock, seconds)
        assert not server.writes

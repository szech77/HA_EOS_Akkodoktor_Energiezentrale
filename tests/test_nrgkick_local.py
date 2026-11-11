"""Real HTTP round trips against a local NRGkick Gen2 API emulator."""
import base64
from contextlib import contextmanager
from datetime import timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from threading import Thread
from unittest.mock import patch, Mock
from urllib.parse import parse_qs, urlsplit

import pytest

from custom_components.eos_energiezentrale.energy.contracts import UnsupportedFeature
from custom_components.eos_energiezentrale.energy.drivers import WALLBOX_DRIVERS
from custom_components.eos_energiezentrale.energy.plugins.nrgkick_local import NRGkickAPIError
from custom_components.eos_energiezentrale.energy.plugin_registry import describe
from test_energy import NOW, instruction, temporary_project_directory


class API(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self):
        super().__init__(("127.0.0.1", 0), Handler)
        self.info = {"general":{"model_type":"NRGkick Gen2","rated_current":32},
                     "connector":{"phase_count":3,"max_current":32},"grid":{"phases":7,"voltage":230}}
        self.control = {"current_set":6.,"charge_pause":1,"phase_count":3,"energy_limit":12345}
        self.values = {"general":{"status":2,"charge_permitted":0,"relay_state":0,
                                  "error_code":0,"rcd_trigger":0},"powerflow":{"total_active_power":0.}}
        self.writes, self.requests = [], []
        self.ignore = set()
        self.fail = set()
        self.authorization = None
        self.redirect = False
        self.invalid_json = False


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        target = urlsplit(self.path)
        self.server.requests.append(self.path)
        if self.server.authorization and self.headers.get("Authorization") != self.server.authorization:
            self.send_error(401)
            return
        if self.server.redirect:
            self.send_response(302)
            self.send_header("Location", "/trap")
            self.end_headers()
            return
        if target.path in self.server.fail:
            self.send_error(500)
            return
        if target.path == "/control":
            changes = {key:values[0] for key,values in parse_qs(target.query).items()}
            if changes:
                self.server.writes.append(changes)
                for key,value in changes.items():
                    if key not in self.server.ignore:
                        self.server.control[key] = float(value) if key == "current_set" else int(value)
            body = self.server.control
        elif target.path == "/info":
            body = self.server.info
        elif target.path == "/values":
            body = self.server.values
        else:
            self.send_error(404)
            return
        data = b"bad json" if self.server.invalid_json else json.dumps(body).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


@contextmanager
def api(**parameters):
    with API() as server:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval":.01}, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        driver = WALLBOX_DRIVERS['nrgkick_local'](None,{"url":url,**parameters})
        try:
            yield driver,server
        finally:
            server.shutdown()
            thread.join(timeout=2)


def test_discovery_and_reading_need_no_ha_entities_and_preserve_real_zero():
    with api() as (driver,server):
        measured = driver.read({},NOW)
        assert (measured.watts,measured.status,measured.enabled,measured.phases)==(0,'connected',False,3)
        assert (measured.amps,measured.step,measured.maximum,measured.sample)==(6,.1,32,NOW)
        assert all(not value for value in driver.ids.values())
        assert describe(driver)['measurements']==['car']
        assert '/values?raw&powerflow&general' in server.requests
        assert not server.writes


@pytest.mark.parametrize('status,expected',[(0,'unknown'),(1,'disconnected'),(2,'connected'),
                                         (3,'charging'),(6,'error'),(7,'wakeup'),('CONNECTED','connected')])
def test_status_mapping(status,expected):
    with api() as (driver,server):
        server.values['general'].update(status=status,relay_state=15)
        assert driver.read({},NOW).status==expected


def test_current_limit_uses_both_hardware_and_attachment_and_refreshes():
    with api() as (driver,server):
        server.info['connector']['max_current']=10
        assert driver.read({},NOW).maximum==10
        server.info['general']['rated_current']=16
        server.info['connector']['max_current']=32
        assert driver.read({},NOW).maximum==16


@pytest.mark.parametrize('power',[None,True,-1,float('nan'),float('inf')])
def test_invalid_power_is_unknown_never_zero(power):
    with api() as (driver,server):
        server.values['powerflow']['total_active_power']=power
        measured=driver.read({},NOW)
        assert measured.watts is None and measured.sample is None


def test_read_failure_still_allows_independent_confirmed_pause():
    with api() as (driver,server):
        server.control['charge_pause']=0
        server.fail.add('/values')
        measured=driver.read({},NOW)
        assert measured.status=='unavailable' and measured.watts is None
        driver.pause(measured)
        assert server.control['charge_pause']==1
        assert server.writes==[{'charge_pause':'1'}]


def test_current_is_confirmed_before_unpausing_and_energy_limit_is_preserved():
    with api() as (driver,server):
        driver.charge(10.1,driver.read({},NOW))
        assert server.writes==[{'current_set':'10.1'},{'charge_pause':'0'}]
        assert server.control['energy_limit']==12345


def test_a_write_echo_is_not_a_confirmation_and_failed_current_never_enables():
    with api() as (driver,server):
        server.ignore.add('current_set')
        with pytest.raises(NRGkickAPIError):
            driver.charge(10,driver.read({},NOW))
        assert server.control['charge_pause']==1
        assert server.writes==[{'current_set':'10.0'}]


def test_fresh_device_limit_is_checked_before_a_command():
    with api() as (driver,server):
        old=driver.read({},NOW)
        server.info['connector']['max_current']=10
        with pytest.raises(NRGkickAPIError): driver.charge(16,old)
        assert not server.writes


def test_a_concurrent_phase_change_cannot_enable_three_times_the_reserved_load():
    with api() as (driver,server):
        server.control['phase_count']=1
        old=driver.read({},NOW)
        server.control['phase_count']=3
        with pytest.raises(NRGkickAPIError): driver.charge(6,old)
        assert not server.writes


def test_a_concurrent_voltage_change_cannot_increase_the_reserved_load():
    with api() as (driver,server):
        server.info['grid']['voltage']=120
        old=driver.read({},NOW)
        server.info['grid']['voltage']=230
        with pytest.raises(NRGkickAPIError): driver.charge(6,old)
        assert not server.writes


@pytest.mark.parametrize('code,rcd',[(16,0),(0,1),(None,0)])
def test_hardware_faults_prevent_enabling(code,rcd):
    with api() as (driver,server):
        old=driver.read({},NOW)
        server.values['general'].update(error_code=code,rcd_trigger=rcd)
        with pytest.raises(NRGkickAPIError): driver.charge(6,old)
        assert not server.writes


def test_phase_switching_is_opt_in_and_requires_three_phase_hardware():
    with api() as (driver,server):
        old=driver.read({},NOW)
        with pytest.raises(UnsupportedFeature): driver.phase(1,old)
        assert not server.writes
    with api(phase_switching=True) as (driver,server):
        server.info['connector']['phase_count']=1
        assert driver.read({},NOW).phases==1
        assert not driver.features.phase_switching


def test_phase_switch_waits_for_two_new_zero_readings_after_confirmed_pause():
    with api(phase_switching=True) as (driver,server):
        server.control['charge_pause']=0
        server.values['powerflow']['total_active_power']=100
        assert not driver.phase(1,driver.read({},NOW))
        assert server.writes==[{'charge_pause':'1'}]
        server.values['powerflow']['total_active_power']=0
        for seconds in (1,1,2):
            assert not driver.phase(1,driver.read({},NOW+timedelta(seconds=seconds)))
            assert server.control['phase_count']==3
        assert not driver.phase(1,driver.read({},NOW+timedelta(seconds=4)))
        assert server.control['phase_count']==1
        assert server.control['charge_pause']==1
        assert driver.phase(1,driver.read({},NOW+timedelta(seconds=5)))
        driver.charge(6,driver.read({},NOW+timedelta(seconds=6)))
        assert server.writes[-2:]==[{'current_set':'6.0'},{'charge_pause':'0'}]


def test_phase_switch_cannot_proceed_on_residual_power_or_unconfirmed_pause():
    with api(phase_switching=True) as (driver,server):
        server.control['charge_pause']=0
        server.ignore.add('charge_pause')
        with pytest.raises(NRGkickAPIError): driver.phase(1,driver.read({},NOW))
        assert server.control['phase_count']==3
        server.ignore.clear()
        assert not driver.phase(1,driver.read({},NOW))
        server.values['powerflow']['total_active_power']=31
        for seconds in (4,10):
            assert not driver.phase(1,driver.read({},NOW+timedelta(seconds=seconds)))
        assert server.control['phase_count']==3


def test_pending_phase_confirmation_times_out():
    with api(phase_switching=True) as (driver,server):
        state=driver.read({},NOW)
        driver.phase_requested=(1,0)
        with patch('custom_components.eos_energiezentrale.energy.plugins.nrgkick_local.monotonic',return_value=46):
            with pytest.raises(NRGkickAPIError): driver.phase(1,state)
        assert not server.writes


def test_basic_auth_uses_environment_and_secrets_never_enter_errors():
    with api(username='local',password_env='NRGKICK_TEST_PASSWORD') as (driver,server):
        expected='Basic '+base64.b64encode(b'local:fixture-password').decode()
        server.authorization=expected
        with patch.dict('os.environ',{'NRGKICK_TEST_PASSWORD':'fixture-password'}):
            assert driver.read({},NOW).watts==0
        with pytest.raises(NRGkickAPIError) as error: driver.pause(driver.read({},NOW))
        assert 'fixture-password' not in str(error.value) and '127.0.0.1' not in str(error.value)


def test_http_redirects_and_malformed_json_are_not_followed_or_used():
    with api() as (driver,server):
        server.redirect=True
        assert driver.read({},NOW).status=='unavailable'
        assert not any('/trap' in path for path in server.requests)
        server.redirect=False
        server.invalid_json=True
        assert driver.read({},NOW).watts is None


@pytest.mark.parametrize('params',[{'url':'http://user:password@nrgkick.local'}, {'url':'http://nrgkick.local/api'},
                                  {'url':'http://nrgkick.local:0'},{'username':'local'},
                                  {'username':'local','password_env':'invalid-name'}])
def test_invalid_configuration_fails_before_network_access(params):
    with patch('urllib.request.OpenerDirector.open') as open_request,pytest.raises(ValueError):
        WALLBOX_DRIVERS['nrgkick_local'](None,params)
    open_request.assert_not_called()


@pytest.mark.parametrize('already_enabled',[False,True])
def test_two_native_devices_share_grid_headroom_without_ha_wallbox_entities(already_enabled):
    from custom_components.eos_energiezentrale.const import DEFAULTS
    from custom_components.eos_energiezentrale.energy.fleet import create_controller
    from test_fleet import definitions, LocalHA
    with api() as (_,first),api() as (_,second),temporary_project_directory() as directory:
        devices=(first,second)
        vehicles=definitions()
        for vehicle,device in zip(vehicles,devices):
            vehicle['wallbox_type']='nrgkick_local'
            vehicle['wallbox_parameters']={'url':f'http://127.0.0.1:{device.server_port}'}
            device.control.update(phase_count=1,charge_pause=0 if already_enabled else 1)
        opts={**DEFAULTS,'vehicles':json.dumps(vehicles),'heat_entity':'','phase_wait_s':10,
              'max_current_a':6 if already_enabled else 16}
        ha=LocalHA(opts)
        budget=2000 if already_enabled else 6000
        ha.rows[opts['grid_entity']]['state']=str(-budget)
        for old in definitions():
            for entity in old['wallbox_parameters'].values(): ha.rows.pop(entity,None)
        app=create_controller(ha,opts,directory)
        app.config.eos=Mock()
        app.config.eos.plan.return_value={'generated_at':NOW.isoformat(),'instructions':[instruction(NOW,'NON_EXPORT')]+[
            {**instruction(NOW,'NON_EXPORT'),'resource_id':row['resource']} for row in vehicles]}
        app.config.eos.solution.return_value={}
        app.battery_driver.apply=Mock();app.battery_driver.release=Mock()
        for key,_,_ in app.controllers:
            app.change_vehicle_settings(key,{'pv':True,'phase_auto':False})
        app.set_armed(True)
        for seconds in (0,20,25): app.tick(NOW+timedelta(seconds=seconds),seconds)
        assert 0<sum(app.targets.values())<=budget
        if already_enabled:
            assert sum(device.control['charge_pause']==0 for device in devices)==1
        else:
            assert all(device.control['charge_pause']==0 for device in devices)
        assert not ha.writes
        if not already_enabled:
            first.fail.update(('/info','/values','/control'))
            previous_calls=app.battery_driver.apply.call_count+app.battery_driver.release.call_count
            app.tick(NOW+timedelta(seconds=35),35)
            assert app.armed and second.control['charge_pause']==0
            assert app.live['car'] is None
            assert app.vehicle_snapshots[0]['live']['car_connected'] is False
            assert 'wallbox_stop' in app.vehicle_snapshots[0]['errors']
            assert app.battery_driver.apply.call_count+app.battery_driver.release.call_count>previous_calls
            first.fail.clear()
        first.fail.add('/values')
        app.set_armed(False)
        assert all(device.control['charge_pause']==1 for device in devices)


def test_duplicate_direct_device_is_rejected_without_network_access():
    from custom_components.eos_energiezentrale.const import DEFAULTS
    from custom_components.eos_energiezentrale.energy.fleet import vehicle_options
    from test_fleet import definitions
    vehicles=definitions()
    for index,vehicle in enumerate(vehicles):
        vehicle['wallbox_type']='nrgkick_local'
        vehicle['wallbox_parameters']={'url':'http://NRGKICK.local' if index==0 else 'http://nrgkick.local:80/'}
    with patch('urllib.request.OpenerDirector.open') as open_request,pytest.raises(ValueError):
        vehicle_options({**DEFAULTS,'vehicles':json.dumps(vehicles)})
    open_request.assert_not_called()


@pytest.mark.parametrize('phases,grid,amps,watts',[(1,1,10,2300),(3,7,16,11040),(3,1,13,2990)])
def test_socket_limits_translate_to_eos_power_and_discrete_rates(phases,grid,amps,watts):
    from custom_components.eos_energiezentrale.energy.vehicle_limits import charging_profile
    with api(phase_switching=True) as (driver,server):
        server.info['connector'].update(phase_count=phases,max_current=amps)
        server.info['grid']['phases']=grid
        box=driver.read({},NOW)
        profile=charging_profile(box,driver,{'max_current_a':32},{'phase_auto':True},True)
        assert box.max_phases == (3 if phases==3 and grid==7 else 1)
        assert box.max_power_w==watts
        assert profile[0]==watts and profile[3] is True
        assert profile[2][0]==0 and profile[2][-1]==1
        assert profile[1]==1380


def test_missing_socket_limits_never_make_an_active_eos_profile():
    from custom_components.eos_energiezentrale.energy.vehicle_limits import charging_profile
    with api() as (driver,server):
        server.info['grid'].pop('voltage')
        profile=charging_profile(driver.read({},NOW),driver,{'max_current_a':16},{'phase_auto':False},True)
        assert profile == (None,None,(0.,),False)


@contextmanager
def native_controller(driver):
    from types import SimpleNamespace
    from zoneinfo import ZoneInfo
    from custom_components.eos_energiezentrale.energy.controller import Controller
    from custom_components.eos_energiezentrale.energy.contracts import BatteryReading
    from custom_components.eos_energiezentrale.energy.settings import daily_settings
    from test_requirements import OPTIONS, ControllerRequirements
    with temporary_project_directory() as directory:
        ha,eos,battery=Mock(),Mock(),Mock()
        ha.states.return_value=ControllerRequirements.states(grid=-6000)
        battery.read.return_value=BatteryReading(50,0,0)
        eos.plan.return_value={'generated_at':NOW.isoformat(),'instructions':[instruction(NOW,'NON_EXPORT')]}
        eos.solution.return_value={}
        config=SimpleNamespace(directory=directory,options={**OPTIONS,'wallbox_type':'nrgkick_local'},
            daily=daily_settings({},20),zone=ZoneInfo('Europe/Berlin'),wallbox=driver,
            eos=eos,battery=battery,influx=SimpleNamespace(url=None))
        app=Controller(ha,config)
        app.set_armed(True)
        yield app,battery,eos


@pytest.mark.parametrize('offline',[False,True])
def test_absent_ev_does_not_block_startup_or_battery_control_and_reconnects(offline):
    with api() as (driver,server),native_controller(driver) as (app,battery,eos):
        app.config.daily.update(schedule='once',departure=(NOW+timedelta(hours=4)).isoformat())
        if offline: server.fail.update(('/info','/control','/values'))
        else: server.values['general']['status']=1
        app.tick(NOW,0)
        assert app.armed and not app.restore_pending
        assert app.live['car_connected'] is False
        assert app.live['car_available'] is (not offline)
        assert app.live['car'] == (None if offline else 0.)
        assert app.order_for('ev1',NOW) is None
        assert app.eos_resources()=={'battery1'}
        assert battery.apply.called or battery.release.called
        assert ('wallbox_stop' in app.errors) is offline
        assert eos.set_vehicle_charging_limits.call_args.args[-2:]==((0.,),False)
        eos.set_vehicle_goal.assert_called_with('ev1',0,None)
        if offline:
            assert app.commanded_car_w is None
        server.fail.clear()
        server.values['general']['status']=2
        app.tick(NOW+timedelta(seconds=30),30)
        assert app.live['car_connected'] is True
        assert 'wallbox_stop' not in app.errors
        assert app.vehicle_profile[-1] is True
        assert eos.set_vehicle_charging_limits.call_args.args[-1] is True
        assert eos.set_vehicle_goal.call_args.args[1]>0
        assert app.armed


def test_socket_change_refreshes_eos_limits_and_local_fast_charge_is_bounded():
    with api() as (driver,server),native_controller(driver) as (app,_,eos):
        app.config.daily.update(fast=True,phase_auto=False)
        app.tick(NOW,0)
        server.info['connector'].update(phase_count=1,max_current=10)
        server.info['grid']['phases']=1
        server.control['phase_count']=1
        app.tick(NOW+timedelta(seconds=30),30)
        assert app.vehicle_profile[0]==2300
        assert eos.set_vehicle_charging_limits.call_args.args[1]==2300
        assert server.control['current_set']<=10
        assert app.commanded_car_w<=2300


def test_unconfirmed_charge_and_stop_remain_local_to_portable_charger():
    with api() as (driver,server),native_controller(driver) as (app,battery,_):
        app.config.daily.update(fast=True,phase_auto=False)
        server.ignore.update(('current_set','charge_pause'))
        app.tick(NOW,0)
        assert app.armed
        assert 'wallbox' in app.errors and 'wallbox_stop' not in app.errors
        # A failed current write has not enabled charging; a confirmed stop is safe.
        assert server.control['charge_pause']==1
        assert battery.apply.called or battery.release.called

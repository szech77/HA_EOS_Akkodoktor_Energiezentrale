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
            self.server.writes.append(changes)
            body={key:'denied' if key in self.server.reject else True for key in changes}
            for key,value in changes.items():
                if key in self.server.reject or key in self.server.ignore: continue
                if self.server.delay and key=='amp': self.server.pending[key]=(value,self.server.delay)
                else: self.server.data[key]=value
                if key=='frc':
                    self.server.data['alw']=value==2
                    if value==1 and self.server.data['car']==2: self.server.data['car']=3
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

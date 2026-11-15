"""Victron incidents at the real driver boundary, without an open panel."""
from datetime import timedelta
import json
import logging
from unittest.mock import patch

import pytest

from custom_components.eos_energiezentrale.configuration_logging import configuration_failure
from custom_components.eos_energiezentrale.energy._modbus_tcp import ModbusError
from custom_components.eos_energiezentrale.energy.device_io import DeviceConfirmationError, DeviceNotReady
from custom_components.eos_energiezentrale.energy.devices import DeviceSite
from custom_components.eos_energiezentrale.energy.drivers import BATTERY_DRIVERS
from test_energy import NOW
from test_victron_modbus import gx, command
import test_victron_ha as shared


@pytest.mark.parametrize('address,stage,count',[(800,'identity',6),(834,'firmware',1),(840,'battery',4),
    (850,'dc_pv',1),(808,'ac_pv_output',3),(811,'ac_pv_input',3),(820,'grid',3),(817,'consumption',3)])
def test_modbus_device_failure_logs_context_once_then_recovers(address,stage,count,caplog):
    caplog.set_level(logging.INFO,logger='custom_components.eos_energiezentrale')
    with gx(ac_pv_output_enabled=True,ac_pv_input_enabled=True) as (_,server,params):
        site=DeviceSite(None,[{'id':'private-id','name':'Private installation','kind':'battery','plugin':'victron_modbus',
            'parameters':params,'capacity_wh':32000,'charge_w':5000,'discharge_w':5000,'grid_source':True}])
        original=server.registers[address]
        server.registers[address]=0 if address in (800,834,840) else 65535 if address!=820 else 32767
        assert site.read({},NOW).soc is None
        issue=site.site_summary['devices'][0]['telemetry_status'][0]
        assert issue['plugin']=='victron_modbus' and issue['scope']=='device/1'
        assert issue['code']=='plugin_read_failed'
        assert {key:issue['details'][key] for key in ('stage','unit','address','count')}==dict(stage=stage,unit=100,address=address,count=count)
        assert len(caplog.records)==1
        site.read({},NOW)
        assert len(caplog.records)==1
        server.registers[address]=original
        assert site.read({},NOW).soc==60
        assert not site.site_summary['devices'][0]['telemetry_status']
        assert 'resolved' in caplog.records[-1].message
        assert not server.writes
    assert 'Private installation' not in caplog.text and 'private-id' not in caplog.text


def test_modbus_transport_rejection_and_snapshot_timeout_have_distinct_causes(caplog):
    with gx() as (driver,server,_):
        server.reject=True
        with pytest.raises(ModbusError): driver.read({},NOW)
        assert driver.telemetry_status[0]['details']['exception_code']==3
        with patch.object(driver.client,'read',side_effect=TimeoutError('private-host test-secret')):
            with pytest.raises(TimeoutError): driver.read({},NOW)
        assert driver.telemetry_status[0]['details']['exception']=='TimeoutError'
        assert 'changed' in caplog.records[-1].message
        server.reject=False
        with patch('custom_components.eos_energiezentrale.energy.plugins.victron_modbus.monotonic',side_effect=[0,11]):
            with pytest.raises(ModbusError): driver.read({},NOW)
        assert driver.telemetry_status[0]['details']['stage']=='snapshot_timeout'
        assert 'address' not in driver.telemetry_status[0]['details']
        assert 'private-host' not in caplog.text and 'test-secret' not in caplog.text


@pytest.mark.parametrize('operation,address,stage',[
    ('apply',5423,'dynamic_ess'),('apply',826,'grid_connection'),('release',2902,'ess_mode'),
    ('power_limits',840,'battery')])
def test_modbus_operation_guards_are_logged_without_new_writes(operation,address,stage,caplog):
    caplog.set_level(logging.INFO,logger='custom_components.eos_energiezentrale')
    with gx() as (driver,server,_):
        original=server.registers[address]
        server.registers[address]=3 if address==2902 else 0 if address in (840,826) else 1
        def run():
            return driver.apply(command(),{}) if operation=='apply' else getattr(driver,operation)({})
        for _ in range(2):
            with pytest.raises(ModbusError): run()
        assert len(caplog.records)==1
        issue=driver.telemetry_status[0]
        assert issue['code']=='plugin_operation_failed' and issue['scope'].endswith('/'+operation)
        assert issue['severity']=='error' and issue['details']['stage']==stage
        assert issue['details']['address']==(2900 if address==2902 else address)
        assert not server.writes
        # A healthy regular read cannot clear an unconfirmed command incident.
        if operation!='power_limits':
            driver.read({},NOW)
            assert driver.telemetry_status
        server.registers[address]=original
        run()
        assert not driver.telemetry_status
        assert 'resolved' in caplog.records[-1].message


@pytest.mark.parametrize('operation,address', [('apply',2705),('release',2716)])
def test_modbus_write_confirmation_failure_identifies_register(operation,address,caplog):
    with gx() as (driver,server,_):
        server.ignore_writes=True
        if operation=='release': server.registers[2717]=3000
        with pytest.raises(ModbusError):
            if operation=='apply': driver.apply(command('grid_charge',2000,0),{})
            else: driver.release({})
        issue=driver.telemetry_status[0]
        assert issue['details']['stage']=='write_confirmation' and issue['details']['address']==address
        assert issue['scope'].endswith('/'+operation)
        assert len(server.writes)==1


@pytest.fixture(params=['victron_ha','victron_gx'])
def entity_driver(request):
    case=shared.VictronTests()
    case.plugin_id=request.param
    case.setUp()
    return case


@pytest.mark.parametrize('change,reason', [
    ('missing','entity_missing'),('unavailable','state_unavailable'),('invalid','invalid_value'),
    ('unit','unit_invalid'),('stale','stale'),('future','future_sample'),('no_stamp','sample_missing')])
def test_entity_plugins_log_precise_missing_source_cause_and_valid_zero_recovers(entity_driver,change,reason,caplog):
    case=entity_driver;driver=case.driver;row=case.ha.rows['sensor.solar']
    caplog.set_level(logging.INFO,logger='custom_components.eos_energiezentrale')
    original=dict(row,attributes=dict(row['attributes']))
    if change=='missing': del case.ha.rows['sensor.solar']
    elif change=='unavailable': row['state']='unavailable'
    elif change=='invalid': row['state']='private-invalid-value'
    elif change=='unit': row['attributes']['unit_of_measurement']='private-invalid-unit'
    elif change=='stale': row['last_reported']=(case.ha.now-timedelta(seconds=46)).isoformat()
    elif change=='future': row['last_reported']=(case.ha.now+timedelta(seconds=1)).isoformat()
    else: row.pop('last_reported')
    assert driver.read(case.ha.rows,case.ha.now).measurements['solar'].value is None
    issue=driver.telemetry_status[0]
    assert issue['plugin']==case.plugin_id and issue['measurements']==['solar']
    assert issue['source_problems']==[{'measurement':'solar','reason':reason,'max_age_s':45}]
    driver.read(case.ha.rows,case.ha.now)
    assert len(caplog.records)==1
    case.ha.rows['sensor.solar']={**original,'state':'0'}
    assert driver.read(case.ha.rows,case.ha.now).measurements['solar'].value==0
    assert not driver.telemetry_status and 'resolved' in caplog.records[-1].message
    assert 'sensor.solar' not in caplog.text and 'private-invalid' not in caplog.text


def test_entity_soc_grace_period_and_battery_power_failures_are_logged(entity_driver):
    case=entity_driver;driver=case.driver
    case.ha.rows['sensor.soc']['last_reported']=(case.ha.now-timedelta(seconds=200)).isoformat()
    driver.read(case.ha.rows,case.ha.now)
    assert not driver.telemetry_status
    case.ha.rows['sensor.soc']['last_reported']=(case.ha.now-timedelta(seconds=361)).isoformat()
    case.ha.rows['sensor.battery']['attributes']['unit_of_measurement']='A'
    driver.read(case.ha.rows,case.ha.now)
    issues={item['measurement']:item for item in driver.telemetry_status[0]['source_problems']}
    assert issues['battery_soc']['reason']=='stale' and issues['battery_soc']['max_age_s']==360
    assert issues['battery_charge']['reason']==issues['battery_discharge']['reason']=='unit_invalid'


def test_entity_wrong_ess_mode_and_unconfirmed_controls_are_logged(entity_driver,caplog):
    case=entity_driver;driver=case.driver
    caplog.set_level(logging.INFO,logger='custom_components.eos_energiezentrale')
    case.ha.rows['select.ess']['state']='external_control'
    for _ in range(2):
        with pytest.raises(ValueError): driver.apply(case.command(),{})
    assert len(caplog.records)==1 and not case.ha.writes
    assert driver.telemetry_status[0]['details']['stage']=='ess_mode'
    assert driver.telemetry_status[0]['details']['parameter']=='ess_mode'
    case.ha.rows['select.ess']['state']='optimized_no_battery_life'
    case.ha.ignore.add('number.charge')
    with patch('custom_components.eos_energiezentrale.energy.device_io.monotonic',side_effect=[0,6]):
        with pytest.raises(DeviceConfirmationError): driver.apply(case.command('grid_charge',2000,0),{})
    issue=driver.telemetry_status[0]
    assert issue['details']['stage']=='write_confirmation' and issue['details']['parameter']=='charge_limit'
    assert issue['details']['exception']=='DeviceConfirmationError'
    assert case.ha.writes==[('number.charge',40)]
    case.ha.ignore.clear()
    driver.apply(case.command('grid_charge',2000,0),{})
    assert not driver.telemetry_status and 'resolved' in caplog.records[-1].message
    assert 'number.charge' not in caplog.text


@pytest.mark.parametrize('operation', ['release','power_limits'])
def test_entity_release_and_power_limits_errors_remain_visible(entity_driver,operation,caplog):
    case=entity_driver;driver=case.driver
    case.ha.rows['number.discharge']['state']='unavailable'
    with pytest.raises(DeviceNotReady): getattr(driver,operation)(case.ha.rows)
    issue=driver.telemetry_status[0]
    assert issue['scope'].endswith('/'+operation) and issue['details']['parameter']=='discharge_limit'
    assert issue['details']['exception']=='DeviceNotReady'
    assert not case.ha.writes


@pytest.mark.parametrize('plugin,params,parameter',[
    ('victron_modbus',{'host':'gx.test','port':0},'port'),
    ('victron_modbus',{'host':'http://private-host'},'host'),
    ('victron_modbus',{'host':'gx.test','control_enabled':True},'release_charge_current'),
    ('victron_ha',{'soc':'sensor.soc','battery_power':'sensor.battery','control_enabled':True},'grid'),
    ('victron_gx',{'soc':'sensor.soc','battery_power':'sensor.battery','charge_efficiency':0},'charge_efficiency')])
def test_invalid_victron_configuration_logs_parameter_without_value(plugin,params,parameter,caplog):
    from types import SimpleNamespace
    owner=SimpleNamespace(data={})
    with patch('socket.create_connection') as connect:
        with pytest.raises(ValueError) as caught: BATTERY_DRIVERS[plugin](None,params)
        configuration_failure(owner,'device_parameters',caught.value,plugin)
        connect.assert_not_called()
    assert 'configuration_invalid' in caplog.text
    assert json.loads(caplog.records[-1].message.split(': ',1)[1])['details']['parameter']==parameter
    assert 'private-host' not in caplog.text and 'sensor.soc' not in caplog.text

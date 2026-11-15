"""Deye, generic entity drivers and Fronius HA incidents at real boundaries."""
from dataclasses import replace
from datetime import timedelta
import json
import logging
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from custom_components.eos_energiezentrale.configuration_logging import configuration_failure
from custom_components.eos_energiezentrale.energy._modbus_tcp import ModbusError
from custom_components.eos_energiezentrale.energy.device_io import DeviceConfirmationError, DeviceNotReady
from custom_components.eos_energiezentrale.energy.domain import BatteryCommand
from custom_components.eos_energiezentrale.energy.drivers import BATTERY_DRIVERS, INVERTER_DRIVERS, WALLBOX_DRIVERS
from test_deye_modbus import deye
from test_devices import storage
from test_energy import NOW
from test_plugins import EntityHA, row, generic_wallbox


def fronius():
    driver=BATTERY_DRIVERS['fronius'](None,{})
    rows={driver.ids[key]:row(value,unit) for key,value,unit in
        [('soc',60,'%'),('charge_power',0,'W'),('discharge_power',0,'W')]}
    rows[driver.ids['mode']]=row('Auto',options=['Auto',*driver.modes.values()])
    for key in ('pv_limit','discharge_limit','grid_charge'):
        rows[driver.ids[key]]=row(0,'W',min=0,max=5000,step=10)
    ha=EntityHA(rows)
    return BATTERY_DRIVERS['fronius'](ha,{}),ha


@pytest.fixture(params=['generic_battery','generic_inverter','generic_wallbox','fronius'])
def entity_plugin(request):
    if request.param=='generic_battery':
        definition,ha=storage()
        return BATTERY_DRIVERS['generic'](ha,definition['parameters']),ha,'soc','battery_soc'
    if request.param=='generic_inverter':
        ha=EntityHA({'sensor.pv':row(0,'W'),'sensor.ac':row(0,'W')})
        return INVERTER_DRIVERS['generic'](ha,{'solar':'sensor.pv','inverter_ac':'sensor.ac'}),ha,'solar','solar'
    if request.param=='generic_wallbox':
        params,ha=generic_wallbox()
        return WALLBOX_DRIVERS['generic'](ha,params),ha,'power','car'
    driver,ha=fronius()
    return driver,ha,'charge_power','battery_charge'


@pytest.mark.parametrize('change,reason', [('missing','entity_missing'),('unavailable','state_unavailable'),
    ('invalid','invalid_value'),('stale','stale'),('future','future_sample'),('stamp','sample_missing')])
def test_entity_read_causes_are_precise_deduplicated_and_recover(entity_plugin,change,reason,caplog):
    driver,ha,key,measurement=entity_plugin
    entity=driver.ids[key];original=ha.rows[entity];bad={**original}
    ha.rows[entity]=bad
    if change=='missing': del ha.rows[entity]
    elif change=='unavailable': bad['state']='unavailable'
    elif change=='invalid': bad['state']='private-invalid-state'
    elif change=='stale': bad['last_reported']=(NOW-timedelta(seconds=121)).isoformat()
    elif change=='future': bad['last_reported']=(NOW+timedelta(seconds=1)).isoformat()
    else: bad.pop('last_reported')
    caplog.set_level(logging.INFO,logger='custom_components.eos_energiezentrale')
    for _ in range(2): driver.read(ha.rows,NOW)
    assert len(caplog.records)==1
    issue=driver.telemetry_status[0]
    assert issue['code']=='plugin_measurements_incomplete' and measurement in issue['measurements']
    assert next(item for item in issue['source_problems'] if item['measurement']==measurement)['reason']==reason
    ha.rows[entity]=original
    driver.read(ha.rows,NOW)
    assert not driver.telemetry_status and 'resolved' in caplog.records[-1].message
    assert entity not in caplog.text and 'private-invalid-state' not in caplog.text


def test_generic_battery_units_mode_and_hardware_bounds_are_logged(caplog):
    definition,ha=storage();driver=BATTERY_DRIVERS['generic'](ha,definition['parameters'])
    ha.rows['sensor.charge']['attributes']['unit_of_measurement']='A'
    assert driver.read(ha.rows,NOW).charge is None
    assert driver.telemetry_status[0]['source_problems'][0]['reason']=='unit_invalid'
    ha.rows['sensor.charge']['attributes']['unit_of_measurement']='W'
    driver.read(ha.rows,NOW)
    ha.rows['input_number.charge']['attributes']['max']='private-invalid-bound'
    with pytest.raises(ValueError): driver.power_limits(ha.rows)
    assert driver.telemetry_status[0]['scope'].endswith('/power_limits')
    assert driver.telemetry_status[0]['details']['parameter']=='charge_limit'
    ha.rows['input_number.charge']['attributes']['max']=2000
    driver.power_limits(ha.rows)
    ha.rows['input_select.mode']['attributes']['options']=[]
    for _ in range(2):
        with pytest.raises(ValueError): driver.apply(BatteryCommand('limits'),ha.rows)
    issue=driver.telemetry_status[0]
    assert issue['scope'].endswith('/apply') and issue['details']['parameter']=='mode_map'
    assert issue['details']['stage']=='mode_option'
    assert 'private-invalid-bound' not in caplog.text and 'input_select.mode' not in caplog.text


@pytest.mark.parametrize('kind,operation', [('generic','apply'),('generic','release'),('fronius','apply'),('fronius','release')])
def test_battery_unconfirmed_modes_are_logged_and_success_resolves(kind,operation,caplog):
    if kind=='generic':
        definition,ha=storage();driver=BATTERY_DRIVERS[kind](ha,definition['parameters'])
        ha.rows[driver.ids['mode']]['state']='limits' if operation=='release' else 'auto'
    else:
        driver,ha=fronius()
        ha.rows[driver.ids['mode']]['state']='Charge from Grid' if operation=='release' else 'Auto'
    def run():
        return driver.apply(BatteryCommand('limits'),ha.rows) if operation=='apply' else driver.release(ha.rows)
    with patch.object(ha,'set'),patch('custom_components.eos_energiezentrale.energy.device_io.monotonic',side_effect=[0,6]):
        with pytest.raises(DeviceConfirmationError): run()
    issue=driver.telemetry_status[0]
    assert issue['details']['parameter']=='mode' and issue['details']['stage']=='write_confirmation'
    assert issue['scope'].endswith('/'+operation)
    caplog.set_level(logging.INFO,logger='custom_components.eos_energiezentrale')
    run()
    assert not driver.telemetry_status and 'resolved' in caplog.records[-1].message


def test_fronius_mode_dependent_limit_keeps_wait_timeout_and_parameter_context():
    driver,ha=fronius();ha.rows[driver.ids['mode']]['state']='Charge from Grid'
    ha.rows[driver.ids['grid_charge']]['state']='unavailable'
    for timestamp,error in ((100,DeviceNotReady),(145,DeviceConfirmationError)):
        with patch('custom_components.eos_energiezentrale.energy.plugins.fronius.monotonic',return_value=timestamp):
            with pytest.raises(error): driver.apply(BatteryCommand('grid_charge',1000),ha.rows)
        issue=driver.telemetry_status[0]
        assert issue['details']['parameter']=='grid_charge' and issue['details']['stage']=='control_state'
        assert issue['details']['exception']==error.__name__
    assert not ha.commands
    ha.rows[driver.ids['grid_charge']]['state']='0'
    driver.apply(BatteryCommand('grid_charge',1000),ha.rows)
    assert not driver.telemetry_status


@pytest.mark.parametrize('key,change,reason', [('enable','state','state_unavailable'),('current','unit','unit_invalid'),
    ('plugged','state','state_unavailable'),('phases','state','state_unavailable')])
def test_wallbox_control_problems_name_fixed_parameters(key,change,reason):
    params,ha=generic_wallbox();driver=WALLBOX_DRIVERS['generic'](ha,params)
    if change=='unit': ha.rows[params[key]]['attributes']['unit_of_measurement']='W'
    else: ha.rows[params[key]]['state']='unavailable'
    driver.read(ha.rows,NOW)
    assert {'parameter':key,'reason':reason} in driver.telemetry_status[0]['control_problems']


def test_wallbox_charge_pause_and_phase_failures_have_operation_context(caplog):
    params,ha=generic_wallbox();params.update(phases='number.phases',phase_switching=True)
    ha.rows['number.phases']=row(3)
    driver=WALLBOX_DRIVERS['generic'](ha,params);state=driver.read(ha.rows,NOW)
    with patch.object(ha,'set'),patch('custom_components.eos_energiezentrale.energy.device_io.monotonic',side_effect=[0,6]):
        with pytest.raises(DeviceConfirmationError): driver.charge(7,state)
    assert driver.telemetry_status[0]['details']['parameter']=='current'
    assert driver.telemetry_status[0]['scope'].endswith('/charge')
    driver.charge(7,state)
    with patch.object(ha,'set',side_effect=OSError('private-host test-secret')):
        with pytest.raises(OSError): driver.pause(replace(state,enabled=True))
    assert driver.telemetry_status[0]['scope'].endswith('/pause')
    driver.pause(state)
    driver.phase_requested=(1,NOW-timedelta(seconds=60))
    with pytest.raises(ValueError): driver.phase(1,state)
    assert driver.telemetry_status[0]['details']['stage']=='phase_feedback'
    # An ongoing retry cannot resolve a timed-out hardware confirmation.
    assert driver.phase(1,replace(state,sample=NOW-timedelta(seconds=30))) is False
    assert driver.telemetry_status
    assert driver.phase(1,replace(state,phases=1)) is True
    assert not driver.telemetry_status
    assert 'private-host' not in caplog.text and 'test-secret' not in caplog.text


@pytest.mark.parametrize('kind', ['battery','inverter'])
def test_deye_read_failure_logs_protocol_rejection_and_transport_without_private_data(kind,caplog):
    with deye() as (battery,server,params):
        driver=battery if kind=='battery' else INVERTER_DRIVERS['deye_modbus'](None,
            {key:value for key,value in params.items() if key not in {'remote_control','grid_discharge_supported'}})
        server.reject=True
        for _ in range(2):
            with pytest.raises(ModbusError): driver.read({},NOW)
        assert len(caplog.records)==1
        details=driver.telemetry_status[0]['details']
        assert details['stage']=='identity' and details['address']==0 and details['count']==25 and details['unit']==1
        assert details['exception_code']==3
        with patch.object(driver.connection.client,'read',side_effect=TimeoutError('private-host test-secret')):
            with pytest.raises(TimeoutError): driver.read({},NOW)
        assert driver.telemetry_status[0]['details']['exception']=='TimeoutError'
        server.reject=False
        driver.read({},NOW)
        assert not driver.telemetry_status
        assert 'private-host' not in caplog.text and 'test-secret' not in caplog.text


@pytest.mark.parametrize('kind', ['battery','inverter'])
def test_deye_partial_invalid_values_keep_good_measurements_and_locate_rejected_pv(kind):
    with deye() as (battery,server,params):
        driver=battery if kind=='battery' else INVERTER_DRIVERS['deye_modbus'](None,
            {key:value for key,value in params.items() if key not in {'remote_control','grid_discharge_supported'}})
        server.registers[672]=65535
        result=driver.read({},NOW)
        assert result.measurements['solar'].value is None and result.measurements['grid'].value==1200
        issue=driver.telemetry_status[0]
        assert issue['details']['address']==672 and issue['details']['count']==2
        assert issue['source_problems'][0]['reason']=='invalid_value'
        server.registers[672]=0;server.registers[673]=0
        assert driver.read({},NOW).measurements['solar'].value==0
        assert not driver.telemetry_status and not server.writes


@pytest.mark.parametrize('kind', ['battery','inverter'])
@pytest.mark.parametrize('address,count,stage',[(0,25,'identity'),(587,108,'telemetry'),(111,1,'battery_mode')])
def test_deye_each_read_step_keeps_its_actual_failed_register(kind,address,count,stage):
    with deye() as (battery,server,params):
        driver=battery if kind=='battery' else INVERTER_DRIVERS['deye_modbus'](None,
            {key:value for key,value in params.items() if key not in {'remote_control','grid_discharge_supported'}})
        read=driver.connection.client.read
        def rejected(register,words):
            if register==address: raise ModbusError('private response',exception_code=2)
            return read(register,words)
        with patch.object(driver.connection.client,'read',side_effect=rejected):
            with pytest.raises(ModbusError): driver.read({},NOW)
        details=driver.telemetry_status[0]['details']
        assert (details['address'],details['count'],details['stage'],details['exception_code'])==(address,count,stage,2)
        assert not server.writes


def test_deye_invalid_storage_is_logged_without_requiring_storage_on_pv_only_driver():
    with deye(grid=False) as (driver,server,params):
        server.registers[588]=65535
        assert driver.read({},NOW).soc is None
        assert driver.telemetry_status[0]['measurements']==['battery_soc']
        assert driver.telemetry_status[0]['details']['address']==588
        with pytest.raises(ModbusError): driver.apply(BatteryCommand('grid_charge',1200),{})
        assert next(item for item in driver.telemetry_status if item['scope'].endswith('/apply'))['details']['address']==588
        pv=INVERTER_DRIVERS['deye_modbus'](None,
            {key:value for key,value in params.items() if key not in {'remote_control','grid_discharge_supported'}})
        assert pv.read({},NOW).measurements['solar'].value==5000
        assert not pv.telemetry_status
        server.registers[0]=0
        with pytest.raises(ModbusError): pv.read({},NOW)
        assert pv.telemetry_status[0]['details']['stage']=='identity'


def test_deye_power_limits_and_remote_mode_errors_are_distinct_and_recover():
    with deye() as (driver,server,_):
        server.registers[212]=65535
        with pytest.raises(ModbusError): driver.power_limits({})
        issue=driver.telemetry_status[0]
        assert issue['scope'].endswith('/power_limits') and issue['details']['address']==212
        server.registers[212]=100;driver.power_limits({})
        server.registers[1100]=2
        with pytest.raises(ModbusError): driver.apply(BatteryCommand('grid_charge',1200),{})
        assert driver.telemetry_status[0]['details']['stage']=='remote_mode'
        assert not server.writes
        server.registers[1100]=0
        driver.apply(BatteryCommand('grid_charge',1200),{})
        assert not driver.telemetry_status


def test_deye_nested_power_limit_error_keeps_original_register_in_both_operations():
    with deye() as (driver,server,_):
        server.registers[212]=65535
        with pytest.raises(ModbusError): driver.apply(BatteryCommand('grid_charge',1200),{})
        issues={item['scope'].rsplit('/',1)[-1]:item['details'] for item in driver.telemetry_status}
        assert issues['power_limits']['address']==issues['apply']['address']==212
        assert issues['power_limits']['stage']==issues['apply']['stage']=='bms_limits'
        assert not server.writes


def test_deye_failed_activation_and_cleanup_preserve_both_causes():
    with deye() as (driver,server,_):
        write=driver.client.write
        def failed_ack(address,values):
            write(address,values)
            if address==1100:
                if values==[1]: raise TimeoutError('private activation')
                raise ModbusError('private cleanup',exception_code=4)
        with patch.object(driver.client,'write',side_effect=failed_ack):
            with pytest.raises(TimeoutError): driver.apply(BatteryCommand('grid_charge',1200),{})
        issues={item['scope'].rsplit('/',1)[-1]:item['details'] for item in driver.telemetry_status}
        assert issues['apply']['exception']=='TimeoutError' and issues['apply']['address']==1100
        assert issues['release']['exception']=='ModbusError' and issues['release']['exception_code']==4
        assert server.registers[1100]==0
        driver.release({})
        assert len(driver.telemetry_status)==1 and driver.telemetry_status[0]['scope'].endswith('/apply')
        driver.apply(BatteryCommand('grid_charge',1200),{})
        assert not driver.telemetry_status


@pytest.mark.parametrize('kind,plugin,params,parameter',[
    ('battery','deye_modbus',{'host':'gx.test','unit_id':248},'unit_id'),
    ('battery','deye_modbus',{'host':'gx.test','maximum_soc':101},'maximum_soc'),
    ('battery','generic',{'mode_map':{}},'mode_map'),
    ('battery','fronius',{'soc':'select.private'},'soc'),
    ('wallbox','generic',{'status_map':{'secret':'not-a-status'}},'status_map')])
def test_configuration_failures_identify_parameter_without_values(kind,plugin,params,parameter,caplog):
    if plugin=='generic' and kind=='battery': params=storage()[0]['parameters'] | params
    if kind=='wallbox': params=generic_wallbox()[0] | params
    factory=(BATTERY_DRIVERS if kind=='battery' else WALLBOX_DRIVERS)[plugin]
    with pytest.raises(ValueError) as caught: factory(None,params)
    configuration_failure(SimpleNamespace(data={}), 'device_parameters',caught.value,plugin)
    issue=json.loads(caplog.records[-1].message.split(': ',1)[1])
    assert issue['details']['parameter']==parameter
    assert 'select.private' not in caplog.text and 'not-a-status' not in caplog.text

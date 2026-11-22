"""Optional firmware discovery must not confuse Venus 3.66 with old ESS APIs."""
from unittest.mock import patch

import pytest

from custom_components.eos_energiezentrale.diagnostics import device_diagnostics
from custom_components.eos_energiezentrale.energy._modbus_tcp import ModbusError
from custom_components.eos_energiezentrale.energy.failures import PluginParameterError
from custom_components.eos_energiezentrale.energy.drivers import BATTERY_DRIVERS
from test_victron_modbus import gx,command,NOW,target


def test_reserved_firmware_register_does_not_hide_measurements_and_labels_assumed_range():
    with gx(control_enabled=False) as (driver,server,_):
        server.registers.update({834:65535,835:65535})
        sample=driver.read({},NOW)
        assert sample.soc==60 and sample.measurements['solar'].value==2000
        assert driver.read_diagnostics['failure'] is None
        assert driver.read_diagnostics['firmware']=={
            'version':'v3.50–v3.69','source':'assumed','configured':None,'detected':None,
            'register_status':'reserved','raw_words':[65535,65535]}
        assert not server.writes and not driver.telemetry_status


@pytest.mark.parametrize('version,address',[('v3.49',2700),('v3.66',2716)])
def test_explicit_version_selects_correct_ess_registers_when_firmware_is_reserved(version,address):
    with gx(firmware_version=version,legacy_control_enabled=version=='v3.49') as (driver,server,_):
        server.registers.update({834:65535,835:65535})
        driver.apply(command('grid_charge',2000,0),{})
        assert (address,[3000] if address==2700 else [0,3000]) in server.writes
        assert not any(item[0]==(2716 if address==2700 else 2700) for item in server.writes)
        driver.release({})
        assert (address,[50] if address==2700 else [0,50]) in server.writes
        assert driver.read_diagnostics['firmware']['version']==version
        assert driver.read_diagnostics['firmware']['source']=='configured'
        assert driver.read_diagnostics['firmware']['detected'] is None


def test_missing_firmware_defaults_to_modern_control_without_configuration_or_legacy_opt_in():
    with gx() as (driver,server,_):
        server.registers.update({834:65535,835:65535})
        assert driver.power_limits({})==(5000,5000)
        driver.apply(command('grid_charge',2000,0),{})
        assert (2716,[0,3000]) in server.writes
        driver.release({})
        assert target(server)==50
        assert not any(address==2700 for _,_,address,_ in server.requests)
        assert not driver.telemetry_status
        assert driver.read({},NOW).soc==60


@pytest.mark.parametrize('code',[2,10,11,None])
@pytest.mark.parametrize('version',[None,'v3.66'])
def test_only_explicit_unsupported_firmware_register_allows_version_fallback(code,version):
    with gx(firmware_version=version) as (driver,server,_):
        original=driver.client.read
        def read(address,count):
            if address==834:
                if code is None:raise TimeoutError('private server')
                raise ModbusError('private response',exception_code=code)
            return original(address,count)
        with patch.object(driver.client,'read',side_effect=read):
            if code==2:
                assert driver.read({},NOW).soc==60
                driver.apply(command('grid_charge',2000,0),{})
                assert target(server)==3000
                assert driver.read_diagnostics['firmware']['register_status']=='unsupported'
                assert driver.read_diagnostics['firmware']['raw_words'] is None
                assert driver.read_diagnostics['firmware']['source']==('configured' if version else 'assumed')
            else:
                with pytest.raises(OSError):driver.read({},NOW)
                with pytest.raises(OSError):driver.apply(command(),{})
                assert not server.writes
                assert driver.read_diagnostics['firmware']['register_status']=='transport_error'


def test_detected_firmware_takes_precedence_and_reports_both_versions_after_upgrade():
    with gx(firmware_version='3.66') as (driver,server,_):
        server.registers.update({834:65535,835:65535})
        assert driver.read({},NOW).soc==60
        assert driver.read_diagnostics['firmware']['source']=='configured'
        server.registers.update({834:0x0374,835:0x42})
        driver.client.close()  # The GX restarts for the upgrade.
        driver.apply(command('grid_charge',2000,0),{})
        assert target(server)==3000
        assert driver.read_diagnostics['firmware']=={
            'version':'v3.74~42','source':'detected','configured':'v3.66','detected':'v3.74~42',
            'register_status':'valid','raw_words':[0x0374,0x42]}


def test_detected_version_replaces_assumed_range_when_it_becomes_available():
    with gx() as (driver,server,_):
        server.registers.update({834:65535,835:65535})
        driver.read({},NOW)
        assert driver.read_diagnostics['firmware']['source']=='assumed'
        server.registers.update({834:0x0374,835:0})
        driver.client.close()  # The GX restarts for the upgrade.
        driver.read({},NOW)
        assert driver.read_diagnostics['firmware']['version']=='v3.74'
        assert driver.read_diagnostics['firmware']['source']=='detected'


def test_manual_newer_version_cannot_override_detected_legacy_firmware_without_opt_in():
    with gx(firmware_version='v3.66') as (driver,server,_):
        server.registers[834]=0x0349
        with pytest.raises(ModbusError,match='legacy ESS control permission'):
            driver.apply(command(),{})
        assert not server.writes
        assert driver.read_diagnostics['firmware']['version']=='v3.49'
        assert driver.read_diagnostics['firmware']['source']=='detected'


@pytest.mark.parametrize('version',['3.66.1','unknown','http://private-host','v3.100','v0.66'])
def test_invalid_manual_version_is_rejected_with_a_field_error_without_io(version):
    with patch('socket.create_connection') as connect:
        with pytest.raises(PluginParameterError) as caught:
            BATTERY_DRIVERS['victron_modbus'](None,{'host':'gx.test','firmware_version':version})
        assert caught.value.parameter=='firmware_version'
        connect.assert_not_called()


def test_diagnostic_export_includes_firmware_provenance_but_no_extra_driver_fields():
    firmware={'version':'v3.66','source':'configured','configured':'v3.66','detected':None,
        'register_status':'reserved','raw_words':[65535,65535],'secret':'private host'}
    data={'battery_group':{'devices':[{'plugin':{'identifier':'victron_modbus'},
        'read_diagnostics':{'firmware':firmware,'host':'private host'}}]}}
    exported=device_diagnostics(data)[0]['firmware']
    assert exported=={key:value for key,value in firmware.items() if key!='secret'}
    assert 'private host' not in repr(exported)

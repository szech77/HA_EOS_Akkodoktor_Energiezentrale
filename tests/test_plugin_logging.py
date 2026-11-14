"""Physical plugin incidents must be visible independently of panel/source selection."""
from datetime import timedelta
import json
import logging
from types import SimpleNamespace
from urllib.error import HTTPError

import pytest

from custom_components.eos_energiezentrale.energy.contracts import (
    InverterDriver, InverterReading, Measurement, PluginInfo, WallboxDriver, WallboxFeatures, WallboxReading)
from custom_components.eos_energiezentrale.energy.devices import DeviceSite
from custom_components.eos_energiezentrale.energy.plugin_parameters import parameters
from custom_components.eos_energiezentrale.configuration_logging import configuration_failure, configuration_success
from test_devices import storage
from test_energy import NOW


class Inverter(InverterDriver):
    info = PluginInfo('test_inverter','Private label','inverter')
    configuration = ()
    ids = {}
    def __init__(self):
        self.value = InverterReading({'solar':Measurement(0,NOW),'inverter_ac':Measurement(0,NOW)})
        self.error = None
    def _read(self, states, now):
        if self.error:
            raise self.error
        return self.value


class Charger(WallboxDriver):
    info = PluginInfo('test_charger','Private charger','wallbox')
    features = WallboxFeatures(optional_connection=True)
    configuration = ()
    ids = {}
    def __init__(self):
        self.value = WallboxReading(0,'disconnected',False,None,None,None,None,NOW)
    def _read(self, states, now): return self.value
    def _charge(self, amps, state): pass
    def _pause(self, state): pass
    def _phase(self, phases, state): return True


def test_missing_plugin_values_log_once_and_zero_readings_resolve_incident(caplog):
    driver = Inverter()
    driver.value = InverterReading({'solar':Measurement(None,None),'inverter_ac':Measurement(0,NOW)})
    caplog.set_level(logging.INFO,logger='custom_components.eos_energiezentrale')
    assert driver.read({},NOW).measurements['solar'].value is None
    assert len(caplog.records) == 1
    assert 'plugin_measurements_incomplete' in caplog.text and 'test_inverter' in caplog.text
    driver.read({},NOW)
    assert len(caplog.records) == 1
    driver.value = InverterReading({'solar':Measurement(0,NOW),'inverter_ac':Measurement(0,NOW)})
    assert driver.read({},NOW).measurements['solar'].value == 0
    assert 'resolved' in caplog.records[-1].message
    assert not driver.telemetry_status


def test_stale_and_invalid_plugin_measurements_report_changed_causes(caplog):
    driver = Inverter()
    driver.value = InverterReading({'solar':Measurement(1000,NOW-timedelta(seconds=46)), 'inverter_ac':Measurement(0,NOW)})
    driver.read({},NOW)
    assert driver.telemetry_status[0]['source_problems'][0]['reason'] == 'stale'
    driver.value = InverterReading({'solar':Measurement(-1,NOW),'inverter_ac':Measurement(0,NOW)})
    driver.read({},NOW)
    assert driver.telemetry_status[0]['source_problems'][0]['reason'] == 'invalid_value'
    assert 'changed' in caplog.records[-1].message


def test_exception_still_propagates_with_private_details_removed(caplog):
    driver = Inverter()
    driver.error = OSError('http://private-host/test-secret')
    driver.read_diagnostics = {'failure':{'stage':'dc_pv','unit':100,'address':850,'count':1,'exception_code':2,
                                        'host':'private-host','value':98765}}
    with pytest.raises(OSError) as caught:
        driver.read({},NOW)
    assert caught.value is driver.error
    details = driver.telemetry_status[0]['details']
    assert details['stage'] == 'dc_pv' and details['address'] == 850 and details['exception_code'] == 2
    for private in ('private-host','test-secret','98765','Private label'):
        assert private not in caplog.text + json.dumps(driver.telemetry_status)


def test_invalid_return_type_is_logged_without_weakening_plugin_contract(caplog):
    driver = Inverter()
    driver.value = {'solar':0}
    with pytest.raises(ValueError):
        driver.read({},NOW)
    assert 'plugin_read_failed' in caplog.text and 'PluginContractError' in caplog.text


def test_charger_disconnection_is_valid_but_missing_connected_controls_are_logged(caplog):
    driver = Charger()
    driver.read({},NOW)
    assert not caplog.records
    driver.value = WallboxReading(0,'connected',False,None,None,None,None,NOW)
    driver.read({},NOW)
    issue = driver.telemetry_status[0]
    assert issue['missing_controls'] == ['amps','max_phases','maximum','nominal_voltage','phases','step']
    assert issue['code'] == 'plugin_measurements_incomplete'
    driver.value = WallboxReading(None,'unavailable',False,None,None,None,None,None)
    driver.read({},NOW)
    assert driver.telemetry_status[0]['code'] == 'plugin_unavailable'


def test_device_site_reports_physical_child_without_exposing_configured_names(caplog):
    definition, ha = storage()
    definition.update(id='private-id',name='Private device')
    ha.rows['sensor.soc']['state'] = 'unavailable'
    site = DeviceSite(ha,[definition])
    assert site.read(ha.rows,NOW).soc is None
    assert 'device/1' in caplog.text and 'generic' in caplog.text
    assert 'battery_soc' in caplog.text
    assert 'Private device' not in caplog.text and 'private-id' not in caplog.text
    assert site.site_summary['devices'][0]['telemetry_status']


def test_wrapped_http_failure_keeps_status_without_exception_text():
    from custom_components.eos_energiezentrale.energy.status import failure_details
    try:
        try:
            raise HTTPError('http://private-host',401,'test-secret',{},None)
        except OSError:
            raise ValueError('private-response') from None
    except ValueError as error:
        result = failure_details(error)
    assert result['exception'] == 'ValueError' and result['http_status'] == 401 and result['cause'] == 'HTTPError'
    for private in ('private-host','test-secret','private-response'):
        assert private not in json.dumps(result)


def test_plugin_parameter_failure_logs_field_name_and_recovers_without_values(caplog):
    from custom_components.eos_energiezentrale.energy.contracts import PluginField
    owner = SimpleNamespace(hass=SimpleNamespace(data={}))
    caplog.set_level(logging.INFO,logger='custom_components.eos_energiezentrale')
    try:
        parameters((PluginField('port','Port','number'),),{'port':'test-secret'})
    except ValueError as error:
        for _ in range(2):
            configuration_failure(owner,'device_parameters',error,'test_inverter')
    assert len(caplog.records) == 1
    assert 'parameter' in caplog.text and 'port' in caplog.text and 'test_inverter' in caplog.text
    assert 'test-secret' not in caplog.text
    configuration_success(owner,'device_parameters')
    assert 'resolved' in caplog.records[-1].message


def test_nrgkick_missing_credential_is_logged_despite_unavailable_return(monkeypatch, caplog):
    from custom_components.eos_energiezentrale.energy.drivers import WALLBOX_DRIVERS
    monkeypatch.delenv('EOS_TEST_MISSING_CREDENTIAL',raising=False)
    driver = WALLBOX_DRIVERS['nrgkick_local'](None,{'username':'private-user','password_env':'EOS_TEST_MISSING_CREDENTIAL'})
    assert driver.read({},NOW).status == 'unavailable'
    assert driver.telemetry_status[0]['code'] == 'plugin_read_failed'
    assert driver.telemetry_status[0]['details']['reason'] == 'credential_unavailable'
    assert driver.telemetry_status[0]['details']['fields'] == ['password_env']
    assert 'EOS_TEST_MISSING_CREDENTIAL' not in caplog.text and 'private-user' not in caplog.text


def test_fronius_partial_read_failure_is_logged_while_battery_data_remains_usable(monkeypatch, caplog):
    from custom_components.eos_energiezentrale.energy.plugins.fronius_modbus import FroniusModbus
    from test_fronius_modbus import inverter
    with inverter() as (_,server):
        driver = FroniusModbus(None,{'host':'127.0.0.1','port':server.server_address[1]})
        def failed_ac():
            raise OSError('http://private-host/test-secret')
        monkeypatch.setattr(driver,'_ac_power',failed_ac)
        reading = driver.read({},NOW)
    assert reading.soc is not None
    assert driver.telemetry_status[0]['details']['stage'] == 'inverter_ac'
    assert driver.telemetry_status[0]['code'] == 'plugin_read_failed'
    assert 'test-secret' not in caplog.text and 'private-host' not in caplog.text

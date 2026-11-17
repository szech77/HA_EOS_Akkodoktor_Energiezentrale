"""Explicit backup mode, freshness, device aggregation and safe recovery."""
from dataclasses import replace
from datetime import timedelta
import logging
from unittest.mock import Mock, patch

import pytest

from custom_components.eos_energiezentrale.adapter import StateSnapshot
from custom_components.eos_energiezentrale.const import DEFAULTS
from custom_components.eos_energiezentrale.energy.contracts import BatteryReading, PowerSupplyReading
from custom_components.eos_energiezentrale.energy.power_supply import (
    aggregate_supply, checked_supply, configured_supply, fronius_entity_supply, supply_view, validate_supply_options)
from custom_components.eos_energiezentrale.energy.status import IssueLog, view_state
from custom_components.eos_energiezentrale.energy._fronius_backup import FroniusBackup
from test_energy import NOW, temporary_project_directory
from test_fronius_modbus import inverter
from test_victron_modbus import gx


def api(mode=False, stamp=NOW):
    return {'Head':{'Status':{'Code':0}, 'Timestamp':stamp.isoformat()},
            'Body':{'Data':{'Site':{'BackupMode':mode}}}}


@pytest.mark.parametrize('watts', [0, None, 500, -500])
def test_grid_power_alone_never_proves_backup_mode(watts):
    result = view_state({'live':{'grid':watts}, 'display':{'grid':{'value':500}}}, NOW)
    assert result['power_supply']['state'] == 'unsupported'
    assert not any(item['code'].startswith('backup_power') for item in result['notices'])
    assert result['live']['grid'] == watts


@pytest.mark.parametrize('stamp', [None, NOW.replace(tzinfo=None), NOW-timedelta(seconds=120),
                                 NOW+timedelta(seconds=1)])
def test_stale_missing_naive_and_future_status_cannot_keep_grid_disconnected(stamp):
    supply = checked_supply(PowerSupplyReading('backup', stamp), NOW)
    assert supply.mode == 'unknown'
    assert supply_view(supply, NOW)['grid_active'] is None


def test_backup_warning_is_logged_once_changes_to_unknown_and_resolves(caplog):
    state = {'power_supply':supply_view(PowerSupplyReading('backup', NOW), NOW), 'live':{'grid':1500}}
    log = IssueLog()
    caplog.set_level(logging.INFO, logger='custom_components.eos_energiezentrale')
    result = view_state(state, NOW)
    assert result['power_supply']['grid_active'] is False
    assert result['live']['grid'] == 1500  # Display policy never overwrites measurements.
    log.update('state', result['notices'])
    log.update('state', result['notices'])
    assert len(log.events) == 1 and 'backup_power_active' in caplog.text
    expired = view_state(state, NOW+timedelta(seconds=120))
    assert expired['power_supply']['state'] == 'unknown'
    log.update('state', expired['notices'])
    assert log.events[-1]['state'] == 'changed'
    assert log.events[-1]['code'] == 'backup_power_unknown'
    state['power_supply'] = supply_view(PowerSupplyReading('grid', NOW), NOW)
    log.update('state', view_state(state, NOW)['notices'])
    assert log.events[-1]['state'] == 'resolved'


def test_configured_status_supports_inversion_and_unavailable_is_not_grid_operation():
    options = {**DEFAULTS, 'backup_mode_entity':'binary_sensor.grid_connected',
               'backup_active_state':'off', 'backup_inactive_state':'on'}
    states = {options['backup_mode_entity']:{'state':'off', 'last_reported':NOW.isoformat()}}
    assert configured_supply(options, states, NOW).mode == 'backup'
    states[options['backup_mode_entity']]['state'] = 'on'
    assert configured_supply(options, states, NOW).mode == 'grid'
    for value in ('unavailable', 'unknown', 'unexpected', None):
        states[options['backup_mode_entity']]['state'] = value
        assert configured_supply(options, states, NOW).mode == 'unknown'


@pytest.mark.parametrize('changes', [
    {'backup_mode_entity':'switch.relay'}, {'backup_mode_entity':17},
    {'backup_active_state':'off'}, {'backup_inactive_state':'ON'},
    {'backup_active_state':'unknown'}, {'backup_active_state':' on'},
])
def test_invalid_status_configuration_is_rejected(changes):
    with pytest.raises(ValueError):
        validate_supply_options({**DEFAULTS, **changes})


def test_fronius_ha_uses_matching_registry_identity_and_renamed_sensor():
    states = StateSnapshot({'binary_sensor.renamed_backup':{'state':'on', 'last_reported':NOW.isoformat()},
                            'binary_sensor.other_system':{'state':'off', 'last_reported':NOW.isoformat()}})
    states.fronius_backup_modes = {'sensor.our_charge':'binary_sensor.renamed_backup',
                                  'sensor.other_charge':'binary_sensor.other_system'}
    assert fronius_entity_supply(states, ['sensor.our_charge'], NOW).mode == 'backup'
    assert fronius_entity_supply(states, ['sensor.other_charge'], NOW).mode == 'grid'
    assert fronius_entity_supply(states, ['sensor.our_charge','sensor.other_charge'], NOW).mode == 'unknown'
    assert fronius_entity_supply(states, ['sensor.unrelated'], NOW) is None
    states['binary_sensor.renamed_backup']['state'] = 'unavailable'
    assert fronius_entity_supply(states, ['sensor.our_charge'], NOW).mode == 'unknown'


@pytest.mark.parametrize('mode, expected', [(True,'backup'), (False,'grid')])
def test_fronius_solar_api_uses_explicit_boolean_and_caches_bounded_status(mode, expected):
    probe = FroniusBackup('http://inverter.test')
    with patch('custom_components.eos_energiezentrale.energy._fronius_backup.request', return_value=api(mode)) as request:
        assert probe.read(NOW).mode == expected
        assert probe.read(NOW+timedelta(seconds=10)).mode == expected
        request.assert_called_once_with('http://inverter.test/solar_api/v1/GetPowerFlowRealtimeData.fcgi')
        assert probe.read(NOW+timedelta(seconds=121)).mode == 'unknown'


@pytest.mark.parametrize('payload', [
    api('false'), api(0), api(None), api(True, NOW-timedelta(seconds=120)),
    api(True, NOW+timedelta(minutes=1)),
    {'Head':{'Status':{'Code':1}},'Body':{'Data':{'Site':{}}}},
    {'Head':{'Status':{'Code':0}},'Body':{'Data':{'Site':[]}}},
])
def test_fronius_solar_api_invalid_data_is_unknown_and_reportable(payload):
    probe = FroniusBackup('http://inverter.test')
    with patch('custom_components.eos_energiezentrale.energy._fronius_backup.request', return_value=payload):
        assert probe.read(NOW).mode == 'unknown'
        assert probe.error is not None


def test_fronius_api_failure_or_removed_field_does_not_reuse_old_backup_state():
    probe = FroniusBackup('http://inverter.test')
    with patch('custom_components.eos_energiezentrale.energy._fronius_backup.request', return_value=api(True)):
        assert probe.read(NOW).mode == 'backup'
    probe.last_probe -= 31
    with patch('custom_components.eos_energiezentrale.energy._fronius_backup.request', side_effect=TimeoutError('private-host')):
        assert probe.read(NOW).mode == 'unknown'
        assert isinstance(probe.error, TimeoutError)
    probe.last_probe -= 31
    payload = api()
    payload['Body']['Data']['Site'].clear()
    with patch('custom_components.eos_energiezentrale.energy._fronius_backup.request', return_value=payload):
        assert probe.read(NOW).mode == 'unknown'
        assert isinstance(probe.error, ValueError)
        first_probe = FroniusBackup('http://inverter.test')
        assert first_probe.read(NOW).mode == 'unknown'
        assert isinstance(first_probe.error, ValueError)


def test_fronius_modbus_keeps_power_readings_when_solar_api_fails(caplog):
    with inverter() as (driver, server):
        with patch('custom_components.eos_energiezentrale.energy._fronius_backup.request', return_value=api(True)):
            value = driver.read({}, NOW)
        assert value.power_supply.mode == 'backup' and value.soc is not None
        driver.backup.last_probe -= 31
        with patch('custom_components.eos_energiezentrale.energy._fronius_backup.request', side_effect=TimeoutError('private-host')):
            value = driver.read({}, NOW)
        assert value.power_supply.mode == 'unknown'
        assert all(item is not None for item in (value.soc, value.charge, value.discharge))
        assert not server.writes
    assert 'backup_status' in caplog.text
    assert 'private-host' not in caplog.text


@pytest.mark.parametrize('source, expected', [(1,'grid'), (240,'backup'), (0,'unknown'),
                                           (2,'unknown'), (3,'unknown'), (65535,'unknown')])
def test_victron_explicit_island_source_is_separate_from_generator_and_missing_data(source, expected):
    with gx(control_enabled=False) as (driver, server, _):
        server.registers[826] = source
        assert driver.read({}, NOW).power_supply.mode == expected
        assert not server.writes


def test_storage_groups_require_agreement_or_an_explicit_common_grid_source():
    backup = BatteryReading(50, 0, 1000, power_supply=PowerSupplyReading('backup', NOW))
    grid = replace(backup, power_supply=PowerSupplyReading('grid', NOW))
    assert aggregate_supply([(False,backup),(False,backup)]).mode == 'backup'
    assert aggregate_supply([(False,backup),(False,grid)]).mode == 'unknown'
    assert aggregate_supply([(False,backup),(False,None)]).mode == 'unknown'
    assert aggregate_supply([(True,grid),(False,backup)]).mode == 'grid'


def test_controller_exposes_backup_even_when_control_is_off_and_never_falls_back_from_explicit_source():
    from custom_components.eos_energiezentrale.energy.controller import Controller
    from custom_components.eos_energiezentrale.energy.settings import Configuration
    from test_requirements import ControllerRequirements
    options = {**DEFAULTS, 'wallbox_type':'none', 'backup_mode_entity':'binary_sensor.backup'}
    with temporary_project_directory() as directory:
        ha = Mock()
        config = Configuration(options, ha, directory)
        config.battery = Mock()
        config.battery.read.return_value = BatteryReading(50, 0, 500, NOW, NOW, NOW,
                                                          power_supply=PowerSupplyReading('grid', NOW))
        app = Controller(ha, config)
        app.external_eos_polling = True
        app.sync_battery_limits = Mock()
        states = ControllerRequirements.states(when=NOW)
        states[options['backup_mode_entity']] = {'state':'on', 'last_reported':NOW.isoformat()}
        ha.states.return_value = states
        app.tick(NOW, 1)
        assert app.snapshot(NOW)['power_supply']['state'] == 'backup'
        assert not app.armed
        states[options['backup_mode_entity']]['state'] = 'unavailable'
        app.tick(NOW, 2)
        assert app.snapshot(NOW)['power_supply']['state'] == 'unknown'


def test_device_site_carries_automatic_fronius_backup_status():
    from custom_components.eos_energiezentrale.energy.devices import DeviceSite
    from test_devices import primary
    with inverter() as (_, server), patch(
        'custom_components.eos_energiezentrale.energy._fronius_backup.request', return_value=api(True)):
        site = DeviceSite(None, [primary(server)])
        assert site.read({}, NOW).power_supply.mode == 'backup'


@pytest.mark.parametrize('mode, expected', [(True, 'backup'), (False, 'grid'), (None, 'unknown')])
def test_fronius_backup_status_survives_missing_smart_meter(mode, expected, caplog):
    from custom_components.eos_energiezentrale.energy.devices import DeviceSite
    from test_devices import primary
    payload = api(mode)
    if mode is None:
        payload['Body']['Data']['Site'].clear()
    with inverter() as (_, server), patch(
        'custom_components.eos_energiezentrale.energy._fronius_backup.request', return_value=payload):
        site = DeviceSite(None, [primary(server)])
        # Healthy reading first: neither old watts nor old operating mode may
        # conceal a grid-meter outage on the next read.
        site.read({}, NOW)
        server.meters.clear()
        value = site.read({}, NOW)
        assert value.measurements['grid'].value is None
        assert value.measurements['house_total'].value is None
        assert value.soc is not None
        result = view_state({'power_supply':supply_view(value.power_supply, NOW)}, NOW)
        assert result['power_supply']['state'] == expected
        assert result['power_supply']['grid_active'] is (False if mode is True else True if mode is False else None)
        if mode is not False:
            assert any(item['code'] == ('backup_power_active' if mode else 'backup_power_unknown')
                       for item in result['notices'])
        assert not server.writes
    if mode is None:
        assert 'backup_status' in caplog.text


def test_sensor_picker_can_be_cleared_and_accepts_binary_sensor():
    from custom_components.eos_energiezentrale.config_flow import schema_for
    options = {**DEFAULTS, 'backup_mode_entity':'binary_sensor.previous'}
    assert schema_for('sensors', options)({'backup_mode_entity':''})['backup_mode_entity'] == ''
    assert schema_for('sensors', DEFAULTS)({'backup_mode_entity':'binary_sensor.backup'})['backup_mode_entity'] == 'binary_sensor.backup'

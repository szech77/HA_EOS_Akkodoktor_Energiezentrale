"""Storage control and vehicle charging control are enabled separately and
only with a matching controllable device."""
import json
import os
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from custom_components.eos_energiezentrale.energy.contracts import BatteryFeatures
from custom_components.eos_energiezentrale.energy.settings import daily_settings, load_control_scope
from test_energy import NOW
import test_requirements as requirements


@pytest.fixture
def control():
    case = requirements.ControllerRequirements()
    case.setUp()
    case.battery.features = BatteryFeatures()
    case.config.daily = daily_settings({'fast': True}, 20)
    case.config.set_control_scope = Mock()
    try:
        yield case
    finally:
        case.doCleanups()


def poll(case, seconds):
    now = NOW + timedelta(seconds=seconds)
    case.ha.states.return_value = case.states(when=now)
    case.eos.plan.return_value = case.plan(now)
    case.box.read.return_value = replace(requirements.wallbox(), sample=now)
    case.app.tick(now, seconds)
    return case.app.snapshot(now)


def test_vehicle_only_control_charges_and_never_writes_to_the_storage(control):
    control.app.set_control(vehicle=True)
    snapshot = poll(control, 0)
    assert snapshot['armed'] and snapshot['control']['vehicle']['enabled']
    assert not snapshot['control']['battery']['enabled'] and snapshot['control']['battery']['available']
    control.box.charge.assert_called_once()
    control.battery.apply.assert_not_called()
    control.battery.release.assert_not_called()
    assert snapshot['live']['battery_control'] == 'auto'
    control.config.set_control_scope.assert_called_once_with({'battery': False, 'vehicle': True}, False)


def test_storage_only_control_never_touches_the_charger(control):
    control.app.set_control(battery=True)
    poll(control, 0)
    control.battery.apply.assert_called_once()
    control.box.charge.assert_not_called()
    control.box.pause.assert_not_called()
    control.app.set_armed(False)
    control.battery.release.assert_called_once()
    control.box.pause.assert_not_called()


def test_releasing_one_area_keeps_the_other_area_controlled(control):
    control.app.set_armed(True)
    poll(control, 0)
    control.box.charge.assert_called_once()
    control.battery.apply.assert_called_once()
    control.app.set_control(vehicle=False)
    control.box.pause.assert_called_once()
    control.battery.release.assert_not_called()
    snapshot = poll(control, 5)
    assert snapshot['armed'] and not snapshot['release_pending']
    assert snapshot['control']['battery']['enabled'] and not snapshot['control']['vehicle']['enabled']
    assert control.battery.apply.call_count == 2
    control.box.charge.assert_called_once()


def test_unconfirmed_area_release_stays_visible_and_is_retried(control):
    control.app.set_armed(True)
    poll(control, 0)
    control.box.pause.side_effect = OSError('offline')
    with pytest.raises(OSError):
        control.app.set_control(vehicle=False)
    snapshot = poll(control, 5)
    assert snapshot['release_pending'] and snapshot['control']['vehicle']['release_pending']
    control.box.charge.assert_called_once()
    control.box.pause.side_effect = None
    snapshot = poll(control, 10)
    assert not snapshot['release_pending'] and snapshot['control']['battery']['enabled']


def test_read_only_storage_offers_only_vehicle_control(control):
    # Issue #33: Victron without ESS control reports no charge/discharge limits.
    control.battery.features = BatteryFeatures(False, False, False, False)
    with pytest.raises(ValueError):
        control.app.set_control(battery=True)
    control.app.set_armed(True)
    snapshot = poll(control, 0)
    assert snapshot['control']['battery'] == {'available': False, 'enabled': False, 'release_pending': False}
    assert snapshot['control']['vehicle']['enabled']
    control.battery.apply.assert_not_called()
    control.box.charge.assert_called_once()
    # Every controllable area is on: an older version may resume full control.
    control.config.set_control_scope.assert_called_once_with({'battery': True, 'vehicle': True}, True)


def test_without_charger_the_vehicle_area_is_unavailable(control):
    control.config.options['wallbox_type'] = 'none'
    with pytest.raises(ValueError):
        control.app.set_control(vehicle=True)
    assert control.app.snapshot(NOW)['control']['vehicle']['available'] is False


def test_invalid_area_requests_are_rejected(control):
    for request in ({}, {'battery': 1}, {'vehicle': 'on'}):
        with pytest.raises(ValueError):
            control.app.set_control(**request)
    assert not control.app.armed
    control.config.set_control_scope.assert_not_called()


def test_persisted_scope_is_restored_and_older_control_file_changes_win(tmp_path):
    scope_file, control_file = tmp_path / 'control_scope.json', tmp_path / 'control.json'
    assert load_control_scope(scope_file, control_file, True) == {'battery': True, 'vehicle': True}
    control_file.write_text(json.dumps({'enabled': False}), encoding='utf-8')
    scope_file.write_text(json.dumps({'battery': False, 'vehicle': True}), encoding='utf-8')
    assert load_control_scope(scope_file, control_file, False) == {'battery': False, 'vehicle': True}
    # An older version switched control on later: its all-or-nothing intent wins.
    stamp = scope_file.stat().st_mtime_ns
    os.utime(control_file, ns=(stamp + 10**9, stamp + 10**9))
    assert load_control_scope(scope_file, control_file, True) == {'battery': True, 'vehicle': True}
    scope_file.write_text(json.dumps({'battery': 'yes', 'vehicle': True}), encoding='utf-8')
    os.utime(scope_file, ns=(stamp + 2 * 10**9, stamp + 2 * 10**9))
    with pytest.raises(ValueError):
        load_control_scope(scope_file, control_file, True)


def test_controller_restores_the_persisted_scope_and_owns_only_those_areas(control):
    from custom_components.eos_energiezentrale.energy.controller import Controller
    control.config.control_scope = {'battery': False, 'vehicle': True}
    app = Controller(control.ha, control.config)
    assert app.restore_pending and app.holding == {'vehicle'}
    assert app.control_view()['battery']['enabled'] is False


def test_area_switches_exist_only_for_controllable_devices(monkeypatch):
    import asyncio
    from custom_components.eos_energiezentrale import switch
    monkeypatch.setattr(switch, 'EnergySwitch', lambda coordinator, key: key)
    for controllable, expected in ((lambda area: area == 'vehicle', ['control_vehicle']),
                                   (lambda area: True, ['control_battery', 'control_vehicle'])):
        added = []
        entry = SimpleNamespace(runtime_data=SimpleNamespace(app=SimpleNamespace(controllable=controllable)))
        asyncio.run(switch.async_setup_entry(None, entry, lambda entities: added.extend(entities)))
        assert [key for key in added if key.startswith('control_')] == expected and 'control' in added

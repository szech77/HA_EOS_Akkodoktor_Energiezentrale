"""Backup is a reversible control pause, including long outages and fleets."""
from dataclasses import replace
from datetime import timedelta
from unittest.mock import Mock

import pytest

from custom_components.eos_energiezentrale.energy.contracts import BatteryReading, PowerSupplyReading
from custom_components.eos_energiezentrale.energy.controller import SUPPLY_GRACE_S
from custom_components.eos_energiezentrale.energy.status import view_state
from test_energy import NOW
import test_requirements as requirements


@pytest.fixture
def control():
    case = requirements.ControllerRequirements()
    case.setUp()
    case.config.set_control_enabled = Mock()
    case.app.set_armed(True)
    try:
        yield case
    finally:
        case.doCleanups()


def poll(case, seconds, mode, *, meter=True, plan=True, car=None):
    now = NOW + timedelta(seconds=seconds)
    rows = case.states(when=now)
    if not meter:
        for key in ('sensor.grid', 'sensor.house'):
            rows[key]['state'] = 'unavailable'
    case.ha.states.return_value = rows
    case.battery.read.return_value = BatteryReading(50, 0, 0, now, now, now,
        power_supply=PowerSupplyReading(mode, now if mode in ('grid', 'backup') else None))
    case.box.read.return_value = replace(car or requirements.wallbox(), sample=now)
    case.eos.plan.side_effect = None if plan else OSError('unavailable')
    case.eos.plan.return_value = case.plan(now)
    case.app.tick(now, seconds)
    return view_state(case.app.snapshot(now), now)


def test_long_backup_keeps_intent_and_resumes_only_with_grid_measurements_and_plan(control):
    assert poll(control, 0, 'grid')['control_status'] == 'active'
    control.battery.apply.reset_mock()
    control.box.pause.reset_mock()
    result = poll(control, 5, 'backup', meter=False)
    assert result['control_status'] == 'backup'
    assert result['armed'] and result['control_paused']
    assert [(row['code'], row['severity']) for row in result['notices']] == [('backup_power_active', 'info')]
    for seconds, mode in ((7200, 'backup'), (86400, 'unknown'), (172800, 'backup')):
        result = poll(control, seconds, mode, meter=False, plan=False)
        assert result['armed'] and result['control_paused']
        control.battery.apply.assert_not_called()
        control.box.charge.assert_not_called()
    control.battery.release.assert_called_once()
    control.box.pause.assert_called_once()
    control.config.set_control_enabled.assert_called_once_with(True)
    assert poll(control, 172805, 'grid', meter=False, plan=False)['control_status'] == 'waiting'
    control.box.read.side_effect = TimeoutError('recovering')
    assert poll(control, 172810, 'grid', meter=False, plan=False)['control_status'] == 'waiting'
    control.box.read.side_effect = None
    control.battery.apply.assert_not_called()
    result = poll(control, 172850, 'grid')
    assert result['control_status'] == 'active'
    assert not result['control_paused']
    control.battery.apply.assert_called_once()


def test_manual_off_during_backup_is_not_overridden_on_grid_recovery(control):
    poll(control, 0, 'backup')
    control.app.set_armed(False)
    result = poll(control, 7200, 'grid')
    assert not result['armed'] and result['control_status'] == 'read_only'
    control.battery.apply.assert_not_called()
    assert control.config.set_control_enabled.call_args.args == (False,)


def test_backup_default_stops_a_restarted_charge_and_keeps_failed_stops_visible(control):
    poll(control, 0, 'backup')
    control.box.pause.reset_mock()
    charging = requirements.wallbox(watts=2000, status='charging', enabled=True)
    poll(control, 10, 'backup', car=charging)
    control.box.pause.assert_called_once()
    control.box.pause.side_effect = OSError('unavailable')
    result = poll(control, 20, 'backup', car=charging)
    assert 'wallbox_stop' in result['errors'] and result['armed']
    result = poll(control, 30, 'grid', car=charging)
    assert result['control_paused']
    control.battery.apply.assert_not_called()
    control.box.pause.side_effect = None
    result = poll(control, 40, 'grid')
    assert 'wallbox_stop' not in result['errors'] and not result['control_paused']
    control.battery.release.assert_called_once()


def test_backup_manual_charging_opt_in_leaves_eos_paused_and_does_not_issue_charge_commands(control):
    control.config.options['allow_backup_ev_charging'] = True
    charging = requirements.wallbox(watts=2000, status='charging', enabled=True)
    for seconds in (0, 7200):
        assert poll(control, seconds, 'backup', car=charging)['control_status'] == 'backup'
    control.box.pause.assert_not_called()
    control.box.charge.assert_not_called()
    control.battery.apply.assert_not_called()
    control.battery.release.assert_called_once()


def test_failed_cleanup_stays_visible_and_blocks_resume_without_clearing_intent(control):
    control.battery.release.side_effect = OSError('unavailable')
    result = poll(control, 0, 'backup')
    assert 'release' in result['errors'] and result['armed']
    result = poll(control, 7200, 'grid')
    assert result['control_status'] == 'waiting'
    control.battery.apply.assert_not_called()
    control.battery.release.side_effect = None
    result = poll(control, 7240, 'grid')
    assert result['control_status'] == 'active'
    assert 'release' not in result['errors']
    control.battery.apply.assert_called_once()


def test_lost_status_and_device_reads_after_backup_do_not_disable_saved_control(control):
    poll(control, 0, 'backup')
    control.battery.read.side_effect = TimeoutError('unavailable')
    control.box.read.side_effect = TimeoutError('unavailable')
    result = poll(control, 86400, 'unknown', meter=False, plan=False)
    assert result['control_status'] == 'power_supply_waiting' and result['armed']
    assert {'battery_read', 'wallbox_read'} <= result['errors'].keys()
    control.config.set_control_enabled.assert_called_once_with(True)
    control.battery.apply.assert_not_called()
    control.battery.read.side_effect = control.box.read.side_effect = None
    assert poll(control, 86440, 'grid')['control_status'] == 'active'


def test_backup_only_suppresses_expected_unavailable_grid_and_house_warnings():
    now = NOW
    supply = {'state':'backup', 'sample':now.isoformat()}
    report = {'missing':['price'], 'unavailable':['grid', 'house_total', 'solar', 'car_soc']}
    data = {'power_supply':supply, 'armed':True, 'control_paused':True, 'source_configuration':report,
            'errors':{'release':'TimeoutError'}}
    result = view_state(data, now)
    assert next(row for row in result['notices'] if row['code'] == 'sources_unavailable')['measurements'] == ['car_soc', 'solar']
    assert any(row['code'] == 'release' and row['severity'] == 'error' for row in result['notices'])
    assert any(row['code'] == 'sources_missing' for row in result['notices'])
    assert report['unavailable'] == ['grid', 'house_total', 'solar', 'car_soc']
    report['sources'] = {'grid':{'reason':'unit_invalid'}, 'house_total':{'reason':'future_sample'}}
    still_visible = view_state(data, now)
    assert next(row for row in still_visible['notices'] if row['code'] == 'sources_unavailable')['measurements'] == ['car_soc', 'grid', 'house_total', 'solar']
    result = view_state(data, now+timedelta(seconds=120))
    assert next(row for row in result['notices'] if row['code'] == 'sources_unavailable')['measurements'] == ['car_soc', 'grid', 'house_total', 'solar']


def test_all_fleet_wallboxes_and_shared_battery_pause_and_resume_after_long_backup():
    from test_fleet import FleetRequirements
    case = FleetRequirements()
    try:
        app, ha, _, _ = case.setup_fleet()
        for _, child, _ in app.controllers:
            child.config.options['backup_mode_entity'] = 'binary_sensor.backup'
        app.set_armed(True)
        for seconds, mode in ((0, 'on'), (86400, 'on'), (172800, 'unknown'), (172840, 'off')):
            now = NOW+timedelta(seconds=seconds)
            ha.rows['binary_sensor.backup'] = {'state':mode}
            for row in ha.rows.values():
                row.update(last_reported=now.isoformat(), last_updated=now.isoformat())
            app.config.eos.plan.return_value['generated_at'] = now.isoformat()
            app.tick(now, seconds)
            snapshot = view_state(app.snapshot(now), now)
            assert snapshot['armed']
            if mode != 'off':
                assert snapshot['control_paused']
                assert all(child.backup_paused for _, child, _ in app.controllers)
                app.battery_driver.apply.assert_not_called()
                assert not any(entity.startswith('switch.') and value is True for entity, value in ha.writes)
            else:
                assert snapshot['control_status'] == 'active'
                assert not snapshot['control_paused']
                app.battery_driver.apply.assert_called_once()
        app.battery_driver.release.assert_called_once()
    finally:
        case.doCleanups()


def test_unknown_status_after_grid_operation_pauses_and_releases_until_fresh_grid(control):
    assert poll(control, 0, 'grid')['control_status'] == 'active'
    charging = requirements.wallbox(watts=2000, status='charging', enabled=True)
    # A single failed status read keeps the confirmed grid operation for up to a minute.
    result = poll(control, 5, 'unknown', car=charging)
    assert result['control_status'] == 'active' and not result['control_paused']
    assert not any(row['code'] == 'backup_power_unknown' for row in result['notices'])
    control.battery.apply.reset_mock()
    control.box.charge.reset_mock()
    control.box.pause.reset_mock()
    for seconds in (SUPPLY_GRACE_S, 600):
        result = poll(control, seconds, 'unknown', car=charging)
        assert result['control_status'] == 'power_supply_waiting'
        assert result['armed'] and result['control_paused']
        assert any(row['code'] == 'backup_power_unknown' for row in result['notices'])
    control.battery.apply.assert_not_called()
    control.box.charge.assert_not_called()
    control.battery.release.assert_called_once()
    assert control.box.pause.call_count == 2  # Released, then a restarted charge stopped again.
    control.config.set_control_enabled.assert_called_once_with(True)
    result = poll(control, 640, 'grid')
    assert result['control_status'] == 'active' and not result['control_paused']
    control.battery.apply.assert_called_once()


def test_reported_backup_or_status_pauses_at_once_and_a_retained_grid_never_ends_a_pause(control):
    assert poll(control, 0, 'grid')['control_status'] == 'active'
    assert poll(control, 5, 'backup')['control_status'] == 'backup'
    # The grid report before the backup is no longer retained for a failed read.
    assert poll(control, 10, 'unknown')['control_paused']
    assert poll(control, 20, 'grid')['control_status'] == 'active'
    # An unknown source reported with a sample (e.g. generator) is a real status.
    now = NOW + timedelta(seconds=25)
    control.battery.read.return_value = BatteryReading(50, 0, 0, now, now, now, power_supply=PowerSupplyReading('unknown', now))
    control.app.tick(now, 25)
    assert view_state(control.app.snapshot(now), now)['control_paused']
    # While paused, a failed read never stands in for the grid report recovery needs.
    assert poll(control, 30, 'unknown')['control_paused']


def test_startup_with_unknown_status_never_passes_the_readiness_gate(control):
    for seconds in (0, 300):
        result = poll(control, seconds, 'unknown')
        assert result['control_status'] == 'power_supply_waiting' and result['armed']
    control.battery.apply.assert_not_called()
    control.box.charge.assert_not_called()
    assert poll(control, 340, 'grid')['control_status'] == 'active'


def entity_poll(case, seconds, state, *, stamp=None, battery_error=None):
    now = NOW + timedelta(seconds=seconds)
    rows = case.states(when=now)
    rows['binary_sensor.backup'] = {'state':state, 'last_reported':(stamp or now).isoformat()}
    case.ha.states.return_value = rows
    case.battery.read.side_effect = battery_error
    case.battery.read.return_value = BatteryReading(50, 0, 0, now, now, now)
    case.box.read.return_value = replace(requirements.wallbox(), sample=now)
    case.eos.plan.return_value = case.plan(now)
    case.app.tick(now, seconds)
    return view_state(case.app.snapshot(now), now)


def test_unchanged_explicit_grid_state_of_a_configured_entity_keeps_control_running(control):
    control.config.options['backup_mode_entity'] = 'binary_sensor.backup'
    for seconds in (0, 3600, 86400):
        result = entity_poll(control, seconds, 'off', stamp=NOW)
        assert result['control_status'] == 'active' and not result['control_paused']
    control.battery.release.assert_not_called()


def test_unknown_status_with_a_failed_device_read_keeps_the_remembered_intent(control):
    control.config.options['backup_mode_entity'] = 'binary_sensor.backup'
    assert entity_poll(control, 0, 'off')['control_status'] == 'active'
    result = entity_poll(control, 5, 'unavailable', battery_error=TimeoutError('unavailable'))
    assert result['armed'] and result['control_status'] == 'power_supply_waiting'
    assert 'battery_read' in result['errors']
    control.config.set_control_enabled.assert_called_once_with(True)
    assert entity_poll(control, 45, 'off')['control_status'] == 'active'

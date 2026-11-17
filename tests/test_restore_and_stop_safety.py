"""Device release after restarts and stop failures never silently end control."""
from dataclasses import replace
from datetime import timedelta

import pytest

from custom_components.eos_energiezentrale.energy.contracts import BatteryReading
from custom_components.eos_energiezentrale.energy.controller import Controller
from custom_components.eos_energiezentrale.energy.device_io import DeviceConfirmationError
import test_requirements as requirements
from test_energy import NOW


@pytest.fixture
def case():
    fixture = requirements.ControllerRequirements()
    fixture.setUp()
    try:
        yield fixture
    finally:
        fixture.doCleanups()


def poll(case, app, second, *, car=None):
    now = NOW + timedelta(seconds=second)
    case.ha.states.return_value = case.states(when=now)
    case.battery.read.return_value = BatteryReading(50, 0, 0, now, now, now)
    case.box.read.return_value = replace(car or requirements.wallbox(), sample=now)
    case.eos.plan.return_value = case.plan(now)
    app.tick(now, second)
    return app.snapshot(now)


def restored(case):
    case.config.control_enabled = True
    return Controller(case.ha, case.config)


def test_unreachable_wallbox_stop_failure_stays_visible_and_retried_without_ending_control(case):
    app = case.app
    app.set_armed(True)
    poll(case, app, 0)
    assert app.owned and not app.restore_pending
    case.box.pause.side_effect = DeviceConfirmationError('switch.wallbox_enable')
    unknown = requirements.wallbox(status='unknown')
    for second in (5, 10):
        case.battery.apply.reset_mock()
        result = poll(case, app, second, car=unknown)
        assert app.armed and 'wallbox_stop' in result['errors']
        case.battery.apply.assert_called_once()  # Storage control continues.
    assert case.box.pause.call_count >= 2
    case.box.charge.assert_not_called()
    case.box.pause.side_effect = None
    assert 'wallbox_stop' not in poll(case, app, 15, car=unknown)['errors']


def test_reachable_wallbox_without_stop_confirmation_remains_a_control_error(case):
    app = case.app
    app.set_armed(True)
    poll(case, app, 0)
    case.box.pause.side_effect = DeviceConfirmationError('switch.wallbox_enable')
    with pytest.raises(DeviceConfirmationError):
        poll(case, app, 5, car=requirements.wallbox(watts=2000, status='charging', enabled=True))


def test_restart_releases_a_reachable_battery_even_while_the_wallbox_is_unreadable(case):
    app = restored(case)
    case.eos.plan.side_effect = OSError('unavailable')
    unknown = requirements.wallbox(status='unknown')
    for second in (0, 5):
        poll(case, app, second, car=unknown)
    assert case.battery.release.call_count == 2
    case.box.pause.assert_not_called()
    assert app.owned and app.armed and app.restore_pending  # Wallbox release still pending.
    poll(case, app, 10)
    case.box.pause.assert_called_once()
    assert not app.owned
    case.battery.apply.assert_not_called()


def test_failed_release_after_explicit_off_is_retried_until_confirmed(case):
    app = restored(case)
    case.battery.release.side_effect = OSError('not ready')
    with pytest.raises(OSError):
        app.set_armed(False)
    assert not app.armed and app.owned
    result = poll(case, app, 0)
    assert 'release' in result['errors'] and app.owned
    case.battery.release.side_effect = None
    result = poll(case, app, 5)
    assert 'release' not in result['errors'] and not app.owned
    calls = case.battery.release.call_count
    poll(case, app, 10)
    assert case.battery.release.call_count == calls  # Nothing owned, nothing repeated.
    case.battery.apply.assert_not_called()
    case.box.charge.assert_not_called()

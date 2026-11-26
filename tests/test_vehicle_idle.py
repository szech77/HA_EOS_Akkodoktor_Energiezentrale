"""A confirmed release without charging becomes a notice; replanning does not pause a running plan."""
from dataclasses import replace
from datetime import timedelta
import logging

import pytest

from custom_components.eos_energiezentrale.energy.controller import PLAN_HOLD_S
from custom_components.eos_energiezentrale.energy.settings import daily_settings
from custom_components.eos_energiezentrale.energy.status import view_state
from custom_components.eos_energiezentrale.energy.vehicle_idle import VEHICLE_IDLE_S
from test_energy import NOW
import test_requirements as requirements


@pytest.fixture
def case():
    harness = requirements.ControllerRequirements()
    harness.setUp()
    try:
        yield harness
    finally:
        harness.doCleanups()


def tick(case, seconds, box=None):
    now = NOW + timedelta(seconds=seconds)
    case.ha.states.return_value = case.states(when=now)
    if box is not None:
        case.box.read.return_value = replace(box, sample=now)
    case.app.tick(now, seconds)
    return view_state(case.app.snapshot(now), now)


def idle_notices(view):
    return [notice for notice in view['notices'] if notice['code'] == 'vehicle_idle']


def fast_charging(case):
    case.config.daily = daily_settings({'fast': True}, 20)
    case.app.set_armed(True)
    tick(case, 0)
    amps = case.box.charge.call_args.args[0]
    return requirements.wallbox(enabled=True, amps=amps, watts=0)


def test_a_released_connected_vehicle_without_power_becomes_a_notice_after_three_minutes(case):
    released = fast_charging(case)
    case.box.idle_reason.return_value = 'vehicle_complete'
    for seconds in (10, 60, VEHICLE_IDLE_S):
        assert not idle_notices(tick(case, seconds, released))
    notices = idle_notices(tick(case, VEHICLE_IDLE_S + 10, released))
    assert len(notices) == 1
    notice = notices[0]
    assert notice['id'] == 'system/vehicle_idle' and notice['severity'] == 'warning'
    assert notice['message'] == 'notice.vehicle_idle_vehicle_complete'
    assert notice['details']['reason'] == 'vehicle_complete'
    # Display only: control keeps running and no control error is recorded.
    assert 'vehicle_idle' not in case.app.errors and case.app.armed
    # Charging power ends the notice at once.
    assert not idle_notices(tick(case, VEHICLE_IDLE_S + 20, replace(released, watts=3000, status='charging')))


def test_an_unknown_or_failing_reason_keeps_the_generic_text(case):
    released = fast_charging(case)
    case.box.idle_reason.side_effect = RuntimeError('private')
    tick(case, 10, released)
    notice = idle_notices(tick(case, VEHICLE_IDLE_S + 10, released))[0]
    assert notice['message'] == 'notice.vehicle_idle_unknown'


@pytest.mark.parametrize('change', [{'enabled': False}, {'status': 'disconnected'}, {'watts': 500}, {'watts': None}])
def test_no_notice_without_a_confirmed_release_to_a_connected_idle_vehicle(case, change):
    released = replace(fast_charging(case), **change)
    for seconds in (10, VEHICLE_IDLE_S + 10, 2 * VEHICLE_IDLE_S):
        assert not idle_notices(tick(case, seconds, released))


def test_no_notice_when_control_is_released(case):
    released = fast_charging(case)
    tick(case, 10, released)
    assert idle_notices(tick(case, VEHICLE_IDLE_S + 10, released))
    case.app.set_armed(False)
    assert not idle_notices(tick(case, VEHICLE_IDLE_S + 20, released))
    assert 'vehicle_idle' not in case.app.snapshot(NOW + timedelta(seconds=VEHICLE_IDLE_S + 20))['error_details']


def test_the_notice_is_logged_once_with_its_cause_through_the_issue_log(case, caplog):
    from custom_components.eos_energiezentrale.energy.status import IssueLog
    released = fast_charging(case)
    case.box.idle_reason.return_value = 'access_control'
    log = IssueLog(logging.getLogger('test.vehicle_idle'))
    caplog.set_level(logging.INFO, 'test.vehicle_idle')
    tick(case, 10, released)
    for seconds in (VEHICLE_IDLE_S + 10, VEHICLE_IDLE_S + 20):
        log.update('state', tick(case, seconds, released)['notices'])
    messages = [record.getMessage() for record in caplog.records if 'vehicle_idle' in record.getMessage()]
    assert len(messages) == 1 and 'access_control' in messages[0]


DEPARTURE = NOW + timedelta(hours=4)


def plan_charging(case):
    """Plan-based grid charging is running with a confirmed release."""
    case.config.daily = daily_settings({'schedule': 'once', 'departure': DEPARTURE.isoformat(), 'target_soc': 70}, 20)
    case.app.set_armed(True)
    for offset in (0, 134):
        now = NOW + timedelta(seconds=offset)
        case.eos.plan.return_value = case.plan(now)
        tick(case, offset)
    amps = case.box.charge.call_args.args[0]
    return requirements.wallbox(enabled=True, amps=amps, watts=4000, status='charging')


def test_a_running_plan_based_charge_is_not_paused_while_eos_replans(case, caplog):
    caplog.set_level(logging.INFO, 'custom_components.eos_energiezentrale.energy.controller')
    charging = plan_charging(case)
    case.box.pause.reset_mock()
    # A changed goal needs a new EOS plan; the old generation is no longer accepted.
    case.config.daily = daily_settings({'schedule': 'once', 'departure': DEPARTURE.isoformat(), 'target_soc': 75}, 20)
    for seconds in (170, 200, 400):
        view = tick(case, seconds, charging)
        assert view['vehicle_planning'] == 'plan_pending'
        assert view['vehicle_plan_hold'] is True
    case.box.pause.assert_not_called()
    assert any('continues with the previous EOS plan' in record.getMessage() for record in caplog.records)
    # Bounded: an old decision does not last.
    tick(case, 170 + PLAN_HOLD_S + 30, charging)
    case.box.pause.assert_called()
    assert any('plan hold ended: timeout' in record.getMessage() for record in caplog.records)


def test_ending_fast_charging_is_never_held(case):
    charging = replace(fast_charging(case), watts=4000, status='charging')
    case.box.pause.reset_mock()
    case.config.daily = daily_settings({'schedule': 'once', 'departure': DEPARTURE.isoformat(), 'target_soc': 70}, 20)
    view = tick(case, 30, charging)
    assert view['vehicle_plan_hold'] is False
    case.box.pause.assert_called()


def test_a_paused_wallbox_is_not_started_by_an_old_plan_while_eos_replans(case):
    charging = plan_charging(case)
    case.config.daily = daily_settings({'schedule': 'once', 'departure': DEPARTURE.isoformat(), 'target_soc': 75}, 20)
    case.box.charge.reset_mock()
    view = tick(case, 170, replace(charging, enabled=False, watts=0, status='connected'))
    assert view['vehicle_plan_hold'] is False
    case.box.charge.assert_not_called()

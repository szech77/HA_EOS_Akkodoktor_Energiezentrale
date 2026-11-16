"""Multiple vehicle goals, migration and local German holiday rules."""
from datetime import date, datetime, timedelta, timezone
from unittest.mock import Mock
from zoneinfo import ZoneInfo

import pytest

from custom_components.eos_energiezentrale.energy.charge_plans import holiday_dates, plan_view, selected_goal
from custom_components.eos_energiezentrale.energy.controller import Controller
from custom_components.eos_energiezentrale.energy.domain import next_departure
from custom_components.eos_energiezentrale.energy.failures import BackendError
from custom_components.eos_energiezentrale.energy.settings import Configuration, changed_settings, daily_settings, settings_payload
from test_energy import NOW, temporary_project_directory
from test_requirements import OPTIONS

ZONE = ZoneInfo('Europe/Berlin')


def once(identity='trip', hours=4, target=70, active=True):
    return dict(id=identity, active=active, schedule='once', target_soc=target,
                departure=(NOW + timedelta(hours=hours)).isoformat())


def weekly(**changes):
    return dict(id='commute', active=True, schedule='weekly', target_soc=80,
                departure_time='07:30', weekdays=[0, 1, 2, 3, 4], holidays=False, **changes)


def test_earliest_active_goal_and_higher_target_for_simultaneous_departures():
    settings = daily_settings({'charge_plans': [once('later', 6, 90), once('off', 1, active=False),
        once('expired', -1), once('first', 2, 60), once('same', 2, 75)]}, 20)
    assert selected_goal(settings, NOW, ZONE) == (75, NOW + timedelta(hours=2))
    assert next_departure(settings, NOW, ZONE) == NOW + timedelta(hours=2)
    assert selected_goal(settings, NOW + timedelta(hours=2), ZONE) == (90, NOW + timedelta(hours=6))
    settings['charge_plans'] = []
    assert selected_goal(settings, NOW, ZONE) is None


def test_legacy_schedule_is_visible_without_changing_its_deadline_or_target():
    settings = daily_settings({'schedule': 'once', 'target_soc': 65,
        'departure': (NOW + timedelta(hours=4)).isoformat()}, 20)
    rows = plan_view(settings, NOW, ZONE)
    assert rows[0]['id'] == 'legacy'
    assert rows[0]['departure_local'] == '2026-11-08T17:00'
    migrated = daily_settings(settings_payload({'charge_plans': [
        {key: value for key, value in rows[0].items() if key not in {'next_departure', 'selected', 'departure'}}]}, ZONE), 20)
    assert selected_goal(migrated, NOW, ZONE) == (65, NOW + timedelta(hours=4))


def test_german_state_and_local_calendars():
    assert date(2026, 10, 3) in holiday_dates(2026, '', '', False)
    assert date(2026, 1, 6) in holiday_dates(2026, 'BY', '', False)
    assert date(2026, 1, 6) not in holiday_dates(2026, 'BE', '', False)
    assert date(2026, 8, 15) not in holiday_dates(2026, 'BY', '', False)
    assert date(2026, 8, 15) in holiday_dates(2026, 'BY', '', True)
    assert date(2026, 8, 8) in holiday_dates(2026, 'BY', 'augsburg', False)
    for state in ('SN', 'TH'):
        assert date(2026, 6, 4) not in holiday_dates(2026, state, '', False)
        assert date(2026, 6, 4) in holiday_dates(2026, state, '', True)


def test_holidays_add_to_weekdays_and_holiday_only_can_reach_next_year():
    row = weekly()
    row.update(weekdays=[], holidays=True)
    settings = daily_settings({'charge_plans': [row]}, 20)
    now = datetime(2026, 12, 27, 12, tzinfo=timezone.utc)
    assert next_departure(settings, now, ZONE).isoformat() == '2027-01-01T07:30:00+01:00'
    row.update(weekdays=[0])
    settings = daily_settings({'charge_plans': [row]}, 20)
    assert next_departure(settings, now, ZONE).day == 28


def test_weekly_dst_gap_moves_forward_and_nonexistent_once_is_rejected():
    row = weekly()
    row.update(weekdays=[6], departure_time='02:30')
    settings = daily_settings({'charge_plans': [row]}, 20)
    now = datetime(2027, 3, 27, 12, tzinfo=timezone.utc)
    assert next_departure(settings, now, ZONE).isoformat() == '2027-03-28T03:30:00+02:00'
    with pytest.raises(BackendError):
        settings_payload({'charge_plans': [{'id': 'gap', 'departure_local': '2027-03-28T02:30'}]}, ZONE)


@pytest.mark.parametrize('changes', [
    {'charge_plans': [once(), once()]}, {'charge_plans': [once(target=101)]},
    {'charge_plans': [{**once(), 'active': 'yes'}]}, {'charge_plans': [{**once(), 'id': '../file'}]},
    {'charge_plans': [{**once(), 'departure': '2027-01-01T07:30'}]},
    {'charge_plans': [{**weekly(), 'weekdays': [], 'holidays': False}]},
    {'charge_plans': [once(str(i)) for i in range(33)]},
    {'holiday_state': 'DE'}, {'holiday_locality': 'augsburg'}, {'holiday_catholic': True},
])
def test_invalid_goals_or_calendar_rejected(changes):
    with pytest.raises(BackendError):
        daily_settings(changes, 20)


def test_plans_persist_delete_and_use_selected_soc_for_confirmed_eos_goal():
    with temporary_project_directory() as directory:
        config = Configuration(OPTIONS, Mock(), directory)
        config.update({**config.daily, 'target_soc': 95, 'charge_plans': [once(target=63), once('later', 8, 90)]})
        restored = Configuration(OPTIONS, Mock(), directory)
        assert restored.daily['charge_plans'] == config.daily['charge_plans']
        app = Controller(Mock(), restored)
        app.config.eos = Mock()
        departure = next_departure(restored.daily, NOW, ZONE)
        assert app.sync_goal(NOW, 100, departure)
        app.config.eos.set_vehicle_goal.assert_called_once_with('ev1', 63, departure)
        assert app.snapshot(NOW)['charge_target_soc'] == 63
        assert len(app.snapshot(NOW)['charge_plan_view']) == 2
        restored.update({**restored.daily, 'charge_plans': []})
        assert not app.sync_goal(NOW + timedelta(seconds=31), 131, None)
        app.config.eos.set_vehicle_goal.assert_called_with('ev1', 0, None)
        assert Configuration(OPTIONS, Mock(), directory).daily['charge_plans'] == []


def test_obsolete_api_edit_is_reported_instead_of_silently_ignored():
    settings = daily_settings({'charge_plans': [once()]}, 20)
    with pytest.raises(BackendError) as failure:
        changed_settings(settings, {'schedule': 'off'}, 20)
    assert failure.value.reason == 'invalid_schedule'
    assert failure.value.fields == ['charge_plans']
    assert changed_settings(settings, {'target_soc': 90}, 20)['charge_plans'] == settings['charge_plans']

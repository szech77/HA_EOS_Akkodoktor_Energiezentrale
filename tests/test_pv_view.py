from datetime import datetime, timedelta, timezone

import pytest

from custom_components.eos_energiezentrale.energy.pv_view import pv_effects, pv_hours, pv_now, weather_days

# 14:30 local time in Berlin (UTC+1).
NOW = datetime(2026, 11, 18, 13, 30, tzinfo=timezone.utc)
ZONE = 'Europe/Berlin'


def slot(hours, **values):
    start = NOW.replace(minute=0) + timedelta(hours=hours)
    return {'time': start.isoformat(), 'end': (start + timedelta(hours=1)).isoformat(), **values}


def forecast():
    # PV in daylight 08–16 local (07–15 UTC), dark otherwise.
    rows = []
    for hours in range(0, 40):
        local = (NOW.replace(minute=0) + timedelta(hours=hours)).astimezone(timezone(timedelta(hours=1))).hour
        rows.append(slot(hours, solar=2000. if 8 <= local < 16 else 0., grid=-1500 if hours < 2 else 300, price=30.,
                         battery=0, battery_soc=60))
    return rows


def weather():
    return [{**slot(hours), 'condition': 'clear-night' if hours > 2 else 'sunny', 'temperature': 7 - hours * .2,
             'cloud_coverage': 10, 'precipitation': 0, 'precipitation_probability': 5} for hours in range(0, 30)]


def test_hours_join_weather_with_pv_and_fold_dark_hours_into_one_night_block():
    hours = pv_hours(forecast(), weather(), NOW, ZONE)
    first = hours[0]
    assert first['now'] is True and first['pv_kwh'] == pytest.approx(1.0)
    assert first['condition'] == 'sunny' and first['cloud_coverage'] == 10
    assert [item['kind'] for item in hours[:3]] == ['hour', 'hour', 'night']
    night = hours[2]
    # 16:00 local until 08:00 local next day is one block with the lowest temperature.
    assert night['start'] == datetime(2026, 11, 18, 15, tzinfo=timezone.utc).isoformat()
    assert night['end'] == datetime(2026, 11, 19, 7, tzinfo=timezone.utc).isoformat()
    assert night['condition'] == 'clear-night' and night['low'] == pytest.approx(7 - 17 * .2)
    assert hours[-1]['end'] == datetime(2026, 11, 19, 23, tzinfo=timezone.utc).isoformat()


def test_unknown_pv_hours_stay_visible_instead_of_becoming_night():
    hours = pv_hours([], [], NOW, ZONE)
    assert all(item['kind'] == 'hour' and item['pv_kwh'] is None for item in hours)
    assert len(hours) == 34


def test_days_combine_pv_totals_with_daylight_weather():
    totals = [{'date': '2026-11-18', 'kwh': 3.0, 'total_kwh': 12.0, 'complete': True},
              {'date': '2026-11-19', 'kwh': 16.0, 'complete': True},
              {'date': '2026-11-20', 'kwh': None, 'complete': False}]
    days = weather_days(weather(), totals, 9.0, NOW, ZONE)
    assert [day['pv_kwh'] for day in days] == [12.0, 16.0, None]
    assert days[0]['today'] and days[0]['measured_kwh'] == 9.0 and days[1]['measured_kwh'] is None
    assert days[1]['condition'] == 'clear-night' and days[1]['high'] > days[1]['low']
    assert days[2]['condition'] is None and days[2]['weather_hours'] == 0 and not days[2]['complete']


def test_pv_now_compares_live_power_with_the_current_forecast_interval():
    assert pv_now({'live': {'solar': 1800}, 'forecast': forecast()}, NOW) == {
        'power_w': 1800, 'forecast_w': 2000., 'ratio': pytest.approx(.9)}
    night = NOW + timedelta(hours=5)
    assert pv_now({'live': {'solar': 0}, 'forecast': forecast()}, night)['ratio'] is None


def test_effects_explain_tomorrow_battery_export_and_car_plan():
    rows = forecast()
    rows[12].update(battery=3000, solar=0, price=24)
    rows[13].update(battery=3000, solar=0, price=26)
    rows[14].update(battery_soc=90)
    data = {'forecast': rows, 'pv_forecast_totals': [{'date': '2026-11-18', 'kwh': 3, 'total_kwh': 20, 'complete': True},
                                                    {'date': '2026-11-19', 'kwh': 6, 'complete': True}],
            'plan_events': [{'kind': 'battery_full', 'time': slot(1)['time'], 'soc': 95}],
            'vehicle_name': 'ID.4',
            'charge_plan': {'state': 'active', 'grid_kwh': 25.4, 'grid_from': slot(12)['time'], 'grid_price_ct': 24.1,
                            'pv_kwh': 5.4, 'pv_until': slot(2)['time']}}
    effects = pv_effects(data, NOW)
    assert [item['id'] for item in effects] == ['tomorrow_low', 'export', 'battery_full', 'battery_grid', 'car_grid']
    assert effects[0] == {'id': 'tomorrow_low', 'kwh': 6, 'today_kwh': 20, 'date': '2026-11-19'}
    battery = effects[3]
    assert battery['kwh'] == pytest.approx(6) and battery['price_ct'] == pytest.approx(25) and battery['soc'] == 90
    assert effects[1]['kwh'] == pytest.approx(1.5 * .5 + 1.5)
    assert effects[4]['vehicle_name'] == 'ID.4' and effects[4]['kwh'] == 25.4


def test_effects_skip_reached_cars_and_report_pv_only_charging():
    plan = {'state': 'active', 'grid_kwh': 0, 'pv_kwh': 4, 'pv_until': slot(2)['time']}
    data = {'forecast': [], 'vehicles': [{'id': 'a', 'name': 'A', 'charge_plan': plan},
                                          {'id': 'b', 'name': 'B', 'charge_plan': {**plan, 'state': 'reached'}}]}
    assert pv_effects(data, NOW) == [{'id': 'car_pv', 'vehicle_name': 'A', 'vehicle_id': 'a', 'kwh': 4, 'end': plan['pv_until']}]
    assert pv_effects({'forecast': []}, NOW) == []


def test_current_hour_without_hourly_weather_shows_the_current_weather():
    # The hourly forecast starts at the next full hour, as many weather services do.
    later = [row for row in weather() if row['time'] != slot(0)['time']]
    current = {'condition': 'cloudy', 'temperature': 9.5, 'unit': '°C'}
    first = pv_hours(forecast(), later, NOW, ZONE, current)[0]
    assert first['now'] and first['condition'] == 'cloudy' and first['temperature'] == 9.5
    assert first['cloud_coverage'] is None
    # A current hour with hourly weather keeps it; unknown current weather adds nothing.
    assert pv_hours(forecast(), weather(), NOW, ZONE, current)[0]['condition'] == 'sunny'
    assert pv_hours(forecast(), later, NOW, ZONE, {'condition': 'unknown'})[0]['condition'] is None
    assert pv_hours(forecast(), later, NOW, ZONE)[1]['condition'] == 'sunny'

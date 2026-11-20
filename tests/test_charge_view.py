from datetime import datetime, timedelta, timezone

import pytest

from custom_components.eos_energiezentrale.energy.charge_view import charge_plan

NOW = datetime(2026, 11, 18, 14, 0, tzinfo=timezone.utc)
LIMITS = {'capacity_wh': 50000, 'efficiency': 1, 'maximum_w': 11000, 'max_current_a': 16, 'phases': None}


def row(hours, car, soc, *, grid=0, price=30., solar=0., house=500., length=1):
    start = NOW + timedelta(hours=hours)
    return {'time': start.isoformat(), 'end': (start + timedelta(hours=length)).isoformat(), 'car': car,
            'car_soc': soc, 'grid': grid, 'price': price, 'solar': solar, 'house_total': house}


def data(forecast, **values):
    result = {'armed': True, 'live': {'car_soc': 40, 'car_connected': True}, 'charge_target_soc': 80,
              'charge_departure': (NOW + timedelta(hours=8)).isoformat(), 'charge_limits': LIMITS,
              'vehicle_forecast_source': 'eos', 'settings': {'fast': False}, 'errors': {},
              'plan_generated_at': (NOW - timedelta(minutes=2)).isoformat(), 'forecast': forecast}
    result.update(values)
    return result


def plan_rows():
    # 1 h PV surplus at 3.7 kW, 3 h pause, 2.5 h grid charging at 7.4 kW, then the target is held.
    return [row(0, 3700, 40, solar=5000, price=30),
            *[row(hours, 0, 47.4, price=36) for hours in (1, 2, 3)],
            row(4, 7400, 47.4, grid=7900, price=24), row(5, 7400, 62.2, grid=7900, price=24),
            row(6, 3700, 77, grid=4200, price=24, length=.5), row(6.5, 0, 80.7, price=25, length=1.5)]


def test_charge_plan_splits_the_forecast_into_pv_pause_grid_and_ready_with_costs():
    plan = charge_plan(data(plan_rows()), NOW, pv_price_ct=8.)
    assert [item['kind'] for item in plan['segments']] == ['pv', 'pause', 'grid', 'ready']
    pv, pause, grid, ready = plan['segments']
    assert pv['kwh'] == pytest.approx(3.7) and pv['phases'] == 1 and pv['cost_eur'] == pytest.approx(3.7 * .08)
    assert pv['value_ct'] == 8. and pause['kwh'] == 0 and pause['price_ct'] == pytest.approx(36)
    assert grid['start'] == (NOW + timedelta(hours=4)).isoformat() and grid['phases'] == 3
    assert grid['kwh'] == pytest.approx(16.65) and grid['price_ct'] == pytest.approx(24)
    assert grid['power_w'] == pytest.approx(16650 / 2.5)
    assert ready['end'] == (NOW + timedelta(hours=8)).isoformat()
    assert plan['state'] == 'active' and plan['remaining_kwh'] == pytest.approx(20)
    assert plan['pv_until'] == (NOW + timedelta(hours=1)).isoformat()
    assert plan['grid_from'] == grid['start'] and plan['grid_price_ct'] == pytest.approx(24)
    assert plan['reached_at'] == (NOW + timedelta(hours=6.5)).isoformat()
    assert plan['buffer_s'] == pytest.approx(1.5 * 3600)
    cost = 3.7 * .08 + 16.65 * .24
    assert plan['plan_cost']['eur'] == pytest.approx(cost)
    assert plan['plan_cost']['price_ct'] == pytest.approx(cost / (3.7 + 16.65) * 100)
    assert plan['curve'][0] == {'time': NOW.isoformat(), 'soc': 40}


def test_immediate_charging_uses_full_power_and_forecast_pv_surplus():
    plan = charge_plan(data(plan_rows()), NOW, pv_price_ct=8.)
    now = plan['immediate_cost']
    # 20 kWh at 11 kW: 4.5 kWh surplus in the first hour, the rest from the grid at 30 and 36 ct.
    assert now['pv_kwh'] == pytest.approx(4.5) and now['grid_kwh'] == pytest.approx(15.5)
    assert now['eur'] == pytest.approx(4.5 * .08 + 6.5 * .30 + 9 * .36)
    assert now['reached_at'] == (NOW + timedelta(hours=1 + 9 / 11)).isoformat()
    assert plan['plan_cost']['eur'] < now['eur']


@pytest.mark.parametrize(('values', 'state'), [
    ({'armed': False}, 'read_only'),
    ({'errors': {'wallbox': 'TimeoutError'}}, 'suspended'),
    ({'settings': {'fast': True}}, 'overridden'),
    ({'live': {'car_soc': 40, 'car_connected': False}}, 'disconnected'),
    ({'live': {'car_soc': 80, 'car_connected': True}}, 'reached'),
    ({'vehicle_forecast_source': 'constant'}, 'no_plan'),
])
def test_charge_plan_states_explain_why_the_plan_is_not_followed(values, state):
    assert charge_plan(data(plan_rows(), **values), NOW, 8.)['state'] == state


def test_charge_plan_without_eos_curve_keeps_the_projection_but_no_segments_or_costs():
    rows = [{'time': row(hours, 0, 40)['time'], 'end': row(hours, 0, 40)['end'], 'car_soc': 40 + hours}
            for hours in range(3)]
    plan = charge_plan(data(rows, vehicle_forecast_source='pv_estimate'), NOW, None)
    assert plan['segments'] == [] and plan['plan_cost'] is None and plan['immediate_cost'] is None
    assert [point['soc'] for point in plan['curve']] == [40, 41, 42]


def test_charge_plan_counts_pv_as_free_without_tariff_and_marks_unpriced_grid():
    rows = plan_rows()
    rows[4]['price'] = None
    plan = charge_plan(data(rows), NOW, None)
    assert plan['segments'][0]['cost_eur'] == 0 and plan['pv_price_ct'] is None
    assert plan['segments'][2]['cost_eur'] is None and plan['plan_cost'] is None


def test_charge_plan_without_departure_covers_24_hours():
    plan = charge_plan(data(plan_rows(), charge_departure=None), NOW, 8.)
    assert plan['end'] == (NOW + timedelta(hours=24)).isoformat() and plan['buffer_s'] is None
    assert plan['segments'][-1]['kind'] == 'ready'


def test_short_segment_between_two_pauses_joins_them_without_losing_energy():
    rows = [row(0, 3700, 40, solar=5000), row(1, 0, 47.4), row(2, 3700, 47.4, solar=5000, length=1 / 30),
            row(2 + 1 / 30, 0, 47.6, length=2 - 1 / 30), row(4, 7400, 47.6, grid=7900, price=24, length=2.5)]
    plan = charge_plan(data(rows), NOW, pv_price_ct=8.)
    assert [item['kind'] for item in plan['segments']] == ['pv', 'pause', 'grid']
    pause = plan['segments'][1]
    assert pause['start'] == (NOW + timedelta(hours=1)).isoformat() and pause['end'] == (NOW + timedelta(hours=4)).isoformat()
    assert pause['pv_kwh'] == pytest.approx(3.7 / 30)
    assert plan['pv_kwh'] == pytest.approx(3.7 + 3.7 / 30) and plan['pv_until'] == (NOW + timedelta(hours=1)).isoformat()

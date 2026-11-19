"""Display estimates never replace measured SoC or control/EOS planning."""
from copy import deepcopy
from datetime import timedelta

import pytest

from custom_components.eos_energiezentrale.energy.vehicle_projection import average_power, projected_vehicle_soc
from test_energy import NOW

SETTINGS = dict(capacity_wh=10000, charging_efficiency=1, pv=True, fast=False, pv_target_soc=80, reserve_w=0)


def slot(minutes=0, **changes):
    return dict(time=(NOW+timedelta(minutes=minutes)).isoformat(),
                end=(NOW+timedelta(minutes=minutes+15)).isoformat(), solar=5000, house_total=1000, **changes)


def project(evidence=(), soc=40, **changes):
    return projected_vehicle_soc([], evidence, NOW, soc, {**SETTINGS, **changes},
        connected=True, maximum_w=11000, minimum_w=1380)


def test_no_eos_or_pv_data_carries_current_soc_through_next_24_hours():
    rows, source = project()
    assert source == 'constant'
    assert len(rows) == 97
    assert {row['car_soc'] for row in rows} == {40}
    assert rows[-1]['time'] == (NOW+timedelta(hours=24)).isoformat()
    assert all('car' not in row for row in rows)


def test_pv_surplus_is_integrated_with_efficiency_and_target_and_missing_intervals_hold():
    evidence = [slot(), slot(15)]
    original = deepcopy(evidence)
    rows, source = project(evidence, charging_efficiency=.9, pv_target_soc=55)
    assert source == 'pv_estimate'
    assert [row['car_soc'] for row in rows[:4]] == [40,49,55,55]
    assert rows[-1]['car_soc'] == 55
    assert evidence == original


def test_battery_charging_and_foreign_ev_are_reserved_before_estimating_pv():
    evidence = [slot(battery=1000, car=1000)]
    rows, source = projected_vehicle_soc([], evidence, NOW, 40, SETTINGS,
        connected=True, maximum_w=11000, minimum_w=1380, foreign_vehicle=True)
    assert source == 'pv_estimate'
    assert rows[1]['car_soc'] == 45
    rows, source = projected_vehicle_soc([], evidence, NOW, 40, SETTINGS,
        connected=True, maximum_w=11000, minimum_w=1380, foreign_vehicle=True, pv_share=.5)
    assert source == 'constant'  # The remaining shared power cannot start charging.
    assert rows[1]['car_soc'] == 40


@pytest.mark.parametrize('changes', [{'pv':False},{'fast':True},{'capacity_wh':0},{'charging_efficiency':None}])
def test_pv_projection_requires_valid_settings(changes):
    rows, source = project([slot()], **changes)
    assert source == 'constant'
    assert rows[-1]['car_soc'] == 40


@pytest.mark.parametrize('connected', [False,None])
def test_disconnected_or_unknown_connection_does_not_predict_charging(connected):
    rows, source = projected_vehicle_soc([], [slot()], NOW, 40, SETTINGS,
        connected=connected, maximum_w=11000, minimum_w=1380)
    assert source == 'constant'
    assert rows[-1]['car_soc'] == 40


@pytest.mark.parametrize('soc', [None,-1,101,float('nan')])
def test_invalid_current_soc_does_not_invent_a_curve(soc):
    assert project([slot()],soc) == ([], 'unavailable')


def test_matching_eos_soc_always_takes_precedence_even_without_current_soc():
    original = [slot(car_soc=20), slot(15,car_soc=35)]
    rows, source = projected_vehicle_soc(original, [], NOW, None, SETTINGS, connected=True)
    assert rows is original
    assert source == 'eos'


def test_unplanned_eos_zero_curve_carries_known_positive_soc_forward():
    zero = [slot(car_soc=0), slot(15,car_soc=0)]
    original = deepcopy(zero)
    rows, source = projected_vehicle_soc(zero, [], NOW, 53, {**SETTINGS,'pv':False}, connected=True)
    assert source == 'constant'
    assert {row['car_soc'] for row in rows if 'car_soc' in row} == {53}
    assert zero == original


def test_eos_zero_placeholder_uses_pv_estimate_starting_at_actual_soc():
    zero = [slot(car_soc=0), slot(15,car_soc=0)]
    rows, source = projected_vehicle_soc(zero, zero, NOW, 53, SETTINGS,
        connected=True, maximum_w=11000, minimum_w=1380)
    values = [row['car_soc'] for row in rows if 'car_soc' in row]
    assert source == 'pv_estimate'
    assert values[:3] == [53,63,73]
    assert min(values) == 53
    assert max(values) <= 80


@pytest.mark.parametrize('current',[0,None])
def test_zero_eos_curve_is_not_rejected_without_a_contradicting_current_soc(current):
    zero = [slot(car_soc=0), slot(15,car_soc=0)]
    rows, source = projected_vehicle_soc(zero, [], NOW, current, SETTINGS, connected=True)
    assert source == 'eos'
    assert rows is zero


def test_nonzero_eos_charge_curve_retains_priority_over_local_pv_projection():
    curve = [slot(car_soc=53), slot(15,car_soc=60)]
    rows, source = projected_vehicle_soc(curve, [], NOW, 53, SETTINGS, connected=True)
    assert source == 'eos'
    assert rows is curve


def test_no_projection_over_missing_forecast_coverage_or_below_charger_minimum():
    rows, source = project([slot(30)])
    assert source == 'pv_estimate'
    assert [row['car_soc'] for row in rows[:4]] == [40,40,40,50]
    assert project([{**slot(),'house_total':None}])[1] == 'constant'
    assert project([{**slot(),'solar':1100}])[1] == 'constant'


def test_pv_estimate_carries_the_expected_charging_power_and_zero_once_the_target_is_reached():
    rows, source = project([slot(), slot(15), {**slot(30), 'solar': 1500}], pv_target_soc=55)
    assert source == 'pv_estimate'
    # 5000 W PV - 1000 W house; at the 55 % target charging stops, even without later PV data.
    assert [row.get('car') for row in rows[:4]] == [4000, 4000, 0, 0]
    # Below the target: no PV data means unknown power, too little surplus means 0 W.
    rows, _ = project([{**slot(30), 'solar': 1500}])
    assert rows[0].get('car') is None and rows[2]['car'] == 0


def test_disconnected_vehicle_shows_zero_power_and_unknown_connection_shows_none():
    rows, _ = projected_vehicle_soc([], [slot()], NOW, 40, SETTINGS, connected=False, maximum_w=11000, minimum_w=1380)
    assert {row['car'] for row in rows} == {0}
    rows, _ = projected_vehicle_soc([], [slot()], NOW, 40, SETTINGS, connected=None, maximum_w=11000, minimum_w=1380)
    assert all('car' not in row for row in rows)


def test_fast_charging_uses_maximum_power_until_the_charge_target():
    rows, source = project([], fast=True, target_soc=50, charging_efficiency=1)
    assert source == 'fast_estimate'
    # 11 kW for 15 minutes adds 27.5 % of 10 kWh; capped at the 50 % target.
    assert [(row['car_soc'], row['car']) for row in rows[:3]] == [(40, 11000), (50, 0), (50, 0)]


def test_without_vehicle_charging_control_nothing_is_predicted():
    for changes in ({}, {'fast': True, 'target_soc': 90}):
        rows, source = projected_vehicle_soc([], [slot()], NOW, 40, {**SETTINGS, **changes}, connected=True,
            maximum_w=11000, minimum_w=1380, controlled=False)
        assert source == 'constant'
        assert {row['car_soc'] for row in rows} == {40} and all('car' not in row for row in rows)


def test_average_power_needs_full_coverage():
    rows = [dict(time=NOW.isoformat(), end=(NOW+timedelta(minutes=30)).isoformat(), car=2000),
            dict(time=(NOW+timedelta(minutes=30)).isoformat(), end=(NOW+timedelta(hours=1)).isoformat(), car=0)]
    assert average_power(rows, NOW, NOW+timedelta(hours=1)) == 1000
    assert average_power(rows, NOW, NOW+timedelta(hours=2)) is None
    assert average_power(rows[:1], NOW, NOW+timedelta(minutes=15)) == 2000

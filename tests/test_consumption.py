from datetime import datetime, timedelta, timezone

from custom_components.eos_energiezentrale.energy.consumption import ConsumptionBalance, split_vehicles

T0 = datetime(2026, 11, 18, 17, 0, tzinfo=timezone.utc)


def live(**values):
    return {'solar': 0, 'grid': 500, 'battery_charge': 0, 'battery_discharge': 0, 'house_total': 500, 'car': 0, 'heat': 0, **values}


def step(balance, seconds, commanded=None, **values):
    return balance.update(live(**values), T0 + timedelta(seconds=seconds), commanded_car_w=commanded)


def test_total_follows_the_sources_and_replaces_a_wrong_measured_total():
    # Issue #33: 10 W import + 510 W discharge, the GX reports 940 W.
    result = ConsumptionBalance().update(live(grid=10, battery_discharge=510, house_total=940), T0)
    assert result['house_total'] == 520 and result['house_total_measured'] == 940 and result['house'] == 520
    assert result['estimated'] == {} and result['complete'] is True
    assert result['deviation_since'] == T0.isoformat()


def test_heat_pump_switch_off_before_its_new_value_keeps_the_house_value():
    balance = ConsumptionBalance()
    assert step(balance, 0, grid=2500, house_total=2500, heat=2000)['house'] == 500
    # The heat pump stopped: the grid drops by its power, the sensor still reports 2 kW.
    result = step(balance, 10, grid=520, house_total=520, heat=2000)
    assert result['consumers'] == {'house': 500, 'car': 0, 'heat': 20}
    assert result['estimated'] == {'heat': 'heat_drop', 'house': 'held'}
    # The estimate holds while the old value persists and ends with the new reading.
    assert step(balance, 30, grid=510, house_total=510, heat=2000)['estimated']['heat'] == 'heat_drop'
    result = step(balance, 40, grid=510, house_total=510, heat=0)
    assert result['consumers'] == {'house': 510, 'car': 0, 'heat': 0} and result['estimated'] == {}


def test_wallbox_stop_commanded_by_this_integration_uses_the_command():
    balance = ConsumptionBalance()
    step(balance, 0, commanded=7000, grid=7400, house_total=7400, car=7000)
    result = step(balance, 10, commanded=0, grid=420, house_total=420, car=7000)
    # The whole remaining total is house consumption; the car follows the command.
    assert result['consumers'] == {'house': 420, 'car': 0, 'heat': 0}
    assert result['estimated'] == {'car': 'car_command', 'house': 'held'}


def test_wallbox_start_rise_is_attributed_to_the_car_until_the_wallbox_reports():
    balance = ConsumptionBalance()
    step(balance, 0, commanded=0, grid=400, house_total=400, car=0)
    result = step(balance, 10, commanded=7000, grid=400, house_total=400, car=0)
    assert result['estimated'] == {}
    result = step(balance, 20, commanded=7000, grid=7300, house_total=7300, car=0)
    assert result['consumers'] == {'house': 400, 'car': 6900, 'heat': 0} and result['estimated'] == {'car': 'car_command'}
    result = step(balance, 30, commanded=7000, grid=7300, house_total=7300, car=6900)
    assert result['consumers'] == {'house': 400, 'car': 6900, 'heat': 0} and result['estimated'] == {}


def test_unexplained_deficit_is_proportional_and_still_fully_attributed():
    balance = ConsumptionBalance()
    step(balance, 0, grid=2400, house_total=2400, car=1500, heat=400)
    # The drop of 900 W matches neither device: scale both into what is left after the house.
    result = step(balance, 10, grid=1500, house_total=1500, car=1500, heat=400)
    consumers = result['consumers']
    assert abs(sum(consumers.values()) - 1500) < 1e-9 and abs(consumers['house'] - 500) < 1e-9
    assert abs(consumers['car'] - 1500 * 1000 / 1900) < 1e-9
    assert result['estimated'] == {'car': 'proportional', 'heat': 'proportional', 'house': 'held'}
    later = step(balance, 200, grid=1500, house_total=1500, car=1500, heat=400)
    assert abs(sum(later['consumers'].values()) - 1500) < 1e-9


def test_wallbox_switch_off_by_the_car_is_recognised_from_the_drop():
    balance = ConsumptionBalance()
    step(balance, 0, grid=3000, house_total=3000, car=1500, heat=1000)
    result = step(balance, 10, grid=1500, house_total=1500, car=1500, heat=1000)
    assert result['consumers'] == {'house': 500, 'car': 0, 'heat': 1000}
    assert result['estimated'] == {'car': 'car_drop', 'house': 'held'}


def test_small_timing_offset_scales_consumers_without_a_held_house():
    result = ConsumptionBalance().update(live(grid=2000, house_total=2000, car=1500, heat=650), T0)
    assert result['consumers']['house'] == 0 and abs(result['consumers']['car'] + result['consumers']['heat'] - 2000) < 1e-9


def test_missing_sources_follow_from_the_measured_total_or_hold_briefly():
    balance = ConsumptionBalance()
    result = balance.update(live(solar=None, grid=-1000, house_total=600, battery_charge=400), T0)
    assert result['solar'] == 2000 and result['estimated'] == {'solar': 'source_balance'}
    result = balance.update(live(battery_charge=None, battery_discharge=None, grid=200, solar=1000, house_total=700), T0)
    assert (result['battery_charge'], result['battery_discharge']) == (500, 0)
    # Two sources missing: the last values hold for a short time.
    result = balance.update(live(solar=None, grid=None, house_total=None), T0 + timedelta(seconds=60))
    assert result['estimated']['solar'] == 'source_hold' and result['complete'] is True
    result = balance.update(live(solar=None, grid=None, house_total=None), T0 + timedelta(seconds=400))
    assert result['complete'] is False and result['house_total'] is None


def test_negative_total_reduces_the_charge_and_missing_consumers_stay_in_the_house():
    result = ConsumptionBalance().update(live(grid=0, solar=1000, battery_charge=1500, house_total=0), T0)
    assert result['battery_charge'] == 1000 and result['house_total'] == 0
    assert result['estimated'] == {'battery_charge': 'battery_balance'}
    balance = ConsumptionBalance()
    balance.update(live(heat=800, grid=1300, house_total=1300), T0)
    held = balance.update(live(heat=None, grid=1300, house_total=1300), T0 + timedelta(seconds=60))
    assert held['consumers']['heat'] == 800 and held['estimated'] == {'heat': 'consumer_hold'}
    missing = balance.update(live(heat=None, grid=1300, house_total=1300), T0 + timedelta(seconds=300))
    assert missing['consumers'] == {'house': 1300, 'car': 0, 'heat': None}
    assert missing['estimated'] == {'house': 'unmeasured_in_house'}


def test_vehicle_split():
    assert split_vehicles(3000, {'a': 2000, 'b': 1000}, {}) == {'a': 2000, 'b': 1000}
    assert split_vehicles(3000, {'a': 0, 'b': 0}, {'a': 1000, 'b': 2000}) == {'a': 1000, 'b': 2000}
    assert split_vehicles(0, {'a': 0, 'b': None}, {}) == {'a': 0, 'b': 0}


def test_accounting_attributes_a_deviating_measured_total_without_unknown_share():
    from zoneinfo import ZoneInfo
    from custom_components.eos_energiezentrale.energy.accounting import Accounting
    from custom_components.eos_energiezentrale.energy.consumption import apply_balance
    from test_energy import temporary_project_directory

    def report(with_balance):
        with temporary_project_directory() as directory:
            ledger = Accounting(directory, ZoneInfo('Europe/Berlin'))
            ledger.configure({'pv_price_source': 'manual', 'efficiency_source': 'manual', 'capacity_wh': 10000,
                              'charge_efficiency': .9, 'discharge_efficiency': 1.})
            balance = ConsumptionBalance()
            for seconds in (0, 60):
                now = T0 + timedelta(seconds=seconds)
                # Issue #33: the meter doubles the discharge; heat pump and car are measured separately.
                row = {'time': now.isoformat(), 'solar': 0, 'grid': 1010, 'battery_charge': 0, 'battery_discharge': 510,
                       'battery_soc': 50, 'house_total': 2030, 'house': 1030, 'heat': 600, 'car': 400, 'price': 30}
                if with_balance:
                    apply_balance(row, balance.update(row, now))
                ledger.observe(row)
            return ledger.report({'period': 'day'}, T0)['consumers']

    measured = report(False)
    assert measured['house']['total']['sources']['unknown']['kwh'] > 0
    balanced = report(True)
    for key in ('house', 'heat', 'car'):
        assert balanced[key]['total']['sources']['unknown']['kwh'] == 0
    total = sum(balanced[key]['total']['kwh'] for key in ('house', 'heat', 'car'))
    # 1520 W supply for one minute; the house keeps 520 W after heat pump and car.
    assert abs(total - 1520 / 60000) < 1e-9
    assert abs(balanced['house']['total']['kwh'] - 520 / 60000) < 1e-9

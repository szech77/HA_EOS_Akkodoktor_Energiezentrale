"""Retrospective tariffs follow charging dates, energy shares and battery losses."""
from contextlib import closing
from copy import deepcopy
from datetime import datetime
import json
from zoneinfo import ZoneInfo

import pytest

from custom_components.eos_energiezentrale.energy.accounting import Accounting, empty, add
from custom_components.eos_energiezentrale.energy.grid_inventory import reprice_battery
from custom_components.eos_energiezentrale.energy.report_values import report_values
from test_energy import temporary_project_directory

ZONE = ZoneInfo('Europe/Berlin')


def tariff(day='', price=20):
    return {'valid_from': day, 'amount_eur': 0, 'period': 'month', 'grid_price_source': 'fixed', 'grid_price_ct': price}


def row(day, **changes):
    return {'time': datetime.fromisoformat(day).replace(tzinfo=ZONE).isoformat(), 'solar': 0, 'grid': 1000,
            'battery_charge': 1000, 'battery_discharge': 0, 'house_total': 0, 'consumers': {'house': 0},
            'price': 60, **changes}


def ledger_at(directory):
    ledger = Accounting(directory, ZONE)
    ledger.configure({'efficiency_source': 'manual', 'charge_efficiency': .8, 'discharge_efficiency': .8,
                      'pv_price_source': 'manual', 'pv_price_ct': 10})
    ledger.stock = {'kwh': 0., 'cost': 0., 'unknown': 0.}
    return ledger


def test_reprice_remaining_grid_stock_and_past_withdrawals_by_charging_date_preserving_pv():
    with temporary_project_directory() as directory:
        ledger = ledger_at(directory)
        ledger.configure({'base_price_history': [tariff('2026-11-01'), tariff('2026-11-02', 60)]})
        ledger.allocate(row('2026-11-01'), .001, ledger.effective())
        ledger.allocate(row('2026-11-02', solar=1000, battery_charge=2000), .001, ledger.effective())
        old = ledger.allocate(row('2026-11-03', grid=0, battery_charge=0, battery_discharge=960,
            house_total=960, consumers={'house': 960}), .001, ledger.effective())['house']
        assert old['cost_eur'] == pytest.approx(.45)
        before = deepcopy(ledger.stock)
        ledger.configure({'base_price_history': [tariff('2026-11-01', 40), tariff('2026-11-02', 10)]})
        assert ledger.stock['cost'] == pytest.approx(.3)
        assert ledger.stock['grid_cost'] == pytest.approx(.25)
        assert ledger.stock['pv_cost'] == before['pv_cost'] == pytest.approx(.05)
        for key in ('kwh', 'grid_kwh', 'pv_kwh', 'unknown'):
            assert ledger.stock[key] == before[key]
        reprice_battery(old, ledger.settings)
        assert old['cost_eur'] == pytest.approx(.3)
        assert old['sources']['battery']['grid_cost_eur'] == pytest.approx(.25)
        assert old['sources']['battery']['pv_cost_eur'] == pytest.approx(.05)
        assert old['kwh'] == pytest.approx(.96)
        assert old['estimated_kwh'] == 0
        again = deepcopy(old)
        reprice_battery(old, ledger.settings)
        assert old == again
        total = empty()
        add(total, old)
        add(total, old)
        assert total['sources']['battery']['grid_charges']['2026-11-01']['ac_kwh'] == pytest.approx(1.)
        assert total['cost_eur'] == pytest.approx(.6)
        assert Accounting(directory, ZONE).stock == ledger.stock


@pytest.mark.parametrize('original', [0, -10, 20])
def test_original_zero_and_negative_prices_do_not_affect_energy_based_repricing(original):
    with temporary_project_directory() as directory:
        ledger = ledger_at(directory)
        ledger.configure({'base_price_history': [tariff(price=original)]})
        ledger.allocate(row('2026-11-01'), .001, ledger.effective())
        ledger.configure({'base_price_history': [tariff(price=40)]})
        assert ledger.stock['cost'] == pytest.approx(.4)
        assert ledger.stock['grid_kwh'] == pytest.approx(.8)
        discharged = ledger.allocate(row('2026-11-02', grid=0, battery_charge=0, battery_discharge=640,
            house_total=640, consumers={'house': 640}), .001, ledger.effective())['house']
        assert discharged['cost_eur'] == pytest.approx(.4)
        assert ledger.stock['cost'] == pytest.approx(0.)
        assert ledger.stock['grid_lots'] == {}


def test_repricing_replaces_an_old_unknown_price_estimate_without_adding_it_twice():
    with temporary_project_directory() as directory:
        ledger = ledger_at(directory)
        ledger.allocate(row('2026-11-01', price=None), .001, ledger.effective())
        assert ledger.stock['cost'] == pytest.approx(.1)  # existing PV-based fallback estimate
        assert ledger.stock['grid_cost'] == pytest.approx(.1)
        ledger.configure({'base_price_history': [tariff(price=40)]})
        assert ledger.stock['cost'] == pytest.approx(.4)
        assert ledger.stock['grid_cost'] == pytest.approx(.4)
        assert ledger.stock['unknown'] == 0


def write_legacy(ledger, values):
    with closing(ledger.connect()) as db, db:
        for day, consumer, amount in values:
            stamp = int(datetime.fromisoformat(day).replace(tzinfo=ZONE).timestamp())
            db.execute('INSERT INTO energy VALUES (?,?,?,?)', (stamp, day, consumer, json.dumps(amount)))


def test_legacy_stock_and_consumption_reports_use_charge_day_with_estimate_marker_and_keep_ledger():
    with temporary_project_directory() as directory:
        ledger = ledger_at(directory)
        charged, used = empty(), empty()
        charged.update(kwh=2, cost_eur=.4)
        charged['sources']['grid'].update(kwh=2, cost_eur=.4)
        used.update(kwh=.8, cost_eur=.25)
        used['sources']['battery'].update(kwh=.8, cost_eur=.25, grid_kwh=.8, grid_cost_eur=.25)
        write_legacy(ledger, [('2026-11-01', 'storage', charged), ('2026-11-02', 'house', used)])
        ledger.stock = {'kwh': 1., 'cost': .19, 'unknown': 0., 'grid_kwh': .6, 'grid_cost': .15,
                        'pv_kwh': .4, 'pv_cost': .04}
        with closing(ledger.connect()) as db:
            before = db.execute('SELECT * FROM energy').fetchall()
        ledger.configure({'base_price_history': [tariff('2026-11-01', 40), tariff('2026-11-02', 99)]})
        assert ledger.stock['grid_cost'] == pytest.approx(.3)
        assert ledger.stock['cost'] == pytest.approx(.34)
        assert ledger.stock['pv_cost'] == .04
        assert ledger.stock['estimated'] >= .6
        stock = deepcopy(ledger.stock)
        for period in ('day', 'month', 'year'):
            report = report_values(ledger.report({'period': period, 'date': '2026-11-02'}, datetime(2026, 11, 22, tzinfo=ZONE)))
            amount = report['consumers']['house']['total']
            assert amount['cost_eur'] == pytest.approx(.5)  # .8 / .8 / .8 charged kWh × .40
            assert amount['sources']['battery']['grid_cost_eur'] == pytest.approx(.5)
            assert amount['estimated']
        assert ledger.stock == stock
        with closing(ledger.connect()) as db:
            assert db.execute('SELECT * FROM energy').fetchall() == before


def test_unknown_charging_date_is_not_replaced_by_a_later_tariff():
    with temporary_project_directory() as directory:
        ledger = ledger_at(directory)
        ledger.stock = {'kwh': .8, 'cost': .2, 'unknown': 0., 'grid_kwh': .8, 'grid_cost': .2}
        ledger.configure({'base_price_history': [tariff('2026-11-01', 40)]})
        assert ledger.stock['cost'] == pytest.approx(.2)
        assert ledger.stock['estimated'] == pytest.approx(.8)
        assert '' in ledger.stock['grid_lots']
        # An undated tariff explicitly covers even this untracked charging date.
        ledger.configure({'base_price_history': [tariff(price=40)]})
        assert ledger.stock['cost'] == pytest.approx(.4)


def test_soc_correction_scales_charging_cohorts_with_remaining_energy():
    with temporary_project_directory() as directory:
        ledger = ledger_at(directory)
        ledger.configure({'capacity_wh': 10000, 'base_price_history': [tariff(price=20)]})
        ledger.allocate(row('2026-11-01'), .001, ledger.effective())
        ledger.reconcile_stock({'battery_soc': 4}, ledger.effective())
        assert ledger.stock['grid_lots']['2026-11-01']['ac_kwh'] == pytest.approx(.5)
        ledger.configure({'base_price_history': [tariff(price=40)]})
        assert ledger.stock['cost'] == pytest.approx(.2)

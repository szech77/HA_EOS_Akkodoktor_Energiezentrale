"""Retrospective grid tariffs use local calendar days and preserve legacy fees."""
from datetime import datetime
from contextlib import closing
from zoneinfo import ZoneInfo

import pytest

from custom_components.eos_energiezentrale.energy.accounting import Accounting, checked_settings
from custom_components.eos_energiezentrale.energy.failures import BackendError
from custom_components.eos_energiezentrale.energy.report_values import report_values
from custom_components.eos_energiezentrale.energy.base_prices import fixed_grid_price, dynamic_price_required
from test_energy import temporary_project_directory


def tariff(start='', period='month', amount=18.25):
    return {'valid_from': start, 'period': period, 'amount_eur': amount}


def test_history_validates_sorts_and_keeps_legacy_value():
    rows = [tariff('2026-11-15', 'day', '.1234'), tariff()]
    settings = checked_settings({'base_price_eur_month': 99, 'base_price_history': rows})
    assert settings['base_price_history'] == [tariff(), tariff('2026-11-15', 'day', .1234)]
    assert rows[0]['amount_eur'] == '.1234'
    assert settings['base_price_eur_month'] == 99
    assert checked_settings({})['base_price_history'] is None


@pytest.mark.parametrize('history', [
    {}, 'bad', [None], [tariff(amount=True)], [tariff(amount=float('nan'))],
    [tariff(amount=float('inf'))], [tariff(amount=-1)], [tariff(amount=1001)],
    [tariff(period='year')], [tariff(period=[])], [tariff('2026-02-30')],
    [tariff('20261115')], [tariff('1999-12-31')], [tariff('2101-01-01')],
    [tariff(None)], [tariff(), tariff()], [tariff('2026-11-15'), tariff('2026-11-15')],
    [{**tariff(), 'other': 1}], [{'valid_from': ''}], [tariff()] * 129,
])
def test_invalid_history_has_safe_field_error(history):
    with pytest.raises(BackendError) as caught:
        checked_settings({'base_price_history': history})
    assert caught.value.fields == ['base_price_history']


def test_legacy_migration_retrospective_changes_and_restart():
    zone = ZoneInfo('Europe/Berlin')
    now = datetime(2026, 11, 30, 12, tzinfo=zone)
    with temporary_project_directory() as directory:
        ledger = Accounting(directory, zone)
        ledger.started = datetime(2026, 11, 10, 23, tzinfo=zone).isoformat()
        ledger.configure({'base_price_eur_month': 18.25})
        before = report_values(ledger.report({'period': 'month'}, now))['balance']
        assert before['base_days'] == 21
        assert before['base_eur'] == pytest.approx(12.6)
        ledger.configure({'base_price_history': [tariff('2026-12-01', 'day', 5), tariff(),
                                                tariff('2026-11-15', 'day', .1234)]})
        result = report_values(ledger.report({'period': 'month'}, now))['balance']
        assert result['base_eur'] == pytest.approx(5 * .6 + 16 * .1234)
        assert [(row['start'], row['end'], row['days']) for row in result['base_segments']] == [
            ('2026-11-10', '2026-11-14', 5), ('2026-11-15', '2026-11-30', 16)]
        assert result['net_eur'] == result['total_cost_eur'] == result['grid_balance_eur'] == result['base_eur']
        restored = Accounting(directory, zone)
        assert restored.settings == ledger.settings
        restored.started = ledger.started
        assert report_values(restored.report({'period': 'month'}, now))['balance'] == result
        # Removing all entries is explicit zero; the retained monthly value cannot reappear.
        restored.configure({'base_price_history': []})
        assert report_values(restored.report({'period': 'month'}, now))['balance']['base_eur'] == 0


@pytest.mark.parametrize('selected,period,expected_days', [
    ('2024-02-01', 'month', 29), ('2024-01-01', 'year', 366),
    ('2026-03-29', 'day', 1), ('2026-10-25', 'day', 1),
])
def test_calendar_day_fee_includes_leap_day_and_dst(selected, period, expected_days):
    with temporary_project_directory() as directory:
        ledger = Accounting(directory, ZoneInfo('Europe/Berlin'))
        ledger.configure({'base_price_history': [tariff('', 'day', .123456789)]})
        report = ledger.report({'period': period, 'date': selected}, datetime(2026, 12, 31, tzinfo=ledger.zone))
        balance = report_values(report)['balance']
        assert balance['base_days'] == expected_days
        assert balance['base_eur'] == pytest.approx(expected_days * .123456789, rel=1e-12, abs=1e-12)


def test_no_fee_before_first_entry_and_future_reports_or_partial_months():
    with temporary_project_directory() as directory:
        ledger = Accounting(directory, ZoneInfo('Europe/Berlin'))
        ledger.configure({'base_price_eur_month': 100, 'base_price_history': [tariff('2026-11-15', 'day', .5)]})
        now = datetime(2026, 11, 18, 1, tzinfo=ledger.zone)
        for selected, period, expected in [('2026-11-14', 'day', 0), ('2026-11-15', 'day', .5),
                                           ('2026-11-01', 'month', 2), ('2026-12-01', 'month', 0)]:
            balance = report_values(ledger.report({'date': selected, 'period': period}, now))['balance']
            assert balance['base_eur'] == expected


def test_multiple_monthly_and_daily_changes_in_one_year():
    raw = {'date': '2024-01-01', 'base_start': '2024-01-01', 'base_days': 366, 'consumers': {},
           'settings': {'base_price_eur_month': 999, 'base_price_history': [
               tariff('2024-01-01', 'month', 36.5), tariff('2024-02-01', 'day', .1234),
               tariff('2024-03-01', 'month', 18.25)]}}
    result = report_values(raw)
    assert result['balance']['base_eur'] == pytest.approx(31 * 1.2 + 29 * .1234 + 306 * .6)
    assert report_values(result) == result


def fixed(start='', price=25):
    return {**tariff(start), 'grid_price_source': 'fixed', 'grid_price_ct': price}


@pytest.mark.parametrize('extra', [
    {'grid_price_source': 'other'}, {'grid_price_source': []},
    {'grid_price_source': 'fixed'}, {'grid_price_source': 'fixed', 'grid_price_ct': None},
    *({'grid_price_source': 'fixed', 'grid_price_ct': value} for value in [True, float('nan'), float('inf'), -1001, 1001, {}]),
    {'grid_price_source': 'dynamic', 'grid_price_ct': 'bad'},
])
def test_invalid_fixed_tariffs_have_safe_field_errors(extra):
    with pytest.raises(BackendError) as caught:
        checked_settings({'base_price_history': [{**tariff(), **extra}]})
    assert caught.value.fields == ['base_price_history']


def test_fixed_prices_and_sensor_fallback_follow_local_dates():
    settings = checked_settings({'base_price_history': [fixed('2026-11-15', '25.1234'),
        tariff('2026-12-01'), fixed('2027-01-01', 0), fixed('2027-02-01', -5)]})
    assert fixed_grid_price(settings, '2026-11-14') is None
    assert fixed_grid_price(settings, '2026-11-15') == 25.1234
    assert fixed_grid_price(settings, '2026-12-01') is None
    assert fixed_grid_price(settings, '2027-01-01') == 0
    assert fixed_grid_price(settings, '2027-02-01') == -5
    assert not dynamic_price_required(settings, '2026-11-15', '2026-12-01')
    assert dynamic_price_required(settings, '2026-11-14', '2026-12-01')
    assert dynamic_price_required(settings, '2026-11-15', '2026-12-02')


def grid_sample(stamp, **values):
    return {'time': stamp.isoformat(), 'solar': 0, 'grid': 1000, 'house_total': 1000, 'house': 1000,
            'heat': 0, 'car': 0, 'battery_charge': 0, 'battery_discharge': 0,
            'price': 99, 'consumers': {'house': 1000}, **values}


@pytest.mark.parametrize('price', [25.1234, 0, -5])
def test_fixed_price_needs_no_sensor_and_does_not_mark_measured_energy_estimated(price):
    from datetime import timedelta
    zone = ZoneInfo('Europe/Berlin')
    start = datetime(2026, 11, 18, 12, tzinfo=zone)
    with temporary_project_directory() as directory:
        ledger = Accounting(directory, zone)
        ledger.configure({'efficiency_source': 'manual', 'base_price_history': [fixed(price=price)]})
        ledger.observe(grid_sample(start, price=None))
        ledger.observe(grid_sample(start+timedelta(minutes=1), price=None))
        raw = ledger.report({'period': 'day'}, start)
        value = report_values(raw)['consumers']['house']['total']
        assert value['kwh'] == pytest.approx(1/60)
        assert value['cost_eur'] == pytest.approx(1/60 * price / 100)
        assert value['cost_unknown_kwh'] == value['estimated_kwh'] == 0
        assert Accounting(directory, zone).settings['base_price_history'] == [fixed(price=price)]


def test_report_reprices_grid_charging_and_estimates_legacy_battery_costs_without_changing_feed_in():
    import json
    from custom_components.eos_energiezentrale.energy.accounting import empty
    zone = ZoneInfo('Europe/Berlin')
    start = datetime(2026, 11, 18, 12, tzinfo=zone)
    with temporary_project_directory() as directory:
        ledger = Accounting(directory, zone)
        ledger.configure({'base_price_history': [fixed(price=25)], 'pv_price_source': 'manual', 'pv_price_ct': 10})
        used, stored, exported = empty(), empty(), empty()
        used.update(kwh=2, cost_eur=1.19)
        used['sources']['grid'].update(kwh=1, cost_eur=.99)
        used['sources']['battery'].update(kwh=1, cost_eur=.2, grid_kwh=1, grid_cost_eur=.2)
        stored.update(kwh=1, cost_eur=.99)
        stored['sources']['grid'].update(kwh=1, cost_eur=.99)
        exported.update(kwh=1, cost_eur=.1)
        exported['sources']['pv'].update(kwh=1, cost_eur=.1)
        with closing(ledger.connect()) as db, db:
            for consumer, amount in [('house', used), ('storage', stored), ('export', exported)]:
                db.execute('INSERT INTO energy VALUES (?,?,?,?)', (int(start.timestamp()), '2026-11-18', consumer, json.dumps(amount)))
        report = report_values(ledger.report({'period': 'day'}, start))
        assert report['consumers']['house']['total']['cost_eur'] == pytest.approx(.25 + .25 / .95**2)
        assert report['consumers']['house']['total']['sources']['battery']['grid_cost_eur'] == pytest.approx(.25 / .95**2)
        assert report['consumers']['house']['total']['estimated']
        assert report['consumers']['storage']['total']['cost_eur'] == .25
        assert report['balance']['export_eur'] == .1
        assert report['balance']['grid_import_cost_eur'] == .5


def test_live_intervals_split_at_tariff_midnight_without_carrying_fixed_prices_to_dynamic():
    from datetime import timedelta
    zone = ZoneInfo('Europe/Berlin')
    start = datetime(2026, 11, 14, 23, 59, tzinfo=zone)
    with temporary_project_directory() as directory:
        ledger = Accounting(directory, zone)
        ledger.configure({'efficiency_source': 'manual', 'base_price_history': [fixed(price=10), fixed('2026-11-15', 30), tariff('2026-11-16')]})
        ledger.observe(grid_sample(start))
        ledger.observe(grid_sample(start+timedelta(minutes=2)))
        for day, price in [('2026-11-14', .1), ('2026-11-15', .3)]:
            value = ledger.report({'period': 'day', 'date': day}, start+timedelta(minutes=2))['consumers']['house']['total']
            assert value['kwh'] == pytest.approx(1/60)
            assert value['cost_eur'] == pytest.approx(price/60)
        assert ledger.grid_price(grid_sample(datetime(2026, 11, 16, tzinfo=zone))) == 99


def test_grid_battery_charges_keep_the_charging_tariff_and_losses_after_a_change():
    zone = ZoneInfo('Europe/Berlin')
    with temporary_project_directory() as directory:
        ledger = Accounting(directory, zone)
        ledger.configure({'efficiency_source': 'manual', 'charge_efficiency': .8, 'discharge_efficiency': .8,
                          'base_price_history': [fixed(price=25), fixed('2026-11-19', 40)]})
        ledger.stock = {'kwh': 0., 'cost': 0., 'unknown': 0.}
        ledger.allocate(grid_sample(datetime(2026, 11, 18, tzinfo=zone), house_total=0,
                                   consumers={'house': 0}, battery_charge=1000), .001, ledger.effective())
        assert ledger.stock['kwh'] == pytest.approx(.8)
        assert ledger.stock['cost'] == pytest.approx(.25)
        value = ledger.allocate(grid_sample(datetime(2026, 11, 19, tzinfo=zone), grid=0,
            house_total=640, battery_discharge=640, consumers={'house': 640}), .001, ledger.effective())['house']
        assert value['kwh'] == pytest.approx(.64)
        assert value['cost_eur'] == pytest.approx(.25)
        assert value['sources']['battery']['grid_cost_eur'] == pytest.approx(.25)


def test_retrospective_fixed_price_revalues_grid_reports_without_changing_ledger_stock_or_feed_in():
    from datetime import timedelta
    zone = ZoneInfo('Europe/Berlin')
    start = datetime(2026, 11, 18, 12, tzinfo=zone)
    with temporary_project_directory() as directory:
        ledger = Accounting(directory, zone)
        ledger.configure({'efficiency_source': 'manual'})
        ledger.observe(grid_sample(start, price=None))
        ledger.observe(grid_sample(start+timedelta(minutes=1), price=None))
        from copy import deepcopy
        with closing(ledger.connect()) as db:
            rows = db.execute('SELECT * FROM energy').fetchall()
        stock = deepcopy(ledger.stock)
        ledger.configure({'base_price_history': [fixed(price=25)]})
        for period in ('day', 'month', 'year'):
            report = report_values(ledger.report({'period': period}, start))
            assert report['consumers']['house']['total']['cost_unknown_kwh'] == 0
            assert report['consumers']['house']['total']['cost_eur'] == pytest.approx(.25/60)
            assert report['balance']['grid_import_price_ct'] == 25
        assert ledger.stock == stock
        with closing(ledger.connect()) as db:
            assert db.execute('SELECT * FROM energy').fetchall() == rows
        ledger.configure({'base_price_history': [tariff()]})
        assert ledger.report({'period': 'day'}, start)['consumers']['house']['total']['cost_unknown_kwh'] > 0


def test_influx_fixed_price_reconstruction_does_not_query_an_unused_price_sensor():
    from types import SimpleNamespace
    from datetime import timedelta
    from unittest.mock import Mock
    from custom_components.eos_energiezentrale.energy.accounting_history import reconstruct
    zone = ZoneInfo('Europe/Berlin')
    start = datetime(2026, 11, 18, tzinfo=zone)
    with temporary_project_directory() as directory:
        ledger = Accounting(directory, zone)
        ledger.configure({'efficiency_source': 'manual', 'base_price_history': [fixed(price=25)]})
        config = SimpleNamespace(zone=zone, options={'pv_entity': 'pv', 'house_entity': 'house', 'grid_entity': 'grid',
            'heat_entity': '', 'price_entity': 'price', 'wallbox_type': 'none'},
            battery=SimpleNamespace(ids={'charge_power': 'charge', 'discharge_power': 'discharge'}),
            wallbox=SimpleNamespace(ids={}), influx=Mock(url='http://influx:8086'))
        def read(entity, *args, **kwargs):
            assert entity != 'price'
            return [(start.isoformat(), {'pv': 0, 'house': 1000, 'grid': 1000, 'charge': 0, 'discharge': 0}[entity])]
        config.influx.history.side_effect = read
        raw = ledger.report({'period': 'day'}, start)
        value = reconstruct(config, raw, start+timedelta(minutes=5))['house']['total']
        assert value['kwh'] == pytest.approx(1/12)
        assert value['cost_eur'] == pytest.approx(.25/12)
        assert value['cost_unknown_kwh'] == 0

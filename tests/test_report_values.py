"""Combined consumption reports preserve cost provenance and calendar bins."""
from copy import deepcopy

import pytest

from custom_components.eos_energiezentrale.energy.accounting import empty
from custom_components.eos_energiezentrale.energy.report_values import report_values


def amount(kwh, cost, unknown=0, source='grid', estimated=0):
    value = empty()
    value.update(kwh=kwh, cost_eur=cost, cost_unknown_kwh=unknown,
                 estimated_kwh=estimated, seconds=3600, estimated_seconds=1800 if estimated else 0)
    value['sources'][source].update(kwh=kwh, cost_eur=cost,
                                     cost_unknown_kwh=unknown, estimated_kwh=estimated)
    return value


@pytest.mark.parametrize('period,stamps', [
    ('day', ['2026-10-25T00:00:00+00:00', '2026-10-25T01:00:00+00:00']),
    ('month', ['2026-11-01', '2026-11-03']),
    ('year', ['2026-01', '2026-03']),
])
def test_combined_report_counts_aggregate_car_once_and_preserves_bins(period, stamps):
    values = {'house': amount(1, -.1, source='pv'), 'heat': amount(2, .6),
              'car': amount(3, .4, unknown=1, source='battery', estimated=2),
              'car/one': amount(1, .1), 'car/two': amount(2, .3)}
    raw = {'period': period, 'consumers': {
        key: {'total': value, 'bins': [{'time': stamps[0], **value}]}
        for key, value in values.items()}}
    # Different consumers may have data in different bins; gaps stay open.
    raw['consumers']['heat']['bins'][0]['time'] = stamps[1]
    before = deepcopy(raw)
    result = report_values(raw)
    total = result['total']['total']
    assert total == result['overview']['total']
    assert total['kwh'] == 6
    assert total['cost_eur'] == pytest.approx(.9)
    assert total['average_price_ct'] == pytest.approx(18)  # .9 EUR / 5 priced kWh
    assert total['cost_partial'] and total['estimated']
    assert total['cost_unknown_kwh'] == 1 and total['estimated_kwh'] == 2
    assert total['seconds'] == 7200 and total['estimated_seconds'] == 1800
    assert total['sources']['pv']['share_percent'] == pytest.approx(100 / 6)
    assert total['sources']['pv']['cost_eur'] == -.1
    assert [row['time'] for row in result['total']['bins']] == stamps
    assert [row['kwh'] for row in result['total']['bins']] == [4, 2]
    assert result['total']['bins'][0]['seconds'] == 3600
    assert result['total']['bins'][0]['cost_unknown_kwh'] == 1
    assert raw == before
    assert report_values(result) == result


def test_combined_report_respects_enabled_consumers_and_existing_records():
    raw = {'consumers': {'house': {'total': amount(1, .3), 'bins': []},
                         'heat': {'total': amount(2, .6), 'bins': []},
                         'car': {'total': amount(3, .9), 'bins': []}}}
    result = report_values(raw, ['house'])
    assert result['total']['total']['kwh'] == 1
    assert result['total']['total']['cost_eur'] == .3
    assert result['total']['bins'] == []
    assert set(result['overview']['consumers']) == {'house'}


def test_combined_report_keeps_unpriced_consumption_unknown_and_empty_periods_empty():
    raw = {'consumers': {'house': {'total': amount(2, 0, unknown=2), 'bins': []}}}
    value = report_values(raw)['total']['total']
    assert not value['cost_available'] and value['average_price_ct'] is None
    assert value['cost_unknown_kwh'] == 2
    result = report_values({'consumers': {}})['total']
    assert result['total']['kwh'] == 0
    assert result['total']['average_price_ct'] is None
    assert result['bins'] == []


def test_balance_combines_consumers_feed_in_storage_and_base_price_without_double_counting():
    from custom_components.eos_energiezentrale.energy.accounting import empty
    from custom_components.eos_energiezentrale.energy.report_values import report_values

    def amount(**sources):
        result = empty()
        for key, (kwh, cost, unknown) in sources.items():
            result['sources'][key].update(kwh=kwh, cost_eur=cost, cost_unknown_kwh=unknown)
            result['kwh'] += kwh; result['cost_eur'] += cost; result['cost_unknown_kwh'] += unknown
        return result
    house = amount(pv=(4, .32, 0), battery=(2, .30, 0), grid=(4, 1.20, 0))
    heat = amount(grid=(2, .60, 0))
    export = amount(pv=(5, .40, 0))
    storage = amount(pv=(1, .08, 0), grid=(2, .60, 0))
    report = {'period':'day', 'date':'2026-11-18', 'base_days':30, 'settings':{'base_price_eur_month':18.25},
              'consumers':{'house':{'total':house, 'bins':[{'time':'h1', **house}]},
                           'heat':{'total':heat, 'bins':[{'time':'h1', **heat}]},
                           'export':{'total':export, 'bins':[{'time':'h1', **export}]},
                           'storage':{'total':storage, 'bins':[]}}}
    balance = report_values(report, ['house', 'heat'])['balance']
    assert balance['consumption_kwh'] == pytest.approx(12)
    assert balance['self_kwh'] == pytest.approx(6) and balance['autarky_percent'] == pytest.approx(50)
    assert balance['grid_kwh'] == pytest.approx(6) and balance['grid_import_kwh'] == pytest.approx(8)
    assert balance['grid_price_ct'] == pytest.approx(30)
    assert balance['pv_kwh'] == pytest.approx(10) and balance['self_consumption_percent'] == pytest.approx(50)
    assert balance['export_eur'] == pytest.approx(.40) and balance['feed_in_price_ct'] == pytest.approx(8)
    assert balance['base_eur'] == pytest.approx(18.25 * 12 / 365 * 30)
    # Storage grid charging is already part of the battery book price, so it adds kWh but no cost.
    assert balance['cost_eur'] == pytest.approx(2.42)
    assert balance['net_eur'] == pytest.approx(2.42 + balance['base_eur'] - .40)
    assert balance['savings_eur'] == pytest.approx(6 * .30 - .62)
    assert balance['bins'] == [{'time':'h1', 'consumption_kwh':12, 'export_kwh':5, 'storage_kwh':0., 'grid_import_kwh':6}]
    assert not balance['cost_partial']
    empty_balance = report_values({'consumers':{}}, ['house'])['balance']
    assert empty_balance['autarky_percent'] is None and empty_balance['grid_price_ct'] is None and empty_balance['net_eur'] == 0


def _sources(**sources):
    result = empty()
    for key, (kwh, cost) in sources.items():
        result['sources'][key].update(kwh=kwh, cost_eur=cost, cost_unknown_kwh=0)
        result['kwh'] += kwh
        result['cost_eur'] += cost
    return result


def test_report_views_supply_key_figures_prices_and_notable_bins_per_page():
    sunny, evening = _sources(pv=(3, .24), grid=(1, .30)), _sources(grid=(4, 1.20))
    house = _sources(pv=(3, .24), grid=(5, 1.50))
    export, storage = _sources(pv=(2, .16)), _sources(pv=(1, .08), grid=(1, .30))
    report = {'period':'month', 'base_days':10, 'settings':{'base_price_eur_month':36.5},
              'consumers':{'house':{'total':house, 'bins':[{'time':'2026-11-01', **sunny}, {'time':'2026-11-02', **evening}]},
                           'car':{'total':empty(), 'bins':[]},
                           'export':{'total':export, 'bins':[{'time':'2026-11-01', **export}]},
                           'storage':{'total':storage, 'bins':[{'time':'2026-11-02', **storage}]}}}
    result = report_values(report, ['house', 'car'])
    balance, views = result['balance'], result['views']
    house_view = views['house']
    assert house_view['kwh'] == 8 and house_view['self_percent'] == pytest.approx(37.5)
    assert house_view['grid_price_ct'] == pytest.approx(30) and house_view['self_price_ct'] == pytest.approx(8)
    # Self-supplied energy compared with the period's grid price.
    assert house_view['savings_eur'] == pytest.approx(3 * .30 - .24)
    assert house_view['per_day_kwh'] == pytest.approx(.8) and house_view['per_day_eur'] == pytest.approx(.174)
    facts = {fact['id']: fact for fact in house_view['facts']}
    assert facts['best'] == {'id':'best', 'time':'2026-11-01', 'unit':'day', 'percent':pytest.approx(75)}
    assert facts['max_grid'] == {'id':'max_grid', 'time':'2026-11-02', 'unit':'day', 'kwh':pytest.approx(4)}
    assert facts['savings']['grid_price_ct'] == pytest.approx(30) and 'charge_days' not in facts
    assert views['car']['facts'] == [{'id':'no_charging'}]
    # Grid-charged battery energy counts for the grid balance, not again for consumers.
    assert balance['grid_import_kwh'] == 6 and balance['grid_import_cost_eur'] == pytest.approx(1.80)
    assert balance['grid_import_price_ct'] == pytest.approx(30) and balance['storage_grid_kwh'] == 1
    assert balance['base_eur'] == pytest.approx(12) and balance['total_cost_eur'] == pytest.approx(1.74 + 12)
    assert balance['grid_balance_eur'] == pytest.approx(1.80 + 12 - .16)
    assert balance['pv_use']['direct'] == {'kwh':3, 'share_percent':pytest.approx(50)}
    assert balance['pv_use']['export']['kwh'] == 2 and balance['pv_export_kwh'] == 2
    grid = {fact['id']: fact for fact in views['grid']['facts']}
    assert grid['max_export'] == {'id':'max_export', 'time':'2026-11-01', 'unit':'day', 'kwh':2, 'eur':pytest.approx(.16)}
    assert grid['max_import']['time'] == '2026-11-02' and grid['max_import']['kwh'] == 5
    assert grid['grid_per_day'] == {'id':'grid_per_day', 'export_kwh':pytest.approx(.2), 'import_kwh':pytest.approx(.6)}
    total = views['total']
    assert [fact['id'] for fact in total['facts']] == ['consumer', 'consumer', 'export']
    assert total['facts'][0] == {'id':'consumer', 'key':'house', 'kwh':8, 'self_percent':pytest.approx(37.5),
                                 'cost_eur':pytest.approx(1.74), 'cost_available':True}
    assert 'export' not in views and 'storage' not in views


def test_report_view_facts_cover_car_charging_days_and_empty_grid_exchange():
    days = [{'time':f'2026-11-0{index}', **_sources(pv=(kwh, 0), grid=(0, 0))} for index, kwh in ((1, 5), (2, .01), (3, 4))]
    car = _sources(pv=(9.01, 0))
    report = {'period':'month', 'base_days':3, 'consumers':{'car':{'total':car, 'bins':days}}}
    views = report_values(report, ['car'])['views']
    facts = {fact['id']: fact for fact in views['car']['facts']}
    assert facts['charge_days'] == {'id':'charge_days', 'count':2, 'days':3}
    assert 'max_grid' not in facts and 'savings' not in facts
    assert views['grid']['facts'] == [{'id':'no_exchange'}]
    day = report_values({'period':'day', 'consumers':{'house':{'total':_sources(grid=(1, .3)), 'bins':[]}}}, ['house'])['views']
    assert day['house']['per_day_kwh'] is None and day['house']['facts'] == [{'id':'no_consumption'}]

"""Unknown source estimates preserve consumption, known costs and stored history."""
from contextlib import closing
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import json
from zoneinfo import ZoneInfo

import pytest

from custom_components.eos_energiezentrale.energy.accounting import Accounting, empty
from custom_components.eos_energiezentrale.energy.source_estimates import estimate_sources

START = datetime(2026, 11, 18, tzinfo=timezone.utc)


def amount(hour, source, kwh=1., cost=.3):
    row = {'time': (START + timedelta(hours=hour)).isoformat(), **empty()}
    unknown = kwh if source == 'unknown' else 0.
    row.update(kwh=kwh, cost_eur=cost if not unknown else 0., cost_unknown_kwh=unknown, seconds=3600.)
    row['sources'][source].update(kwh=kwh, cost_eur=row['cost_eur'], cost_unknown_kwh=unknown)
    return row


def test_interpolates_only_unknown_share_with_costs_and_battery_origin():
    left = amount(0, 'battery', cost=.2)
    left['sources']['battery'].update(pv_kwh=.6, pv_cost_eur=.12, grid_kwh=.4, grid_cost_eur=.08)
    middle = amount(1, 'unknown', kwh=2.)
    # One already attributed kWh must retain its actual cost.
    middle['kwh'] += 1.
    middle['cost_eur'] = .7
    middle['sources']['grid'].update(kwh=1., cost_eur=.7)
    rows = [left, middle, amount(4, 'grid', cost=.4)]
    estimate_sources(rows)
    assert middle['kwh'] == 3.
    assert middle['sources']['unknown']['kwh'] == 0.
    assert middle['sources']['battery']['kwh'] == pytest.approx(1.5)
    assert middle['sources']['battery']['pv_kwh'] == pytest.approx(.9)
    assert middle['sources']['battery']['grid_kwh'] == pytest.approx(.6)
    assert middle['sources']['grid']['kwh'] == pytest.approx(1.5)
    assert middle['cost_eur'] == pytest.approx(1.2)
    assert middle['estimated_kwh'] == 2.
    assert middle['seconds'] == 3600.


def test_missing_donor_prices_stay_unpriced_and_estimates_are_not_reused_as_anchors():
    rows = [amount(0, 'pv'), amount(1, 'unknown'), amount(2, 'unknown'), amount(4, 'grid')]
    rows[0].update(cost_eur=0., cost_unknown_kwh=1.)
    rows[0]['sources']['pv'].update(cost_eur=0., cost_unknown_kwh=1.)
    estimate_sources(rows)
    assert rows[1]['sources']['pv']['kwh'] == pytest.approx(.75)
    assert rows[2]['sources']['pv']['kwh'] == pytest.approx(.5)
    assert rows[1]['cost_unknown_kwh'] == pytest.approx(.75)
    assert rows[1]['cost_eur'] == pytest.approx(.075)


@pytest.mark.parametrize('hours', [(0, 1), (0, 1, 7)])
def test_unbounded_or_long_unknown_runs_remain_unknown(hours):
    rows = [amount(hour, 'unknown' if hour == 1 else 'grid') for hour in hours]
    original = deepcopy(rows)
    estimate_sources(rows)
    assert rows == original


def test_previously_estimated_unknown_energy_is_not_double_counted():
    rows = [amount(0, 'grid'), amount(1, 'unknown'), amount(2, 'grid')]
    rows[1]['estimated_kwh'] = 1.
    rows[1]['sources']['unknown']['estimated_kwh'] = 1.
    estimate_sources(rows)
    assert rows[1]['estimated_kwh'] == 1.
    assert rows[1]['sources']['grid']['estimated_kwh'] == 1.


def test_report_repairs_hourly_before_period_aggregation_without_changing_ledger_or_stock(tmp_path):
    ledger = Accounting(tmp_path, ZoneInfo('Europe/Berlin'))
    ledger.stock = {'kwh': 5., 'cost': 1., 'unknown': 0.}
    stock = deepcopy(ledger.stock)
    # A donor from the previous day must also work in a day report.
    records = [amount(-2, 'pv', cost=.1), amount(-1, 'unknown'), amount(0, 'grid', cost=.3)]
    with closing(ledger.connect()) as db, db:
        for row in records:
            stamp = datetime.fromisoformat(row['time'])
            for consumer in ('house', 'storage', 'export'):
                db.execute('INSERT INTO energy VALUES (?,?,?,?)',
                           (int(stamp.timestamp()), stamp.astimezone(ledger.zone).date().isoformat(), consumer, json.dumps(row)))
    for period in ('day', 'month', 'year'):
        report = ledger.report({'period': period, 'date': '2026-11-18'}, START)
        house = report['consumers']['house']
        assert house['total']['sources']['unknown']['kwh'] == 0.
        assert house['total']['estimated_kwh'] == 1.
        assert house['total']['cost_eur'] == pytest.approx(.5 if period == 'day' else .6)
        assert house['total']['kwh'] == (2. if period == 'day' else 3.)
        assert report['consumers']['storage']['total']['sources']['unknown']['kwh'] == 1.
        assert report['consumers']['export']['total']['sources']['unknown']['kwh'] == 1.
    assert ledger.stock == stock
    with closing(ledger.connect()) as db:
        stored = json.loads(db.execute("SELECT payload FROM energy WHERE consumer='house' ORDER BY hour LIMIT 1 OFFSET 1").fetchone()[0])
    assert stored == records[1]


def test_report_does_not_borrow_another_consumers_sources(tmp_path):
    ledger = Accounting(tmp_path, ZoneInfo('UTC'))
    with closing(ledger.connect()) as db, db:
        for hour, consumer, source in ((0, 'car', 'pv'), (1, 'house', 'unknown'), (2, 'car', 'grid')):
            row = amount(hour, source)
            db.execute('INSERT INTO energy VALUES (?,?,?,?)',
                       (int(datetime.fromisoformat(row['time']).timestamp()), '2026-11-18', consumer, json.dumps(row)))
    result = ledger.report({'period': 'day', 'date': '2026-11-18'}, START)
    assert result['consumers']['house']['total']['sources']['unknown']['kwh'] == 1.


def test_report_keeps_midnight_fragments_in_zones_with_fractional_hours(tmp_path):
    ledger = Accounting(tmp_path, ZoneInfo('Asia/Kathmandu'))
    # Local midnight is 18:15 UTC; both days have part of the same UTC hour.
    stamp = datetime(2026, 11, 17, 18, tzinfo=timezone.utc)
    with closing(ledger.connect()) as db, db:
        for day, kwh in (('2026-11-17', .25), ('2026-11-18', .75)):
            db.execute('INSERT INTO energy VALUES (?,?,?,?)',
                       (int(stamp.timestamp()), day, 'house', json.dumps(amount(0, 'grid', kwh=kwh))))
    for day, kwh in (('2026-11-17', .25), ('2026-11-18', .75)):
        result = ledger.report({'period': 'day', 'date': day}, START)
        assert result['consumers']['house']['total']['kwh'] == kwh


def test_six_hour_limit_is_inclusive_and_negative_prices_remain_valid():
    rows = [amount(0, 'grid', cost=-.2), amount(3, 'unknown'), amount(6, 'grid', cost=0.)]
    estimate_sources(rows)
    assert rows[1]['sources']['grid']['kwh'] == 1.
    assert rows[1]['cost_eur'] == pytest.approx(-.1)
    assert rows[1]['cost_unknown_kwh'] == 0.

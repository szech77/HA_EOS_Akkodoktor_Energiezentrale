"""The day report's power profile splits minute samples onto sources like the accounting."""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.eos_energiezentrale.energy.history import History
from custom_components.eos_energiezentrale.energy.power_profile import day_bounds, power_profile

ZONE = 'Europe/Berlin'
# 2026-11-18 00:00 local time (UTC+1).
START = datetime(2026, 11, 17, 23, tzinfo=timezone.utc)


def sample(minute, *, solar, grid, discharge=0, charge=0, house=None, heat=0, car=0, balance=True):
    total = solar + grid + discharge - charge if house is None else house
    values = {'solar': solar, 'grid': grid, 'battery_discharge': discharge, 'battery_charge': charge,
              'house_total': total, 'consumers': {'house': total - heat - car, 'heat': heat, 'car': car}}
    row = {'time': (START + timedelta(minutes=minute)).isoformat()}
    if balance:
        row['balance'] = values
    else:
        row.update({key: value for key, value in values.items() if key != 'consumers'},
                   house=total - heat - car, heat=heat, car=car)
    return row


def test_samples_are_split_onto_sources_and_averaged_per_two_minutes():
    samples = [sample(0, solar=3000, grid=1000, heat=1000), sample(1, solar=1000, grid=1000, discharge=2000, heat=1000)]
    profile = power_profile(samples, '2026-11-18', ZONE)
    assert profile['step_s'] == 120 and len(profile['points']) == 1
    point = profile['points'][0]
    assert point['time'] == START.isoformat()
    # Minute 1: 3000 PV / 1000 grid of 4000; minute 2: 1000 PV / 1000 grid / 2000 battery of 4000.
    assert point['total'] == {'pv': 2000, 'battery': 1000, 'grid': 1000, 'unknown': 0}
    assert point['heat'] == {'pv': 500, 'battery': 250, 'grid': 250, 'unknown': 0}
    assert point['house'] == {'pv': 1500, 'battery': 750, 'grid': 750, 'unknown': 0}
    assert point['grid'] == {'import': 1000, 'export': 0}


def test_unbalanced_samples_are_unknown_and_feed_in_is_reported_separately():
    samples = [sample(10, solar=5000, grid=-2000, house=3000), sample(20, solar=0, grid=500, house=3000),
               sample(30, solar=0, grid=None, house=900, balance=False)]
    points = power_profile(samples, '2026-11-18', ZONE)['points']
    assert points[0]['total'] == {'pv': 3000, 'battery': 0, 'grid': 0, 'unknown': 0}
    assert points[0]['grid'] == {'import': 0, 'export': 2000}
    # 500 W import cannot supply 3000 W: the balance does not close, so the power is unknown.
    assert points[1]['total'] == {'pv': 0, 'battery': 0, 'grid': 0, 'unknown': 3000}
    # Raw live fields without a balance still count; a missing grid reading leaves the source unknown.
    assert points[2]['total']['unknown'] == 900 and points[2]['grid'] is None


def test_only_the_local_day_counts_and_daylight_saving_days_keep_their_length():
    samples = [sample(-1, solar=100, grid=0), sample(24 * 60, solar=100, grid=0), sample(5, solar=100, grid=0)]
    assert [point['time'] for point in power_profile(samples, '2026-11-18', ZONE)['points']] == \
        [(START + timedelta(minutes=4)).isoformat()]
    start, end = day_bounds('2026-10-25', ZONE)
    assert (end - start).total_seconds() == 25 * 3600
    assert power_profile([], '2026-11-18', ZONE)['points'] == []


def test_history_reads_one_range_for_the_profile(tmp_path):
    history = History(tmp_path / 'history.sqlite3')
    for minute in (0, 1, 70):
        history.write(START + timedelta(minutes=minute), sample(minute, solar=100, grid=0))
    rows = history.read_range(START, START + timedelta(hours=1))
    assert [row['time'] for row in rows] == [(START + timedelta(minutes=minute)).isoformat() for minute in (0, 1)]
    assert power_profile(rows, '2026-11-18', ZONE)['points'][0]['total']['pv'] == pytest.approx(100)

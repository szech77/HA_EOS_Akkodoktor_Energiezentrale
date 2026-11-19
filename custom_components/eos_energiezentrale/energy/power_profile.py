"""Power profile of one local day for the report page, from the local minute history.

Each sample is split onto its sources exactly like the accounting splits energy: in
proportion to PV, grid import and battery discharge, provided the AC balance closes;
otherwise the power counts as unknown. Display only; never a control input.
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .domain import energy_balance, instant, number

SOURCES = ('pv', 'battery', 'grid', 'unknown')
CONSUMERS = ('house', 'heat', 'car')
STEP_S = 120
# A gap longer than this between samples is shown as a gap, never interpolated.
GAP_S = 600


def day_bounds(day, zone):
    """UTC start and end of a local calendar day (ISO date)."""
    local = ZoneInfo(zone)
    start = datetime.combine(datetime.fromisoformat(day).date(), time.min, local)
    end = datetime.combine(start.date() + timedelta(days=1), time.min, local)
    return start.astimezone(timezone.utc), end.astimezone(timezone.utc)


def _split(sample):
    """Source shares and the consumer and grid powers of one history sample."""
    balance = sample.get('balance') if isinstance(sample.get('balance'), dict) else {}
    value = lambda key: number(balance.get(key, sample.get(key)))
    pv, grid = value('solar'), value('grid')
    discharge, charge, total = value('battery_discharge'), value('battery_charge'), value('house_total')
    pv, discharge, charge = (max(0., item) if item is not None else None for item in (pv, discharge, charge))
    result = energy_balance(pv, grid, discharge, charge, total)
    supplied = result['supplied_w'] if result else 0
    shares = ({'pv': pv / supplied, 'battery': discharge / supplied, 'grid': max(0., grid) / supplied}
              if result and result['balanced'] and supplied > 0 else {'unknown': 1.})
    fitted = balance.get('consumers') or {}
    consumers = {key: number(fitted.get(key, sample.get(key))) for key in CONSUMERS}
    return shares, consumers, total, grid


def power_profile(samples, day, zone, consumers=CONSUMERS):
    """Average power per STEP_S of the local day: per consumer and in total, split by source (W),
    plus grid import and feed-in. Empty when the local history does not cover the day."""
    start, end = day_bounds(day, zone)
    buckets = {}
    for sample in samples:
        stamp = instant(sample.get('time'))
        if stamp is None or not start <= stamp < end:
            continue
        shares, values, total, grid = _split(sample)
        slot = buckets.setdefault(int((stamp - start).total_seconds()) // STEP_S, {'count': 0, 'rows': []})
        slot['count'] += 1
        slot['rows'].append((shares, values, total, grid))
    points = []
    for index in sorted(buckets):
        rows = buckets[index]['rows']
        point = {'time': (start + timedelta(seconds=index * STEP_S)).isoformat()}
        for key in (*consumers, 'total'):
            parts = dict.fromkeys(SOURCES, 0.)
            known = 0
            for shares, values, total, _ in rows:
                watts = total if key == 'total' else values.get(key)
                if watts is None:
                    continue
                known += 1
                for source, share in shares.items():
                    parts[source] += max(0., watts) * share
            point[key] = {source: round(parts[source] / known) for source in SOURCES} if known else None
        grids = [grid for *_, grid in rows if grid is not None]
        point['grid'] = ({'import': round(sum(max(0., value) for value in grids) / len(grids)),
                          'export': round(sum(max(0., -value) for value in grids) / len(grids))} if grids else None)
        points.append(point)
    return {'step_s': STEP_S, 'gap_s': GAP_S, 'points': points}

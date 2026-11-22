"""Power profile of one local day for the report page, from the local minute history.

Each sample is split onto its sources exactly like the accounting splits energy: in
proportion to PV, grid import and battery discharge, provided the AC balance closes;
otherwise unknown shares are estimated between known neighbors when possible.
Display only; never a control input.
"""
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .domain import energy_balance, instant, number
from .source_estimates import brackets

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


PV_FLOWS = ('house', 'car', 'heat', 'storage', 'export')
PV_GAPS = ('battery_pv', 'battery_grid', 'battery_unknown', 'grid', 'unknown')


def battery_origin(report, consumers=CONSUMERS):
    """Share of PV- and grid-charged energy in the battery energy of each hour of a day report."""
    hours = {}
    for key in consumers:
        for row in ((report.get('consumers') or {}).get(key) or {}).get('bins', []):
            battery = (row.get('sources') or {}).get('battery') or {}
            total = hours.setdefault(row['time'], [0., 0., 0.])
            total[0] += battery.get('kwh', 0)
            total[1] += battery.get('pv_kwh', 0)
            total[2] += battery.get('grid_kwh', 0)
    return {hour: (pv / kwh, grid / kwh) for hour, (kwh, pv, grid) in hours.items() if kwh > 0}


def _pv_flow(sample, shares, values, origin):
    """PV destinations and uncovered consumption of one sample (W), like the accounting splits energy."""
    balance = sample.get('balance') if isinstance(sample.get('balance'), dict) else {}
    value = lambda key: number(balance.get(key, sample.get(key)))
    pv = max(0., value('solar') or 0)
    charge, discharge, grid = max(0., value('battery_charge') or 0), max(0., value('battery_discharge') or 0), value('grid')
    flow, gap = dict.fromkeys(PV_FLOWS, 0.), dict.fromkeys(PV_GAPS, 0.)
    from_pv, from_grid = origin
    for key, watts in values.items():
        if watts is None or key not in flow:
            continue
        watts = max(0., watts)
        flow[key] += watts * shares.get('pv', 0)
        battery = watts * shares.get('battery', 0)
        gap['battery_pv'] += battery * from_pv
        gap['battery_grid'] += battery * from_grid
        gap['battery_unknown'] += battery * max(0., 1 - from_pv - from_grid)
        gap['grid'] += watts * shares.get('grid', 0)
        gap['unknown'] += watts * shares.get('unknown', 0)
    flow['storage'] = charge * shares.get('pv', 0)
    if grid is not None and grid < 0 and pv + discharge > 0:
        flow['export'] = -grid * pv / (pv + discharge)
    return flow, gap


def power_profile(samples, day, zone, consumers=CONSUMERS, origin=None):
    """Average power per STEP_S of the local day: per consumer and in total, split by source (W),
    plus grid import and feed-in, and where PV went and what it did not cover (``pv_flow``,
    ``pv_gap``; battery origin per hour from ``origin``). Empty when the local history does not
    cover the day."""
    start, end = day_bounds(day, zone)
    buckets = {}
    prepared = sorted(((instant(sample.get('time')), sample, _split(sample)) for sample in samples
                       if instant(sample.get('time')) is not None), key=lambda item:item[0])
    estimates = {}
    for index, left, right, fraction in brackets([item[0] for item in prepared],
            [not item[2][0].get('unknown') for item in prepared]):
        if prepared[index][2][0].get('unknown'):
            estimates[index] = {key:prepared[left][2][0].get(key,0.) * (1-fraction)
                                    + prepared[right][2][0].get(key,0.) * fraction for key in SOURCES}
    for index, (stamp, sample, split) in enumerate(prepared):
        if not start <= stamp < end:
            continue
        shares, values, total, grid = split
        shares = estimates.get(index, shares)
        slot = buckets.setdefault(int((stamp - start).total_seconds()) // STEP_S,
                                  {'count': 0, 'rows': [], 'solar': [], 'flows': [], 'estimated': False})
        slot['estimated'] |= index in estimates
        slot['count'] += 1
        slot['rows'].append((shares, values, total, grid))
        hour = stamp.replace(minute=0, second=0, microsecond=0).isoformat()
        slot['flows'].append(_pv_flow(sample, shares, values, (origin or {}).get(hour, (0., 0.))))
        balance = sample.get('balance') if isinstance(sample.get('balance'), dict) else {}
        slot['solar'].append(number(balance.get('solar', sample.get('solar'))))
    points = []
    for index in sorted(buckets):
        rows = buckets[index]['rows']
        point = {'time': (start + timedelta(seconds=index * STEP_S)).isoformat()}
        if buckets[index]['estimated']:
            point['source_estimated'] = True
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
        flows = buckets[index]['flows']
        for field, keys, position in (('pv_flow', PV_FLOWS, 0), ('pv_gap', PV_GAPS, 1)):
            point[field] = {key: round(sum(item[position][key] for item in flows) / len(flows)) for key in keys}
        solar = [value for value in buckets[index]['solar'] if value is not None]
        point['solar'] = round(sum(max(0., value) for value in solar) / len(solar)) if solar else None
        grids = [grid for *_, grid in rows if grid is not None]
        point['grid'] = ({'import': round(sum(max(0., value) for value in grids) / len(grids)),
                          'export': round(sum(max(0., -value) for value in grids) / len(grids))} if grids else None)
        points.append(point)
    return {'step_s': STEP_S, 'gap_s': GAP_S, 'points': points}

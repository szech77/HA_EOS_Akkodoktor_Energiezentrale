"""Energy and price calculations for all consumers, independent of a browser."""
from copy import deepcopy

from .accounting import add, empty
from .domain import number


def complete_sources(amount):
    result = deepcopy(amount)
    result['sources'] = {key:{**value, **amount.get('sources', {}).get(key, {})}
                         for key, value in empty()['sources'].items()}
    return result


def amount_values(amount):
    if amount is None:
        return None
    result = deepcopy(amount)
    kwh, cost, unknown = (number(amount.get(key)) for key in ('kwh', 'cost_eur', 'cost_unknown_kwh'))
    estimated = number(amount.get('estimated_kwh')) or 0
    result['estimated'] = estimated > 0 or (unknown is not None and unknown > 0)
    result['energy_estimated'] = (number(amount.get('estimated_seconds')) or 0) > 0
    result['cost_available'] = cost is not None and kwh is not None and unknown is not None and not (kwh > 0 and unknown >= kwh)
    result['cost_partial'] = unknown is not None and unknown > .0001
    result['average_price_ct'] = None
    if (kwh is not None and kwh > 0 and cost is not None and unknown is not None and 0 <= unknown <= kwh
            and kwh - unknown > max(1e-12, kwh * 1e-9)):
        result['average_price_ct'] = number(cost / (kwh - unknown) * 100)
    for source, value in result.get('sources', {}).items():
        result['sources'][source] = amount_values(value)
        result['sources'][source]['share_percent'] = value['kwh'] / kwh * 100 if kwh is not None and kwh > 0 else None
    return result


def report_values(report, consumers=('house', 'heat', 'car')):
    result = deepcopy(report)
    total = empty()
    bins = {}
    overview = {}
    unbinned = {'seconds': 0, 'estimated_seconds': 0}

    def combine(target, amount):
        # Consumers run concurrently; their observation times must not be added.
        seconds = max(target.get('seconds', 0), amount.get('seconds', 0))
        estimated = max(target.get('estimated_seconds', 0), amount.get('estimated_seconds', 0))
        add(target, complete_sources(amount))
        target.update(seconds=seconds, estimated_seconds=estimated)

    for key, entry in result.get('consumers', {}).items():
        if key in consumers:
            add(total, complete_sources(entry['total']))
            for row in entry.get('bins', []):
                combine(bins.setdefault(row['time'], empty()), row)
            # Cached daily history may supply totals without their chart bins.
            for field in unbinned:
                missing = entry['total'].get(field, 0) - sum(row.get(field, 0) for row in entry.get('bins', []))
                unbinned[field] = max(unbinned[field], missing)
            overview[key] = amount_values(entry['total'])
        entry['total'] = amount_values(entry['total'])
        entry['bins'] = [amount_values(row) for row in entry.get('bins', [])]
    for field, missing in unbinned.items():
        total[field] = sum(row[field] for row in bins.values()) + missing
    result['overview'] = {'consumers': overview, 'total': amount_values(total)}
    result['total'] = {'total': amount_values(total),
                       'bins': [amount_values({'time': key, **bins[key]}) for key in sorted(bins)]}
    result['balance'] = balance_values(report, consumers)
    return result


def current_day_values(report, historical=None, consumers=('house', 'heat', 'car')):
    result = deepcopy(report)
    if historical and report.get('date') == historical.get('date'):
        for key, old in historical.get('historical_consumers', {}).items():
            entry = result['consumers'].setdefault(key, {'total': empty(), 'bins': []})
            entry['total'] = complete_sources(entry['total'])
            add(entry['total'], complete_sources(old))
    return report_values(result, consumers)


def _ratio(numerator, denominator, scale=100):
    return numerator / denominator * scale if denominator > 1e-9 else None


def balance_values(report, consumers=('house', 'heat', 'car')):
    """Period balance: consumption, self-supply, grid, feed-in, base price and net cost.

    Consumer costs already contain battery energy at its book price, which includes
    grid-charged energy; storage charging therefore adds import kWh but no extra cost.
    """
    from .accounting import EXPORT, STORAGE
    entries = report.get('consumers', {})
    totals = {key: complete_sources(entries[key]['total']) if key in entries else empty()
              for key in (*consumers, EXPORT, STORAGE)}
    used = empty()
    for key in consumers:
        add(used, totals[key])
    export, storage = totals[EXPORT], totals[STORAGE]
    source = used['sources']
    grid_known = source['grid']['kwh'] - source['grid']['cost_unknown_kwh']
    self_kwh = source['pv']['kwh'] + source['battery']['kwh']
    self_cost = source['pv']['cost_eur'] + source['battery']['cost_eur']
    self_known = self_kwh - source['pv']['cost_unknown_kwh'] - source['battery']['cost_unknown_kwh']
    pv_kwh = source['pv']['kwh'] + storage['sources']['pv']['kwh'] + export['sources']['pv']['kwh']
    grid_price = _ratio(source['grid']['cost_eur'], grid_known)
    feed_in_price = _ratio(export['cost_eur'], export['kwh'] - export['cost_unknown_kwh'])
    settings = report.get('settings') or {}
    base_month = number(settings.get('base_price_eur_month')) or 0.
    base_days = report.get('base_days') or 0
    base = base_month * 12 / 365 * base_days
    savings = self_kwh * grid_price / 100 - self_cost if grid_price is not None else None
    bins = {}
    for key, field in ((EXPORT, 'export_kwh'), (STORAGE, 'storage_kwh'), *((key, 'consumption_kwh') for key in consumers)):
        for row in entries.get(key, {}).get('bins', []):
            target = bins.setdefault(row['time'], {'time':row['time'], 'consumption_kwh':0., 'export_kwh':0.,
                                                   'storage_kwh':0., 'grid_import_kwh':0.})
            target[field] += row.get('kwh', 0)
            if key != EXPORT:
                target['grid_import_kwh'] += (row.get('sources', {}).get('grid') or {}).get('kwh', 0)
    unknown = used['cost_unknown_kwh'] + export['cost_unknown_kwh']
    return {
        'consumption_kwh': used['kwh'], 'self_kwh': self_kwh, 'unknown_source_kwh': source['unknown']['kwh'],
        'autarky_percent': _ratio(self_kwh, used['kwh'] - source['unknown']['kwh']),
        'grid_kwh': source['grid']['kwh'], 'grid_import_kwh': source['grid']['kwh'] + storage['sources']['grid']['kwh'],
        'grid_cost_eur': source['grid']['cost_eur'], 'grid_price_ct': grid_price,
        'self_cost_eur': self_cost, 'self_price_ct': _ratio(self_cost, self_known),
        'pv_kwh': pv_kwh, 'pv_direct_kwh': source['pv']['kwh'], 'pv_storage_kwh': storage['sources']['pv']['kwh'],
        'export_kwh': export['kwh'], 'export_eur': export['cost_eur'], 'feed_in_price_ct': feed_in_price,
        'self_consumption_percent': _ratio(pv_kwh - export['sources']['pv']['kwh'], pv_kwh),
        'base_days': base_days, 'base_price_eur_month': base_month, 'base_eur': base,
        'cost_eur': used['cost_eur'], 'savings_eur': savings, 'net_eur': used['cost_eur'] + base - export['cost_eur'],
        'cost_partial': unknown > .0001, 'estimated': used.get('estimated_kwh', 0) + export.get('estimated_kwh', 0) > 0,
        'bins': [bins[key] for key in sorted(bins)],
    }

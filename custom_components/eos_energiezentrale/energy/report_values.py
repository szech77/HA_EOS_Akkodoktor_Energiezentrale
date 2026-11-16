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
    return result


def current_day_values(report, historical=None, consumers=('house', 'heat', 'car')):
    result = deepcopy(report)
    if historical and report.get('date') == historical.get('date'):
        for key, old in historical.get('historical_consumers', {}).items():
            entry = result['consumers'].setdefault(key, {'total': empty(), 'bins': []})
            entry['total'] = complete_sources(entry['total'])
            add(entry['total'], complete_sources(old))
    return report_values(result, consumers)

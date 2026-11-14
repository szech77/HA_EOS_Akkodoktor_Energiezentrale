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
    overview = {}
    for key, entry in result.get('consumers', {}).items():
        if key in consumers:
            add(total, complete_sources(entry['total']))
            overview[key] = amount_values(entry['total'])
        entry['total'] = amount_values(entry['total'])
        entry['bins'] = [amount_values(row) for row in entry.get('bins', [])]
    result['overview'] = {'consumers': overview, 'total': amount_values(total)}
    return result


def current_day_values(report, historical=None, consumers=('house', 'heat', 'car')):
    result = deepcopy(report)
    if historical and report.get('date') == historical.get('date'):
        for key, old in historical.get('historical_consumers', {}).items():
            entry = result['consumers'].setdefault(key, {'total': empty(), 'bins': []})
            entry['total'] = complete_sources(entry['total'])
            add(entry['total'], complete_sources(old))
    return report_values(result, consumers)

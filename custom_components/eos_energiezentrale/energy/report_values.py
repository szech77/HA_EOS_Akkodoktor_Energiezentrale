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
    result['views'] = view_values(result, consumers)
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
    own_kwh = _own_kwh(used)
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
                                                   'storage_kwh':0., 'grid_import_kwh':0., 'grid_import_eur':0.,
                                                   'export_eur':0., 'cost_partial':False, 'pv_kwh':0.,
                                                   'pv_direct_kwh':0., 'pv_storage_kwh':0., 'pv_export_kwh':0.})
            target[field] += row.get('kwh', 0)
            # Money per bin for the euro chart: grid import cost (consumers and storage) and feed-in credit.
            grid = row if key == EXPORT else (row.get('sources', {}).get('grid') or {})
            if key == EXPORT:
                target['export_eur'] += row.get('cost_eur', 0)
            else:
                target['grid_import_kwh'] += grid.get('kwh', 0)
                target['grid_import_eur'] += grid.get('cost_eur', 0)
            target['cost_partial'] = target['cost_partial'] or grid.get('cost_unknown_kwh', 0) > .0001
            # PV production of the bin by its use: consumed directly, stored or fed in.
            pv = (row.get('sources', {}).get('pv') or {}).get('kwh', 0)
            use = 'pv_export_kwh' if key == EXPORT else 'pv_storage_kwh' if key == STORAGE else 'pv_direct_kwh'
            target[use] += pv
            target['pv_kwh'] += pv
    unknown = used['cost_unknown_kwh'] + export['cost_unknown_kwh']
    storage_grid = storage['sources']['grid']
    import_cost = source['grid']['cost_eur'] + storage_grid['cost_eur']
    import_known = grid_known + storage_grid['kwh'] - storage_grid['cost_unknown_kwh']
    pv_export = export['sources']['pv']['kwh']
    pv_use = {key: {'kwh': value, 'share_percent': _ratio(value, pv_kwh)} for key, value in
              (('direct', source['pv']['kwh']), ('storage', storage['sources']['pv']['kwh']), ('export', pv_export))}
    return {
        'consumption_kwh': used['kwh'], 'self_kwh': self_kwh, 'own_kwh': own_kwh,
        'unknown_source_kwh': source['unknown']['kwh'],
        'autarky_percent': _ratio(own_kwh, used['kwh'] - source['unknown']['kwh']),
        'grid_kwh': source['grid']['kwh'], 'grid_import_kwh': source['grid']['kwh'] + storage['sources']['grid']['kwh'],
        'grid_cost_eur': source['grid']['cost_eur'], 'grid_price_ct': grid_price,
        'self_cost_eur': self_cost, 'self_price_ct': _ratio(self_cost, self_known),
        'pv_kwh': pv_kwh, 'pv_direct_kwh': source['pv']['kwh'], 'pv_storage_kwh': storage['sources']['pv']['kwh'],
        'export_kwh': export['kwh'], 'export_eur': export['cost_eur'], 'feed_in_price_ct': feed_in_price,
        'self_consumption_percent': _ratio(pv_kwh - pv_export, pv_kwh), 'pv_export_kwh': pv_export, 'pv_use': pv_use,
        'storage_grid_kwh': storage_grid['kwh'], 'grid_import_cost_eur': import_cost,
        'grid_import_price_ct': _ratio(import_cost, import_known),
        'grid_balance_eur': import_cost + base - export['cost_eur'], 'total_cost_eur': used['cost_eur'] + base,
        'base_days': base_days, 'base_price_eur_month': base_month, 'base_eur': base,
        'cost_eur': used['cost_eur'], 'savings_eur': savings, 'net_eur': used['cost_eur'] + base - export['cost_eur'],
        'cost_partial': unknown > .0001, 'estimated': used.get('estimated_kwh', 0) + export.get('estimated_kwh', 0) > 0,
        'bins': [bins[key] for key in sorted(bins)],
    }


# Chart bins per period: hours for a day, days for a month, months for a year.
UNITS = {'day': 'hour', 'month': 'day', 'year': 'month'}
NOTABLE_KWH = .05


def _source(amount, key):
    return amount.get('sources', {}).get(key) or {'kwh': 0., 'cost_eur': 0., 'cost_unknown_kwh': 0.}


def _own_kwh(amount):
    """Energy covered on site: PV direct and stored energy not charged from the grid.

    Grid-charged storage is grid energy shifted in time and does not count as self-supply.
    Stored energy without a recorded origin (before the origin was recorded) still counts."""
    battery = _source(amount, 'battery')
    return _source(amount, 'pv')['kwh'] + max(0., battery['kwh'] - battery.get('grid_kwh', 0.))


def battery_origin(pv, battery):
    """Self-supplied energy split into PV direct and stored energy by its charging origin.

    Stored energy without a recorded origin (e.g. before the split was recorded) stays
    separate, so grid-charged storage is never shown as own power."""
    def part(kwh, cost, known):
        return {'kwh': kwh, 'cost_eur': cost, 'price_ct': _ratio(cost, known)}
    pv_kwh, grid_kwh = battery.get('pv_kwh', 0.), battery.get('grid_kwh', 0.)
    pv_cost, grid_cost = battery.get('pv_cost_eur', 0.), battery.get('grid_cost_eur', 0.)
    rest = max(0., battery['kwh'] - pv_kwh - grid_kwh)
    rest_known = max(0., battery['kwh'] - battery['cost_unknown_kwh'] - pv_kwh - grid_kwh)
    return {'pv_direct': part(pv['kwh'], pv['cost_eur'], pv['kwh'] - pv['cost_unknown_kwh']),
            'battery_pv': part(pv_kwh, pv_cost, pv_kwh),
            'battery_grid': part(grid_kwh, grid_cost, grid_kwh),
            'battery_unknown': part(rest, max(0., battery['cost_eur'] - pv_cost - grid_cost), rest_known)}


def consumer_view(entry, balance, period, days, car=False):
    """Key figures of one consumer (or all consumers) for its report page."""
    amount = complete_sources(entry['total'])
    kwh = amount['kwh']
    pv, battery, grid, unknown = (amount['sources'][key] for key in ('pv', 'battery', 'grid', 'unknown'))
    self_kwh = pv['kwh'] + battery['kwh']
    own_kwh = _own_kwh(amount)
    self_cost = pv['cost_eur'] + battery['cost_eur']
    self_known = self_kwh - pv['cost_unknown_kwh'] - battery['cost_unknown_kwh']
    # Savings compare the self-supplied energy with the period's average grid price.
    reference = balance.get('grid_price_ct')
    savings = self_kwh * reference / 100 - self_cost if reference is not None and self_kwh > 0 else None
    per_day = period != 'day' and days > 1
    view = {
        'kwh': kwh, 'self_kwh': self_kwh, 'own_kwh': own_kwh, 'self_percent': _ratio(own_kwh, kwh - unknown['kwh']),
        'pv_kwh': pv['kwh'], 'battery_kwh': battery['kwh'], 'battery_own_kwh': own_kwh - pv['kwh'], 'grid_kwh': grid['kwh'], 'unknown_kwh': unknown['kwh'],
        'grid_cost_eur': grid['cost_eur'], 'grid_price_ct': _ratio(grid['cost_eur'], grid['kwh'] - grid['cost_unknown_kwh']),
        'self_cost_eur': self_cost, 'self_price_ct': _ratio(self_cost, self_known),
        'self_origin': battery_origin(pv, battery),
        'cost_eur': amount['cost_eur'], 'price_ct': entry['total'].get('average_price_ct'),
        'cost_available': entry['total'].get('cost_available', False), 'cost_partial': entry['total'].get('cost_partial', False),
        'estimated': entry['total'].get('estimated', False), 'savings_eur': savings,
        'reference_price_ct': reference, 'days': days,
        'per_day_kwh': kwh / days if per_day else None, 'per_day_eur': amount['cost_eur'] / days if per_day else None,
    }
    view['facts'] = consumer_facts(entry.get('bins', []), view, period, car)
    return view


def consumer_facts(bins, view, period, car=False):
    """Notable bins of a consumer: best self-supply, highest grid draw, averages and savings."""
    unit = UNITS.get(period, 'hour')
    used = [row for row in bins if (number(row.get('kwh')) or 0) > 0]
    if not used:
        return [{'id': 'no_charging' if car else 'no_consumption'}]
    average = sum(row['kwh'] for row in used) / len(used)
    candidates = [row for row in used if row['kwh'] > max(NOTABLE_KWH, average * .3)] or used

    def share(row):
        return _own_kwh(row) / row['kwh']

    best = max(candidates, key=share)
    facts = [{'id': 'best', 'time': best['time'], 'unit': unit, 'percent': share(best) * 100}]
    worst = max(candidates, key=lambda row: _source(row, 'grid')['kwh'])
    if _source(worst, 'grid')['kwh'] > NOTABLE_KWH:
        facts.append({'id': 'max_grid', 'time': worst['time'], 'unit': unit, 'kwh': _source(worst, 'grid')['kwh']})
    if car and period == 'month':
        facts.append({'id': 'charge_days', 'count': sum(row['kwh'] > NOTABLE_KWH for row in used), 'days': view['days']})
    if view['per_day_kwh'] is not None:
        facts.append({'id': 'per_day', 'kwh': view['per_day_kwh'], 'eur': view['per_day_eur'],
                      'cost_available': view['cost_available']})
    if view['savings_eur'] is not None:
        facts.append({'id': 'savings', 'eur': view['savings_eur'], 'self_price_ct': view['self_price_ct'],
                      'grid_price_ct': view['reference_price_ct']})
    return facts


def pv_facts(balance, period):
    """Notable bins of the PV production: the strongest bin and the daily average."""
    unit = UNITS.get(period, 'hour')
    best = max(balance['bins'], key=lambda item: item.get('pv_kwh', 0), default=None)
    facts = []
    if best is not None and best.get('pv_kwh', 0) > NOTABLE_KWH:
        facts.append({'id': 'max_pv', 'time': best['time'], 'unit': unit, 'kwh': best['pv_kwh']})
    days = balance['base_days']
    if facts and period != 'day' and days > 1:
        facts.append({'id': 'pv_per_day', 'kwh': balance['pv_kwh'] / days})
    return facts or [{'id': 'no_pv'}]


def grid_facts(balance, period):
    """Notable bins of the grid exchange: most feed-in, highest import and daily averages."""
    unit = UNITS.get(period, 'hour')
    bins = balance['bins']
    facts = []
    for fact, field, price in (('max_export', 'export_kwh', 'feed_in_price_ct'),
                               ('max_import', 'grid_import_kwh', 'grid_import_price_ct')):
        row = max(bins, key=lambda item: item[field], default=None)
        if row is not None and row[field] > NOTABLE_KWH:
            rate = balance[price]
            facts.append({'id': fact, 'time': row['time'], 'unit': unit, 'kwh': row[field],
                          'eur': row[field] * rate / 100 if rate is not None else None})
    days = balance['base_days']
    if facts and period != 'day' and days > 1:
        facts.append({'id': 'grid_per_day', 'export_kwh': balance['export_kwh'] / days,
                      'import_kwh': balance['grid_import_kwh'] / days})
    return facts or [{'id': 'no_exchange'}]


def view_values(result, consumers):
    """Everything a report page shows, per consumer plus the totals and the grid exchange."""
    from .accounting import EXPORT, STORAGE
    balance, period = result['balance'], result.get('period', 'day')
    days = balance['base_days']
    views = {}
    for key, entry in result.get('consumers', {}).items():
        if key not in (EXPORT, STORAGE):
            views[key] = consumer_view(entry, balance, period, days, car=key == 'car' or key.startswith('car/'))
    total = consumer_view(result['total'], balance, period, days)
    total['facts'] = [{'id': 'consumer', 'key': key, 'kwh': views[key]['kwh'], 'self_percent': views[key]['self_percent'],
                       'cost_eur': views[key]['cost_eur'], 'cost_available': views[key]['cost_available']}
                      for key in consumers if key in views]
    total['facts'].append({'id': 'export', 'kwh': balance['export_kwh'], 'eur': balance['export_eur']})
    views['total'] = total
    views['grid'] = {'facts': grid_facts(balance, period)}
    views['pv'] = {'facts': pv_facts(balance, period)}
    return views

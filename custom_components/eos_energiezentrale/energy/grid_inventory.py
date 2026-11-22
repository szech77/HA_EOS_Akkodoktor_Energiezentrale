"""Grid charging dates and proportional costs of the remaining battery stock."""
from itertools import groupby

from .base_prices import fixed_grid_price

FIELDS = ('kwh', 'ac_kwh', 'cost_eur', 'cost_unknown_kwh', 'original_cost_eur', 'original_unknown_kwh')


def merge(target, source, factor=1.):
    for day, values in source.items():
        lot = target.setdefault(day, dict.fromkeys(FIELDS, 0.))
        for key in FIELDS:
            lot[key] += values.get(key, 0.) * factor


def scale(stock, fraction):
    if fraction <= 0:
        stock.get('grid_lots', {}).clear()
        return
    lots = stock.get('grid_lots', {})
    for day, values in list(lots.items()):
        for key in FIELDS:
            values[key] *= fraction
        if values['kwh'] <= 1e-12 and values['ac_kwh'] <= 1e-12:
            del lots[day]


def charging_lot(day, ac, efficiency, price):
    if ac <= 0:
        return {}
    return {day: {'kwh': ac * efficiency, 'ac_kwh': ac,
                  'cost_eur': ac * price / 100 if price is not None else 0.,
                  'cost_unknown_kwh': 0. if price is not None else ac * efficiency,
                  'original_cost_eur': ac * price / 100 if price is not None else 0.,
                  'original_unknown_kwh': 0. if price is not None else ac * efficiency}}


def withdrawals(stock, fraction, discharge_efficiency, delivered):
    """Charge provenance per delivered battery kWh, before removing it from stock."""
    if delivered <= 0:
        return {}
    return {day: {key: value * fraction / delivered *
                        (discharge_efficiency if key in ('kwh', 'cost_unknown_kwh', 'original_unknown_kwh') else 1.)
                  for key, value in values.items()}
            for day, values in stock.get('grid_lots', {}).items()}


def legacy_lots(rows, effective, traced=None):
    """Best available reconstruction from hourly charge/discharge origin records.

    Intra-hour order, old efficiencies and SoC corrections are no longer known.
    Callers must mark these recovered charge dates and quantities as estimates.
    """
    lots = {}
    for _, grouped in groupby(rows, key=lambda row: (row[0], row[1])):
        group = list(grouped)
        for _, day, consumer, amount in group:
            if consumer != 'storage':
                continue
            source = amount['sources']['grid']
            ac = source['kwh']
            if ac > 0:
                price = source['cost_eur'] / ac * 100
                charge = charging_lot(day, ac, effective['charge_efficiency'], price)
                charge[day]['cost_unknown_kwh'] = source['cost_unknown_kwh'] * effective['charge_efficiency']
                charge[day]['original_unknown_kwh'] = charge[day]['cost_unknown_kwh']
                merge(lots, charge)
        has_car = any(consumer == 'car' for _, _, consumer, _ in group)
        discharged = sum(amount['sources']['battery'].get('grid_kwh', 0.)
                         for _, _, consumer, amount in group if consumer not in ('storage', 'export')
                         and not (has_car and consumer.startswith('car/')))
        available = sum(lot['kwh'] for lot in lots.values())
        if traced is not None:
            for hour, day, consumer, amount in group:
                if consumer not in ('storage', 'export'):
                    entry = legacy_withdrawal(amount['sources']['battery'], lots, effective, discharged)
                    if entry is not None:
                        traced[(hour, day, consumer)] = entry
        if available > 0:
            scale({'grid_lots': lots}, max(0., 1 - discharged / effective['discharge_efficiency'] / available))
    return lots


def legacy_withdrawal(source, lots, effective, total_delivered):
    existing = source.get('grid_charges', {})
    missing = source.get('grid_kwh', 0.) - sum(lot['kwh'] for lot in existing.values())
    if missing <= 1e-9:
        return None
    available = sum(lot['kwh'] for lot in lots.values())
    needed = total_delivered / effective['discharge_efficiency']
    coverage = min(1., available / needed) if needed > 0 else 0.
    cohorts = {}
    if available > 0:
        fraction = missing / effective['discharge_efficiency'] / available * coverage
        merge(cohorts, withdrawals({'grid_lots': lots}, fraction, effective['discharge_efficiency'], missing), missing)
    uncovered = max(0., missing - sum(lot['kwh'] for lot in cohorts.values()))
    if uncovered > 1e-9:
        fallback = charging_lot('', uncovered / effective['discharge_efficiency'] / effective['charge_efficiency'],
                                effective['charge_efficiency'], None)
        merge(cohorts, withdrawals({'grid_lots': fallback}, 1., effective['discharge_efficiency'], 1.))
    original_unknown = sum(lot['cost_unknown_kwh'] for lot in cohorts.values())
    target = source.get('grid_cost_eur', 0.) - sum(lot['cost_eur'] for lot in existing.values())
    correction = 0.
    if original_unknown > 0 and source['cost_unknown_kwh'] < original_unknown:
        remaining_cost = source['cost_eur'] - source.get('pv_cost_eur', 0.) - source.get('grid_cost_eur', 0.)
        remaining_energy = max(missing, source['kwh'] - source.get('pv_kwh', 0.))
        correction = remaining_cost * min(1., original_unknown / remaining_energy)
        target += correction
    cost = sum(lot['cost_eur'] for lot in cohorts.values())
    unresolved = min(original_unknown, source['cost_unknown_kwh'])
    for lot in cohorts.values():
        lot['cost_eur'] += (target-cost) * lot['kwh'] / missing
        lot['original_cost_eur'] = lot['cost_eur']
        lot['cost_unknown_kwh'] *= unresolved / original_unknown if original_unknown > 0 else 0.
        lot['original_unknown_kwh'] = lot['cost_unknown_kwh']
    return {'grid_charges': cohorts, 'origin_cost_correction': correction}


def recover(stock, rows, effective):
    """Attach estimated cohorts to stock from older installations without cohorts."""
    if 'grid_lots' in stock:
        return
    energy = stock.get('grid_kwh', 0.)
    lots = legacy_lots(rows, effective) if energy > 0 else {}
    available = sum(lot['kwh'] for lot in lots.values())
    if energy > 0 and available > 1e-9:
        scale({'grid_lots': lots}, energy / available)
    elif energy > 0:
        # No invented charging date: only an undated fixed tariff can value this lot.
        lots = {'': {'kwh': energy, 'ac_kwh': energy / effective['charge_efficiency'],
                     'cost_eur': stock.get('grid_cost', 0.), 'cost_unknown_kwh': 0.,
                     'original_cost_eur': stock.get('grid_cost', 0.), 'original_unknown_kwh': 0.}}
    unpriced = sum(lot['cost_unknown_kwh'] for lot in lots.values())
    if unpriced > 0:
        # Older fallback valuations were not assigned to their known grid origin.
        unassigned = stock['cost'] - stock.get('grid_cost', 0.) - stock.get('pv_cost', 0.)
        remaining = max(energy, stock['kwh'] - stock.get('pv_kwh', 0.))
        stock['grid_cost'] = stock.get('grid_cost', 0.) + unassigned * min(1., unpriced / remaining)
        unresolved = min(unpriced, stock['unknown'])
        for lot in lots.values():
            lot['cost_unknown_kwh'] *= unresolved / unpriced
            lot['original_unknown_kwh'] = lot['cost_unknown_kwh']
    cost = sum(lot['cost_eur'] for lot in lots.values())
    for lot in lots.values():
        correction = (stock.get('grid_cost', 0.) - cost) * lot['kwh'] / energy if energy > 0 else 0.
        lot['cost_eur'] += correction
        lot['original_cost_eur'] += correction
    stock['grid_lots'] = lots
    if energy > 0:
        stock['estimated'] = max(stock.get('estimated', 0.), energy)


def valued(lot, price):
    return ((lot['ac_kwh'] * price / 100, 0.) if price is not None
            else (lot['original_cost_eur'], lot['original_unknown_kwh']))


def revalue(stock, settings):
    cost_delta, unknown_delta = 0., 0.
    for day, lot in stock.get('grid_lots', {}).items():
        cost, unknown = valued(lot, fixed_grid_price(settings, day))
        cost_delta += cost - lot['cost_eur']
        unknown_delta += unknown - lot['cost_unknown_kwh']
        lot.update(cost_eur=cost, cost_unknown_kwh=unknown)
    stock['cost'] += cost_delta
    stock['grid_cost'] = stock.get('grid_cost', 0.) + cost_delta
    stock['unknown'] = max(0., min(stock['kwh'], stock['unknown'] + unknown_delta))


def reprice_battery(amount, settings):
    source = amount['sources']['battery']
    cohorts = source.get('grid_charges')
    if not cohorts:
        return
    old_cost = sum(lot['cost_eur'] for lot in cohorts.values())
    old_unknown = sum(lot['cost_unknown_kwh'] for lot in cohorts.values())
    costs = [valued(lot, fixed_grid_price(settings, day)) for day, lot in cohorts.items()]
    delta = sum(cost for cost, _ in costs) - old_cost
    unknown_delta = sum(unknown for _, unknown in costs) - old_unknown
    if source.get('grid_charges_estimated') and (abs(delta) > 1e-9 or abs(unknown_delta) > 1e-9):
        source['estimated_kwh'] = min(source['kwh'], max(source.get('estimated_kwh', 0.), source.get('grid_kwh', 0.)))
        amount['estimated_kwh'] = min(amount['kwh'], max(amount.get('estimated_kwh', 0.), source.get('grid_kwh', 0.)))
    source['grid_cost_eur'] = source.get('grid_cost_eur', 0.) + delta
    source['cost_eur'] += delta
    source['cost_unknown_kwh'] = max(0., source['cost_unknown_kwh'] + unknown_delta)
    amount['cost_eur'] += delta
    amount['cost_unknown_kwh'] = max(0., amount['cost_unknown_kwh'] + unknown_delta)
    for day, lot in cohorts.items():
        cost, unknown = valued(lot, fixed_grid_price(settings, day))
        lot.update(cost_eur=cost, cost_unknown_kwh=unknown)


def value_unknown(stock, rate):
    """Assign an estimated fallback to tracked grid energy as well as total stock."""
    for lot in stock.get('grid_lots', {}).values():
        unknown = lot['cost_unknown_kwh']
        if unknown <= 0:
            continue
        cost = unknown * rate
        lot['cost_eur'] += cost
        lot['cost_unknown_kwh'] = 0.
        if lot['original_unknown_kwh'] > 0:
            lot['original_cost_eur'] += cost
            lot['original_unknown_kwh'] = 0.
        stock['grid_cost'] = stock.get('grid_cost', 0.) + cost

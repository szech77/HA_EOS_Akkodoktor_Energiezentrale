"""Dated fixed grid charges, evaluated by local calendar day without rounding."""
from datetime import date, timedelta

from .domain import number
from .failures import BackendError


def checked_history(values):
    """None preserves the old monthly setting; an empty list explicitly means no fee.

    An empty valid_from is the legacy rate before all dated changes. Other entries
    take effect at local midnight, including changes entered retrospectively.
    """
    if values is None:
        return None
    def invalid(reason='invalid_type'):
        raise BackendError('Invalid base price history', reason=reason, fields=('base_price_history',))
    if not isinstance(values, list) or len(values) > 128:
        invalid()
    result, seen = [], set()
    for row in values:
        if (not isinstance(row, dict) or not {'valid_from', 'period', 'amount_eur'} <= row.keys()
                or row.keys() - {'valid_from', 'period', 'amount_eur', 'grid_price_source', 'grid_price_ct'}):
            invalid()
        start = row['valid_from']
        if not isinstance(start, str):
            invalid()
        if start:
            try:
                day = date.fromisoformat(start)
            except ValueError:
                invalid()
            if day.isoformat() != start or not 2000 <= day.year <= 2100:
                invalid()
        if start in seen or row['period'] not in ('month', 'day'):
            invalid()
        amount = number(row['amount_eur'])
        if isinstance(row['amount_eur'], bool) or amount is None or not 0 <= amount <= 1000:
            invalid('out_of_range')
        source = row.get('grid_price_source', 'dynamic')
        if source not in ('dynamic', 'fixed'):
            invalid()
        price = number(row.get('grid_price_ct'))
        if ((source == 'fixed' or row.get('grid_price_ct') is not None)
                and (isinstance(row.get('grid_price_ct'), bool) or price is None or not -1000 <= price <= 1000)):
            invalid('out_of_range')
        seen.add(start)
        item = {'valid_from': start, 'period': row['period'], 'amount_eur': amount}
        if 'grid_price_source' in row or 'grid_price_ct' in row:
            item.update(grid_price_source=source, grid_price_ct=price)
        result.append(item)
    return sorted(result, key=lambda row: row['valid_from'])


def fixed_grid_price(settings, day):
    """The configured gross ct/kWh on this local date; None means sensor price."""
    row = next((row for row in reversed(settings.get('base_price_history') or [])
                if row['valid_from'] <= day), None)
    return row.get('grid_price_ct') if row and row.get('grid_price_source') == 'fixed' else None


def dynamic_price_required(settings, first, last):
    """Whether an Influx range needs sensor prices (last date is exclusive)."""
    dates = [first, *(row['valid_from'] for row in settings.get('base_price_history') or []
                       if first < row['valid_from'] < last)]
    return any(fixed_grid_price(settings, day) is None for day in dates)


def reprice_grid(amount, price):
    """Revalue direct grid shares in report copies; stored battery costs stay booked."""
    if price is None:
        return
    grid = amount['sources']['grid']
    cost = grid['kwh'] * price / 100
    amount['cost_eur'] += cost - grid['cost_eur']
    amount['cost_unknown_kwh'] = max(0., amount['cost_unknown_kwh'] - grid['cost_unknown_kwh'])
    grid.update(cost_eur=cost, cost_unknown_kwh=0.)


def base_price_values(report):
    settings = report.get('settings') or {}
    days = report.get('base_days') or 0
    history = settings.get('base_price_history')
    if history is None:
        return {'base_eur': (number(settings.get('base_price_eur_month')) or 0.) * 12 / 365 * days}
    if not days or not history:
        return {'base_eur': 0., 'base_segments': []}
    start = date.fromisoformat(report.get('base_start') or report['date'])
    end = start + timedelta(days=days)
    segments = []
    for index, row in enumerate(history):
        first = max(start, date.fromisoformat(row['valid_from']) if row['valid_from'] else start)
        last = min(end, date.fromisoformat(history[index+1]['valid_from'])) if index+1 < len(history) else end
        if first >= last:
            continue
        count = (last-first).days
        rate = row['amount_eur'] if row['period'] == 'day' else row['amount_eur'] * 12 / 365
        segments.append({**row, 'start': first.isoformat(), 'end': (last-timedelta(days=1)).isoformat(),
                         'days': count, 'cost_eur': rate * count})
    return {'base_eur': sum(row['cost_eur'] for row in segments), 'base_segments': segments}

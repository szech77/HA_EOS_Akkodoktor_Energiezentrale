"""Retrospective source attribution in report copies, never in control or inventory."""
from copy import deepcopy

from .accounting_estimates import MAX_GAP_SECONDS
from .domain import instant

KNOWN = ('pv', 'battery', 'grid')
ORIGIN = ('pv_kwh', 'pv_cost_eur', 'grid_kwh', 'grid_cost_eur')


def brackets(stamps, usable, max_gap=MAX_GAP_SECONDS):
    """Nearest original anchors on both sides; estimates never become anchors."""
    following = [None] * len(stamps)
    right = None
    for index in range(len(stamps) - 1, -1, -1):
        following[index] = right
        if usable[index]:
            right = index
    left = None
    for index, stamp in enumerate(stamps):
        right = following[index]
        if left is not None and right is not None:
            span = (stamps[right] - stamps[left]).total_seconds()
            if 0 < span <= max_gap:
                yield index, left, right, (stamp - stamps[left]).total_seconds() / span
        if usable[index]:
            left = index


def estimate_sources(rows):
    """Fill only unknown kWh between hourly known source mixes, in place.

    Known portions in partially unknown hours are valid anchors for other hours.
    Costs and battery origins follow the donors per known kWh, including their
    unpriced portions. Raw ledger rows and live battery stock remain untouched.
    """
    if not any(row['sources']['unknown']['kwh'] > 0 for row in rows):
        return
    original = deepcopy([row['sources'] for row in rows])
    known = [sum(sources[key]['kwh'] for key in KNOWN) for sources in original]
    for index, left, right, fraction in brackets(
            [instant(row['time']) for row in rows], [value > 1e-12 for value in known]):
        row = rows[index]
        missing = row['sources']['unknown']['kwh']
        if missing <= 0:
            continue
        donors = ((original[left], (1 - fraction) / known[left]),
                  (original[right], fraction / known[right]))
        old = row['sources']['unknown']
        # Replace the unknown portion, preserving every measured/known portion.
        row['cost_eur'] -= old['cost_eur']
        row['cost_unknown_kwh'] = max(0., row['cost_unknown_kwh'] - old['cost_unknown_kwh'])
        row['estimated_kwh'] = min(row['kwh'], row.get('estimated_kwh', 0.)
                                   + missing - old.get('estimated_kwh', 0.))
        for key in KNOWN:
            target = row['sources'][key]
            fields = ('kwh', 'cost_eur', 'cost_unknown_kwh', *ORIGIN) if key == 'battery' else ('kwh', 'cost_eur', 'cost_unknown_kwh')
            additions = {field: missing * sum(donor[key].get(field, 0.) * weight
                                             for donor, weight in donors) for field in fields}
            for field, value in additions.items():
                target[field] = target.get(field, 0.) + value
            target['estimated_kwh'] = target.get('estimated_kwh', 0.) + additions['kwh']
            row['cost_eur'] += additions['cost_eur']
            row['cost_unknown_kwh'] += additions['cost_unknown_kwh']
        row['sources']['unknown'] = dict.fromkeys(old, 0.)

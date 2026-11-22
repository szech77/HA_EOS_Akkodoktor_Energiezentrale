"""Current fee-inclusive EOS prices, bounded by real prediction intervals.

EOS ElecPriceDataRecord.elecprice_marketprice_wh includes configured fees.
Never interpolate prices, extend the final point or turn a gap into free energy.
"""
from datetime import timedelta

from .contracts import Measurement
from .domain import instant, number
from .failures import BackendError

PRICE_MAX_AGE_S = 120


def unavailable():
    raise BackendError('Current EOS electricity price unavailable', reason='price_unavailable')


def price_intervals(response, now):
    data = response.get('data') if isinstance(response, dict) else None
    if not isinstance(data, dict) or not 2 <= len(data) <= 4096:
        unavailable()
    points = []
    for key, value in data.items():
        stamp = instant(key)
        if stamp is None:
            unavailable()
        price = number(value)
        points.append((stamp, price * 100000 if price is not None and -0.01 <= price <= .01 else None))
    points.sort(key=lambda item: item[0])
    deltas = [(b[0] - a[0]).total_seconds() for a, b in zip(points, points[1:])]
    if any(delta <= 0 for delta in deltas):
        unavailable()
    cadence = min(deltas)
    if not 60 <= cadence <= 3600:
        unavailable()
    rows = []
    for (stamp, price), (following, _) in zip(points, points[1:]):
        end = min(following, stamp + timedelta(seconds=cadence))
        if price is not None:
            rows.append({'time': stamp.isoformat(), 'end': end.isoformat(), 'price_ct': price})
    if not any(instant(row['time']) <= now < instant(row['end']) for row in rows):
        unavailable()
    return rows


class EOSPrices:
    def __init__(self):
        self.rows = ()
        self.fetched = None

    def clear(self):
        self.rows = ()
        self.fetched = None

    def update(self, rows, now):
        if not isinstance(rows, list) or not rows or len(rows) > 4096:
            unavailable()
        checked = []
        for row in rows:
            if not isinstance(row, dict):
                unavailable()
            start, end, price = instant(row.get('time')), instant(row.get('end')), number(row.get('price_ct'))
            if start is None or end is None or not 0 < (end - start).total_seconds() <= 3600 or price is None or not -1000 <= price <= 1000:
                unavailable()
            checked.append((start, end, price))
        checked.sort(key=lambda row: row[0])
        if any(a[1] > b[0] for a, b in zip(checked, checked[1:])):
            unavailable()
        self.rows, self.fetched = tuple(checked), now

    def current(self, now):
        # Source resolution checks retrieval freshness in addition to the slot bounds.
        value = next((price for start, end, price in self.rows if start <= now < end), None)
        return Measurement(value, self.fetched)

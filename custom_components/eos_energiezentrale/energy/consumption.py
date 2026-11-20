"""Site consumption from the AC balance, for display, history and accounting.

Never an input for device control. Sources (PV, grid, battery) define the total
consumption: total = PV + grid (import positive) + discharge - charge. A
measured site total only fills in when sources are incomplete and remains a
plausibility check. Separately measured consumers (vehicle, heat pump) are
fitted into the total; short telemetry delays after a switch are estimated:

- ``car_command``: this integration changed the charging power recently;
  the commanded power replaces a not yet updated wallbox value.
- ``heat_drop`` / ``car_drop``: the total fell by about the last value of a
  device that still reports that value, so the device most likely switched off.
- ``proportional``: no specific cause; measured consumers are scaled to fit.
- ``consumer_hold``: a consumer reading is briefly missing; its last value holds.
- ``unmeasured_in_house``: a consumer stays unreadable; its share stays in the
  house consumption so the total is still attributed.
- ``source_balance`` / ``source_hold``: a missing source follows from the
  measured total, or its last value holds briefly.
- ``battery_balance``: a negative total (charge reported before its supply)
  reduces the charge so the balance closes.
"""
from datetime import timedelta

from .domain import number

TOLERANCE_W = 300
TOLERANCE_RATIO = .1
MATCH_RATIO = .15
WINDOW_S = 120
HOUSE_HOLD_S = 900
SOURCE_HOLD_S = 120
SOURCES = ('solar', 'grid', 'battery_charge', 'battery_discharge')


def _tolerance(value):
    return max(TOLERANCE_W, abs(value) * TOLERANCE_RATIO)


def _matches(drop, value):
    return value > 0 and abs(drop - value) <= max(TOLERANCE_W, value * MATCH_RATIO)


class ConsumptionBalance:
    def __init__(self):
        self.held = {}          # key -> (value, time) of the last valid reading
        self.house = None       # (value, time) of the last measured-consistent house value
        self.previous = None    # (total, car, heat) of the last sample
        self.command = None     # (commanded W, time it changed)
        self.deficit = None
        self.deviation_since = None

    def _hold(self, key, value, now, limit):
        if value is not None:
            self.held[key] = (value, now)
            return value, False
        remembered = self.held.get(key)
        if remembered and 0 <= (now - remembered[1]).total_seconds() <= limit:
            return remembered[0], True
        return None, False

    def _sources(self, live, measured, now, estimates):
        values = {}
        for key in SOURCES:
            value = number(live.get(key))
            values[key] = max(0., value) if value is not None and key != 'grid' else value
        missing = [key for key in SOURCES if values[key] is None]
        battery_missing = {'battery_charge', 'battery_discharge'} & set(missing)
        if measured is not None and missing and (set(missing) <= {'battery_charge', 'battery_discharge'}
                                                 or len(missing) == 1):
            # One unknown of the AC balance follows from the measured total.
            pv, grid = values['solar'], values['grid']
            if battery_missing and pv is not None and grid is not None:
                net = pv + grid - measured
                values.update(battery_charge=max(0., net), battery_discharge=max(0., -net))
            elif missing == ['solar'] and grid is not None:
                values['solar'] = max(0., measured + values['battery_charge'] - grid - values['battery_discharge'])
            elif missing == ['grid'] and pv is not None:
                values['grid'] = measured + values['battery_charge'] - pv - values['battery_discharge']
            for key in missing:
                if values[key] is not None:
                    estimates[key] = 'source_balance'
        for key in SOURCES:
            value, held = self._hold(key, values[key], now, SOURCE_HOLD_S)
            if held:
                estimates[key] = 'source_hold'
            values[key] = value
        return values

    def update(self, live, now, *, car_enabled=True, heat_enabled=True, commanded_car_w=None, island=False):
        """Return the balance view; ``live`` is not modified."""
        estimates = {}
        measured = number(live.get('house_total'))
        measured = max(0., measured) if measured is not None else None
        sources = self._sources(live, measured, now, estimates)
        complete = all(sources[key] is not None for key in SOURCES)
        if island and measured is not None:
            # Off-grid the grid meter is no source; the inverter AC output is the site total.
            total = measured
        elif complete:
            total = sources['solar'] + sources['grid'] + sources['battery_discharge'] - sources['battery_charge']
            if total < 0:
                # Charging reported before its supply: the charge cannot exceed the supply.
                sources['battery_charge'] += total
                estimates['battery_charge'] = 'battery_balance'
                total = 0.
        else:
            total = measured
        if commanded_car_w is not None and (self.command is None or self.command[0] != commanded_car_w):
            self.command = (commanded_car_w, now)
        elif commanded_car_w is None:
            self.command = None
        car, car_held = self._hold('car', number(live.get('car')) if car_enabled else 0., now, WINDOW_S)
        heat, heat_held = self._hold('heat', number(live.get('heat')) if heat_enabled else 0., now, WINDOW_S)
        if car_held:
            estimates['car'] = 'consumer_hold'
        if heat_held:
            estimates['heat'] = 'consumer_hold'
        result = {**sources, 'house_total': total, 'house_total_measured': measured, 'complete': complete}
        if total is None:
            self.previous = None
            return {**result, 'house': None, 'consumers': {'house': None, 'car': car, 'heat': heat}, 'estimated': estimates}
        unmeasured = [key for key, value in (('car', car), ('heat', heat)) if value is None]
        for key in unmeasured:
            estimates['house'] = 'unmeasured_in_house'
        car_value, heat_value = car or 0., heat or 0.
        if total - car_value - heat_value < -_tolerance(total) and self.deficit is None:
            recent = self.command is not None and 0 <= (now - self.command[1]).total_seconds() <= WINDOW_S
            self.deficit = {'since': now, 'cause': self._cause(total, car_value, heat_value, recent),
                            'car': car_value, 'heat': heat_value}
        measured_consumers = (car_value, heat_value)
        house, car_value, heat_value = self._fit(total, car_value, heat_value, now, estimates)
        consumers = {'house': house, 'car': None if car is None else car_value, 'heat': None if heat is None else heat_value}
        if 'house' not in estimates and not {'car', 'heat'} & estimates.keys():
            self.house = (house, now)
        self.previous = (total, *measured_consumers)
        # Plausibility of the measured site total against the balance.
        if complete and not island and measured is not None and abs(measured - total) > _tolerance(total):
            self.deviation_since = self.deviation_since or now
        else:
            self.deviation_since = None
        result['deviation_since'] = self.deviation_since.isoformat() if self.deviation_since else None
        return {**result, 'house': house, 'consumers': consumers, 'estimated': estimates}

    def _fit(self, total, car, heat, now, estimates):
        raw = total - car - heat
        recent = self.command is not None and 0 <= (now - self.command[1]).total_seconds() <= WINDOW_S
        previous_house = (self.house[0] if self.house and 0 <= (now - self.house[1]).total_seconds() <= HOUSE_HOLD_S
                          else None)
        if raw >= -_tolerance(total):
            self.deficit = None
        if raw >= 0:
            target = self.command[0] if recent else None
            # Charging rises before the wallbox reports it: the rise belongs to the car.
            if (target is not None and previous_house is not None and target - car >= TOLERANCE_W
                    and raw - previous_house >= TOLERANCE_W):
                estimated = min(target, car + raw - previous_house)
                estimates['car'] = 'car_command'
                return total - estimated - heat, estimated, heat
            return raw, car, heat
        if self.deficit is None:
            # Small timing offset: scale consumers to the total.
            factor = total / (car + heat)
            for key, value in (('car', car), ('heat', heat)):
                if value > 0:
                    estimates[key] = 'proportional'
            return 0., car * factor, heat * factor
        return self._deficit(total, car, heat, now, recent, previous_house, estimates)

    def _cause(self, total, car, heat, recent):
        """Why the measured consumers exceed the total at the start of a deficit."""
        drop = self.previous[0] - total if self.previous else None
        if recent and self.command[0] < car - TOLERANCE_W:
            return 'car_command'
        if drop is not None and heat == self.previous[2] and _matches(drop, heat):
            return 'heat_drop'
        if drop is not None and car == self.previous[1] and _matches(drop, car):
            return 'car_drop'
        return 'proportional'

    def _deficit(self, total, car, heat, now, recent, previous_house, estimates):
        deficit = self.deficit
        cause = deficit['cause'] if (now - deficit['since']).total_seconds() <= WINDOW_S else 'proportional'
        # The estimate ends as soon as the device reports a new value.
        if (cause == 'heat_drop' and heat != deficit['heat'] or cause == 'car_drop' and car != deficit['car']
                or cause == 'car_command' and not (recent and self.command[0] < car - TOLERANCE_W)):
            cause = 'proportional'
        house = min(previous_house or 0., total)
        rest = total - house
        if cause == 'car_command':
            car_value = min(self.command[0], rest)
            heat_value = min(heat, rest - car_value)
        elif cause == 'heat_drop':
            car_value = min(car, rest)
            heat_value = max(0., rest - car_value)
        elif cause == 'car_drop':
            heat_value = min(heat, rest)
            car_value = max(0., rest - heat_value)
        else:
            factor = rest / (car + heat)
            car_value, heat_value = car * factor, heat * factor
        # The device named by the cause carries it; a further reduction of the other is proportional.
        named = {'car_command': 'car', 'car_drop': 'car', 'heat_drop': 'heat'}.get(cause)
        for key, measured, value in (('car', car, car_value), ('heat', heat, heat_value)):
            if abs(measured - value) > 1e-9:
                estimates[key] = cause if key == named else 'proportional'
        if house > 0:
            estimates['house'] = 'held'
        return total - car_value - heat_value, car_value, heat_value


def apply_balance(live, balance, car_enabled=True, heat_enabled=True):
    """Expose the balance in a live sample.

    Raw source readings stay unchanged for control. Display and the local
    history only take values derived from fresh measurements: the balanced
    total when no source had to be estimated, and the house value when no
    consumer had to be estimated. Accounting uses the complete balance with
    its marked estimates (``live['balance']``).
    """
    from .domain import house_only
    live['balance'] = balance
    measured = number(live.get('house_total'))
    live['house_total_measured'] = measured
    sources_estimated = any(key in balance['estimated'] for key in SOURCES)
    total = balance['house_total'] if balance['complete'] and not sources_estimated else measured
    live['house_total'] = total
    consumers_estimated = bool({'house', 'car', 'heat'} & balance['estimated'].keys())
    live['house'] = (balance['house'] if total == balance['house_total'] and not consumers_estimated else
                     house_only(total, number(live.get('car')) if car_enabled else 0,
                                number(live.get('heat')) if heat_enabled else 0))
    return live


def split_vehicles(total, measured, targets):
    """Split an estimated fleet charging power across vehicles."""
    if total is None:
        return {key: None for key in measured}
    known = {key: value for key, value in measured.items() if value is not None}
    base = sum(known.values())
    if base > 0:
        return {key: (value * total / base if value is not None else None) for key, value in measured.items()}
    weights = {key: max(0., targets.get(key) or 0.) for key in measured}
    if sum(weights.values()) > 0:
        return {key: total * weight / sum(weights.values()) for key, weight in weights.items()}
    return {key: total / len(measured) for key in measured} if measured else {}

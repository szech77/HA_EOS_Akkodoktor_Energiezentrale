"""Power-dependent battery and inverter efficiencies from EOS device profiles.

API reference: Akkudoktor-EOS/EOS, ``GET /v1/profile/battery/<name>`` with
``charge_efficiency``/``discharge_efficiency`` over the absolute C-rate (DC, cells and
BMS) and ``GET /v1/profile/inverter/<name>`` with ``ac_to_dc_efficiency`` (charging)
and ``dc_to_ac_efficiency`` (discharging) over the load fraction, i.e. AC power
relative to the inverter's nominal power. Lookups follow EOS: linear or nearest
breakpoint inside the axis, the edge value outside it. EOS itself falls back to the
nearest breakpoint where a curve rejects a query, so "none" and "reject" behave alike.

The accounting books AC-side energy, so the efficiency of a sample is the product of
the inverter conversion and the battery at the measured power.
"""
from math import isfinite

DIRECTIONS = ('charge', 'discharge')
MAX_POINTS = 64
# The accounting accepts efficiencies in this range (see accounting.checked_settings).
MIN_EFFICIENCY = .1
SUMMARY_POINTS = 40


class CurveError(ValueError):
    """A profile does not contain a usable efficiency curve."""


def _number(value):
    return float(value) if type(value) in (int, float) and isfinite(value) else None


def checked_curve(document, axis):
    """Normalized ``{'x', 'y', 'mode'}`` of an EOS efficiency curve document."""
    if not isinstance(document, dict):
        raise CurveError('Efficiency curve missing')
    x, y = document.get(axis), document.get('efficiency')
    if (not isinstance(x, list) or not isinstance(y, list) or not 1 <= len(x) <= MAX_POINTS
            or len(x) != len(y)):
        raise CurveError('Invalid efficiency curve')
    x, y = [_number(value) for value in x], [_number(value) for value in y]
    if (any(value is None or value < 0 for value in x) or any(left >= right for left, right in zip(x, x[1:]))
            or any(value is None or not 0 < value <= 1 for value in y)):
        raise CurveError('Invalid efficiency curve')
    interpolation = document.get('interpolation', 'linear')
    if interpolation not in ('linear', 'nearest', 'none'):
        raise CurveError('Unknown efficiency interpolation')
    return {'x': x, 'y': y, 'mode': 'linear' if interpolation == 'linear' else 'nearest'}


def battery_curves(profile):
    return {direction: checked_curve(profile.get(direction + '_efficiency') if isinstance(profile, dict) else None,
                                     'c_rate') for direction in DIRECTIONS}


def inverter_curves(profile, nominal_power_w):
    nominal = _number(nominal_power_w)
    if nominal is None or not 1 <= nominal <= 1000000:
        raise CurveError('Inverter nominal power missing')
    profile = profile if isinstance(profile, dict) else {}
    return {'charge': checked_curve(profile.get('ac_to_dc_efficiency'), 'load_fraction'),
            'discharge': checked_curve(profile.get('dc_to_ac_efficiency'), 'load_fraction'),
            'nominal_power_w': nominal}


def checked_curves(value):
    """Validate stored or received curves; raises CurveError for anything unusable."""
    if not isinstance(value, dict) or value.keys() - {'battery', 'inverter'} or 'battery' not in value:
        raise CurveError('Invalid efficiency curves')
    battery = value['battery']
    if not isinstance(battery, dict) or battery.keys() != set(DIRECTIONS):
        raise CurveError('Invalid battery efficiency curves')
    result = {'battery': {direction: _stored(battery[direction]) for direction in DIRECTIONS}, 'inverter': None}
    inverter = value.get('inverter')
    if inverter is not None:
        if not isinstance(inverter, dict) or inverter.keys() != {*DIRECTIONS, 'nominal_power_w'}:
            raise CurveError('Invalid inverter efficiency curves')
        nominal = _number(inverter['nominal_power_w'])
        if nominal is None or not 1 <= nominal <= 1000000:
            raise CurveError('Invalid inverter nominal power')
        result['inverter'] = {**{direction: _stored(inverter[direction]) for direction in DIRECTIONS},
                              'nominal_power_w': nominal}
    return result


def _stored(curve):
    if not isinstance(curve, dict) or curve.keys() != {'x', 'y', 'mode'} or curve['mode'] not in ('linear', 'nearest'):
        raise CurveError('Invalid stored efficiency curve')
    checked = checked_curve({'x': curve['x'], 'efficiency': curve['y'], 'interpolation': curve['mode']}, 'x')
    return checked


def lookup(curve, query):
    x, y = curve['x'], curve['y']
    if query <= x[0]:
        return y[0]
    if query >= x[-1]:
        return y[-1]
    if curve['mode'] == 'nearest':
        # Like EOS: exactly between two breakpoints the lower one wins.
        return y[min(range(len(x)), key=lambda index: (abs(x[index] - query), index))]
    for index in range(len(x) - 1):
        if x[index] <= query <= x[index + 1]:
            share = (query - x[index]) / (x[index + 1] - x[index])
            return y[index] + share * (y[index + 1] - y[index])
    return y[-1]


def efficiency(effective, direction, watts):
    """AC-side efficiency at a measured AC power; the constant value without curves."""
    constant = effective[direction + '_efficiency']
    curves = effective.get('curves')
    power = _number(watts)
    capacity = _number(effective.get('capacity_wh'))
    if not curves or power is None or power <= 0 or not capacity:
        return constant
    inverter = curves.get('inverter')
    conversion = lookup(inverter[direction], power / inverter['nominal_power_w']) if inverter else 1.
    # The battery sees the DC side: less power when charging, more when discharging.
    dc_power = power * conversion if direction == 'charge' else power / conversion
    battery = lookup(curves['battery'][direction], dc_power / capacity)
    return min(1., max(MIN_EFFICIENCY, conversion * battery))


def summary(effective):
    """Lowest and highest AC-side efficiency up to the maximum power, for display."""
    curves = (effective or {}).get('curves')
    capacity = _number((effective or {}).get('capacity_wh'))
    if not curves or not capacity:
        return None
    inverter = curves.get('inverter')
    result = {'inverter': inverter is not None}
    for direction in DIRECTIONS:
        maximum = inverter['nominal_power_w'] if inverter else capacity * curves['battery'][direction]['x'][-1]
        values = [efficiency(effective, direction, maximum * (index + 1) / SUMMARY_POINTS)
                  for index in range(SUMMARY_POINTS)]
        result[direction] = [round(min(values), 4), round(max(values), 4)]
    return result

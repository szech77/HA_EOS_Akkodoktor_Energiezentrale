"""Numeric diagnostics of all configured measurement sources for the settings page.

Pure presentation of the current snapshot: values are the same ones control,
display and accounting use. No HA state, credentials or entity attributes beyond
the configured entity id are exposed.
"""
from .domain import energy_balance, instant, number
from .measurement_sources import SOURCES

UNITS = {**{key: unit for key, (_, _, unit, _) in SOURCES.items()}, 'heat_load': '%',
         'battery_soc': '%', 'battery_charge': 'W', 'battery_discharge': 'W', 'car': 'W', 'house': 'W'}
PLUGIN_MEASUREMENTS = (('battery', 'battery_soc'), ('battery', 'battery_charge'),
                       ('battery', 'battery_discharge'), ('wallbox', 'car'))
DEVICE_VALUES = ('solar', 'inverter_ac', 'grid', 'house_total')


def _age(sample, now):
    stamp = instant(sample) if isinstance(sample, str) else None
    return max(0., (now - stamp).total_seconds()) if stamp else None


def _value(live, key, entry):
    # The vehicle SoC row shows the sensor reading, not the controller's
    # estimate (fleets carry the SoC per vehicle, not in the shared live data).
    value = number(entry['value'] if key == 'car_soc' and 'value' in entry else live.get(key))
    if key == 'heat_load' and value is not None:
        return value * 100
    return value


def _rows(data, now):
    live = data.get('live') or {}
    report = data.get('source_configuration') or {}
    sources = report.get('sources') or {}
    missing = set(report.get('missing') or ())
    rows = []
    for key in SOURCES:
        entry = sources.get(key)
        if not isinstance(entry, dict) or (entry.get('source') is None and key not in missing):
            continue
        source = entry.get('source') or {}
        rows.append({'key': key, 'unit': UNITS[key], 'value': _value(live, key, entry) if entry.get('available') else None,
                     'source_type': source.get('type'), 'source': source.get('name'),
                     'available': bool(entry.get('available')), 'reason': entry.get('reason'),
                     'age_s': _age(entry.get('sample'), now), 'max_age_s': entry.get('max_age_s')})
    plugins = data.get('plugins') or {}
    for kind, key in PLUGIN_MEASUREMENTS:
        plugin = plugins.get(kind)
        if not isinstance(plugin, dict) or key not in (plugin.get('measurements') or ()):
            continue
        value = number(live.get(key))
        rows.append({'key': key, 'unit': UNITS[key], 'value': value, 'source_type': 'plugin',
                     'source': plugin.get('name'), 'available': value is not None,
                     'reason': None if value is not None else 'state_unavailable', 'age_s': None, 'max_age_s': None})
    return rows


def _vehicles(data):
    result = []
    for vehicle in data.get('vehicles') or ():
        live = vehicle.get('live') or {}
        result.append({'name': vehicle.get('name'), 'car': number(live.get('car')), 'car_soc': number(live.get('car_soc')),
                       'soc_source': live.get('soc_source'), 'connected': live.get('car_connected')})
    return result


def _devices(data):
    group = data.get('battery_group')
    result = []
    for device in (group.get('devices') or ()) if isinstance(group, dict) else ():
        measurements = device.get('measurements') or {}
        values = {key: number(measurements.get(key)) for key in DEVICE_VALUES if key in measurements}
        if device.get('battery'):
            values.update(battery_soc=number(device.get('soc')), battery_charge=number(device.get('charge')),
                          battery_discharge=number(device.get('discharge')))
        plugin = device.get('plugin') or {}
        result.append({'name': device.get('name'), 'plugin': plugin.get('name'), 'available': bool(device.get('available')),
                       'read_error': device.get('read_error'), 'values': values})
    return result


def source_diagnostics(data, now):
    live = data.get('live') or {}
    def positive(key):
        value = number(live.get(key))
        return max(0., value) if value is not None else None
    balance = energy_balance(positive('solar'), number(live.get('grid')), positive('battery_discharge'),
                             positive('battery_charge'), positive('house_total'))
    features = data.get('features') or {}
    derived = {'house': number(live.get('house')), 'house_total': number(live.get('house_total')),
               'car': number(live.get('car')) if features.get('car') else 0.,
               'heat': number(live.get('heat')) if features.get('heat') else 0.}
    return {'time': live.get('time'), 'sources': _rows(data, now), 'derived': derived,
            'balance': balance, 'devices': _devices(data), 'vehicles': _vehicles(data)}

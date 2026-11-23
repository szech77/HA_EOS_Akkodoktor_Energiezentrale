"""Resolve optional HA sensors before declared plugin measurements, per poll.

Internal rows are local snapshots, never registered HA entities. This lets all
consumers (control, fleet reservation, display, history) use the same source.
"""
from collections.abc import Mapping
from datetime import datetime

from .contracts import BatteryReading, Measurement, PluginContractError
from .clients import reading, measurement_max_age
from .sanitiser import bounded
from .domain import instant, number
from .eos_prices import EOSPrices, PRICE_MAX_AGE_S

# Unchanged vehicle values may legitimately keep their timestamp for a day;
# an older report is no basis for charging decisions or diagnostics.
CAR_SOC_MAX_AGE_S = 36 * 3600

SOURCES = {
    "solar": ("pv_entity", "solar", "W", 45),
    "grid": ("grid_entity", "power", "W", 45),
    "house_total": ("house_entity", "power", "W", 120),
    "heat": ("heat_entity", "power", "W", 120),
    "price": ("price_entity", "price", "ct/kWh", 3600),
    "car_soc": ("car_soc_entity", "soc", "%", CAR_SOC_MAX_AGE_S),
    "heat_load": ("heat_load_entity", "soc", "%", 120),
    # Vehicle range in km (mi sensors are converted); optional, display only.
    "car_range": ("car_range_entity", "range", "km", CAR_SOC_MAX_AGE_S),
}
MEASUREMENT_KEYS = frozenset(SOURCES) | {"battery_soc", "battery_charge", "battery_discharge", "car", "inverter_ac"}
SENSOR_OPTIONS = frozenset(item[0] for item in SOURCES.values())


def checked_measurements(values, declared, now):
    if not isinstance(values, Mapping) or values.keys() - set(declared):
        raise PluginContractError("Undeclared plugin measurements")
    result = {}
    for key, item in values.items():
        if key not in MEASUREMENT_KEYS or not isinstance(item, Measurement):
            raise PluginContractError("Invalid plugin measurement")
        limit = 100 if key in {"car_soc", "battery_soc", "heat_load"} else 5000 if key == "car_range" else 1000000
        low = -1000 if key == "price" else -limit if key in {"grid", "inverter_ac"} else 0
        high = 1000 if key == "price" else limit
        value = bounded(item.value, low, high)
        stamp = item.sample
        age = SOURCES[key][3] if key in SOURCES else 120
        age = measurement_max_age(key, value, age)
        if (not isinstance(stamp, datetime) or stamp.utcoffset() is None
                or not 0 <= (now - stamp).total_seconds() < age):
            value = None
        result[key] = Measurement(value, stamp if value is not None else None)
    return result


def resolve_sources(options, states, providers, now, keys=None, eos_prices=None):
    """Sensor first; then battery plugin, then wallbox plugin. Never fail over a
    configured-but-unavailable sensor. Preserve fleet-adjusted internal rows.
    Confirmed backup replaces grid-based house totals with fresh inverter AC.
    """
    from copy import copy
    from .power_supply import configured_supply, supply_view
    providers = tuple(providers)
    supply = (configured_supply(options, states, now) if options.get('backup_mode_entity') else
              next((sample.power_supply for _, sample in providers if isinstance(sample, BatteryReading)), None))
    backup = supply_view(supply, now)['state'] == 'backup'
    # Preserve metadata on a captured HA state batch (e.g. registry associations).
    opts, rows = dict(options), copy(states) if isinstance(states, dict) else dict(states)
    sources = {}
    for key, (option, kind, unit, age) in SOURCES.items():
        if keys is not None and key not in keys:
            continue
        entity = options.get(option, "")
        if key == 'price' and entity == '@eos:price':
            entity = ''
        opts.setdefault(option, entity)
        source = {"type": "sensor", "name": entity} if entity else None
        if key == 'house_total' and backup:
            for driver, sample in providers:
                declared = getattr(driver, 'measurement_keys', ())
                if not isinstance(declared, tuple) or 'inverter_ac' not in declared:
                    continue
                item = getattr(sample, 'measurements', {}).get('inverter_ac')
                value = bounded(item.value, 0, 1000000) if isinstance(item, Measurement) else None
                stamp = item.sample if isinstance(item, Measurement) else None
                if (not isinstance(stamp, datetime) or stamp.utcoffset() is None
                        or not 0 <= (now-stamp).total_seconds() < age):
                    value = None
                entity = '@backup:house_total'
                opts[option] = entity
                rows[entity] = {'state':value, 'last_reported':stamp.isoformat() if value is not None else None,
                                'attributes':{'unit_of_measurement':unit}}
                source = {'type':'backup', 'name':driver.info.name, 'measurement':'inverter_ac'}
                break
        if not entity:
            for driver, sample in providers:
                declared = getattr(driver, "measurement_keys", ())
                if not isinstance(declared, tuple) or key not in declared:
                    continue
                entity = "@plugin:" + key
                opts[option] = entity
                extra = getattr(sample, "measurements", {})
                item = extra.get(key) if isinstance(extra, Mapping) else None
                if entity not in rows:
                    rows[entity] = {"state": item.value if isinstance(item, Measurement) else None,
                        "last_reported": item.sample.isoformat() if isinstance(item, Measurement) and item.sample else None,
                        "last_updated": item.sample.isoformat() if isinstance(item, Measurement) and item.sample else None,
                        "attributes": {"unit_of_measurement": unit}}
                if key == "car_soc": opts["car_soc_scale"] = "percent"
                if key == "heat_load": opts["heat_load_scale"] = "percent"
                source = {"type": "plugin", "name": driver.info.name}
                break
        if key == 'price' and not entity and options.get('eos_url'):
            entity = '@eos:price'
            opts[option] = entity
            item = eos_prices.current(now) if isinstance(eos_prices, EOSPrices) else Measurement(None, None)
            rows[entity] = {'state': item.value, 'last_reported': item.sample.isoformat() if item.sample else None,
                            'attributes': {'unit_of_measurement': unit}}
            source = {'type': 'eos', 'name': 'Akkudoktor EOS'}
            age = PRICE_MAX_AGE_S
        raw = rows.get(entity, {})
        age = measurement_max_age(kind, raw.get('state'), age, raw.get('attributes', {}).get('unit_of_measurement'))
        available = bool(source and reading(rows, entity, now, kind, age) is not None)
        row = rows.get(entity, {})
        stamp = instant(row.get('last_reported') or row.get('last_updated'))
        reason = (None if available else 'not_configured' if source is None else
            'state_unavailable' if number(row.get('state')) is None else
            'sample_missing' if stamp is None else 'future_sample' if now < stamp else
            'stale' if (now-stamp).total_seconds() >= age else 'unit_invalid')
        if source and source['type'] == 'eos' and not available:
            if stamp and (now - stamp).total_seconds() >= age:
                reason = 'stale'
            rows[entity]['state'] = None  # Live/control/history also reject expired cached prices.
        sources[key] = {"source": source, "available": available, 'reason':reason, 'max_age_s':age,
                        'sample': stamp.isoformat() if source and stamp else None}
    required = {"solar", "grid", "house_total", "price"}
    if options.get("wallbox_type") != "none": required.add("car_soc")
    if opts.get("heat_entity"): required.add("heat")
    required &= sources.keys()
    report = {"sources": sources,
              "missing": sorted(key for key in required if sources[key]["source"] is None),
              "unavailable": sorted(key for key in required if sources[key]["source"] is not None and not sources[key]["available"])}
    return opts, rows, report

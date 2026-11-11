"""Resolve optional HA sensors before declared plugin measurements, per poll.

Internal rows are local snapshots, never registered HA entities. This lets all
consumers (control, fleet reservation, display, history) use the same source.
"""
from collections.abc import Mapping
from datetime import datetime

from .contracts import Measurement, PluginContractError
from .clients import reading
from .sanitiser import bounded

SOURCES = {
    "solar": ("pv_entity", "power", "W", 45),
    "grid": ("grid_entity", "power", "W", 45),
    "house_total": ("house_entity", "power", "W", 120),
    "heat": ("heat_entity", "power", "W", 120),
    "price": ("price_entity", "price", "ct/kWh", 3600),
    "car_soc": ("car_soc_entity", "soc", "%", 120),
    "heat_load": ("heat_load_entity", "soc", "%", 120),
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
        limit = 100 if key in {"car_soc", "battery_soc", "heat_load"} else 1000000
        low = -1000 if key == "price" else -limit if key in {"grid", "inverter_ac"} else 0
        high = 1000 if key == "price" else limit
        value = bounded(item.value, low, high)
        stamp = item.sample
        age = SOURCES[key][3] if key in SOURCES else 120
        if (not isinstance(stamp, datetime) or stamp.utcoffset() is None
                or not 0 <= (now - stamp).total_seconds() < age):
            value = None
        result[key] = Measurement(value, stamp if value is not None else None)
    return result


def resolve_sources(options, states, providers, now, keys=None):
    """Sensor first; then battery plugin, then wallbox plugin. Never fail over a
    configured-but-unavailable sensor. Preserve fleet-adjusted internal rows.
    """
    opts, rows = dict(options), dict(states)
    sources = {}
    for key, (option, kind, unit, age) in SOURCES.items():
        if keys is not None and key not in keys:
            continue
        entity = options.get(option, "")
        opts.setdefault(option, entity)
        source = {"type": "sensor", "name": entity} if entity else None
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
        sources[key] = {"source": source, "available": bool(source and reading(rows, entity, now, kind, age) is not None)}
    required = {"solar", "grid", "house_total", "price"}
    if options.get("wallbox_type") != "none": required.add("car_soc")
    if opts.get("heat_entity"): required.add("heat")
    required &= sources.keys()
    report = {"sources": sources,
              "missing": sorted(key for key in required if sources[key]["source"] is None),
              "unavailable": sorted(key for key in required if sources[key]["source"] is not None and not sources[key]["available"])}
    return opts, rows, report

"""Small local cache for samples and modes, with optional InfluxQL history."""
import json
import sqlite3
from contextlib import closing
from datetime import timedelta

from .domain import house_only, instant, number


def forecast_rows(solution, now):
    if not isinstance(solution, dict):
        return []
    start = instant(solution.get("start_solution_datetime"))
    step = number(solution.get("interval_seconds"))
    if not start or not step or not 60 <= step <= 3600 or not 0 <= (now - start).total_seconds() < 3600:
        return []
    params, result = solution.get("parameters") or {}, solution.get("result") or {}
    ems = params.get("ems") or {}
    battery, ev = params.get("pv_battery") or {}, params.get("ev") or {}
    hours = step / 3600

    def at(mapping, key, index):
        series = mapping.get(key)
        return number(series[index]) if isinstance(series, list) and index < len(series) else None

    def power_from_soc(settings, key, index, bidirectional=False):
        start_soc, end_soc = at(result, key, index), at(result, key, index + 1)
        capacity = number(settings.get("capacity_wh"))
        if start_soc is None or end_soc is None or not capacity:
            return None
        delta = (end_soc - start_soc) * capacity / 100 / hours
        efficiency = number(settings.get("charging_efficiency"))
        if delta >= 0:
            return delta / efficiency if efficiency else None
        return delta * (number(settings.get("discharging_efficiency")) or 1) if bidirectional else 0

    rows = []
    for i in range(min(1441, int(25 * 3600 / step))):
        time = start + timedelta(seconds=step * i)
        if time + timedelta(seconds=step) <= now or time > now + timedelta(hours=24):
            continue
        solar = at(ems, "pv_forecast_wh", i)
        load = at(ems, "total_load", i)
        price = at(ems, "electricity_price_per_wh", i)
        export = at(result, "grid_feed_in_wh_per_hour", i)
        grid_import = at(result, "grid_consumption_wh_per_hour", i)
        row = {"time": max(now, time).isoformat(), "end": (time + timedelta(seconds=step)).isoformat(),
               "solar": solar / hours if solar is not None else None,
               "house_total": load / hours if load is not None else None,
               "price": price * 100000 if price is not None else None,
               "grid": (grid_import - export) / hours if grid_import is not None and export is not None else None,
               "battery": power_from_soc(battery, "battery_soc_per_hour", i, True),
               "battery_soc": at(result, "battery_soc_per_hour", i),
               "car": power_from_soc(ev, "ev_soc_per_hour", i),
               "car_soc": at(result, "ev_soc_per_hour", i)}
        if any(value is not None for key, value in row.items() if key not in {"time", "end"}):
            rows.append(row)
    return rows


class History:
    def __init__(self, path):
        self.path = path
        with closing(self.connect()) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS samples (stamp INTEGER PRIMARY KEY, payload TEXT NOT NULL)")

    def connect(self):
        return sqlite3.connect(self.path)

    def write(self, now, values):
        minute = int(now.timestamp()) // 60 * 60
        with closing(self.connect()) as db, db:
            db.execute("INSERT OR REPLACE INTO samples VALUES (?, ?)", (minute, json.dumps(values)))
            db.execute("DELETE FROM samples WHERE stamp < ?", (minute - 172800,))

    def read(self, now):
        with closing(self.connect()) as db:
            rows = db.execute("SELECT payload FROM samples WHERE stamp >= ? ORDER BY stamp",
                              (int(now.timestamp()) - 86400,)).fetchall()
        return [json.loads(row[0]) for row in rows]


def influx_series(config):
    options = config.options
    units = [("W", 1), ("kW", 1000)]
    sources = {key: (options[key + "_entity"], units) for key in ("pv", "house", "grid", "heat")}
    sources["price"] = (options["price_entity"], [("EUR/kWh", 100), ("€/kWh", 100), ("ct/kWh", 1)])
    # Existing drivers expose optional entity mappings for external history.
    battery, wallbox = getattr(config.battery, "ids", {}), getattr(config.wallbox, "ids", {})
    sources.update({"car": (wallbox.get("power", ""), units),
                    "battery_charge": (battery.get("charge_power", ""), units),
                    "battery_discharge": (battery.get("discharge_power", ""), units),
                    "battery_soc": (battery.get("soc", ""), [("%", 1)]),
                    "car_soc": (options["car_soc_entity"], [("state", 100)] if options["car_soc_scale"] == "factor" else [("%", 1)])})
    rows = {}
    for key, (entity, measurements) in sources.items():
        for stamp, value in config.influx.history(entity, measurements):
            rows.setdefault(stamp, {"time": stamp})[key] = value
    for row in rows.values():
        row["solar"] = row.get("pv")
        row["house_total"] = row.get("house")
        row["house"] = house_only(row.get("house_total"), row.get("car"), row.get("heat"))
        if "battery_charge" in row and "battery_discharge" in row:
            row["battery"] = row["battery_charge"] - row["battery_discharge"]
    return [rows[key] for key in sorted(rows)]

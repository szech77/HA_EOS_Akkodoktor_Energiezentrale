"""Validated controller configuration and durable daily settings."""
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from .clients import ENTITY, EOS, Influx
from .domain import instant, number
from .drivers import BATTERY_DRIVERS, WALLBOX_DRIVERS

DAILY = {"schedule": "off", "departure": "", "departure_time": "07:30",
         "weekdays": [0, 1, 2, 3, 4], "target_soc": 80, "pv_target_soc": 80,
         "reserve_w": 0, "pv": False, "fast": False, "battery_pv_support": True,
         "phase_auto": True, "regulation_interval_s": None}


def daily_settings(raw, interval):
    if not isinstance(raw, dict) or raw.keys() - DAILY.keys():
        raise ValueError("Unbekannte Alltagseinstellung")
    values = {**DAILY, "regulation_interval_s": interval, **raw}
    for key in ("pv", "fast", "battery_pv_support", "phase_auto"):
        if type(values[key]) is not bool:
            raise ValueError(f"Ungültige Einstellung: {key}")
    for key, low, high in (("target_soc", 1, 100), ("pv_target_soc", 1, 100),
                           ("reserve_w", 0, 500), ("regulation_interval_s", 5, 120)):
        if type(values[key]) is not int or not low <= values[key] <= high:
            raise ValueError(f"Ungültiger Bereich: {key}")
    if values["schedule"] not in ("off", "once", "weekly"):
        raise ValueError("Ungültiger Zeitplan")
    if (not isinstance(values["departure"], str)
            or (values["schedule"] == "once" and not instant(values["departure"]))):
        raise ValueError("Einmaliger Termin benötigt Datum und Zeitzone")
    if not isinstance(values["departure_time"], str) or not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", values["departure_time"]):
        raise ValueError("Ungültige Abfahrtszeit")
    days = values["weekdays"]
    if not isinstance(days, list) or any(type(day) is not int or not 0 <= day <= 6 for day in days):
        raise ValueError("Ungültige Wochentage")
    values["weekdays"] = sorted(set(days))
    if values["schedule"] == "weekly" and not days:
        raise ValueError("Mindestens einen Wochentag auswählen")
    return values


def save(path, value):
    pending = path.with_suffix(".tmp")
    pending.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    pending.replace(path)


class Configuration:
    def __init__(self, options, ha, directory):
        self.options = options
        self.zone = ZoneInfo(options["timezone"])
        for key in ("pv_entity", "house_entity", "grid_entity", "heat_entity", "price_entity", "car_soc_entity"):
            if not ENTITY.fullmatch(options[key]) or not options[key].startswith("sensor."):
                raise ValueError(f"Ungültige Sensorentität: {key}")
        if not 0 <= options["battery_min_soc"] < options["battery_max_soc"] <= 100:
            raise ValueError("Ungültige Speichergrenzen")
        for key in ("battery_resource", "vehicle_resource"):
            if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", options[key]):
                raise ValueError("Ungültige EOS-Ressource")
        for key, low, high in (("capacity_wh", 1000, 300000), ("charging_efficiency", 0.1, 1),
                               ("grid_limit_w", 1380, 100000), ("max_current_a", 6, 32),
                               ("phase_wait_s", 10, 600), ("regulation_interval_s", 5, 120)):
            value = number(options[key])
            if value is None or not low <= value <= high:
                raise ValueError("Ungültiger technischer Parameter")
        if options["battery_type"] not in BATTERY_DRIVERS or options["wallbox_type"] not in WALLBOX_DRIVERS:
            raise ValueError("Unbekannter Hardwaretyp")
        self.battery = BATTERY_DRIVERS[options["battery_type"]](ha, json.loads(options["battery_parameters"]))
        self.wallbox = WALLBOX_DRIVERS[options["wallbox_type"]](ha, json.loads(options["wallbox_parameters"]))
        self.eos = EOS(options["eos_url"])
        self.influx = Influx(options["influx_url"], options["influx_database"],
                             options["influx_user"], options["influx_password"])
        self.directory = Path(directory)
        self.file = self.directory / "daily.json"
        raw = json.loads(self.file.read_text(encoding="utf-8")) if self.file.exists() else {}
        self.daily = daily_settings({**raw, "fast": False}, options["regulation_interval_s"])

    def update(self, values):
        checked = daily_settings(values, self.options["regulation_interval_s"])
        save(self.file, {**checked, "fast": False})
        self.daily = checked

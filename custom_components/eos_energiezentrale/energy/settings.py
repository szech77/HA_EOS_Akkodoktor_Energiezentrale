"""Validated controller configuration and durable daily settings."""
import json
import os
import re
from pathlib import Path
from zoneinfo import ZoneInfo

from .clients import ENTITY, EOS, Influx
from .domain import instant, number
from .drivers import BATTERY_DRIVERS, WALLBOX_DRIVERS

DAILY = {"schedule": "off", "departure": "", "departure_time": "07:30",
         "weekdays": [0, 1, 2, 3, 4], "target_soc": 80, "pv_target_soc": 80,
         "reserve_w": 0, "pv": False, "fast": False, "battery_pv_support": True,
         "phase_auto": True, "regulation_interval_s": None,
         "battery_min_soc": 20, "battery_max_soc": 100,
         "battery_pv_start": False, "battery_pv_min_soc": 50, "battery_pv_wait_s": 60,
         "battery_pv_surplus_w": 150}


def daily_settings(raw, interval):
    if not isinstance(raw, dict) or raw.keys() - DAILY.keys():
        raise ValueError("Unbekannte Alltagseinstellung")
    values = {**DAILY, "regulation_interval_s": interval, **raw}
    for key in ("pv", "fast", "battery_pv_support", "battery_pv_start", "phase_auto"):
        if type(values[key]) is not bool:
            raise ValueError(f"Ungültige Einstellung: {key}")
    for key, low, high in (("target_soc", 1, 100), ("pv_target_soc", 1, 100),
                           ("reserve_w", 0, 500), ("regulation_interval_s", 5, 120),
                           ("battery_min_soc", 0, 99), ("battery_max_soc", 1, 100),
                           ("battery_pv_min_soc", 0, 98), ("battery_pv_wait_s", 10, 600),
                           ("battery_pv_surplus_w", 1, 5000)):
        if type(values[key]) is not int or not low <= values[key] <= high:
            raise ValueError(f"Ungültiger Bereich: {key}")
    if values["battery_min_soc"] >= values["battery_max_soc"]:
        raise ValueError("Battery minimum must be below maximum SoC")
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


def influx_credential(options, environment=None):
    """Resolve the external secret only at runtime, without persisting its value."""
    env_name = options.get("influx_password_env", "")
    if not env_name:
        return options["influx_password"]
    if not isinstance(env_name, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", env_name):
        raise ValueError("Invalid external secret name")
    source = os.environ if environment is None else environment
    value = source.get(env_name)
    if not isinstance(value, str) or not value:
        raise ValueError("External InfluxDB secret is unavailable")
    return value


class Configuration:
    def __init__(self, options, ha, directory):
        self.options = options
        self.zone = ZoneInfo(options["timezone"])
        for key in ("pv_entity", "house_entity", "grid_entity", "heat_entity", "price_entity", "car_soc_entity", "heat_load_entity"):
            if options.get(key, "") == "":
                continue
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
        from .devices import battery_driver
        self.battery = battery_driver(options,ha)
        self.wallbox = WALLBOX_DRIVERS[options["wallbox_type"]](ha, json.loads(options["wallbox_parameters"]))
        self.eos = EOS(options["eos_url"])
        self.influx = Influx(options["influx_url"], options["influx_database"],
                             options["influx_user"], influx_credential(options))
        self.directory = Path(directory)
        self.control_file = self.directory / "control.json"
        control = json.loads(self.control_file.read_text(encoding="utf-8")) if self.control_file.exists() else {"enabled": False}
        if (not isinstance(control, dict) or control.keys() != {"enabled"}
                or type(control["enabled"]) is not bool):
            raise ValueError("Invalid persisted control setting")
        self.control_enabled = control["enabled"]
        self.file = self.directory / "daily.json"
        raw = json.loads(self.file.read_text(encoding="utf-8")) if self.file.exists() else {}
        self.battery_limits_managed = raw.pop("_battery_limits_managed", False)
        if type(self.battery_limits_managed) is not bool:
            raise ValueError("Invalid battery limits synchronization metadata")
        self.daily = daily_settings({"battery_min_soc": options["battery_min_soc"],
                                     "battery_max_soc": options["battery_max_soc"],
                                     **raw, "fast": False}, options["regulation_interval_s"])

    def update(self, values, *, manage_battery_limits=False):
        checked = daily_settings({"battery_min_soc": self.daily["battery_min_soc"],
                                  "battery_max_soc": self.daily["battery_max_soc"], **values},
                                 self.options["regulation_interval_s"])
        managed = self.battery_limits_managed or manage_battery_limits
        persisted = {**checked, "fast": False}
        if managed:
            persisted["_battery_limits_managed"] = True
        save(self.file, persisted)
        self.daily = checked
        self.battery_limits_managed = managed


    def set_control_enabled(self, enabled):
        if type(enabled) is not bool:
            raise ValueError("Explicit boolean required for control setting")
        if enabled != self.control_enabled:
            save(self.control_file, {"enabled": enabled})
            self.control_enabled = enabled

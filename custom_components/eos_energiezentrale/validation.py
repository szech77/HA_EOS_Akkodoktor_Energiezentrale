"""Commissioning validation shared by configuration flow and setup."""
import json
import re
from zoneinfo import ZoneInfo

from .energy.clients import ENTITY, EOS, Influx
from .energy.domain import number
from .energy.drivers import BATTERY_DRIVERS, WALLBOX_DRIVERS
from .energy.measurement_sources import SENSOR_OPTIONS


def validate_options(options):
    name = options.get("vehicle_name", "E-Auto")
    if (not isinstance(name, str) or not 1 <= len(name.strip()) <= 60
            or any(ord(char) < 32 or ord(char) == 127 for char in name)):
        raise ValueError("Vehicle name must contain 1 to 60 printable characters")
    weather = options.get("weather_entity", "")
    if not isinstance(weather, str) or (weather and (not ENTITY.fullmatch(weather) or not weather.startswith("weather."))):
        raise ValueError("Invalid weather entity")
    env_name = options.get("influx_password_env", "")
    if not isinstance(env_name, str) or (env_name and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", env_name)):
        raise ValueError("Invalid external secret name")
    if env_name and options.get("influx_password"):
        raise ValueError("Choose either a password or an external secret")
    ZoneInfo(options["timezone"])
    EOS(options["eos_url"])
    Influx(options["influx_url"], options["influx_database"], options["influx_user"], options["influx_password"])
    for key in ("pv_entity", "grid_entity", "house_entity", "heat_entity", "price_entity", "car_soc_entity", "heat_load_entity"):
        if key in SENSOR_OPTIONS and options.get(key, "") == "":
            continue
        if not isinstance(options[key], str) or not ENTITY.fullmatch(options[key]) or not options[key].startswith("sensor."):
            raise ValueError("Invalid source entity")
    if options["language"] not in {"auto", "en", "de"} or options["car_soc_scale"] not in {"factor", "percent"}:
        raise ValueError("Invalid language or SoC unit")
    if options.get("heat_load_scale","percent") not in {"percent","factor"}:
        raise ValueError("Invalid heat pump load scale")
    peak = number(options.get("pv_peak_w",10000))
    if peak is None or not 1<=peak<=1000000:
        raise ValueError("Invalid PV reference power")
    if not 0 <= options["battery_min_soc"] < options["battery_max_soc"] <= 100:
        raise ValueError("Invalid battery limits")
    for key in ("battery_resource", "vehicle_resource"):
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", options[key]):
            raise ValueError("Invalid resource")
    if options["battery_resource"] == options["vehicle_resource"]:
        raise ValueError("Resources must be different")
    if type(options["allow_battery_export"]) is not bool:
        raise ValueError("Invalid export permission")
    for key, low, high in (("display_transition_s",0,120),("sensor_alignment_s",1,60),("command_settle_s",5,300),("display_hold_s",60,86400),("capacity_wh", 1000, 300000), ("charging_efficiency", .1, 1),
                           ("grid_limit_w", 1380, 100000), ("max_current_a", 6, 32),
                           ("phase_wait_s", 10, 600), ("regulation_interval_s", 5, 120),
                           ("battery_charge_w", 0, 50000), ("battery_discharge_w", 0, 50000)):
        value = number(options[key])
        if type(options[key]) is bool or value is None or not low <= value <= high:
            raise ValueError("Invalid technical limit")
    from .energy.devices import battery_driver
    battery_driver(options,None)
    for kind, registry in (("wallbox", WALLBOX_DRIVERS),):
        if options[kind + "_type"] not in registry:
            raise ValueError("Unsupported hardware")
        registry[options[kind + "_type"]](None, json.loads(options[kind + "_parameters"]))

    from .energy.fleet import vehicle_options
    for _, values in vehicle_options(options):
        validate_options(values)

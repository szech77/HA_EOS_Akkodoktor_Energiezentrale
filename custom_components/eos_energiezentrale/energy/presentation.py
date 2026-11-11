"""Display-only power references and optional normalized heat-pump utilization."""
from .clients import reading
from .contracts import WallboxFeatures
from .domain import number, instant


def heat_utilization(states,options,now):
    entity = options.get("heat_load_entity","")
    if not entity:
        return None
    value = reading(states,entity,now,"soc",options.get("display_hold_s",900))
    scale = options.get("heat_load_scale","percent")
    unit = states.get(entity,{}).get("attributes",{}).get("unit_of_measurement")
    if unit not in ({None,"1"} if scale=="factor" else {None,"%"}):
        return None
    limit = 1 if scale=="factor" else 100
    return value/limit if value is not None and 0<=value<=limit else None


def power_references(options,live,features):
    phases = live.get("phases") if isinstance(features,WallboxFeatures) and not features.phase_switching else 3
    current = number(options.get("max_current_a",16))
    car = min(11000,current*230*phases) if current is not None and phases in (1,3) else None
    if isinstance(features,WallboxFeatures) and features.optional_connection:
        car = live.get('effective_charge_power_w')
    return {"solar":options.get("pv_peak_w",10000),"car":car,
            "battery_charge":options.get("battery_charge_w"),"battery_discharge":options.get("battery_discharge_w")}


WEATHER_CONDITIONS = frozenset({"clear-night", "cloudy", "exceptional", "fog", "hail",
    "lightning", "lightning-rainy", "partlycloudy", "pouring", "rainy", "snowy",
    "snowy-rainy", "sunny", "windy", "windy-variant"})


def weather_display(states, options, now):
    """Read current weather for display only; never infer weather from a forecast."""
    entity = options.get("weather_entity", "")
    if not entity:
        candidates = sorted(key for key, item in states.items() if key.startswith("weather.")
                            and item.get("state") in WEATHER_CONDITIONS)
        entity = candidates[0] if candidates else None
    if not entity:
        return None
    item = states.get(entity, {})
    reported = instant(item.get("last_reported") or item.get("last_updated"))
    current = reported is not None and 0 <= (now-reported).total_seconds() <= 3600
    condition = item.get("state") if current else None
    if condition not in WEATHER_CONDITIONS:
        condition = "unknown"
    attributes = item.get("attributes", {})
    unit = attributes.get("temperature_unit", "°C")
    temperature = number(attributes.get("temperature")) if current and condition != "unknown" else None
    celsius = ((temperature-32)*5/9 if unit == "°F" else temperature-273.15 if unit == "K"
               else temperature) if temperature is not None else None
    if unit not in {"°C", "°F", "K"} or celsius is None or not -100 <= celsius <= 70:
        temperature = None
    return {"condition": condition, "temperature": temperature,
            "unit": unit if unit in {"°C", "°F", "K"} else "°C"}


def daily_pv_forecast(rows, now, zone):
    """Integrate covered forecast slots over local calendar days, without overlaps."""
    from datetime import datetime, time, timedelta, timezone
    from zoneinfo import ZoneInfo

    local_zone = ZoneInfo(zone)
    today = now.astimezone(local_zone).date()
    slots = []
    for row in rows:
        start, end = instant(row.get("time")), instant(row.get("end"))
        power = number(row.get("solar"))
        if start is not None and end is not None and power is not None and power >= 0 and end > start:
            slots.append((start.astimezone(timezone.utc), end.astimezone(timezone.utc), power))
    slots.sort(key=lambda item: item[0])
    result = []
    for offset in range(3):
        day = today + timedelta(days=offset)
        boundary = datetime.combine(day, time.min, local_zone).astimezone(timezone.utc)
        end = datetime.combine(day + timedelta(days=1), time.min, local_zone).astimezone(timezone.utc)
        start = max(now.astimezone(timezone.utc), boundary)
        cursor, covered, watt_seconds = start, 0.0, 0.0
        for slot_start, slot_end, power in slots:
            first, last = max(start, cursor, slot_start), min(end, slot_end)
            seconds = (last - first).total_seconds()
            if seconds <= 0:
                continue
            covered += seconds
            watt_seconds += power * seconds
            cursor = last
        result.append({"date": day.isoformat(), "kwh": watt_seconds / 3600000 if covered else None,
                       "complete": covered >= (end-start).total_seconds(), "coveredMs": covered * 1000})
    return result

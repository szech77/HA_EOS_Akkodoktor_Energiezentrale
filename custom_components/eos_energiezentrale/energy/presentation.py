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


def weather_source(states, options):
    """Use the same explicitly selected or automatically chosen weather source."""
    entity = options.get("weather_entity", "")
    if not entity:
        candidates = sorted(key for key, item in states.items() if key.startswith("weather.")
                            and item.get("state") in WEATHER_CONDITIONS)
        entity = candidates[0] if candidates else None
    return entity


def weather_display(states, options, now):
    """Read current weather for display only; never infer weather from a forecast."""
    entity = weather_source(states, options)
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


def measured_pv_energy(local, influx, now, zone):
    """Integrate measured samples only, with the same six-minute gap policy."""
    from zoneinfo import ZoneInfo
    local_zone = ZoneInfo(zone)
    today = now.astimezone(local_zone).date()
    local = [row for row in local if number(row.get('solar')) is not None and instant(row.get('time'))]
    first = instant(local[0]['time']) if local else None
    rows = [row for row in influx if number(row.get('solar')) is not None and
            (stamp := instant(row.get('time'))) is not None and (first is None or stamp < first)] + local
    points = [(instant(row['time']), number(row['solar'])) for row in rows
              if instant(row['time']).astimezone(local_zone).date() == today and instant(row['time']) <= now]
    covered, watt_seconds = 0, 0
    for (before, left), (after, right) in zip(points, points[1:]):
        seconds = (after - before).total_seconds()
        if 0 < seconds <= 360:
            covered += seconds
            watt_seconds += (left + right) / 2 * seconds
    return watt_seconds / 3600000 if covered else None


def next24_pv_forecast(rows, now):
    from datetime import timedelta
    end, cursor = now + timedelta(days=1), now
    slots = []
    for row in rows:
        start, stop, watts = instant(row.get('time')), instant(row.get('end')), number(row.get('solar'))
        if start is not None and stop is not None and type(row.get('solar')) in (int, float) and watts is not None and watts >= 0 and stop > start:
            slots.append((start, stop, watts))
    covered, energy, peak = 0, 0, None
    for start, stop, watts in sorted(slots, key=lambda item:item[0]):
        first, last = max(now, cursor, start), min(end, stop)
        seconds = (last-first).total_seconds()
        if seconds > 0:
            covered += seconds
            energy += watts * seconds / 3600000
            peak = max(peak or 0, watts / 1000)
            cursor = last
    return {'kwh':energy if covered else None, 'peak':peak, 'complete':covered >= 86400, 'covered':covered*1000}


def mode_timeline(data, rows, now):
    """Classify history gaps and plan validity before drawing the mode track."""
    from datetime import timedelta

    def intervals(points, first, last, maximum_age, kind):
        ordered = sorted(((stamp, mode) for stamp, mode in points if stamp is not None and stamp < last), key=lambda item:item[0])
        result, cursor = [], first
        def append(start, end, mode):
            if start >= end:
                return
            start_ms, end_ms = start.timestamp()*1000, end.timestamp()*1000
            if result and result[-1]['mode'] == mode and result[-1]['end'] == start_ms:
                result[-1]['end'] = end_ms
            else:
                result.append({'start':start_ms, 'end':end_ms, 'mode':mode, 'kind':kind})
        for index, (stamp, mode) in enumerate(ordered):
            start = max(first, stamp)
            end = min(last, ordered[index+1][0] if index+1 < len(ordered) else last,
                      stamp+maximum_age if maximum_age is not None else last)
            if start < end:
                append(cursor, start, None)
                append(start, end, mode)
                cursor = end
        append(cursor, last, None)
        return result

    result = {}
    end = min(now+timedelta(days=1), instant(data.get('plan_end')) or now+timedelta(days=1))
    for key in ('battery', 'car'):
        historical = [(instant(row.get('time')), row.get('car_actual_mode' if key == 'car' else 'battery_mode')) for row in rows]
        future = [(instant(row.get('time')), row.get('mode')) for row in data.get('plan', {}).get(key, [])]
        result[key] = intervals(historical, now-timedelta(days=1), now, timedelta(seconds=120), 'history')
        result[key] += intervals(future, now, max(now, end), None, 'plan')
        if end < now+timedelta(days=1):
            result[key] += intervals([], max(now,end), now+timedelta(days=1), None, 'plan')
    return result

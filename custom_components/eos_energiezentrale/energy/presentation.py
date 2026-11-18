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


# Notice codes and measurements that belong to one energy-flow node.
NODE_CODES = {'battery_read':'battery', 'battery_limits':'battery', 'wallbox':'car', 'wallbox_stop':'car',
              'wallbox_read':'car', 'goal':'car', 'vehicle_limits':'car', 'backup_power_unknown':'grid'}
MEASUREMENT_NODES = {'solar':'solar', 'inverter_ac':'solar', 'grid':'grid', 'house_total':'house', 'heat':'heat',
                     'heat_load':'heat', 'car':'car', 'car_soc':'car', 'battery_soc':'battery',
                     'battery_charge':'battery', 'battery_discharge':'battery'}


def node_problems(notices, vehicles=()):
    """Worst open warning or error per flow node; vehicle nodes are keyed car/<id>."""
    rank = {'warning':1, 'error':2}
    identities = [vehicle.get('id') for vehicle in vehicles or () if isinstance(vehicle.get('id'), str)]
    result = {}
    for notice in notices:
        severity = notice.get('severity')
        if severity not in rank:
            continue
        nodes = {NODE_CODES[notice.get('code')]} if notice.get('code') in NODE_CODES else set()
        nodes |= {MEASUREMENT_NODES[key] for key in notice.get('measurements', []) if key in MEASUREMENT_NODES}
        scope = notice.get('scope') or 'system'
        for node in nodes:
            key = node
            if node == 'car' and identities:
                index = int(scope.split('/')[1]) - 1 if scope.startswith('vehicle/') and scope.split('/')[1].isdigit() else 0
                if not 0 <= index < len(identities):
                    continue
                key = 'car/' + identities[index]
            if rank[severity] > rank.get(result.get(key), 0):
                result[key] = severity
    return result


# Plan segments shorter than this are EOS interval noise and do not make an upcoming event.
MIN_PLAN_SEGMENT_S = 1800
# Forecast battery power below this counts as holding the charge level.
BATTERY_IDLE_W = 150


def battery_effect(rows, start, stop):
    """What the battery does according to the forecast between start and stop: charge_pv, charge_grid, discharge or hold."""
    weights = power = solar = 0.
    for row in rows or []:
        begin, end = instant(row.get('time')), instant(row.get('end'))
        battery = number(row.get('battery'))
        if begin is None or end is None or battery is None:
            continue
        overlap = (min(end, stop) - max(begin, start)).total_seconds()
        if overlap <= 0:
            continue
        weights += overlap
        power += battery * overlap
        solar += (number(row.get('solar')) or 0.) * overlap
    if not weights:
        return None
    power, solar = power / weights, solar / weights
    if power > BATTERY_IDLE_W:
        return 'charge_pv' if solar >= power * .8 else 'charge_grid'
    return 'discharge' if power < -BATTERY_IDLE_W else 'hold'


def plan_events(data, now, hours=24, limit=6):
    """Upcoming mode changes and forecast milestones in time order, with the import price at that time.

    Mode changes lasting less than MIN_PLAN_SEGMENT_S are skipped. Battery changes carry the
    forecast effect; consecutive changes with the same effect are listed once.
    """
    from datetime import timedelta
    end = now + timedelta(hours=hours)
    prices = [(instant(row.get('time')), instant(row.get('end')), number(row.get('price')))
              for row in data.get('forecast') or []]
    prices = [row for row in prices if None not in row]

    def price_at(stamp):
        return next((price for start, stop, price in prices if start <= stamp < stop), None)

    events = []
    plan_end = instant(data.get('plan_end')) or end

    def changes(rows, current, device, extra, forecast=None):
        ordered = sorted(((instant(row.get('time')), row.get('mode')) for row in rows or []
                          if instant(row.get('time')) is not None and isinstance(row.get('mode'), str)), key=lambda item: item[0])
        # Only the segment in progress is kept from the past; it never merges with future rows.
        past = [item for item in ordered if item[0] <= now][-1:]
        segments = []
        for stamp, mode in past + [item for item in ordered if item[0] > now]:
            if segments and segments[-1][1] == mode and stamp > now and segments[-1][0] > now:
                continue
            segments.append([stamp, mode])
        bounded = [(stamp, mode, segments[index+1][0] if index+1 < len(segments) else max(plan_end, stamp))
                   for index, (stamp, mode) in enumerate(segments)]
        previous, previous_effect = current, None
        for stamp, mode, stop in bounded:
            if stamp > end:
                break
            if stop <= now:
                continue
            begin = max(now, stamp)
            # The first hour tells what starts with the change; later hours belong to later events.
            effect = battery_effect(forecast, begin, min(stop, begin + timedelta(hours=1))) if device == 'battery' else None
            if stamp <= now:
                previous_effect = effect
                continue
            last = stop == bounded[-1][2]
            if (stop - stamp).total_seconds() < MIN_PLAN_SEGMENT_S and not last:
                continue
            if mode == previous or (effect is not None and effect == previous_effect):
                previous = mode
                continue
            previous, previous_effect = mode, effect
            event = {'time':stamp.isoformat(), 'kind':'mode', 'device':device, 'mode':mode,
                     'price_ct':price_at(stamp), **extra}
            if effect is not None:
                event['effect'] = effect
            events.append(event)

    def reached(rows, current, target, kind, extra):
        if target is None or (current is not None and current >= target - .5):
            return
        lower = current is not None
        for row in rows or []:
            stamp, soc = instant(row.get('time')), number(row.get(kind_key[kind]))
            if stamp is None or soc is None or not now <= stamp <= end:
                continue
            if soc < target - .5:
                lower = True
            elif lower:
                events.append({'time':stamp.isoformat(), 'kind':kind, 'soc':target, 'price_ct':price_at(stamp), **extra})
                return

    kind_key = {'battery_full':'battery_soc', 'car_target':'car_soc'}
    live = data.get('live') or {}
    changes((data.get('plan') or {}).get('battery'), live.get('battery_mode'), 'battery', {}, data.get('forecast'))
    reached(data.get('forecast'), number(live.get('battery_soc')),
            number((data.get('settings') or {}).get('battery_max_soc')), 'battery_full', {})
    vehicles = data.get('vehicles') or []
    if vehicles:
        for vehicle in vehicles:
            extra = {'vehicle_id':vehicle.get('id'), 'vehicle_name':vehicle.get('name')}
            changes((vehicle.get('plan') or {}).get('car'), (vehicle.get('live') or {}).get('car_mode'), 'car', extra)
            reached(vehicle.get('forecast'), number((vehicle.get('live') or {}).get('car_soc')),
                    number(vehicle.get('charge_target_soc')), 'car_target', dict(extra))
    elif (data.get('features') or {}).get('car', True):
        changes((data.get('plan') or {}).get('car'), live.get('car_mode'), 'car', {})
        reached(data.get('forecast'), number(live.get('car_soc')), number(data.get('charge_target_soc')), 'car_target', {})
    return sorted(events, key=lambda item: item['time'])[:limit]

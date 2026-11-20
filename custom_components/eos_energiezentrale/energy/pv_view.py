"""Display-only PV & weather view: hourly strip, day cards and what the EOS plan does with the forecast."""
from collections import Counter
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .domain import instant, number

HOUR = timedelta(hours=1)
# Hours with less forecast PV than this count as dark and may be folded into a night block.
DARK_KWH = .05
# Only runs of at least this many dark hours become one night block.
NIGHT_HOURS = 3
# Forecast battery power above this counts as charging.
CHARGING_W = 150
# Below this forecast power the live/forecast ratio is not meaningful.
RATIO_MIN_W = 200
# Tomorrow counts as clearly weaker/stronger than today beyond these ratios.
LOW_RATIO, HIGH_RATIO = .5, 1.5
EXPORT_MIN_KWH = .5


def _slots(rows, key):
    result = []
    for row in rows or []:
        start, end, value = instant(row.get('time')), instant(row.get('end')), number(row.get(key))
        if start is not None and end is not None and value is not None and end > start:
            result.append((start, end, value, row))
    return sorted(result, key=lambda item: item[0])


def _energy(slots, start, end):
    """kWh of W slots inside [start, end); None without any coverage."""
    covered, energy = 0., 0.
    for first, last, watts, _ in slots:
        seconds = (min(end, last) - max(start, first)).total_seconds()
        if seconds > 0:
            covered += seconds
            energy += max(0., watts) * seconds / 3600000
    return energy if covered else None


def _weather_at(rows, stamp):
    return next((row for row in rows if instant(row.get('time')) <= stamp < instant(row.get('end'))), None)


def pv_hours(forecast, weather, now, zone, current=None):
    """Local hours from now to the end of tomorrow with weather above the expected PV energy.

    Runs of dark hours (measured forecast below DARK_KWH) become one night block; unknown PV stays visible.
    Many weather services start the hourly forecast at the next full hour; the current hour then
    shows the current weather (``current``) instead of an unknown condition.
    """
    local = ZoneInfo(zone)
    weather = [row for row in weather or [] if instant(row.get('time')) and instant(row.get('end'))]
    solar = _slots(forecast, 'solar')
    tomorrow = now.astimezone(local).date() + timedelta(days=1)
    stop = datetime.combine(tomorrow + timedelta(days=1), time.min, local).astimezone(timezone.utc)
    stamp = now.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)
    hours = []
    while stamp < stop:
        end = stamp + HOUR
        row = _weather_at(weather, stamp) or {}
        if stamp <= now < end and row.get('condition') in (None, 'unknown') and isinstance(current, dict)                 and current.get('condition') not in (None, 'unknown'):
            row = {**row, 'condition': current['condition'],
                   'temperature': row.get('temperature') if row.get('temperature') is not None else current.get('temperature')}
        kwh = _energy(solar, max(stamp, now), end)
        hours.append({'kind':'hour', 'start':stamp.isoformat(), 'end':end.isoformat(), 'now':stamp <= now < end,
                      'pv_kwh':kwh, 'condition':row.get('condition'), 'temperature':row.get('temperature'),
                      'cloud_coverage':row.get('cloud_coverage'), 'precipitation':row.get('precipitation'),
                      'precipitation_probability':row.get('precipitation_probability')})
        stamp = end
    result, run = [], []

    def flush():
        if len(run) >= NIGHT_HOURS:
            temperatures = [item['temperature'] for item in run if item['temperature'] is not None]
            conditions = Counter(item['condition'] for item in run if item['condition'] not in (None, 'unknown'))
            result.append({'kind':'night', 'start':run[0]['start'], 'end':run[-1]['end'],
                           'condition':conditions.most_common(1)[0][0] if conditions else None,
                           'low':min(temperatures) if temperatures else None})
        else:
            result.extend(run)
        run.clear()

    for item in hours:
        if not item['now'] and item['pv_kwh'] is not None and item['pv_kwh'] < DARK_KWH:
            run.append(item)
            continue
        flush()
        result.append(item)
    flush()
    return result


def weather_days(weather, totals, measured, now, zone):
    """Day cards for the PV forecast days with the weather of their daylight hours."""
    local = ZoneInfo(zone)
    rows = [row for row in weather or [] if instant(row.get('time'))]
    result = []
    for index, total in enumerate(totals or []):
        try:
            day = datetime.fromisoformat(total['date']).date()
        except (KeyError, TypeError, ValueError):
            continue
        hours = [row for row in rows if instant(row['time']).astimezone(local).date() == day]
        daylight = [row for row in hours if 8 <= instant(row['time']).astimezone(local).hour < 18] or hours
        temperatures = [row['temperature'] for row in hours if row.get('temperature') is not None]
        conditions = Counter(row.get('condition') for row in daylight if row.get('condition') not in (None, 'unknown'))
        rain = [row['precipitation'] for row in hours if row.get('precipitation') is not None]
        result.append({'date':day.isoformat(), 'today':index == 0,
                       'pv_kwh':total.get('total_kwh') if index == 0 else total.get('kwh'),
                       'measured_kwh':measured if index == 0 else None,
                       'complete':bool(total.get('complete')),
                       'condition':conditions.most_common(1)[0][0] if conditions else None,
                       'high':max(temperatures) if temperatures else None,
                       'low':min(temperatures) if temperatures else None,
                       'precipitation':sum(rain) if rain else None,
                       'weather_hours':len(hours)})
    return result


def pv_now(data, now):
    """Live PV against the forecast power of the current interval."""
    live = number((data.get('live') or {}).get('solar'))
    row = next((row for first, last, _, row in _slots(data.get('forecast'), 'solar') if first <= now < last), None)
    forecast = number(row.get('solar')) if row else None
    ratio = live / forecast if live is not None and forecast is not None and forecast >= RATIO_MIN_W else None
    return {'power_w':live, 'forecast_w':forecast, 'ratio':ratio}


def _battery_grid(forecast, now, end):
    run = None
    for start, stop, power, row in _slots(forecast, 'battery'):
        if stop <= now or start >= end:
            continue
        solar = number(row.get('solar')) or 0.
        charging = power > CHARGING_W and solar < power * .8
        if charging:
            hours = (stop - max(start, now)).total_seconds() / 3600
            price = number(row.get('price'))
            if run is None:
                run = {'start':max(start, now), 'end':stop, 'kwh':0., 'cost':0., 'priced':0., 'soc':None}
            run['end'] = stop
            run['kwh'] += power * hours / 1000
            if price is not None:
                run['cost'] += power * hours / 1000 * price
                run['priced'] += power * hours / 1000
        elif run is not None:
            run['soc'] = number(row.get('battery_soc'))
            break
    if run is None:
        return None
    return {'id':'battery_grid', 'start':run['start'].isoformat(), 'end':run['end'].isoformat(), 'kwh':run['kwh'],
            'price_ct':run['cost'] / run['priced'] if run['priced'] else None, 'soc':run['soc']}


def _export(forecast, now, end):
    first, energy = None, 0.
    for start, stop, grid, _ in _slots(forecast, 'grid'):
        seconds = (min(end, stop) - max(start, now)).total_seconds()
        if seconds > 0 and grid < 0:
            first = first or max(start, now)
            energy += -grid * seconds / 3600000
    return {'id':'export', 'start':first.isoformat(), 'kwh':energy} if energy >= EXPORT_MIN_KWH else None


def pv_effects(data, now):
    """What the EOS plan does with the PV forecast in the next 24 hours: day comparisons first, then by time."""
    end = now + timedelta(hours=24)
    forecast = data.get('forecast')
    effects = []
    totals = data.get('pv_forecast_totals') or []
    today = number(totals[0].get('total_kwh')) if totals else None
    tomorrow = number(totals[1].get('kwh')) if len(totals) > 1 and totals[1].get('complete') else None
    if today and tomorrow is not None:
        kind = 'tomorrow_low' if tomorrow < today * LOW_RATIO else 'tomorrow_high' if tomorrow > today * HIGH_RATIO else None
        if kind:
            effects.append({'id':kind, 'kwh':tomorrow, 'today_kwh':today, 'date':totals[1].get('date')})
    full = next((event for event in data.get('plan_events') or [] if event.get('kind') == 'battery_full'), None)
    if full:
        effects.append({'id':'battery_full', 'start':full['time'], 'soc':full.get('soc')})
    for item in (_battery_grid(forecast, now, end), _export(forecast, now, end)):
        if item:
            effects.append(item)
    vehicles = [(vehicle.get('charge_plan'), vehicle.get('name'), vehicle.get('id')) for vehicle in data.get('vehicles') or []]
    if not vehicles and data.get('charge_plan'):
        vehicles = [(data['charge_plan'], data.get('vehicle_name'), None)]
    for plan, name, identity in vehicles:
        if not plan or plan.get('state') in ('disconnected', 'reached'):
            continue
        if (plan.get('grid_kwh') or 0) >= DARK_KWH:
            effects.append({'id':'car_grid', 'vehicle_name':name, 'vehicle_id':identity, 'kwh':plan['grid_kwh'],
                            'start':plan.get('grid_from'), 'price_ct':plan.get('grid_price_ct')})
        elif (plan.get('pv_kwh') or 0) >= DARK_KWH:
            effects.append({'id':'car_pv', 'vehicle_name':name, 'vehicle_id':identity, 'kwh':plan['pv_kwh'],
                            'end':plan.get('pv_until')})
    timed = sorted((item for item in effects if item.get('start') or item.get('end')),
                   key=lambda item: instant(item.get('start') or item.get('end')))
    return [item for item in effects if not (item.get('start') or item.get('end'))] + timed

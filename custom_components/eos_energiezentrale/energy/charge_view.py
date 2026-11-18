"""Display-only EV charge plan: segments, SoC curve and cost comparison from the EOS forecast.

Nothing here feeds control. The plan describes what the forecast rows say about the
vehicle until the departure; the comparison estimates charging at full power from now.
"""
from datetime import timedelta

from .domain import instant, number

# Forecast charge power below this counts as a pause.
CHARGING_W = 100
# A charge interval counts as grid charging when more than this share comes from the grid.
GRID_SHARE = .5
# SoC tolerance when comparing with the goal.
SOC_TOLERANCE = .5
# Without a departure the plan covers this horizon.
HORIZON_H = 24
# Errors that keep the wallbox from following the plan.
WALLBOX_ERRORS = frozenset({'wallbox', 'wallbox_stop', 'vehicle_limits'})


def _rows(forecast, start, stop):
    """Forecast rows clipped to [start, stop) in time order, with their duration in hours."""
    result = []
    for row in forecast or []:
        begin, end = instant(row.get('time')), instant(row.get('end'))
        if begin is None or end is None or end <= start or begin >= stop or end <= begin:
            continue
        clipped_begin, clipped_end = max(begin, start), min(end, stop)
        result.append((clipped_begin, clipped_end, (clipped_end - clipped_begin).total_seconds() / 3600, row))
    return sorted(result, key=lambda item: item[0])


def _phases(power, limits):
    fixed = limits.get('phases')
    if fixed in (1, 3):
        return fixed
    current = number(limits.get('max_current_a'))
    if not current or power is None:
        return None
    return 1 if power <= current * 230 * 1.05 else 3


def _state(data, connected, soc, target, has_plan):
    if connected is False:
        return 'disconnected'
    if not data.get('armed'):
        return 'read_only'
    if WALLBOX_ERRORS & set(data.get('errors') or {}):
        return 'suspended'
    if (data.get('settings') or {}).get('fast'):
        return 'overridden'
    if soc is not None and target is not None and soc >= target - SOC_TOLERANCE:
        return 'reached'
    return 'active' if has_plan else 'no_plan'


def _immediate(rows, now, need_kwh, maximum_w, pv_price, efficiency):
    """Estimated cost of charging the remaining energy at full power from now on."""
    if need_kwh is None or not maximum_w or need_kwh <= 0:
        return None
    left = need_kwh / efficiency
    cost = grid = pv = 0.
    for begin, end, hours, row in rows:
        price = number(row.get('price'))
        energy = min(left, maximum_w * hours / 1000)
        surplus = max(0., (number(row.get('solar')) or 0.) - max(0., number(row.get('house_total')) or 0.)) * hours / 1000
        from_pv = min(energy, surplus)
        from_grid = energy - from_pv
        if price is None:
            return None
        cost += from_grid * price / 100 + from_pv * pv_price / 100
        grid, pv = grid + from_grid, pv + from_pv
        left -= energy
        if left <= 1e-6:
            reached = begin + timedelta(hours=energy / maximum_w * 1000)
            return {'eur': cost, 'kwh': grid + pv, 'price_ct': cost / (grid + pv) * 100 if grid + pv else None,
                    'reached_at': reached.isoformat(), 'grid_kwh': grid, 'pv_kwh': pv}
    return None


def charge_plan(data, now, pv_price_ct=None):
    """Explain the EOS charge plan of one vehicle until its departure."""
    live = data.get('live') or {}
    limits = data.get('charge_limits') or {}
    soc = number(live.get('car_soc'))
    target = number(data.get('charge_target_soc'))
    departure = instant(data.get('charge_departure'))
    end = departure if departure and departure > now else now + timedelta(hours=HORIZON_H)
    capacity = number(limits.get('capacity_wh'))
    efficiency = number(limits.get('efficiency'))
    efficiency = efficiency if efficiency and 0 < efficiency <= 1 else 1.
    maximum_w = number(limits.get('maximum_w'))
    source = data.get('vehicle_forecast_source')
    rows = _rows(data.get('forecast'), now, end)
    # Own PV is valued with the lost feed-in tariff; without a tariff it counts as free.
    pv_price = pv_price_ct if pv_price_ct is not None else 0.
    has_plan = source == 'eos' and any(number(row.get('car')) is not None for *_, row in rows)
    connected = live.get('car_connected')
    result = {'state':_state(data, connected, soc, target, has_plan), 'source':source,
              'soc':soc, 'target_soc':target, 'departure':departure.isoformat() if departure else None,
              'end':end.isoformat(), 'generated_at':data.get('plan_generated_at'),
              'remaining_kwh':max(0., (target - soc) * capacity / 100000) if None not in (soc, target, capacity) else None,
              'segments':[], 'curve':[], 'reached_at':None, 'buffer_s':None,
              'pv_kwh':0., 'grid_kwh':0., 'pv_until':None, 'grid_from':None, 'grid_price_ct':None,
              'pv_price_ct':pv_price_ct, 'plan_cost':None, 'immediate_cost':None}
    if soc is not None:
        result['curve'].append({'time':now.isoformat(), 'soc':soc})
    for begin, stop, _, row in rows:
        value = number(row.get('car_soc'))
        if value is not None and 0 <= value <= 100 and begin > now:
            result['curve'].append({'time':begin.isoformat(), 'soc':value})
    if result['curve'] and target is not None:
        reached = next((point['time'] for point in result['curve'] if point['soc'] >= target - SOC_TOLERANCE), None)
        result['reached_at'] = reached
        if reached and departure:
            result['buffer_s'] = max(0., (departure - instant(reached)).total_seconds())
    if not has_plan:
        return result
    segments, cost, priced, grid_cost, grid_priced = [], 0., True, 0., 0.
    level = soc
    for begin, stop, hours, row in rows:
        power = max(0., number(row.get('car')) or 0.)
        kwh = power * hours / 1000
        row_soc = number(row.get('car_soc'))
        level = row_soc if row_soc is not None else level
        if power >= CHARGING_W:
            from_grid = min(kwh, max(0., number(row.get('grid')) or 0.) * hours / 1000)
            kind = 'grid' if from_grid > kwh * GRID_SHARE else 'pv'
        else:
            kwh = from_grid = 0.
            kind = 'ready' if level is not None and target is not None and level >= target - SOC_TOLERANCE else 'pause'
        price = number(row.get('price'))
        from_pv = kwh - from_grid
        row_cost = None
        if kwh:
            if price is None and from_grid:
                priced = False
            else:
                row_cost = from_grid * (price or 0) / 100 + from_pv * pv_price / 100
                cost += row_cost
            if from_grid and price is not None:
                grid_cost += from_grid * price / 100
                grid_priced += from_grid
        if segments and segments[-1]['kind'] == kind:
            segment = segments[-1]
        else:
            segment = {'start':begin, 'kind':kind, 'kwh':0., 'grid_kwh':0., 'pv_kwh':0., 'cost_eur':0.,
                       'priced':True, 'energy_h':0., 'soc_start':segments[-1]['soc_end'] if segments else soc if soc is not None else level,
                       'price_sum':0., 'price_h':0.}
            segments.append(segment)
        segment['end'] = stop
        segment['kwh'] += kwh
        segment['grid_kwh'] += from_grid
        segment['pv_kwh'] += from_pv
        if kwh:
            segment['energy_h'] += hours
            if row_cost is None:
                segment['priced'] = False
            else:
                segment['cost_eur'] += row_cost
        if price is not None:
            segment['price_sum'] += price * hours
            segment['price_h'] += hours
        segment['soc_end'] = level if row_soc is None or capacity is None else min(
            100., row_soc + kwh * efficiency * 100000 / capacity)
    for segment in segments:
        segment['power_w'] = segment['kwh'] * 1000 / segment['energy_h'] if segment['energy_h'] else 0.
        segment['phases'] = _phases(segment['power_w'], limits) if segment['kwh'] else None
        segment['price_ct'] = segment['price_sum'] / segment['price_h'] if segment['price_h'] else None
        if segment['kind'] == 'pv' and pv_price_ct is not None:
            segment['value_ct'] = pv_price_ct
        if not segment['priced'] or not segment['kwh']:
            segment['cost_eur'] = None
        for key in ('price_sum', 'price_h', 'energy_h', 'priced'):
            del segment[key]
        segment['start'], segment['end'] = segment['start'].isoformat(), segment['end'].isoformat()
    result['segments'] = segments
    charging = [item for item in segments if item['kind'] in ('pv', 'grid')]
    result['pv_kwh'] = sum(item['pv_kwh'] for item in segments)
    result['grid_kwh'] = sum(item['grid_kwh'] for item in segments)
    pv = [item for item in charging if item['kind'] == 'pv']
    grid = [item for item in charging if item['kind'] == 'grid']
    result['pv_until'] = pv[-1]['end'] if pv else None
    result['grid_from'] = grid[0]['start'] if grid else None
    result['grid_price_ct'] = grid_cost / grid_priced * 100 if grid_priced else None
    kwh = result['pv_kwh'] + result['grid_kwh']
    if kwh and priced:
        result['plan_cost'] = {'eur':cost, 'kwh':kwh, 'price_ct':cost / kwh * 100, 'reached_at':result['reached_at']}
    need = result['remaining_kwh']
    result['immediate_cost'] = _immediate(_rows(data.get('forecast'), now, now + timedelta(hours=48)),
                                          now, need, maximum_w, pv_price, efficiency)
    return result

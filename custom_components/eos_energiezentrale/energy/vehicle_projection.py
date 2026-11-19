"""Display-only EV SoC projections when EOS has no matching vehicle curve."""
from datetime import timedelta

from .domain import instant, number


def projected_vehicle_soc(rows, evidence, now, soc, daily, *, connected, maximum_w=0,
                          minimum_w=0, pv_share=1, foreign_vehicle=False, controlled=True):
    """Prefer plausible EOS curves; never feed local estimates into control.

    The local estimate also carries the expected charging power (``car``): 0 while
    no charging is expected, the PV surplus share or the fast-charging power
    otherwise. Power stays absent where it cannot be estimated."""
    soc = number(soc)
    future = [value for row in rows if (instant(row.get('end')) or now) > now
              and (value := number(row.get('car_soc'))) is not None and 0 <= value <= 100]
    # EOS can publish an all-zero EV curve when the vehicle is not planned.
    # It contradicts a known positive SoC and must not suppress the local estimate.
    zero_placeholder = bool(future and all(value == 0 for value in future)
                            and soc is not None and 0 < soc <= 100)
    if future and not zero_placeholder:
        return rows, 'eos'
    if soc is None or not 0 <= soc <= 100:
        return rows, 'unavailable'
    capacity, efficiency = number(daily.get('capacity_wh')), number(daily.get('charging_efficiency'))
    # Only a controlled charger follows these modes; otherwise the charging is unknown.
    ready = bool(controlled and connected is True and capacity is not None and capacity > 0
                 and efficiency is not None and 0 < efficiency <= 1 and maximum_w > 0)
    fast_target = number(daily.get('target_soc'))
    fast = bool(ready and daily.get('fast') and fast_target is not None)
    pv = bool(ready and daily.get('pv') and not daily.get('fast') and minimum_w > 0)
    # A disconnected vehicle certainly does not charge.
    idle = connected is False
    target = daily['pv_target_soc']
    result = [{key: value for key, value in row.items() if key not in {'car', 'car_soc'}} for row in rows]
    sources = sorted((row for row in evidence if instant(row.get('time')) and instant(row.get('end'))),
                     key=lambda row: instant(row['time']))
    stamp, limit, increased = now, now + timedelta(hours=24), False
    while stamp <= limit:
        end = min(limit + timedelta(seconds=1), stamp + timedelta(minutes=15))
        source = next((row for row in sources if instant(row['time']) <= stamp < instant(row['end'])), None)
        # Never fill an uncovered PV interval with today's or the last observed power.
        if source:
            end = min(end, instant(source['end']))
        else:
            upcoming = next((instant(row['time']) for row in sources if instant(row['time']) > stamp), None)
            if upcoming:
                end = min(end, upcoming)
        row = {'time': stamp.isoformat(), 'end': end.isoformat(), 'car_soc': soc}
        result.append(row)
        hours = (end - stamp).total_seconds() / 3600
        watts = 0 if idle or fast or pv else None
        if fast and soc < fast_target:
            watts = maximum_w
        elif pv and soc < target:
            solar = number(source.get('solar')) if source else None
            load = number(source.get('house_total')) if source else None
            battery = number(source.get('battery')) if source else None
            other = (number(source.get('car')) or 0) if source and foreign_vehicle else 0
            watts = None
            if solar is not None and load is not None:
                surplus = max(0, solar - max(0, load) - max(0, battery or 0) - max(0, other)
                              - daily.get('reserve_w', 0)) * max(0, min(1, pv_share))
                watts = min(maximum_w, surplus)
                watts = watts if watts >= minimum_w else 0
        if watts is not None:
            row['car'] = watts
            if watts > 0:
                next_soc = min(fast_target if fast else target, soc + watts * hours * efficiency / capacity * 100)
                increased |= next_soc > soc
                soc = next_soc
        stamp = end
    result.sort(key=lambda row: instant(row['time']))
    return result, ('fast_estimate' if fast else 'pv_estimate') if increased else 'constant'


# Below this SoC the range per percent is too sensitive to rounding of both values.
RANGE_MIN_SOC = 10


def car_range_view(measured, soc, per_soc):
    """Range for display: the vehicle's report, otherwise the SoC times the learned factor.

    ``car_range_per_soc`` lets the panel show the range of a SoC while it is being set."""
    soc = number(soc)
    if measured is not None:
        value, source = measured, 'vehicle'
    elif per_soc is not None and soc is not None and 0 <= soc <= 100:
        value, source = soc * per_soc, 'estimate'
    else:
        value, source = None, None
    return {'car_range': value, 'car_range_source': source, 'car_range_per_soc': per_soc}


def average_power(rows, start, end):
    """Time-weighted charging power of ``rows`` over [start, end); None unless fully covered."""
    span = (end - start).total_seconds()
    if span <= 0:
        return None
    covered = energy = 0.
    for row in rows:
        first, last, value = instant(row.get('time')), instant(row.get('end')), number(row.get('car'))
        if first is None or last is None or value is None:
            continue
        overlap = (min(last, end) - max(first, start)).total_seconds()
        if overlap > 0:
            covered += overlap
            energy += overlap * value
    return energy / span if covered >= span - 1 else None

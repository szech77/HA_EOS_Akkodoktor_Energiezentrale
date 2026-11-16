"""Display-only EV SoC projections when EOS has no matching vehicle curve."""
from datetime import timedelta

from .domain import instant, number


def projected_vehicle_soc(rows, evidence, now, soc, daily, *, connected, maximum_w=0,
                          minimum_w=0, pv_share=1, foreign_vehicle=False):
    """Prefer plausible EOS curves; never feed local estimates into control."""
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
    pv = bool(daily.get('pv') and not daily.get('fast') and connected is True
              and capacity is not None and capacity > 0 and efficiency is not None and 0 < efficiency <= 1
              and maximum_w > 0 and minimum_w > 0)
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
        result.append({'time': stamp.isoformat(), 'end': end.isoformat(), 'car_soc': soc})
        solar = number(source.get('solar')) if source else None
        load = number(source.get('house_total')) if source else None
        battery = number(source.get('battery')) if source else None
        other = (number(source.get('car')) or 0) if source and foreign_vehicle else 0
        if pv and solar is not None and load is not None and soc < target:
            surplus = max(0, solar - max(0, load) - max(0, battery or 0) - max(0, other)
                          - daily.get('reserve_w', 0)) * max(0, min(1, pv_share))
            watts = min(maximum_w, surplus)
            if watts >= minimum_w:
                delta = watts * (end - stamp).total_seconds() / 3600 * efficiency / capacity * 100
                next_soc = min(target, soc + delta)
                increased |= next_soc > soc
                soc = next_soc
        stamp = end
    result.sort(key=lambda row: instant(row['time']))
    return result, 'pv_estimate' if increased else 'constant'

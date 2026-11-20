"""PV report: the EOS PV forecast per report bin and as a power curve for the day view.

Only the future is forecast (from ``now``); past bins show measured production only.
"""
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from .domain import instant, number


def _period(report, local):
    start = datetime.combine(date.fromisoformat(report['date']), time.min, local).astimezone(timezone.utc)
    end = datetime.combine(date.fromisoformat(report['end']), time.min, local).astimezone(timezone.utc)
    return start, end


def _bin(stamp, period, local):
    """Report bin key of a moment and the end of that bin (UTC)."""
    if period == 'day':
        first = stamp.replace(minute=0, second=0, microsecond=0)
        return first.isoformat(), first + timedelta(hours=1)
    day = stamp.astimezone(local).date()
    if period == 'month':
        following = day + timedelta(days=1)
        return day.isoformat(), datetime.combine(following, time.min, local).astimezone(timezone.utc)
    following = date(day.year + (day.month == 12), day.month % 12 + 1, 1)
    return day.isoformat()[:7], datetime.combine(following, time.min, local).astimezone(timezone.utc)


def pv_forecast(rows, report, now, zone):
    """Forecast PV energy per bin of the report from ``now`` on, and the day's forecast power."""
    local = ZoneInfo(zone)
    start, end = _period(report, local)
    slots = []
    for row in rows or ():
        first, last, watts = instant(row.get('time')), instant(row.get('end')), number(row.get('solar'))
        if first is not None and last is not None and watts is not None and last > first:
            slots.append((first, last, max(0., watts)))
    slots.sort()
    bins, covered = {}, None
    for first, last, watts in slots:
        cursor, stop = max(first, now, start), min(last, end)
        while cursor < stop:
            key, bin_end = _bin(cursor, report['period'], local)
            step_end = min(stop, bin_end)
            bins[key] = bins.get(key, 0.) + watts * (step_end - cursor).total_seconds() / 3600000
            cursor = step_end
        if last > max(first, now):
            covered = max(covered or last, last)
    points = ([{'time': max(first, now).isoformat(), 'end': min(last, end).isoformat(), 'w': round(watts)}
               for first, last, watts in slots if last > max(now, start) and first < end]
              if report['period'] == 'day' else [])
    return {'bins': [{'time': key, 'kwh': round(value, 3)} for key, value in sorted(bins.items())],
            'points': points, 'kwh': round(sum(bins.values()), 3),
            # Whether the forecast reaches the end of the period (EOS plans about two days ahead).
            'complete': covered is not None and covered >= end}

"""Validated vehicle goals and German holiday calendars, evaluated in the backend."""
from datetime import datetime, timedelta, timezone
from functools import lru_cache
import re

import holidays

from .failures import BackendError

STATES = {'', 'BW', 'BY', 'BE', 'BB', 'HB', 'HH', 'HE', 'MV', 'NI', 'NW', 'RP', 'SL', 'SN', 'ST', 'SH', 'TH'}


def validate_calendar(values):
    state, locality = values['holiday_state'], values['holiday_locality']
    if (not isinstance(state, str) or state not in STATES
            or locality not in ('', 'augsburg')
            or locality == 'augsburg' and state != 'BY'
            or type(values['holiday_catholic']) is not bool
            or values['holiday_catholic'] and state not in {'BY', 'SN', 'TH'}):
        raise BackendError('Invalid German holiday region', reason='invalid_holiday_region',
                           fields=('holiday_state', 'holiday_locality', 'holiday_catholic'))


def validate_plans(rows):
    if rows is None:
        return None  # Retain compatibility with existing single-goal settings.
    def invalid():
        return BackendError('Invalid vehicle charge goal', reason='invalid_charge_plan', fields=('charge_plans',))
    if not isinstance(rows, list) or len(rows) > 32:
        raise invalid()
    result, identities = [], set()
    allowed = {'id', 'active', 'schedule', 'target_soc', 'departure', 'departure_time', 'weekdays', 'holidays'}
    for row in rows:
        if not isinstance(row, dict) or row.keys() - allowed:
            raise invalid()
        value = {'active': True, 'schedule': 'once', 'target_soc': 80, 'departure': '',
                 'departure_time': '07:30', 'weekdays': [], 'holidays': False, **row}
        identity = value.get('id')
        if (not isinstance(identity, str) or not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', identity)
                or identity in identities or type(value['active']) is not bool
                or type(value['holidays']) is not bool or value['schedule'] not in ('once', 'weekly')
                or type(value['target_soc']) is not int or not 1 <= value['target_soc'] <= 100
                or not isinstance(value['departure_time'], str)
                or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', value['departure_time'])
                or not isinstance(value['weekdays'], list)
                or any(type(day) is not int or not 0 <= day <= 6 for day in value['weekdays'])
                or value['schedule'] == 'weekly' and not (value['weekdays'] or value['holidays'])
                or not isinstance(value['departure'], str)):
            raise invalid()
        if value['schedule'] == 'once':
            try:
                date = datetime.fromisoformat(value['departure'].replace('Z', '+00:00'))
                if date.tzinfo is None:
                    raise ValueError('Timezone required')
            except ValueError as error:
                raise invalid() from error
        identities.add(identity)
        value['weekdays'] = sorted(set(value['weekdays']))
        result.append(value)
    return result


def plans(settings):
    rows = settings.get('charge_plans')
    if rows is not None:
        return rows
    if settings['schedule'] == 'off':
        return []
    return [{'id': 'legacy', 'active': True, 'holidays': False,
             **{key: settings[key] for key in ('schedule', 'target_soc', 'departure', 'departure_time', 'weekdays')}}]


@lru_cache(maxsize=128)
def holiday_dates(year, state, locality, catholic):
    return frozenset(holidays.country_holidays('DE', years=year,
        subdiv='Augsburg' if locality == 'augsburg' else state or None,
        categories=('public', 'catholic') if catholic else ('public',)))


def occurrence(row, settings, now, zone):
    if not row['active']:
        return None
    if row['schedule'] == 'once':
        date = datetime.fromisoformat(row['departure'].replace('Z', '+00:00'))
        return date if date > now else None
    local = now.astimezone(zone)
    hour, minute = map(int, row['departure_time'].split(':'))
    for offset in range(371):
        day = local.date() + timedelta(days=offset)
        holiday = row['holidays'] and day in holiday_dates(day.year,
            settings.get('holiday_state', ''), settings.get('holiday_locality', ''), settings.get('holiday_catholic', False))
        if day.weekday() in row['weekdays'] or holiday:
            date = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone)
            date = date.astimezone(timezone.utc).astimezone(zone)
            if date.astimezone(timezone.utc) > now.astimezone(timezone.utc):
                return date
    return None


def selected_goal(settings, now, zone):
    candidates = [(date, -row['target_soc'], row['id']) for row in plans(settings)
                  if (date := occurrence(row, settings, now, zone)) is not None]
    if not candidates:
        return None
    date, negative_target, _ = min(candidates)
    return -negative_target, date


def plan_view(settings, now, zone):
    """Return display dates in the installation zone, without browser date logic."""
    result = []
    goal = selected_goal(settings, now, zone)
    for row in plans(settings):
        date = occurrence(row, settings, now, zone)
        departure = datetime.fromisoformat(row['departure'].replace('Z', '+00:00')) if row['schedule'] == 'once' else None
        result.append({**row, 'departure_local': departure.astimezone(zone).strftime('%Y-%m-%dT%H:%M') if departure else '',
                       'next_departure': date.isoformat() if date else None,
                       'selected': goal == (row['target_soc'], date) if date else False})
    return result

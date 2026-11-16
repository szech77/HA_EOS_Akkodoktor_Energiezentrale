"""PV warning delays and labelled overnight display, never control inputs."""
from datetime import timedelta

from .clients import PV_IDLE_MAX_AGE_S, reading, report_time


class PVAvailability:
    def __init__(self):
        self.entity = None
        self.small = None
        self.missing_since = None

    def observe(self, states, entity, now):
        if entity != self.entity:
            self.entity, self.small, self.missing_since = entity, None, None
        raw = reading(states, entity, now, 'solar')
        if raw is not None and raw > 2:
            self.small = None
        current = reading(states, entity, now, 'solar', 45)
        if current is not None:
            self.missing_since = None
            stamp = report_time(states, entity)
            self.small = (current, stamp) if 0 <= current <= 2 and stamp is not None else None
        elif self.missing_since is None or now < self.missing_since:
            self.missing_since = now

    def retained(self, now):
        if self.small is None:
            return None
        value, stamp = self.small
        age = (now-stamp).total_seconds()
        return {'value': value, 'age_s': age} if 0 <= age < PV_IDLE_MAX_AGE_S else None

    def decorate(self, report, now):
        source = report.get('sources', {}).get('solar', {})
        source.pop('warning_after', None)
        if source.get('available'):
            self.missing_since = None
            return report
        if not source.get('source') or source.get('reason') not in ('stale', 'state_unavailable'):
            return report
        if self.missing_since is None or now < self.missing_since:
            self.missing_since = now
        until = self.missing_since + timedelta(minutes=5)
        if self.small is not None and self.small[1] <= now:
            until = self.small[1] + timedelta(seconds=PV_IDLE_MAX_AGE_S)
        source['warning_after'] = until.isoformat()
        return report

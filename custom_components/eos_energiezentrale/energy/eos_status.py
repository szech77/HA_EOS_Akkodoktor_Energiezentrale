"""Bounded EOS computation status, including timestamp-only older health APIs."""
from .domain import instant


class EOSRunStatus:
    def __init__(self):
        self.checked = None
        self.running_since = None
        self.run_id = None
        self.running = False
        self.healthy = False

    def update(self, value, now):
        self.checked = now
        self.healthy = isinstance(value, dict) and value.get('status') == 'alive'
        if not self.healthy:
            return
        ems = value.get('energy-management')
        ems = ems if isinstance(ems, dict) else {}
        stage = ems.get('stage')
        started = instant(ems.get('start_datetime'))
        finished = instant(ems.get('last_run_datetime'))
        if stage in ('IDLE', 'DATA_AQUISITION', 'DATA_ACQUISITION', 'FORECAST_RETRIEVAL', 'OPTIMIZATION', 'CONTROL_DISPATCH'):
            running = stage != 'IDLE'
        else:
            # Older /v1/health exposes only start and last completion timestamps.
            running = bool(started and started <= now and (finished is None or started > finished))
        if running and (not self.running or self.run_id != started or self.running_since is None):
            self.running_since = now
        if not running:
            self.running_since = None
        self.running, self.run_id = running, started

    def snapshot(self, now, pending_since=None):
        fresh = bool(self.healthy and self.checked and 0 <= (now-self.checked).total_seconds() < 45)
        if not fresh:
            return {'state': 'unknown', 'grace': False, 'elapsed_s': 0}
        since = self.running_since if self.running else pending_since
        elapsed = max(0, (now-since).total_seconds()) if since else 0
        # A healthy timestamp-only API cannot identify runs inside the same rounded
        # planning slot. Still give an unavailable new plan a bounded update window.
        state = 'calculating' if self.running else 'updating' if since else 'idle'
        return {'state': state, 'grace': bool(since is not None and elapsed < 300),
                'elapsed_s': int(elapsed)}

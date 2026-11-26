"""Notice when a confirmed charging release does not lead to charging.

Like evcc's wake-up timer (30 s x 6), a connected vehicle that takes no power for
three minutes although the Energiezentrale wants to charge and the wallbox has
confirmed the release becomes a notice. It is display and log only and never
changes control. Wallbox plugins may explain the cause with ``idle_reason()``
returning one of ``IDLE_REASONS``.
"""
VEHICLE_IDLE_S = 180
IDLE_W = 30
AREA = 'vehicle_idle'
IDLE_REASONS = frozenset({
    'vehicle_complete', 'vehicle_waiting', 'access_control', 'load_management', 'ocpp', 'grid_monitoring',
    'unbalanced_load', 'charger_overtemperature', 'charger_error', 'charger_logic', 'simulating_unplug',
    'phase_switch', 'min_pause', 'reconnect_delay', 'adapter', 'unknown'})


class IdleReleaseWatch:
    def __init__(self):
        self.since = None
        self.reason = None
        self.updated = False

    def begin(self):
        """Start of a control cycle: a cycle without update ends the observation."""
        if not self.updated:
            self.since = self.reason = None
        self.updated = False

    def update(self, box, wants_charge, clock, driver):
        self.updated = True
        idle = bool(wants_charge and box.enabled and box.plugged and box.status == 'connected'
                    and box.watts is not None and box.watts <= IDLE_W)
        if not idle:
            self.since = self.reason = None
            return
        if self.since is None:
            self.since = clock
        if clock - self.since >= VEHICLE_IDLE_S:
            reason = None
            explain = getattr(driver, 'idle_reason', None)
            if callable(explain):
                try:
                    reason = explain()
                except Exception:  # A display hint never affects control.
                    reason = None
            self.reason = reason if reason in IDLE_REASONS else 'unknown'

    def active(self):
        return self.reason if self.updated and self.since is not None and self.reason else None

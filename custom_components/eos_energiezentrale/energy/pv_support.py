"""Debounced battery assistance for a PV session below minimum EV power."""


class PVSupport:
    def __init__(self):
        self.reset()

    def reset(self):
        self.since = self.last = self.import_since = None
        self.active = False
        self.required_w = 0
        self.policy = None

    def update(self, *, enabled, eligible, soc, floor, wait, clock, surplus,
               minimum, required, capacity, grid):
        policy = (enabled, floor, wait)
        if self.policy != policy or (self.last is not None and not 0 <= clock-self.last <= 45):
            self.reset()
        self.policy, self.last = policy, clock
        valid = (enabled and eligible and soc is not None and soc > floor
                 and surplus is not None and 0 < surplus < minimum
                 and 0 < required <= capacity)
        if not valid or (not self.active and soc < floor + 2):
            self.reset()
            return False
        if self.active and grid > 100:
            self.import_since = clock if self.import_since is None else self.import_since
            if clock-self.import_since >= 10:
                self.reset()
                return False
        else:
            self.import_since = None
        self.since = clock if self.since is None else self.since
        self.active = self.active or clock-self.since >= wait
        self.required_w = required if self.active else 0
        return self.active

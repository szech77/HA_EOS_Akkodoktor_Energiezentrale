"""Debounced battery assistance for a PV session below minimum EV power."""


class PVSupport:
    def __init__(self):
        self.reset()

    def reset(self):
        self.since = self.last = self.import_since = self.deficit_since = None
        self.active = False
        self.session = False
        self.required_w = 0
        self.policy = None

    def update(self, *, enabled, eligible, soc, floor, wait, clock, surplus,
               minimum, required, capacity, grid, threshold, pv_balance, running):
        policy = (enabled, floor, wait, threshold)
        if self.last is not None and not 0 <= clock-self.last <= 45:
            self.reset()
            return False
        if self.policy != policy:
            self.reset()
        self.policy, self.last = policy, clock
        valid = (enabled and eligible and soc is not None and soc > floor
                 and surplus is not None and pv_balance is not None)
        if not valid:
            self.reset()
            return False
        if not self.session:
            if running:
                # Preserve an existing local PV charge through later PV dips.
                self.session = True
            elif (soc >= floor + 2 and threshold <= surplus < minimum
                  and 0 < required <= capacity):
                self.since = clock if self.since is None else self.since
                self.session = clock-self.since >= wait
            else:
                self.since = None
        if not self.session:
            return False
        assisting = surplus < minimum
        if assisting and required > capacity:
            self.reset()
            return False
        # Compare PV with all loads except this EV, independently of the export
        # reserve and of battery power covering the deficit at the grid meter.
        if pv_balance <= -threshold:
            self.deficit_since = clock if self.deficit_since is None else self.deficit_since
            if clock-self.deficit_since >= 60:
                self.reset()
                return False
        else:
            self.deficit_since = None
        if assisting and grid > 100:
            self.import_since = clock if self.import_since is None else self.import_since
            if clock-self.import_since >= 10:
                self.reset()
                return False
        else:
            self.import_since = None
        self.active = assisting
        self.required_w = required if self.active else 0
        return self.active

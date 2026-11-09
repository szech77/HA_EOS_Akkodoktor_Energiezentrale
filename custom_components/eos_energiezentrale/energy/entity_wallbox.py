"""Shared acknowledged entity control, including zero-current phase switching."""
from datetime import datetime, timezone
from .contracts import WallboxDriver, WallboxReading
from .clients import reading
from .domain import number, instant
from .device_io import confirmed_state

class EntityWallbox(WallboxDriver):
    def _read(self, states, now):
        power = states.get(self.ids["power"], {})
        setting = states.get(self.ids["current"], {})
        attrs = setting.get("attributes", {})
        phase = number(states.get(self.ids["phases"], {}).get("state"))
        return WallboxReading(reading(states, self.ids["power"], now, "power", 120),
                              states.get(self.ids["status"], {}).get("state", "").lower() if states.get(self.ids["enable"],{}).get("state") in {"on","off"} else "unknown",
                              states.get(self.ids["enable"], {}).get("state") == "on",
                              int(phase) if phase in (1, 3) else None, number(setting.get("state")) if attrs.get("unit_of_measurement")=="A" else None,
                              number(attrs.get("step")), number(attrs.get("max")),
                              instant(power.get("last_reported") or power.get("last_updated")))

    def _pause(self, state):
        self.zero_sample = None
        self.zero_after = None
        self.phase_requested = None
        if state.enabled:
            self.ha.set(self.ids["enable"], False)

    def _phase(self, phases, state):
        if self.phase_requested is not None:
            requested, timestamp = self.phase_requested
            if state.phases == requested:
                self.phase_requested = None
                self.zero_sample = None
            elif state.sample and (state.sample - timestamp).total_seconds() > 45:
                raise ValueError("Wallbox did not confirm phase switch")
            else:
                return False
        if state.phases == phases:
            self.zero_sample = None
            self.zero_after = None
            return True
        if state.enabled:
            self.ha.set(self.ids["enable"], False)
            self.zero_after = datetime.now(timezone.utc)
            self.zero_sample = None
            return False
        if state.watts is None or abs(state.watts) > 30 or state.status != "connected" or state.sample is None:
            self.zero_sample = None
            if state.sample and (self.zero_after is None or state.sample > self.zero_after):
                self.zero_after = state.sample
            return False
        if self.zero_after is not None and state.sample <= self.zero_after:
            return False
        if self.zero_sample is None:
            self.zero_sample = state.sample
            return False
        if (state.sample - self.zero_sample).total_seconds() < 3:
            return False
        self.ha.set(self.ids["phases"], str(phases) if self.ids["phases"].split(".")[0] in {"select","input_select"} else phases)
        self.phase_requested = (phases, state.sample)
        return False

    def _charge(self, amps, state):
        if state.amps is None or abs(state.amps - amps) >= 0.05:
            self.ha.set(self.ids["current"], amps)
            confirmed_state(self.ha, self.ids["current"], lambda row:
                            (value := number(row.get("state"))) is not None and abs(value - amps) < 0.05)
        if not state.enabled:
            self.ha.set(self.ids["enable"], True)



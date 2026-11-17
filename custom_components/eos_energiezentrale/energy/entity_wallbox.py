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
        self._operation_context={'stage':'stop_request','parameter':'enable'}
        self.zero_sample = None
        self.zero_after = None
        self.phase_requested = None
        entity = self.ids["enable"]
        # A known "off" in the polled snapshot needs no command (readers report
        # status "unknown" unless the switch is on/off). An unavailable or missing
        # switch is no evidence of a stopped charge: re-check it live, request the
        # stop and require the entity itself to confirm "off".
        if not state.enabled and state.status not in {"unknown", "unavailable", ""}:
            return
        current = self.ha.state(entity).get("state")
        if current == "off":
            return
        self.ha.set(entity, False)
        self._operation_context={'stage':'stop_confirmation','parameter':'enable'}
        # An unavailable entity rarely recovers within seconds; keep polls short.
        confirmed_state(self.ha, entity, lambda row: row.get("state") == "off",
                        timeout=5 if current == "on" else 1)

    def _phase(self, phases, state):
        self._operation_context={'stage':'phase_feedback','parameter':'phase_feedback' if self.ids.get('phase_feedback') else 'phases'}
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
            self._operation_context={'stage':'stop_request','parameter':'enable'}
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
        self._operation_context={'stage':'phase_request','parameter':'phases'}
        self.ha.set(self.ids["phases"], str(phases) if self.ids["phases"].split(".")[0] in {"select","input_select"} else phases)
        self.phase_requested = (phases, state.sample)
        return False

    def _charge(self, amps, state):
        self._operation_context={'stage':'write_confirmation','parameter':'current'}
        if state.amps is None or abs(state.amps - amps) >= 0.05:
            self.ha.set(self.ids["current"], amps)
            confirmed_state(self.ha, self.ids["current"], lambda row:
                            (value := number(row.get("state"))) is not None and abs(value - amps) < 0.05)
        if not state.enabled:
            self._operation_context={'stage':'enable_request','parameter':'enable'}
            self.ha.set(self.ids["enable"], True)



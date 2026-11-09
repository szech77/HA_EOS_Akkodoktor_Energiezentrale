"""Hardware contracts and built-in driver registry. Add new types here."""
from dataclasses import dataclass
from datetime import datetime, timezone
from math import floor
from time import monotonic, sleep
from typing import Protocol

from .clients import ENTITY, reading
from .domain import BatteryCommand, instant, number


@dataclass(frozen=True)
class BatteryReading:
    soc: float | None
    charge: float | None
    discharge: float | None


@dataclass(frozen=True)
class WallboxReading:
    watts: float | None
    status: str
    enabled: bool
    phases: int | None
    amps: float | None
    step: float | None
    maximum: float | None
    sample: datetime | None

    @property
    def plugged(self):
        return self.status in {"connected", "charging", "wakeup"}

    @property
    def charging(self):
        return self.enabled and self.status == "charging" and (self.watts or 0) > 500


class BatteryDriver(Protocol):
    def read(self, states: dict, now: datetime) -> BatteryReading: ...
    def apply(self, command: BatteryCommand, states: dict) -> None: ...
    def release(self, states: dict) -> None: ...


class WallboxDriver(Protocol):
    def read(self, states: dict, now: datetime) -> WallboxReading: ...
    def pause(self, state: WallboxReading) -> None: ...
    def phase(self, phases: int, state: WallboxReading) -> bool: ...
    def charge(self, amps: float, state: WallboxReading) -> None: ...


def entities(defaults, supplied):
    if not isinstance(supplied, dict) or supplied.keys() - defaults.keys():
        raise ValueError("Unbekannte Treiberparameter")
    result = {**defaults, **supplied}
    for name, value in result.items():
        if not value and name == "grid_discharge":
            continue
        domain = defaults[name].split(".")[0] if defaults[name] else "number"
        if not isinstance(value, str) or not ENTITY.fullmatch(value) or not value.startswith(domain + "."):
            raise ValueError(f"Ungültige Entität für {name}")
    return result


class DeviceNotReady(RuntimeError):
    """A mode-dependent control entity is still waiting for its next report."""
    def __init__(self, entity):
        super().__init__(f"Waiting for control entity: {entity}")
        self.entity = entity


class DeviceConfirmationError(ValueError):
    """A local control entity did not confirm the requested state."""
    def __init__(self, entity):
        super().__init__(f"Device state not confirmed: {entity}")
        self.entity = entity


def confirmed_state(ha, entity, matches, timeout=5):
    deadline = monotonic() + timeout
    while True:
        row = ha.state(entity)
        if matches(row):
            return row
        if monotonic() >= deadline:
            raise DeviceConfirmationError(entity)
        sleep(0.4)


class Fronius:
    prefix = "number.byd_battery_box_premium_hv_"
    defaults = {"mode": "select.byd_battery_box_premium_hv_storage_control_mode",
                "soc": "sensor.byd_battery_box_premium_hv_ladezustand",
                "charge_power": "sensor.fronius_symo_gen24_storage_charging_power",
                "discharge_power": "sensor.fronius_symo_gen24_storage_discharging_power",
                "pv_limit": prefix + "pv_charge_limit", "discharge_limit": prefix + "discharge_limit",
                "grid_charge": prefix + "grid_charge_power", "grid_discharge": ""}
    modes = {"limits": "PV Charge and Discharge Limit", "block_discharge": "Block Discharging",
             "grid_charge": "Charge from Grid", "grid_discharge": "Discharge to Grid"}

    def __init__(self, ha, params):
        self.ha = ha
        self.ids = entities(self.defaults, params)
        self.pending_limits = {}

    def read(self, states, now):
        return BatteryReading(reading(states, self.ids["soc"], now, "soc", 120),
                              reading(states, self.ids["charge_power"], now, "power", 120),
                              reading(states, self.ids["discharge_power"], now, "power", 120))

    def release(self, states):
        self.pending_limits.clear()
        if states.get(self.ids["mode"], {}).get("state") != "Auto":
            self.ha.set(self.ids["mode"], "Auto")
            confirmed_state(self.ha, self.ids["mode"], lambda row: row.get("state") == "Auto")

    def apply(self, command, states):
        mode_id = self.ids["mode"]
        mode = self.modes[command.mode]
        limits = {"limits": (("pv_limit", command.charge_w), ("discharge_limit", command.discharge_w)),
                  "block_discharge": (("pv_limit", command.charge_w),),
                  "grid_charge": (("grid_charge", command.charge_w),),
                  "grid_discharge": (("grid_discharge", command.discharge_w),)}[command.mode]
        if any(not self.ids[key] for key, _ in limits):
            raise ValueError("Fronius-Leistungsentität fehlt")
        if states.get(mode_id, {}).get("state") != mode:
            self.ha.set(mode_id, mode)
            confirmed_state(self.ha, mode_id, lambda row: row.get("state") == mode)
        for key, watts in limits:
            entity = self.ids[key]
            row = self.ha.state(entity)
            if number(row.get("state")) is None:
                now = monotonic()
                since = self.pending_limits.setdefault(entity, now)
                if now - since >= 45:
                    raise DeviceConfirmationError(entity)
                raise DeviceNotReady(entity)
            self.pending_limits.pop(entity, None)
            attrs = row.get("attributes", {})
            maximum, step = number(attrs.get("max")), number(attrs.get("step"))
            if maximum is None or not step or attrs.get("unit_of_measurement") != "W":
                raise ValueError("Fronius-Limit nicht verfügbar")
            target = floor(min(maximum, max(0, watts)) / step) * step
            actual = number(row.get("state"))
            if actual is None or abs(actual - target) >= step / 2:
                self.ha.set(entity, target)
                confirmed_state(self.ha, entity, lambda sample:
                                (value := number(sample.get("state"))) is not None and abs(value - target) < step / 2)


class NRGkick:
    defaults = {"power": "sensor.nrgkick_id_4_gesamt_wirkleistung",
                "status": "sensor.nrgkick_id_4_status",
                "enable": "switch.nrgkick_id_4_laden_aktiviert",
                "current": "number.nrgkick_id_4_ladestromstarke",
                "phases": "number.nrgkick_id_4_phasenanzahl"}

    def __init__(self, ha, params):
        self.ha = ha
        self.ids = entities(self.defaults, params)
        self.zero_sample = None
        self.zero_after = None
        self.phase_requested = None

    def read(self, states, now):
        power = states.get(self.ids["power"], {})
        setting = states.get(self.ids["current"], {})
        attrs = setting.get("attributes", {})
        phase = number(states.get(self.ids["phases"], {}).get("state"))
        return WallboxReading(reading(states, self.ids["power"], now, "power", 120),
                              states.get(self.ids["status"], {}).get("state", "").lower(),
                              states.get(self.ids["enable"], {}).get("state") == "on",
                              int(phase) if phase in (1, 3) else None, number(setting.get("state")),
                              number(attrs.get("step")), number(attrs.get("max")),
                              instant(power.get("last_reported") or power.get("last_updated")))

    def pause(self, state):
        self.zero_sample = None
        self.zero_after = None
        self.phase_requested = None
        if state.enabled:
            self.ha.set(self.ids["enable"], False)

    def phase(self, phases, state):
        if self.phase_requested is not None:
            requested, timestamp = self.phase_requested
            if state.phases == requested:
                self.phase_requested = None
                self.zero_sample = None
            elif state.sample and (state.sample - timestamp).total_seconds() > 45:
                raise ValueError("NRGkick bestätigt Phasenwechsel nicht")
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
        self.ha.set(self.ids["phases"], phases)
        self.phase_requested = (phases, state.sample)
        return False

    def charge(self, amps, state):
        if state.amps is None or abs(state.amps - amps) >= 0.05:
            self.ha.set(self.ids["current"], amps)
            confirmed_state(self.ha, self.ids["current"], lambda row:
                            (value := number(row.get("state"))) is not None and abs(value - amps) < 0.05)
        if not state.enabled:
            self.ha.set(self.ids["enable"], True)


BATTERY_DRIVERS = {"fronius": Fronius}
WALLBOX_DRIVERS = {"nrgkick": NRGkick}

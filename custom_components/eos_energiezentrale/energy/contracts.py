"""Versioned hardware plugin API. Public methods enforce the safety boundary."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import ClassVar, Mapping

from .domain import BatteryCommand

API_VERSION = 2


@dataclass(frozen=True)
class PluginInfo:
    identifier: str
    name: str
    kind: str
    api_version: int = API_VERSION


@dataclass(frozen=True)
class PluginField:
    key: str
    label: str
    kind: str = "entity"
    required: bool = True
    default: object = None
    domains: tuple[str, ...] = ()
    choices: tuple[str, ...] = ()


@dataclass(frozen=True)
class BatteryFeatures:
    charge_limit: bool = True
    discharge_limit: bool = True
    grid_charge: bool = True
    grid_discharge: bool = False


@dataclass(frozen=True)
class WallboxFeatures:
    phase_switching: bool = True


@dataclass(frozen=True)
class BatteryReading:
    soc: float | None
    charge: float | None
    discharge: float | None
    soc_sample: datetime | None = None
    charge_sample: datetime | None = None
    discharge_sample: datetime | None = None


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


class PluginContractError(ValueError):
    """A plugin does not satisfy the published API."""


class UnsupportedFeature(PluginContractError):
    """A command requests a capability this device does not provide."""


class BatteryDriver(ABC):
    info: ClassVar[PluginInfo]
    configuration: ClassVar[tuple[PluginField, ...]]
    features: BatteryFeatures
    ids: Mapping[str, str]

    def read(self, states: dict, now: datetime) -> BatteryReading:
        from .sanitiser import battery_reading
        return battery_reading(self._read(states,now),now)

    def apply(self, command: BatteryCommand, states: dict) -> None:
        from .sanitiser import battery_command
        command = battery_command(command)
        if command.mode in {"grid_charge","grid_discharge"} and not getattr(self.features,command.mode):
            raise UnsupportedFeature(command.mode)
        if command.mode in {"limits","block_discharge"} and (not self.features.charge_limit or not self.features.discharge_limit):
            raise UnsupportedFeature("battery limits")
        if self._apply(command,states) is not None:
            raise PluginContractError("Battery apply must return None")

    def release(self, states: dict) -> None:
        if self._release(states) is not None:
            raise PluginContractError("Battery release must return None")

    @abstractmethod
    def _read(self, states: dict, now: datetime) -> BatteryReading: ...
    @abstractmethod
    def _apply(self, command: BatteryCommand, states: dict) -> None: ...
    @abstractmethod
    def _release(self, states: dict) -> None: ...


class WallboxDriver(ABC):
    info: ClassVar[PluginInfo]
    configuration: ClassVar[tuple[PluginField, ...]]
    features: WallboxFeatures
    ids: Mapping[str, str]

    def read(self, states: dict, now: datetime) -> WallboxReading:
        from .sanitiser import wallbox_reading
        return wallbox_reading(self._read(states,now),now)

    def pause(self, state: WallboxReading) -> None:
        from .sanitiser import wallbox_reading
        if self._pause(wallbox_reading(state)) is not None:
            raise PluginContractError("Wallbox pause must return None")

    def phase(self, phases: int, state: WallboxReading) -> bool:
        from .sanitiser import wallbox_reading
        if type(phases) is not int or phases not in (1,3):
            raise PluginContractError("Invalid phase count")
        if not self.features.phase_switching:
            raise UnsupportedFeature("phase_switching")
        result = self._phase(phases,wallbox_reading(state))
        if type(result) is not bool:
            raise PluginContractError("Phase switch must return bool")
        return result

    def charge(self, amps: float, state: WallboxReading) -> None:
        from .sanitiser import charging_current, wallbox_reading
        state = wallbox_reading(state)
        amps = charging_current(amps,state)
        if self._charge(amps,state) is not None:
            raise PluginContractError("Wallbox charge must return None")

    @abstractmethod
    def _read(self, states: dict, now: datetime) -> WallboxReading: ...
    @abstractmethod
    def _pause(self, state: WallboxReading) -> None: ...
    @abstractmethod
    def _phase(self, phases: int, state: WallboxReading) -> bool: ...
    @abstractmethod
    def _charge(self, amps: float, state: WallboxReading) -> None: ...

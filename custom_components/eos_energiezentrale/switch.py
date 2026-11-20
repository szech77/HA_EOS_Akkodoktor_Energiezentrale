"""Explicit controller ownership and everyday charging switches."""
from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError

from .entity import EnergyEntity


# Separate control areas; a switch exists only with a matching controllable device.
AREAS = {"control_battery": "battery", "control_vehicle": "vehicle"}


async def async_setup_entry(hass, entry, async_add_entities):
    coordinator = entry.runtime_data
    controllable = getattr(coordinator.app, "controllable", None)
    areas = [key for key, area in AREAS.items() if callable(controllable) and controllable(area)]
    async_add_entities(EnergySwitch(coordinator, key) for key in
                       ("control", *areas, "pv", "fast", "battery_pv_support", "battery_pv_start", "phase_auto"))


class EnergySwitch(EnergyEntity, SwitchEntity):
    @property
    def is_on(self):
        data = self.coordinator.data or {}
        if self.key in AREAS:
            return bool(((data.get("control") or {}).get(AREAS[self.key]) or {}).get("enabled"))
        return bool(data.get("armed") if self.key == "control" else data.get("settings", {}).get(self.key))

    async def _set(self, enabled):
        try:
            if self.key == "control":
                await self.coordinator.async_change(enabled=enabled)
            elif self.key in AREAS:
                await self.coordinator.async_change(control={AREAS[self.key]: enabled})
            else:
                await self.coordinator.async_change(settings={self.key: enabled})
        except (ValueError, OSError, TimeoutError) as error:
            raise HomeAssistantError("Control change was not confirmed") from error

    async def async_turn_on(self, **kwargs):
        await self._set(True)

    async def async_turn_off(self, **kwargs):
        await self._set(False)

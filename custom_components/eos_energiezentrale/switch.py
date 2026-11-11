"""Explicit controller ownership and everyday charging switches."""
from homeassistant.components.switch import SwitchEntity
from homeassistant.exceptions import HomeAssistantError

from .entity import EnergyEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(EnergySwitch(entry.runtime_data, key) for key in
                       ("control", "pv", "fast", "battery_pv_support", "battery_pv_start", "phase_auto"))


class EnergySwitch(EnergyEntity, SwitchEntity):
    @property
    def is_on(self):
        data = self.coordinator.data or {}
        return bool(data.get("armed") if self.key == "control" else data.get("settings", {}).get(self.key))

    async def _set(self, enabled):
        try:
            if self.key == "control":
                await self.coordinator.async_change(enabled=enabled)
            else:
                await self.coordinator.async_change(settings={self.key: enabled})
        except (ValueError, OSError, TimeoutError) as error:
            raise HomeAssistantError("Control change was not confirmed") from error

    async def async_turn_on(self, **kwargs):
        await self._set(True)

    async def async_turn_off(self, **kwargs):
        await self._set(False)

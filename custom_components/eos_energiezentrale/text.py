"""Departure fields for dashboards; full schedule editor lives in the panel."""
from homeassistant.components.text import TextEntity

from .entity import EnergyEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(EnergyText(entry.runtime_data, key) for key in ("departure", "departure_time"))


class EnergyText(EnergyEntity, TextEntity):
    _attr_native_max = 40

    @property
    def available(self):
        return super().available and (self.coordinator.data or {}).get('settings', {}).get('charge_plans') is None

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("settings", {}).get(self.key)

    async def async_set_value(self, value):
        if (self.coordinator.data or {}).get('settings', {}).get('charge_plans') is not None:
            raise ValueError('Edit charging goals in the vehicle panel')
        await self.coordinator.async_change(settings={self.key: value})

"""One-time, recurring or disabled departure planning."""
from homeassistant.components.select import SelectEntity

from .entity import EnergyEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([ScheduleSelect(entry.runtime_data, "schedule")])


class ScheduleSelect(EnergyEntity, SelectEntity):
    _attr_options = ["off", "once", "weekly"]

    @property
    def available(self):
        return super().available and (self.coordinator.data or {}).get('settings', {}).get('charge_plans') is None

    @property
    def current_option(self):
        return (self.coordinator.data or {}).get("settings", {}).get("schedule")

    async def async_select_option(self, option):
        if (self.coordinator.data or {}).get('settings', {}).get('charge_plans') is not None:
            raise ValueError('Edit charging goals in the vehicle panel')
        await self.coordinator.async_change(settings={"schedule": option})

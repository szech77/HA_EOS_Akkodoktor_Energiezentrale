"""Availability of the current plan and controller errors."""
from homeassistant.components.binary_sensor import BinarySensorEntity

from .entity import EnergyEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(EnergyBinarySensor(entry.runtime_data, key)
                       for key in ("plan_current", "problem", "release_pending"))


class EnergyBinarySensor(EnergyEntity, BinarySensorEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        if key in {"problem", "release_pending"}:
            self._attr_device_class = "problem"

    @property
    def is_on(self):
        data = self.coordinator.data or {}
        if self.key == "problem":
            return bool(data.get("errors"))
        if self.key == "plan_current":
            return bool(data.get("plan_end"))
        return bool(data.get("release_pending"))

    @property
    def extra_state_attributes(self):
        if self.key == "problem":
            return {"errors": (self.coordinator.data or {}).get("errors", {})}
        return None

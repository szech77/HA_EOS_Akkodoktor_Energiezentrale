"""Daily target SoCs and PV tuning parameters."""
from homeassistant.components.number import NumberEntity, NumberMode

from .entity import EnergyEntity

NUMBERS = {"target_soc": (1, 100, "%"), "pv_target_soc": (1, 100, "%"),
           "battery_min_soc": (0, 99, "%"), "battery_max_soc": (1, 100, "%"),
           "battery_pv_min_soc": (0, 98, "%"), "battery_pv_wait_s": (10, 600, "s"),
           "battery_pv_surplus_w": (1, 5000, "W"),
           "reserve_w": (0, 500, "W"), "regulation_interval_s": (5, 120, "s")}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(EnergyNumber(entry.runtime_data, key) for key in NUMBERS)


class EnergyNumber(EnergyEntity, NumberEntity):
    _attr_mode = NumberMode.BOX
    _attr_native_step = 1

    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        self._attr_native_min_value, self._attr_native_max_value, self._attr_native_unit_of_measurement = NUMBERS[key]

    @property
    def native_value(self):
        return (self.coordinator.data or {}).get("settings", {}).get(self.key)

    async def async_set_native_value(self, value):
        if value != int(value):
            raise ValueError("Whole number required")
        await self.coordinator.async_change(settings={self.key: int(value)})

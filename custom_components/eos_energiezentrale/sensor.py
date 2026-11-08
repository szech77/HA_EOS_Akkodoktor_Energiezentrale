"""Native metering, SoC estimates and EOS modes."""
from homeassistant.components.sensor import SensorEntity, SensorStateClass

from .entity import EnergyEntity

SENSORS = {
    "solar": ("kW", "power"), "house": ("kW", "power"), "heat": ("kW", "power"),
    "grid": ("kW", "power"), "car": ("kW", "power"), "battery": ("kW", "power"),
    "battery_charge": ("kW", "power"), "battery_discharge": ("kW", "power"),
    "battery_soc": ("%", "battery"), "car_soc": ("%", "battery"),
    "car_soc_factor": (None, None), "price": ("ct/kWh", None),
    "battery_mode": (None, None), "car_mode": (None, None), "car_status": (None, None),
}


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(EnergySensor(entry.runtime_data, key) for key in SENSORS)


class EnergySensor(EnergyEntity, SensorEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        if key in {"car", "car_soc", "car_soc_factor", "car_mode", "car_status"}:
            self._attr_translation_placeholders = {
                "vehicle": coordinator.app.config.options.get("vehicle_name", "E-Auto").strip()}
        unit, device_class = SENSORS[key]
        self._attr_native_unit_of_measurement = unit
        self._attr_device_class = device_class
        if unit is not None or key == "car_soc_factor":
            self._attr_state_class = SensorStateClass.MEASUREMENT
        self._attr_suggested_display_precision = 2 if unit == "kW" else 1

    @property
    def native_value(self):
        live = (self.coordinator.data or {}).get("live", {})
        value = live.get("car_soc" if self.key == "car_soc_factor" else self.key)
        if value is None:
            return None
        if self.key == "car_soc_factor":
            return value / 100
        return value / 1000 if self.native_unit_of_measurement == "kW" else value

    @property
    def extra_state_attributes(self):
        if self.key in {"car_soc", "car_soc_factor"}:
            return {"source": (self.coordinator.data or {}).get("live", {}).get("soc_source")}
        return None

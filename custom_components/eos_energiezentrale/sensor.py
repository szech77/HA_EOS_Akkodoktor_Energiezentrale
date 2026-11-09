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
    coordinator=entry.runtime_data
    entities=[EnergySensor(coordinator,key) for key in SENSORS]
    for identity,app,_ in getattr(coordinator.app,"controllers",[]):
        entities.extend(VehicleSensor(coordinator,identity,app.config.options["vehicle_name"],key)
                        for key in ("car","car_soc","car_soc_factor","car_mode","car_status"))
    async_add_entities(entities)


class EnergySensor(EnergyEntity, SensorEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        if key in {"car", "car_soc", "car_soc_factor", "car_mode", "car_status"}:
            self._attr_translation_placeholders = {
                "vehicle": "E-Autos" if hasattr(coordinator.app,"controllers") else coordinator.app.config.options.get("vehicle_name", "E-Auto").strip()}
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


class VehicleSensor(EnergySensor):
    """Stable per-vehicle entities in addition to the aggregate charger power."""
    def __init__(self,coordinator,identity,name,key):
        super().__init__(coordinator,key)
        self.identity=identity
        self._attr_unique_id=f"{coordinator.entry.entry_id}_vehicle_{identity}_{key}"
        self._attr_translation_placeholders={"vehicle":name}

    @property
    def vehicle_live(self):
        return next((item["live"] for item in (self.coordinator.data or {}).get("vehicles",[])
                     if item["id"]==self.identity),{})

    @property
    def native_value(self):
        value=self.vehicle_live.get("car_soc" if self.key=="car_soc_factor" else self.key)
        if value is None:
            return None
        if self.key=="car_soc_factor":
            return value/100
        return value/1000 if self.native_unit_of_measurement=="kW" else value

    @property
    def extra_state_attributes(self):
        return {"vehicle_id":self.identity,"source":self.vehicle_live.get("soc_source")}

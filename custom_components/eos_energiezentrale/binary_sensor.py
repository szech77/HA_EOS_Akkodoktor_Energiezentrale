"""Availability of the current plan and controller errors."""
from homeassistant.components.binary_sensor import BinarySensorEntity

from .entity import EnergyEntity


async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities(EnergyBinarySensor(entry.runtime_data, key)
                       for key in ("plan_current", "problem", "release_pending", "battery_limits_confirmed", "backup_power"))


class EnergyBinarySensor(EnergyEntity, BinarySensorEntity):
    def __init__(self, coordinator, key):
        super().__init__(coordinator, key)
        if key in {"problem", "release_pending"}:
            self._attr_device_class = "problem"
        if key == 'backup_power':
            self._attr_icon = 'mdi:home-lightning-bolt'

    @property
    def available(self):
        return super().available and (self.key != 'backup_power' or
            (self.coordinator.data or {}).get('power_supply', {}).get('state') in ('grid', 'backup'))

    @property
    def is_on(self):
        data = self.coordinator.data or {}
        if self.key == 'backup_power':
            return {'backup':True, 'grid':False}.get(data.get('power_supply', {}).get('state'))
        if self.key == "battery_limits_confirmed":
            return bool(data.get("battery_limits", {}).get("confirmed"))
        if self.key == "problem":
            return (any(item.get('severity') != 'info' for item in data['notices'])
                    if 'notices' in data else bool(data.get('errors')))
        if self.key == "plan_current":
            return bool(data.get("plan_end"))
        return bool(data.get("release_pending"))

    @property
    def extra_state_attributes(self):
        if self.key == 'backup_power':
            data = self.coordinator.data or {}
            return {'operating_state':data.get('power_supply', {}).get('state', 'unsupported'),
                    'sample':data.get('power_supply', {}).get('sample'),
                    'control_paused':data.get('control_paused', False)}
        if self.key == "problem":
            return {"errors": (self.coordinator.data or {}).get("errors", {}),
                    "notices": (self.coordinator.data or {}).get("notices", [])}
        return None

"""Compatibility exports; implementations are discovered from the plugins package."""
from .contracts import BatteryDriver, WallboxDriver, BatteryReading, WallboxReading
from .device_io import entities, confirmed_state, DeviceNotReady, DeviceConfirmationError
from .plugin_registry import load_plugins

BATTERY_DRIVERS, WALLBOX_DRIVERS, INVERTER_DRIVERS, PLUGIN_ERRORS = load_plugins(include_inverters=True)

# Stable imports for existing extensions; these classes are not the registry.
from .plugins.fronius import Fronius
from .plugins.nrgkick import NRGkick
from .plugins.none import NoWallbox

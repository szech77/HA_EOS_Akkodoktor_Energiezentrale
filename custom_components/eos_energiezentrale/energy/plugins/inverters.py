"""Read-only inverter plugins, independent of storage control."""
from ..contracts import InverterDriver, InverterReading, PluginField, PluginInfo, Measurement
from ..clients import reading, report_time
from ..plugin_parameters import parameters
from .fronius_modbus import FroniusModbus


class FroniusInverter(InverterDriver):
    info = PluginInfo('fronius_modbus', 'Fronius PV inverter / Modbus TCP', 'inverter')
    configuration = tuple(field for field in FroniusModbus.configuration if field.key not in {
        'battery_capacity_wh', 'additional_inverters', 'grid_discharge_supported'})

    def __init__(self, ha, params):
        values = parameters(self.configuration, params)
        self.driver = FroniusModbus(ha, values)
        self.ids = {}
        self.measurement_keys = ('solar', 'inverter_ac') + (('grid',) if values['grid_meter_enabled'] else ())

    def _read(self, states, now):
        solar, ac = self.driver._generation()
        result = {'solar': Measurement(solar, now), 'inverter_ac': Measurement(ac, now)}
        if 'grid' in self.measurement_keys:
            try:
                grid = self.driver._grid_power()
            except (OSError, ValueError):
                self.driver.grid_model = None
                grid = None
            result['grid'] = Measurement(grid, now)
        return InverterReading(result)

    @property
    def device_key(self):
        return self.driver.device_key


class GenericInverter(InverterDriver):
    info = PluginInfo('generic', 'Home Assistant PV inverter', 'inverter')
    configuration = (
        PluginField('solar', 'PV power (DC, W/kW)', domains=('sensor',)),
        PluginField('inverter_ac', 'Signed inverter AC power (W/kW)', domains=('sensor',)),
        PluginField('grid', 'Signed grid power (optional)', required=False, default='', domains=('sensor',)),
    )

    def __init__(self, ha, params):
        self.ids = parameters(self.configuration, params)
        self.measurement_keys = tuple(key for key, value in self.ids.items() if value)

    def _read(self, states, now):
        return InverterReading({key: Measurement(reading(states, entity, now, 'power', 45), report_time(states, entity))
            for key, entity in self.ids.items() if entity})


PLUGINS = (FroniusInverter, GenericInverter)

"""Options of a fully configured test installation: the product defaults plus example sensors.

The product ships without preset sensor entities; tests that need a configured site use these."""
from custom_components.eos_energiezentrale.const import DEFAULTS as PRODUCT_DEFAULTS

SENSORS = {'pv_entity': 'sensor.pv_power', 'house_entity': 'sensor.house_power',
           'grid_entity': 'sensor.grid_power', 'heat_entity': 'sensor.heat_pump_power',
           'price_entity': 'sensor.electricity_price', 'car_soc_entity': 'sensor.ev_soc'}
DEFAULTS = {**PRODUCT_DEFAULTS, **SENSORS}

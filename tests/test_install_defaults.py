"""A new installation starts without preset sensor entities."""
from custom_components.eos_energiezentrale.config_flow import schema_for
from custom_components.eos_energiezentrale.const import DEFAULTS, GROUPS


def test_new_installations_start_without_preset_sensor_entities():
    entities = [key for key in GROUPS['sensors'] if key.endswith('_entity')]
    assert entities and all(DEFAULTS[key] == '' for key in entities)
    # The sensor step therefore suggests nothing; the user picks the own entities.
    fields = {str(key): key for key in schema_for('sensors', DEFAULTS).schema}
    assert all(not (fields[key].description or {}).get('suggested_value') for key in entities)

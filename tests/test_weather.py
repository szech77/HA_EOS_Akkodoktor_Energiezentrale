"""Current weather display, independent of energy control."""
import unittest
from datetime import datetime, timedelta, timezone
from custom_components.eos_energiezentrale.energy.presentation import weather_display
from custom_components.eos_energiezentrale.validation import validate_options
from custom_components.eos_energiezentrale.const import DEFAULTS

NOW = datetime(2026, 11, 9, 12, tzinfo=timezone.utc)


def weather(temperature=12.5, condition="partlycloudy", unit="°C", age=0):
    return {"state": condition, "attributes": {"temperature": temperature, "temperature_unit": unit},
            "last_reported": (NOW-timedelta(seconds=age)).isoformat()}


class WeatherDisplayTests(unittest.TestCase):
    def test_current_temperature_and_condition_from_selected_source(self):
        result = weather_display({"weather.home": weather(-2.5)}, {"weather_entity": "weather.home"}, NOW)
        self.assertEqual(result, {"condition": "partlycloudy", "temperature": -2.5, "unit": "°C"})

    def test_automatic_choice_is_stable_and_ignores_unavailable_entities(self):
        states = {"weather.z": weather(22), "weather.a": weather(4),
                  "weather.0": weather(condition="unavailable")}
        self.assertEqual(weather_display(states, {}, NOW)["temperature"], 4)
        self.assertIsNone(weather_display({}, {}, NOW))

    def test_explicit_missing_source_does_not_show_another_locations_weather(self):
        result = weather_display({"weather.other": weather(30)}, {"weather_entity": "weather.home"}, NOW)
        self.assertEqual(result["condition"], "unknown")
        self.assertIsNone(result["temperature"])

    def test_stale_unavailable_nonfinite_or_impossible_values_are_not_temperatures(self):
        for item in (weather(age=3601), weather(condition="unavailable"), weather(float("nan")),
                     weather(900), weather(True), weather(unit="W"), weather(age=-10)):
            with self.subTest(item=item):
                self.assertIsNone(weather_display({"weather.home": item}, {"weather_entity": "weather.home"}, NOW)["temperature"])

    def test_fahrenheit_kelvin_and_zero_are_preserved(self):
        for temperature, unit in ((32, "°F"), (273.15, "K"), (0, "°C")):
            result = weather_display({"weather.home": weather(temperature, unit=unit)}, {}, NOW)
            self.assertEqual((result["temperature"], result["unit"]), (temperature, unit))

    def test_only_weather_entities_are_configurable(self):
        for entity in ("", "weather.home"):
            validate_options({**DEFAULTS, "weather_entity": entity})
        for entity in ("sensor.temperature", "weather.bad/path", None):
            with self.subTest(entity=entity), self.assertRaises(ValueError):
                validate_options({**DEFAULTS, "weather_entity": entity})


    def test_weather_picker_stays_selectable_in_home_assistant_and_can_be_cleared(self):
        import probatio
        from homeassistant.helpers.config_validation import custom_serializer
        from custom_components.eos_energiezentrale.config_flow import schema_for
        schema = schema_for("sensors", DEFAULTS)
        fields = probatio.to_field_list(schema, custom_serializer=custom_serializer)
        field = next(item for item in fields if item["name"] == "weather_entity")
        self.assertIn("entity", field["selector"])
        self.assertEqual(schema({key: DEFAULTS[key] for key in ("pv_entity", "house_entity",
            "grid_entity", "heat_load_scale", "price_entity", "car_soc_scale")})["pv_entity"], DEFAULTS["pv_entity"])
        picker = next(value for key, value in schema.schema.items() if key.schema == "weather_entity")
        self.assertEqual(picker("weather.home"), "weather.home")
        self.assertEqual(picker(""), "")

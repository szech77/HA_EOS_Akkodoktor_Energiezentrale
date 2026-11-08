"""Stationary SoC bounds: persistence, REST preservation and retry behavior."""
from copy import deepcopy
from datetime import timedelta
import json
import unittest
from unittest.mock import Mock, patch

from custom_components.eos_energiezentrale.const import DEFAULTS
from custom_components.eos_energiezentrale.energy.clients import EOS
from custom_components.eos_energiezentrale.energy.controller import Controller
from custom_components.eos_energiezentrale.energy.settings import Configuration, daily_settings
from test_energy import NOW, temporary_project_directory
from test_http_boundaries import FixtureHandler, transport


class BatteryConfigServer(FixtureHandler):
    def respond(self):
        if self.path == "/v1/config" and self.command == "GET":
            payload = self.server.configuration
        elif self.path == "/v1/config/devices/batteries" and self.command == "PUT":
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            self.server.writes.append(payload)
            if self.server.apply_write:
                self.server.configuration["devices"]["batteries"] = payload
            payload = {}
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    do_GET = do_PUT = respond


class BatteryLimitsRequirements(unittest.TestCase):
    def configuration(self):
        return {"devices": {
            "batteries": {"battery1": {"device_id": "battery1", "capacity_wh": 11059,
                           "min_soc_percentage": 20, "max_soc_percentage": 100,
                           "charging_efficiency": .9, "charge_rates": [0, .5, 1]},
                          "battery2": {"device_id": "battery2", "capacity_wh": 8000}},
            "electric_vehicles": {"ev1": {"capacity_wh": 77000}},
            "inverters": {"inverter1": {"battery_id": "battery1", "max_power_w": 10000}}}}

    def test_rest_updates_limits_preserves_configuration_and_avoids_repeated_put(self):
        config = self.configuration()
        before = deepcopy(config)
        writes = []
        with transport(eos=(BatteryConfigServer, {"configuration":config, "writes":writes, "apply_write":True})):
            client = EOS("http://eos")
            client.set_battery_limits("battery1", 30, 90)
            client.set_battery_limits("battery1", 30, 90)
        self.assertEqual(len(writes), 1)
        desired = config["devices"]["batteries"]["battery1"]
        self.assertEqual((desired["min_soc_percentage"], desired["max_soc_percentage"]), (30, 90))
        expected = deepcopy(before)
        expected["devices"]["batteries"]["battery1"].update(min_soc_percentage=30, max_soc_percentage=90)
        self.assertEqual(config, expected)

    def test_rejected_write_or_missing_resource_is_not_reported_as_confirmed(self):
        for resource in ("battery1", "not_configured"):
            with self.subTest(resource=resource):
                writes = []
                config = self.configuration()
                before = deepcopy(config)
                with transport(eos=(BatteryConfigServer, {"configuration":config, "writes":writes, "apply_write":False})):
                    with self.assertRaises(ValueError):
                        EOS("http://eos").set_battery_limits(resource, 30, 90)
                self.assertEqual(config, before)
                self.assertEqual(len(writes), 1 if resource == "battery1" else 0)

    def test_invalid_pairs_never_reach_network(self):
        for minimum, maximum in ((-1,90), (20,101), (90,90), (95,90), (True,90), (20.5,90)):
            with self.subTest(minimum=minimum, maximum=maximum):
                with patch("custom_components.eos_energiezentrale.energy.clients.request") as http:
                    with self.assertRaises(ValueError):
                        EOS("http://eos").set_battery_limits("battery1", minimum, maximum)
                    http.assert_not_called()
                with self.assertRaises(ValueError):
                    daily_settings({"battery_min_soc": minimum, "battery_max_soc": maximum}, 20)
        self.assertEqual(daily_settings({"battery_min_soc":0, "battery_max_soc":100},20)["battery_min_soc"], 0)

    def test_existing_config_is_seeded_without_implicitly_taking_over_eos(self):
        with temporary_project_directory() as directory:
            (directory / "daily.json").write_text('{"pv":true}', encoding="utf-8")
            options = {**DEFAULTS, "battery_min_soc":15, "battery_max_soc":95}
            config = Configuration(options, Mock(), directory)
            self.assertEqual((config.daily["battery_min_soc"],config.daily["battery_max_soc"]),(15,95))
            app = Controller(Mock(), config)
            config.eos = Mock()
            app.sync_battery_limits(NOW, 0)
            config.eos.set_battery_limits.assert_not_called()
            config.update({**config.daily, "pv":False})
            self.assertFalse(Configuration(options, Mock(), directory).battery_limits_managed)

    def test_explicit_limits_survive_restart_and_retry_without_enabling_hardware(self):
        with temporary_project_directory() as directory:
            config = Configuration(dict(DEFAULTS), Mock(), directory)
            config.update({**config.daily,"battery_min_soc":30,"battery_max_soc":90}, manage_battery_limits=True)
            config = Configuration(dict(DEFAULTS), Mock(), directory)
            self.assertTrue(config.battery_limits_managed)
            config.eos = Mock()
            config.eos.set_battery_limits.side_effect = [OSError("offline"), None]
            app = Controller(Mock(), config)
            app.sync_battery_limits(NOW, 0)
            self.assertFalse(app.snapshot(NOW)["battery_limits"]["confirmed"])
            self.assertIn("battery_limits", app.errors)
            app.sync_battery_limits(NOW+timedelta(seconds=29),29)
            self.assertEqual(config.eos.set_battery_limits.call_count,1)
            app.sync_battery_limits(NOW+timedelta(seconds=30),30)
            self.assertEqual(config.eos.set_battery_limits.call_count,2)
            config.eos.set_battery_limits.assert_called_with("battery1",30,90)
            self.assertTrue(app.snapshot(NOW)["battery_limits"]["confirmed"])
            self.assertNotIn("battery_limits", app.errors)
            self.assertFalse(app.armed)
            self.assertFalse(app.owned)

    def test_invalid_edit_preserves_persisted_and_active_pair(self):
        with temporary_project_directory() as directory:
            config = Configuration(dict(DEFAULTS), Mock(), directory)
            config.update({**config.daily,"battery_min_soc":30,"battery_max_soc":90}, manage_battery_limits=True)
            before = config.file.read_bytes()
            with self.assertRaises(ValueError):
                config.update({**config.daily,"battery_min_soc":95}, manage_battery_limits=True)
            self.assertEqual(config.file.read_bytes(),before)
            self.assertEqual((config.daily["battery_min_soc"],config.daily["battery_max_soc"]),(30,90))

    def test_external_reset_is_detected_and_repaired_on_periodic_verification(self):
        with temporary_project_directory() as directory:
            config = Configuration(dict(DEFAULTS), Mock(), directory)
            config.update({**config.daily,"battery_min_soc":30,"battery_max_soc":90}, manage_battery_limits=True)
            data, writes = self.configuration(), []
            with transport(eos=(BatteryConfigServer,{"configuration":data,"writes":writes,"apply_write":True})):
                config.eos = EOS("http://eos")
                app = Controller(Mock(),config)
                app.sync_battery_limits(NOW,0)
                data["devices"]["batteries"]["battery1"]["min_soc_percentage"] = 20
                app.sync_battery_limits(NOW+timedelta(seconds=60),60)
            self.assertEqual(len(writes),2)
            self.assertEqual(data["devices"]["batteries"]["battery1"]["min_soc_percentage"],30)

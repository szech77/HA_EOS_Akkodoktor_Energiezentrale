"""Disabling a schedule removes optimizer demand without relying on vehicle telemetry."""
import unittest
from datetime import timedelta
from unittest.mock import patch
import test_requirements
from test_energy import NOW
from custom_components.eos_energiezentrale.energy.clients import EOS


class DisabledVehiclePlanning(unittest.TestCase):
    setUp = test_requirements.ControllerRequirements.setUp
    plan = staticmethod(test_requirements.ControllerRequirements.plan)
    states = staticmethod(test_requirements.ControllerRequirements.states)

    def test_disabled_schedule_clears_stale_eos_demand_after_restart_without_soc(self):
        self.app.sync_goal(NOW, 0, None)
        self.eos.set_vehicle_goal.assert_called_once_with("ev1", 0, None)
        self.app.sync_goal(NOW + timedelta(seconds=40), 40, None)
        self.eos.set_vehicle_goal.assert_called_once()

    def test_failed_disable_is_retried_and_never_grants_a_plan(self):
        self.eos.set_vehicle_goal.side_effect = [ValueError("unavailable"), None]
        self.assertFalse(self.app.sync_goal(NOW, 0, None))
        self.assertIn("goal", self.app.errors)
        self.app.sync_goal(NOW + timedelta(seconds=10), 10, None)
        self.assertEqual(self.eos.set_vehicle_goal.call_count, 1)
        self.assertFalse(self.app.sync_goal(NOW + timedelta(seconds=30), 30, None))
        self.assertNotIn("goal", self.app.errors)
        self.assertEqual(self.eos.set_vehicle_goal.call_count, 2)

    def test_turning_schedule_off_removes_previous_target(self):
        deadline = NOW + timedelta(hours=3)
        self.app.sync_goal(NOW, 0, deadline)
        self.app.sync_goal(NOW + timedelta(seconds=30), 30, None)
        self.eos.set_vehicle_goal.assert_called_with("ev1", 0, None)
        self.assertFalse(self.app.sync_goal(NOW + timedelta(seconds=60), 60, None))

    def test_disable_clears_both_deadline_forms_and_preserves_other_vehicle_and_hardware(self):
        old = {"capacity_wh": 77000, "min_soc_percentage": 45, "max_soc_percentage": 45,
               "min_soc_deadline_datetime": NOW.isoformat(), "min_soc_max_duration_h": 4}
        other = {"capacity_wh": 40000, "min_soc_percentage": 80}
        expected = {**old, "min_soc_percentage": 0, "max_soc_percentage": 0,
                    "min_soc_deadline_datetime": None, "min_soc_max_duration_h": None}
        before = {"devices": {"electric_vehicles": {"ev1": old, "ev2": other}}}
        after = {"devices": {"electric_vehicles": {"ev1": expected, "ev2": other}}}
        with patch("custom_components.eos_energiezentrale.energy.clients.request",
                   side_effect=[before, {}, after]) as request:
            EOS("http://eos:8503").set_vehicle_goal("ev1", 0, None)
        self.assertEqual(request.call_args_list[1].kwargs["payload"], {"ev1": expected, "ev2": other})

"""Regression tests for device ownership, timing, and external data boundaries."""
import json
import unittest
from dataclasses import replace
from datetime import timedelta
from email.message import Message
from io import BytesIO
from threading import Lock
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlsplit
from zoneinfo import ZoneInfo

from custom_components.eos_energiezentrale.energy.clients import EOS, Influx
from custom_components.eos_energiezentrale.energy.controller import Controller
from custom_components.eos_energiezentrale.energy.domain import BatteryCommand, next_departure
from custom_components.eos_energiezentrale.energy.drivers import BatteryReading, Fronius, NRGkick, WallboxReading
from custom_components.eos_energiezentrale.energy.history import forecast_rows, influx_series
from custom_components.eos_energiezentrale.energy.settings import Configuration, daily_settings
from test_energy import LIMITS, NOW, instruction, temporary_project_directory


OPTIONS = {
    **LIMITS,
    "timezone": "Europe/Berlin", "battery_resource": "battery1", "vehicle_resource": "ev1",
    "battery_type": "fronius", "wallbox_type": "nrgkick", "battery_parameters": "{}",
    "wallbox_parameters": "{}", "eos_url": "http://eos:8503", "influx_url": "",
    "influx_database": "homeassistant", "influx_user": "", "influx_password": "",
    "pv_entity": "sensor.pv", "house_entity": "sensor.house", "grid_entity": "sensor.grid",
    "heat_entity": "sensor.heat", "price_entity": "sensor.price", "car_soc_entity": "sensor.soc",
    "car_soc_scale": "factor", "capacity_wh": 77000, "charging_efficiency": .9,
    "max_current_a": 16, "phase_wait_s": 60, "regulation_interval_s": 20,
}


def wallbox(*, watts=0, status="connected", enabled=False, phases=3, amps=6, step=.1):
    return WallboxReading(watts, status, enabled, phases, amps, step, 16, NOW)


def state(value, unit="W", when=NOW):
    return {"state": str(value), "attributes": {"unit_of_measurement": unit},
            "last_updated": when.isoformat(), "last_reported": when.isoformat()}


class ControllerRequirements(unittest.TestCase):
    def setUp(self):
        self.directory = self.enterContext(temporary_project_directory())
        self.ha, self.battery, self.box, self.eos = Mock(), Mock(), Mock(), Mock()
        self.config = SimpleNamespace(directory=self.directory, options=dict(OPTIONS), zone=ZoneInfo("Europe/Berlin"),
                                      daily=daily_settings({}, 20), battery=self.battery,
                                      wallbox=self.box, eos=self.eos, influx=SimpleNamespace(url=None))
        self.app = Controller(self.ha, self.config)
        self.box.read.return_value = wallbox()
        self.battery.read.return_value = BatteryReading(50, 0, 0)
        self.eos.solution.return_value = {}
        self.eos.plan.return_value = self.plan()
        self.ha.states.return_value = self.states()

    @staticmethod
    def states(soc=.4, grid=0, when=NOW):
        return {"sensor.soc": state(soc, when=when), "sensor.grid": state(grid, when=when),
                "sensor.pv": state(7000, when=when), "sensor.house": state(4000, when=when),
                "sensor.heat": state(1000, when=when), "sensor.price": state(.3, "EUR/kWh", when)}

    @staticmethod
    def plan(generated=NOW, mode="GRID_SUPPORT_IMPORT", factor=.5):
        orders = [instruction(NOW - timedelta(minutes=5)),
                  {**instruction(NOW - timedelta(minutes=5), mode, factor), "resource_id": "ev1"}]
        return {"generated_at": generated.isoformat(), "instructions": orders}

    def test_planned_grid_charge_waits_for_new_plan_after_confirmed_goal(self):
        departure = NOW + timedelta(hours=4)
        self.config.daily = daily_settings({"schedule":"once", "departure":departure.isoformat(),
                                           "target_soc":70}, 20)
        self.app.set_armed(True)
        for offset in (0, 119):
            now = NOW + timedelta(seconds=offset)
            self.eos.plan.return_value = self.plan(now)
            self.ha.states.return_value = self.states(when=now)
            self.app.tick(now, offset)
            self.box.charge.assert_not_called()
        self.eos.set_vehicle_goal.assert_called_once_with("ev1", 70, departure)
        now = NOW + timedelta(seconds=134)
        self.eos.plan.return_value = self.plan(now)
        self.ha.states.return_value = self.states(when=now)
        self.app.tick(now, 134)
        self.box.charge.assert_called_once_with(7.9, self.box.read.return_value)

    def test_running_charge_tracks_new_eos_power_without_waiting_for_wallbox_report(self):
        self.config.daily=daily_settings({"target_soc":70,"phase_auto":False},20)
        self.app.sync_goal=Mock(return_value=True)
        self.app.goal_at=NOW-timedelta(minutes=3)
        self.app.set_armed(True)
        # An unchanged power report is still valid, but predates the previous command.
        for elapsed, factor, previous_amps, expected_amps in (
                (0,.5,6,7.9),(20,.8,7.9,12.7),(40,.6,12.7,9.5)):
            now=NOW+timedelta(seconds=elapsed)
            self.eos.plan.return_value=self.plan(now,factor=factor)
            self.ha.states.return_value=self.states(when=now)
            self.box.read.return_value=wallbox(watts=4140,status="charging",enabled=True,amps=previous_amps)
            self.app.tick(now,elapsed)
            self.assertAlmostEqual(self.box.charge.call_args.args[0],expected_amps)
        self.assertEqual(self.box.charge.call_count,3)
        self.box.pause.assert_not_called()
        # A valid zero-power instruction stops immediately, without waiting for the interval.
        now=NOW+timedelta(seconds=55)
        self.eos.plan.return_value=self.plan(now,factor=0)
        self.ha.states.return_value=self.states(when=now)
        self.app.tick(now,55)
        self.box.pause.assert_called_once()

    def test_absolute_charge_target_still_obeys_regulation_interval_and_grid_limit(self):
        self.config.daily=daily_settings({"phase_auto":False},20)
        self.app.last_write=NOW
        current=wallbox(watts=4140,enabled=True,status="charging")
        self.app.regulate_car(current,{"grid":0,"battery_discharge":0},8800,False,
                              NOW+timedelta(seconds=19),19,self.states())
        self.box.charge.assert_not_called()
        self.app.regulate_car(current,{"grid":18000,"battery_discharge":0},8800,False,
                              NOW+timedelta(seconds=19),19,self.states())
        self.box.pause.assert_called_once()

    def test_failed_goal_sync_does_not_enable_grid_charge(self):
        self.config.daily = daily_settings({"schedule":"once", "departure":(NOW+timedelta(hours=2)).isoformat()}, 20)
        self.eos.set_vehicle_goal.side_effect = ValueError("EOS rejected goal")
        self.app.set_armed(True)
        self.app.tick(NOW, 0)
        self.box.charge.assert_not_called()
        self.assertIn("goal", self.app.snapshot(NOW)["errors"])

    def test_actual_solar_charging_only_supports_storage_above_minimum(self):
        self.config.daily = daily_settings({"pv":True}, 20)
        self.app.set_armed(True)
        self.ha.states.return_value = self.states(grid=-2000)
        self.app.tick(NOW, 0)
        self.assertEqual(self.battery.apply.call_args.args[0], BatteryCommand("limits"))
        self.box.read.return_value = wallbox(watts=4140, enabled=True, status="charging")
        self.app.tick(NOW+timedelta(seconds=5), 5)
        self.assertEqual(self.battery.apply.call_args.args[0].discharge_w, 4760)
        self.battery.read.return_value = BatteryReading(20, 0, 0)
        self.app.tick(NOW+timedelta(seconds=10), 10)
        self.assertEqual(self.battery.apply.call_args.args[0].discharge_w, 0)
        self.battery.read.return_value = BatteryReading(50, 0, 0)
        self.box.read.return_value = wallbox(watts=0, enabled=True, status="connected")
        self.app.tick(NOW+timedelta(seconds=15), 15)
        self.assertEqual(self.battery.apply.call_args.args[0].discharge_w, 0)

    def test_solar_adjustment_requires_interval_and_fresh_grid_sample(self):
        self.config.daily = daily_settings({"pv":True, "regulation_interval_s":20}, 20)
        self.app.last_write = NOW
        current = wallbox(watts=4140, enabled=True, status="charging")
        live = {"grid":-259.17, "solar":7000, "battery_discharge":0}
        for elapsed, sample in ((19, NOW+timedelta(seconds=18)), (20, NOW)):
            self.app.regulate_car(current, dict(live), 0, True, NOW+timedelta(seconds=elapsed), elapsed,
                                  self.states(when=sample))
            self.box.charge.assert_not_called()
        fresh=replace(current,sample=NOW+timedelta(seconds=19))
        self.app.regulate_car(fresh, dict(live), 0, True, NOW+timedelta(seconds=20), 20,
                              self.states(when=NOW+timedelta(seconds=19)))
        self.box.charge.assert_called_once_with(6.4, fresh)

    def test_late_wallbox_sample_cannot_trigger_stop_or_phase_switch_after_charging_command(self):
        self.app.last_write=NOW
        current=wallbox(watts=0,enabled=True,status="connected")
        self.app.regulate_car(current,{"grid":2000,"solar":7000,"battery_discharge":0},
                              0,True,NOW+timedelta(seconds=25),25,self.states(when=NOW+timedelta(seconds=24)))
        self.box.pause.assert_not_called()
        self.box.phase.assert_not_called()
        self.box.charge.assert_not_called()
        self.assertIsNone(self.app.candidate)

    def test_sensor_settling_timeout_pauses_but_grid_overload_is_not_delayed(self):
        self.app.last_write=NOW
        current=wallbox(watts=4140,enabled=True,status="charging")
        self.app.regulate_car(current,{"grid":0,"solar":7000,"battery_discharge":0},
                              0,True,NOW+timedelta(seconds=61),61,self.states(when=NOW+timedelta(seconds=60)))
        self.box.pause.assert_called_once()
        self.box.reset_mock()
        self.app.regulate_car(current,{"grid":18000,"solar":7000,"battery_discharge":0},
                              0,True,NOW+timedelta(seconds=1),1,self.states(when=NOW+timedelta(seconds=1)))
        self.box.pause.assert_called_once()

    def test_actual_charging_continues_through_eos_outage_then_pauses_after_five_minutes(self):
        self.config.daily=daily_settings({"target_soc":70,"phase_auto":False},20)
        self.app.sync_goal=Mock(return_value=True)
        self.app.goal_at=NOW-timedelta(minutes=3)
        self.app.set_armed(True)
        for elapsed in (0,15,150,314):
            now=NOW+timedelta(seconds=elapsed)
            self.ha.states.return_value=self.states(when=now)
            self.box.read.return_value=replace(wallbox(watts=4140,enabled=True,status="charging"),sample=now)
            if elapsed:
                self.eos.plan.side_effect=TimeoutError("EOS not ready")
            self.app.tick(now,elapsed)
            self.box.pause.assert_not_called()
            self.assertTrue(self.app.armed)
        now=NOW+timedelta(seconds=315)
        self.ha.states.return_value=self.states(when=now)
        self.box.read.return_value=replace(wallbox(watts=4140,enabled=True,status="charging"),sample=now)
        self.app.tick(now,315)
        self.box.pause.assert_called_once()
        self.assertTrue(self.app.armed)
        # Recovery requires no manual re-arming.
        self.eos.plan.side_effect=None
        self.eos.plan.return_value=self.plan(NOW+timedelta(seconds=330))
        now=NOW+timedelta(seconds=330)
        self.ha.states.return_value=self.states(when=now)
        self.box.read.return_value=replace(wallbox(watts=4140,enabled=True,status="charging"),sample=now)
        self.box.reset_mock()
        self.app.tick(now,330)
        self.box.pause.assert_not_called()
        self.assertEqual(self.app.live["car_mode"],"GRID_SUPPORT_IMPORT")

    def test_sensor_reports_received_during_eos_request_are_not_rejected_as_future(self):
        from custom_components.eos_energiezentrale.adapter import StateSnapshot
        captured=NOW+timedelta(seconds=10)
        states=StateSnapshot(self.states(when=captured))
        states.captured_at=captured
        self.ha.states.return_value=states
        self.app.tick(NOW,0)
        self.assertEqual(self.app.live["solar"],7000)
        self.assertEqual(self.app.live["grid"],0)
        self.assertEqual(self.app.live["time"],captured.isoformat())

    def test_mixed_mode_uses_nearest_tenth_only_when_pv_dominates(self):
        self.config.daily = daily_settings({"pv":True}, 20)
        box = wallbox(watts=4209, enabled=True, status="charging", amps=6.1)
        self.app.regulate_car(box, {"grid":-54.058, "solar":7000, "battery_discharge":0},
                              2760, True, NOW, 0, self.states())
        self.box.charge.assert_called_once_with(6.2, box)

    def test_cloud_cancels_phase_change_until_a_full_new_wait(self):
        self.config.daily = daily_settings({"pv":True}, 20)
        current = wallbox(watts=4140, enabled=True, status="charging")
        for seconds, grid in ((0, 500), (40, -100), (60, 500), (119, 500)):
            fresh=replace(current,sample=NOW+timedelta(seconds=seconds))
            self.app.regulate_car(fresh, {"grid":grid, "solar":7000, "battery_discharge":0},
                                  0, True, NOW+timedelta(seconds=seconds), seconds,
                                  self.states(when=NOW+timedelta(seconds=seconds)))
            self.box.phase.assert_not_called()
        fresh=replace(current,sample=NOW+timedelta(seconds=120))
        self.app.regulate_car(fresh, {"grid":500, "solar":7000, "battery_discharge":0},
                              0, True, NOW+timedelta(seconds=120), 120,
                              self.states(when=NOW+timedelta(seconds=120)))
        self.box.phase.assert_called_once_with(1, fresh)

    def test_absent_consumers_do_not_block_storage_or_reduce_house_consumption(self):
        from custom_components.eos_energiezentrale.energy.drivers import NoWallbox
        self.config.options.update(wallbox_type="none",heat_entity="",car_soc_entity="")
        self.config.wallbox=NoWallbox(self.ha,{})
        self.ha.states.return_value={key:value for key,value in self.states().items() if key not in {"sensor.heat","sensor.soc"}}
        self.app.set_armed(True)
        self.app.tick(NOW,0)
        result=self.app.snapshot(NOW)
        self.assertEqual(result["features"],{"car":False,"heat":False})
        self.assertEqual(result["live"]["house"],4000)
        self.assertFalse(result["control_waiting"])
        self.assertTrue(result["armed"])
        self.battery.apply.assert_called_once()
        self.eos.set_vehicle_goal.assert_not_called()
        self.box.charge.assert_not_called()
        self.assertEqual(result["plan"]["car"],[])

    def test_configured_but_unavailable_heat_meter_is_not_treated_as_absent(self):
        self.ha.states.return_value.pop("sensor.heat")
        self.app.tick(NOW,0)
        result=self.app.snapshot(NOW)
        self.assertTrue(result["features"]["heat"])
        self.assertIsNone(result["live"]["house"])

    def test_stale_grid_pauses_and_plan_expiry_releases_battery(self):
        self.config.daily = daily_settings({"pv":True}, 20)
        self.app.set_armed(True)
        self.box.read.return_value = wallbox(watts=4140, enabled=True, status="charging")
        self.app.tick(NOW, 0)
        self.box.reset_mock()
        self.battery.reset_mock()
        self.app.tick(NOW+timedelta(hours=1), 3600)
        self.box.pause.assert_called_once()
        self.battery.release.assert_called_once()
        self.box.charge.assert_not_called()

    def test_disarm_stops_writes_even_if_release_fails_and_can_retry(self):
        self.app.armed = self.app.owned = True
        self.ha.states.side_effect = OSError("HA unavailable")
        with self.assertRaises(OSError):
            self.app.set_armed(False)
        self.assertFalse(self.app.armed)
        self.assertTrue(self.app.snapshot(NOW)["release_pending"])
        self.ha.states.side_effect = None
        self.app.set_armed(False)
        self.box.pause.assert_called_once()
        self.battery.release.assert_called_once()
        self.assertFalse(self.app.snapshot(NOW)["release_pending"])

    def test_solar_stops_at_estimated_target_before_vehicle_updates(self):
        self.config.daily = daily_settings({"pv":True, "pv_target_soc":80}, 20)
        self.app.set_armed(True)
        self.app.soc = 79.99
        self.app.soc_time = NOW - timedelta(seconds=10)
        self.app.soc_report = NOW.isoformat()
        self.app.soc_w = 7700
        self.ha.states.return_value = self.states(soc=.79, grid=-500)
        self.box.read.return_value = wallbox(watts=7700, status="charging", enabled=True, amps=11.2)
        self.app.tick(NOW, 0)
        self.assertGreater(self.app.soc, 80)
        self.assertEqual(self.app.live["soc_source"], "estimate")
        self.box.pause.assert_called_once_with(self.box.read.return_value)
        self.box.charge.assert_not_called()

    def test_eos_outage_keeps_valid_battery_plan_but_releases_on_expiry(self):
        self.eos.plan.return_value = {
            "generated_at": NOW.isoformat(),
            "valid_until": (NOW + timedelta(minutes=1)).isoformat(),
            "instructions": [instruction(NOW, "NON_EXPORT")],
        }
        self.app.set_armed(True)
        self.app.tick(NOW, 0)
        self.eos.plan.side_effect = OSError("EOS offline")
        self.battery.reset_mock()
        self.app.tick(NOW + timedelta(seconds=15), 15)
        self.assertEqual(self.battery.apply.call_args.args[0].mode, "block_discharge")
        self.battery.release.assert_not_called()
        self.assertIn("eos", self.app.snapshot(NOW + timedelta(seconds=15))["errors"])
        self.battery.reset_mock()
        self.app.tick(NOW + timedelta(minutes=1), 60)
        self.battery.apply.assert_not_called()
        self.battery.release.assert_called_once()

    def test_unconfirmed_device_command_returns_control_and_does_not_retry_writes(self):
        self.config.daily = daily_settings({"fast": True}, 20)
        self.app.set_armed(True)
        self.box.charge.side_effect = ValueError("Wallbox did not confirm current")
        with (patch("custom_components.eos_energiezentrale.energy.controller.datetime") as clock,
              patch("custom_components.eos_energiezentrale.energy.controller.monotonic", return_value=0),
              patch.object(self.app.stop_event, "wait", side_effect=lambda _: self.app.stop_event.set())):
            clock.now.return_value = NOW
            self.app.run()
        result = self.app.snapshot(NOW)
        self.assertFalse(result["armed"])
        self.assertIn("runtime", result["errors"])
        self.box.pause.assert_called_once()
        self.battery.release.assert_called_once()
        self.box.charge.reset_mock()
        self.battery.apply.reset_mock()
        self.app.tick(NOW + timedelta(seconds=5), 5)
        self.box.charge.assert_not_called()
        self.battery.apply.assert_not_called()

    def test_malformed_forecast_keeps_live_metering_available(self):
        self.eos.solution.return_value = {"start_solution_datetime": NOW.isoformat(),
                                          "interval_seconds": 900, "parameters": "invalid"}
        self.app.tick(NOW, 0)
        result = self.app.snapshot(NOW)
        self.assertEqual(result["live"]["solar"], 7000)
        self.assertEqual(result["forecast"], [])
        self.assertNotIn("forecast", result["errors"])
        self.assertIn("forecast", self.app.snapshot(NOW + timedelta(minutes=5))["errors"])

    def test_failed_emergency_release_leaves_control_off_and_marks_release_pending(self):
        self.config.daily = daily_settings({"fast": True}, 20)
        self.app.set_armed(True)
        self.box.charge.side_effect = OSError("Connection lost while setting current")
        self.box.pause.side_effect = OSError("Charger still offline")
        with (patch("custom_components.eos_energiezentrale.energy.controller.datetime") as clock,
              patch("custom_components.eos_energiezentrale.energy.controller.monotonic", return_value=0),
              patch.object(self.app.stop_event, "wait", side_effect=lambda _: self.app.stop_event.set())):
            clock.now.return_value = NOW
            self.app.run()
        result = self.app.snapshot(NOW)
        self.assertFalse(result["armed"])
        self.assertTrue(result["release_pending"])
        self.assertIn("release", result["errors"])
        self.battery.release.assert_called_once()

    def test_unrelated_old_entities_do_not_interrupt_active_charging(self):
        self.config.daily = daily_settings({"fast": True}, 20)
        self.app.set_armed(True)
        self.ha.states.return_value = {**self.states(), "automation.eos_auto_laderegler": {"state": "on"}}
        self.app.tick(NOW, 0)
        result = self.app.snapshot(NOW)
        self.assertTrue(result["armed"])
        self.box.charge.assert_called_once()
        self.box.pause.assert_not_called()


    def test_slow_heat_meter_keeps_marked_overview_estimate_without_fresh_history(self):
        states = self.states(grid=0)
        states["sensor.house"] = state(574.1381)
        states["sensor.heat"] = state(29.8753452301025, when=NOW-timedelta(seconds=390))
        self.ha.states.return_value = states
        self.box.read.return_value = wallbox(watts=1.072)
        self.app.tick(NOW, 0)
        result = self.app.snapshot(NOW)
        self.assertIsNone(result["live"]["heat"])
        self.assertIsNone(result["live"]["house"])
        self.assertEqual(result["display"]["heat"], {"value":29.8753452301025, "age_s":390})
        estimate = result["display"]["house"]
        self.assertAlmostEqual(estimate["value"], 543.1907547698975)
        self.assertTrue(estimate["estimated"])
        history = self.app.history.read(NOW)[0]
        self.assertIsNone(history["heat"])
        self.assertIsNone(history["house"])
        self.ha.states.return_value = {**states, "sensor.heat":state(30, when=NOW+timedelta(seconds=5))}
        self.app.tick(NOW+timedelta(seconds=5), 5)
        self.assertEqual(self.app.snapshot(NOW+timedelta(seconds=5))["display"], {})

    def test_unavailable_heat_meter_does_not_become_zero_or_estimated_house(self):
        states = self.states()
        states["sensor.heat"] = state("unavailable")
        self.ha.states.return_value = states
        self.app.tick(NOW, 0)
        result = self.app.snapshot(NOW)
        self.assertIsNone(result["live"]["house"])
        self.assertEqual(result["display"], {})


    def test_held_grid_value_is_visible_but_never_used_for_pv_charging_or_history(self):
        self.config.daily=daily_settings({"pv":True},20)
        self.app.set_armed(True)
        self.app.tick(NOW,0)
        states=self.states(when=NOW+timedelta(seconds=60))
        states["sensor.grid"]=state("unavailable",when=NOW+timedelta(seconds=60))
        self.ha.states.return_value=states
        self.box.read.return_value=wallbox(watts=4140,enabled=True,status="charging")
        self.box.reset_mock()
        self.app.tick(NOW+timedelta(seconds=60),60)
        result=self.app.snapshot(NOW+timedelta(seconds=60))
        self.assertIsNone(result["live"]["grid"])
        self.assertEqual(result["display"]["grid"],{"value":0,"age_s":60})
        self.box.pause.assert_called_once()
        self.box.charge.assert_not_called()
        self.assertIsNone(self.app.history.read(NOW+timedelta(seconds=60))[-1]["grid"])

    def test_daily_storage_limits_override_commissioning_values_in_real_commands(self):
        self.config.daily = daily_settings({"battery_min_soc":40,"battery_max_soc":80},20)
        self.eos.plan.return_value = {"generated_at":NOW.isoformat(),
                                     "instructions":[instruction(NOW,"SELF_CONSUMPTION")]}
        self.app.set_armed(True)
        self.battery.read.return_value = BatteryReading(35,0,0)
        self.app.tick(NOW,0)
        self.assertEqual(self.battery.apply.call_args.args[0],BatteryCommand("limits",4760,0))
        self.battery.read.return_value = BatteryReading(85,0,0)
        self.app.tick(NOW+timedelta(seconds=5),5)
        self.assertEqual(self.battery.apply.call_args.args[0],BatteryCommand("limits",0,4760))


class DataAndConfigurationRequirements(unittest.TestCase):
    def test_nrgkick_cannot_enable_with_unconfirmed_current(self):
        ha = Mock()
        driver = NRGkick(ha, {})
        with patch("custom_components.eos_energiezentrale.energy.entity_wallbox.confirmed_state", side_effect=ValueError("No acknowledgement")):
            with self.assertRaises(ValueError):
                driver.charge(6.2, wallbox(phases=1))
        ha.set.assert_called_once_with(driver.ids["current"], 6.2)

    def test_nrgkick_rejects_unconfirmed_phase_change(self):
        ha = Mock()
        driver = NRGkick(ha, {})
        connected = wallbox(phases=1)
        self.assertFalse(driver.phase(3, connected))
        self.assertFalse(driver.phase(3, replace(connected, sample=NOW + timedelta(seconds=5))))
        with self.assertRaises(ValueError):
            driver.phase(3, replace(connected, sample=NOW + timedelta(seconds=51)))
        self.assertNotIn((driver.ids["enable"], True), [call.args for call in ha.set.call_args_list])

    def test_fronius_refuses_unconfirmed_mode_before_setting_power(self):
        ha = Mock()
        driver = Fronius(ha, {})
        selector = driver.ids["mode"]
        ha.state.return_value = {"state":"Auto"}
        with patch("custom_components.eos_energiezentrale.energy.device_io.monotonic", side_effect=iter(range(0, 30, 6))):
            with self.assertRaises(ValueError):
                driver.apply(BatteryCommand("grid_charge", charge_w=3000), {selector: {"state":"Auto"}})
        ha.set.assert_called_once_with(selector, "Charge from Grid")

    def test_daily_settings_persist_except_fast_charge(self):
        with temporary_project_directory() as directory:
            ha = Mock()
            config = Configuration(OPTIONS, ha, directory)
            config.update({"pv":True, "fast":True, "reserve_w":30, "regulation_interval_s":25})
            self.assertTrue(config.daily["fast"])
            reloaded = Configuration(OPTIONS, ha, directory)
            self.assertFalse(reloaded.daily["fast"])
            self.assertTrue(reloaded.daily["pv"])
            self.assertEqual((reloaded.daily["reserve_w"], reloaded.daily["regulation_interval_s"]), (30,25))
            with self.assertRaises(ValueError):
                config.update({"fast": "on"})
            self.assertEqual(json.loads(config.file.read_text(encoding="utf-8")), reloaded.daily)

    def test_driver_overrides_and_unknown_types_are_validated(self):
        with temporary_project_directory() as directory:
            options = {**OPTIONS, "wallbox_parameters":'{"enable":"switch.other"}',
                       "battery_parameters":'{"mode":"select.other"}'}
            config = Configuration(options, Mock(), directory)
            self.assertIsInstance(config.battery, Fronius)
            self.assertIsInstance(config.wallbox, NRGkick)
            self.assertEqual(config.wallbox.ids["enable"], "switch.other")
            self.assertEqual(config.battery.ids["mode"], "select.other")
            with self.assertRaises(ValueError):
                Configuration({**OPTIONS, "battery_type":"unregistered"}, Mock(), directory)

    def test_influx_respects_measurement_units_and_rejects_unsafe_entity(self):
        client = Influx("http://influx:8086", "homeassistant", "reader", "secret")
        with patch("custom_components.eos_energiezentrale.energy.clients.request", side_effect=[{"results":[{}]},
                   {"results":[{"series":[{"values":[[NOW.isoformat(),1.5],[NOW.isoformat(),None]]}]}]}]) as http:
            self.assertEqual(client.history("sensor.power",[("W",1),("kW",1000)]), [[NOW.isoformat(),1500]])
            query = parse_qs(urlsplit(http.call_args.args[0]).query)
            self.assertIn('FROM "kW"', query["q"][0])
            self.assertEqual(query["db"],["homeassistant"])
            self.assertNotIn("secret", http.call_args.args[0])
            self.assertEqual(client.history("sensor.power' OR true",[("W",1)]),[])
            self.assertEqual(http.call_count,2)

    def test_influx_history_aligns_consumers_and_preserves_gaps(self):
        stamps = [NOW.isoformat(), (NOW + timedelta(minutes=5)).isoformat()]
        with temporary_project_directory() as directory:
            config = Configuration({**OPTIONS, "influx_url":"http://influx:8086"}, Mock(), directory)
            samples = {
                "house": [5050, 5200], "heat": [1300, None],
                config.wallbox.ids["power"].split(".")[1]: [2800, 3000],
                config.battery.ids["charge_power"].split(".")[1]: [0, 300],
                config.battery.ids["discharge_power"].split(".")[1]: [800, None],
                "soc": [.45, None],
            }

            def respond(url, **kwargs):
                query = parse_qs(urlsplit(url).query)["q"][0]
                entity = query.split('"entity_id"=\'')[1].split("'")[0]
                return {"results":[{"series":[{"values":list(zip(stamps, samples[entity]))}]}]} if entity in samples else {"results":[{}]}

            with patch("custom_components.eos_energiezentrale.energy.clients.request", side_effect=respond):
                first, second = influx_series(config)
        self.assertEqual((first["house"], first["battery"], first["car_soc"]), (950, -800, 45))
        self.assertEqual(second["house_total"], 5200)
        self.assertIsNone(second["house"])
        self.assertIsNone(second.get("battery"))

    def test_pv_forecast_retains_available_energy_beyond_the_chart_day(self):
        solution = {"start_solution_datetime": NOW.isoformat(), "interval_seconds": 3600,
                    "parameters": {"ems": {"pv_forecast_wh": [1000] * 60}}, "result": {}}
        rows = forecast_rows(solution, NOW)
        self.assertEqual(len(rows), 60)
        self.assertEqual(sum(row["solar"] for row in rows), 60000)
        self.assertEqual(rows[-1]["end"], (NOW + timedelta(hours=60)).isoformat())

    def test_forecast_signed_power_and_units_with_missing_values(self):
        solution = {"start_solution_datetime":NOW.isoformat(), "interval_seconds":900,
                    "parameters":{"ems":{"pv_forecast_wh":[1500,None], "total_load":[750,800]},
                                  "pv_battery":{"capacity_wh":10000,"charging_efficiency":.9,"discharging_efficiency":.9},
                                  "ev":{"capacity_wh":77000,"charging_efficiency":.9}},
                    "result":{"battery_soc_per_hour":[60,55],"ev_soc_per_hour":[40,42],
                              "grid_consumption_wh_per_hour":[100],"grid_feed_in_wh_per_hour":[400]}}
        first, second = forecast_rows(solution,NOW)
        self.assertEqual((first["solar"],first["house_total"],first["grid"],first["battery"]), (6000,3000,-1200,-1800))
        self.assertAlmostEqual(first["car"],6844.444444,places=5)
        self.assertIsNone(second["solar"])
        self.assertIsNone(second["battery"])
        self.assertNotIn("heat", first)

    def test_unchanged_eos_goal_avoids_write_and_unconfirmed_goal_is_rejected(self):
        eos = EOS("http://eos:8503")
        vehicle = {"min_soc_percentage":80, "max_soc_percentage":80, "min_soc_deadline_datetime":NOW.isoformat()}
        response = {"devices":{"electric_vehicles":{"ev1":vehicle}}}
        with patch("custom_components.eos_energiezentrale.energy.clients.request", return_value=response) as http:
            eos.set_vehicle_goal("ev1",80,NOW)
            http.assert_called_once()
        with patch("custom_components.eos_energiezentrale.energy.clients.request", return_value=response):
            with self.assertRaises(ValueError):
                eos.set_vehicle_goal("ev1",70,NOW)

    def test_departure_handles_nonexistent_local_time(self):
        sunday = daily_settings({"schedule":"weekly","weekdays":[6],"departure_time":"02:30"}, 20)
        now = NOW.replace(month=3, day=28)
        departure = next_departure(sunday, now, ZoneInfo("Europe/Berlin"))
        self.assertEqual(departure.isoformat(), "2026-03-29T03:30:00+02:00")



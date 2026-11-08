import json
import re
import shutil
import unittest
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4
from zoneinfo import ZoneInfo

from custom_components.eos_energiezentrale.energy.clients import EOS, base_url, reading
from custom_components.eos_energiezentrale.energy.controller import Controller
from custom_components.eos_energiezentrale.energy.domain import (BatteryCommand, Instruction, battery_command, current_for_power,
                           current_instruction, estimate_soc, house_only, next_departure, pv_budget)
from custom_components.eos_energiezentrale.energy.drivers import BatteryReading, Fronius, NRGkick, WallboxReading
from custom_components.eos_energiezentrale.energy.history import History, forecast_rows
from custom_components.eos_energiezentrale.energy.localization import PACKS, load_language
from custom_components.eos_energiezentrale.energy.settings import daily_settings


NOW = datetime(2026, 11, 8, 12, tzinfo=timezone.utc)
LIMITS = dict(battery_min_soc=20, battery_max_soc=100, battery_charge_w=4760,
              battery_discharge_w=4760, allow_battery_export=False, grid_limit_w=17250)


def instruction(when, mode="IDLE", factor=1):
    return dict(resource_id="battery1", execution_time=when.isoformat(), operation_mode_id=mode,
                operation_mode_factor=factor, type="FRBCInstruction")


@contextmanager
def temporary_project_directory():
    path = Path.cwd() / (".test-" + uuid4().hex)
    path.mkdir()
    try:
        yield path
    finally:
        if path.resolve().parent != Path.cwd().resolve():
            raise ValueError("Test directory escaped the working directory")
        shutil.rmtree(path)


class DomainTests(unittest.TestCase):
    def test_balance_and_missing_data(self):
        self.assertEqual(house_only(5050, 2800, 1300), 950)
        self.assertIsNone(house_only(5050, 2800, None))
        self.assertEqual(house_only(1000, 900, 200), 0)

    def test_plan_freshness_duplicates_and_bad_latest(self):
        past = NOW - timedelta(minutes=15)
        future = NOW + timedelta(minutes=5)
        plan = dict(generated_at=NOW.isoformat(), instructions=[instruction(past), instruction(future)])
        self.assertEqual(current_instruction(plan, "battery1", NOW).mode, "IDLE")
        plan["instructions"].append(instruction(NOW, factor=2))
        self.assertIsNone(current_instruction(plan, "battery1", NOW))
        plan["instructions"][-1] = instruction(past)
        self.assertIsNone(current_instruction(plan, "battery1", NOW))
        plan["instructions"].pop()
        plan["valid_until"] = NOW.isoformat()
        self.assertIsNone(current_instruction(plan, "battery1", NOW))
        plan.pop("valid_until")
        plan["generated_at"] = (NOW - timedelta(hours=1)).isoformat()
        self.assertIsNone(current_instruction(plan, "battery1", NOW))

    def test_storage_override_and_safety(self):
        for mode in ("NON_EXPORT", "IDLE"):
            order = Instruction(NOW, mode, 1)
            self.assertEqual(battery_command(order, 40, LIMITS, False, 0, 0, 0).discharge_w, 0)
            self.assertEqual(battery_command(order, 40, LIMITS, True, 0, 0, 0).discharge_w, 4760)
            self.assertEqual(battery_command(order, 20, LIMITS, True, 0, 0, 0).discharge_w, 0)
        self.assertEqual(battery_command(Instruction(NOW, "FORCED_DISCHARGE", 1), 90, LIMITS, True, 0, 0, 0),
                         BatteryCommand("limits"))
        self.assertEqual(battery_command(Instruction(NOW, "PEAK_SHAVING", 1), 90, LIMITS, False, 17750, 300, 100).discharge_w, 700)

    def test_current_rounding_and_hard_limit(self):
        self.assertEqual(current_for_power(6159.669, 3, .1, 16), 8.9)
        self.assertEqual(current_for_power(4263.058, 3, .1, 16, True), 6.2)
        self.assertEqual(current_for_power(4263.058, 3, .1, 16, True, 4263), 6.1)
        self.assertIsNone(current_for_power(1000, 1, .1, 16))
        self.assertEqual(current_for_power(11000, 3, .1, 16), 15.9)

    def test_pv_budget_accounts_for_storage(self):
        self.assertAlmostEqual(pv_budget(7598, -259.17, 4402.6, 0, 100, 3, 6), 4299.17)
        self.assertEqual(pv_budget(7000, 0, 6200, 500, 100, 3, 9), 5610)
        self.assertEqual(pv_budget(7000, -3583, 0, 0, 100), 3483)

    def test_soc_estimate_reconciles_and_does_not_bridge_gaps(self):
        args = (45, 45, False, True, 7700, 7700)
        self.assertAlmostEqual(estimate_soc(*args, 10, 77000, .9), 45.025)
        self.assertEqual(estimate_soc(*args, 100, 77000, .9), 45)
        self.assertEqual(estimate_soc(48, 46, True, True, 7700, 7700, 10, 77000, .9), 46)
        self.assertIsNone(estimate_soc(None, None, False, True, 7700, 7700, 10, 77000, .9))

    def test_schedule_and_validation(self):
        settings = daily_settings({"schedule":"weekly", "weekdays":[0]}, 20)
        departure = next_departure(settings, NOW, ZoneInfo("Europe/Berlin"))
        self.assertEqual(departure.isoformat(), "2026-11-09T07:30:00+01:00")
        with self.assertRaises(ValueError):
            daily_settings({"target_soc": True}, 20)
        with self.assertRaises(ValueError):
            daily_settings({"schedule":"weekly", "weekdays":[]}, 20)


class DriverTests(unittest.TestCase):
    def test_read_only_tick_builds_live_balance_without_commands(self):
        with temporary_project_directory() as directory:
            ha, box, battery, eos = Mock(), Mock(), Mock(), Mock()
            box.read.return_value = WallboxReading(2800,"charging",True,1,12,.1,16,NOW)
            battery.read.return_value = BatteryReading(68,1150,0)
            eos.plan.return_value = {"generated_at":NOW.isoformat(),"instructions":[instruction(NOW)]}
            eos.solution.return_value = {}
            values = {"pv":6200,"grid":0,"house":5050,"heat":1300,"price":.294,"car_soc":.57}
            opts = {key + "_entity":"sensor." + key for key in values}
            opts.update(battery_resource="battery1",vehicle_resource="ev1",car_soc_scale="factor",
                        capacity_wh=77000,charging_efficiency=.9,timezone="Europe/Berlin")
            ha.states.return_value = {opts[key+"_entity"]:{"state":value,"last_updated":NOW.isoformat(),
                                       "attributes":{"unit_of_measurement":"EUR/kWh" if key == "price" else "W"}}
                                      for key,value in values.items()}
            app = Controller(ha, SimpleNamespace(directory=directory, options=opts, wallbox=box,
                             battery=battery, eos=eos, influx=SimpleNamespace(url=None),
                             daily=daily_settings({},20), zone=ZoneInfo("Europe/Berlin")))
            app.tick(NOW,0)
            snapshot = app.snapshot(NOW)
            self.assertEqual(snapshot["live"]["house"],950)
            self.assertAlmostEqual(snapshot["live"]["car_soc"],57)
            self.assertEqual(snapshot["live"]["battery_mode"],"IDLE")
            self.assertEqual(snapshot["live"]["car_actual_mode"],"CHARGING")
            self.assertEqual(len(app.history.read(NOW)),1)
            ha.publish_soc.assert_not_called()
            battery.apply.assert_not_called()
            box.pause.assert_not_called()
            box.charge.assert_not_called()

    def test_pv_start_chooses_three_phases_before_enabling(self):
        with temporary_project_directory() as directory:
            driver = Mock()
            driver.phase.return_value = False
            config = SimpleNamespace(directory=directory, wallbox=driver, daily=daily_settings({"pv":True},20),
                                     options={"grid_limit_w":17250,"max_current_a":16,"phase_wait_s":60})
            app = Controller(Mock(),config)
            state = WallboxReading(0,"connected",False,1,6,.1,16,NOW)
            live = {"grid":-5000,"solar":8000,"battery_discharge":0}
            app.regulate_car(state,live,0,True,NOW,0,{})
            driver.phase.assert_not_called()
            app.regulate_car(state,live,0,True,NOW+timedelta(seconds=60),60,{})
            driver.phase.assert_called_once_with(3,state)
            driver.charge.assert_not_called()

    def test_nrgkick_stops_and_uses_two_fresh_zero_samples(self):
        ha = Mock()
        box = NRGkick(ha, {})
        def sample(enabled, offset, watts=0, status="connected", phase=1):
            return WallboxReading(watts,status,enabled,phase,6,.1,16,NOW+timedelta(seconds=offset))
        with patch("custom_components.eos_energiezentrale.energy.drivers.datetime") as clock:
            clock.now.return_value = NOW + timedelta(seconds=2)
            self.assertFalse(box.phase(3, sample(True,0,1380,"charging")))
        ha.set.assert_called_once_with(box.ids["enable"], False)
        self.assertFalse(box.phase(3, sample(False,1)))
        ha.set.assert_called_once()
        self.assertFalse(box.phase(3, sample(False,5)))
        ha.set.assert_called_once()
        self.assertFalse(box.phase(3, sample(False,6)))
        ha.set.assert_called_once()
        self.assertFalse(box.phase(3, sample(False,10)))
        ha.set.assert_called_with(box.ids["phases"], 3)
        self.assertTrue(box.phase(3, sample(False,15,phase=3)))

    def test_nrgkick_current_is_confirmed_before_enabling(self):
        ha = Mock()
        box = NRGkick(ha, {})
        ha.state.return_value = {"state":"6.2"}
        box.charge(6.2, WallboxReading(0,"connected",False,1,6,.1,16,NOW))
        self.assertEqual([call.args for call in ha.set.call_args_list], [(box.ids["current"],6.2),(box.ids["enable"],True)])

    def test_fronius_maps_generic_commands(self):
        ha = Mock()
        driver = Fronius(ha, {})
        ha.state.return_value = {"state":"4760","attributes":{"max":10240,"step":10,"unit_of_measurement":"W"}}
        driver.apply(BatteryCommand("block_discharge",4760),
                     {driver.ids["mode"]:{"state":"Block Discharging"}})
        ha.set.assert_not_called()
        with self.assertRaises(ValueError):
            driver.apply(BatteryCommand("grid_discharge",discharge_w=200), {})
        with self.assertRaises(ValueError):
            NRGkick(ha, {"enable":"sensor.wrong_domain"})

    def test_measurement_age_and_units(self):
        rows = {"sensor.power":{"state":"1.5","attributes":{"unit_of_measurement":"kW"},"last_updated":NOW.isoformat()}}
        self.assertEqual(reading(rows,"sensor.power",NOW,"power",45),1500)
        self.assertIsNone(reading(rows,"sensor.power",NOW+timedelta(seconds=50),"power",45))

    def test_control_can_be_enabled_without_querying_old_helpers(self):
        with temporary_project_directory() as directory:
            ha = Mock()
            ha.states.return_value = {"automation.eos_auto_laderegler":{"state":"on"}}
            app = Controller(ha, SimpleNamespace(directory=Path(directory)))
            app.set_armed(True)
            self.assertTrue(app.armed)
            ha.states.assert_not_called()
            ha.set.assert_not_called()


class ClientTests(unittest.TestCase):
    def test_eos_goal_keeps_other_vehicles(self):
        eos = EOS("http://eos:8503")
        other = {"capacity_wh":35000}
        before = {"devices":{"electric_vehicles":{"ev1":{"capacity_wh":77000},"ev2":other}}}
        goal = NOW + timedelta(hours=4)
        after = {"devices":{"electric_vehicles":{"ev1":{"min_soc_percentage":80,"max_soc_percentage":80,
                                                        "min_soc_deadline_datetime":goal.isoformat()}}}}
        with patch("custom_components.eos_energiezentrale.energy.clients.request", side_effect=[before,{},after]) as http:
            eos.set_vehicle_goal("ev1",80,goal)
            self.assertEqual(http.call_args_list[1].kwargs["payload"]["ev2"],other)

    def test_url_safety(self):
        for bad in ("file:///data/options.json","http://user:password@eos","http://eos?x=1","http://eos/api"):
            with self.assertRaises(ValueError):
                base_url(bad)

    def test_history_and_forecast(self):
        with temporary_project_directory() as directory:
            history = History(Path(directory) / "sample.db")
            history.write(NOW, {"time":NOW.isoformat(),"solar":1000})
            self.assertEqual(history.read(NOW)[0]["solar"],1000)
        source = {"start_solution_datetime":NOW.isoformat(),"interval_seconds":900,
                  "parameters":{"ems":{"pv_forecast_wh":[1000],"electricity_price_per_wh":[.0003]}},
                  "result":{}}
        rows = forecast_rows(source,NOW)
        self.assertEqual(rows[0]["solar"],4000)
        self.assertAlmostEqual(rows[0]["price"],30)
        self.assertEqual(forecast_rows(source,NOW+timedelta(hours=2)),[])


class LanguageTests(unittest.TestCase):
    def test_default_covers_static_and_dynamic_ui_keys(self):
        pack = load_language()
        web = PACKS.parent / "web"
        markup = (web / "index.html").read_text(encoding="utf-8")
        script = (web / "app.js").read_text(encoding="utf-8")
        keys = set(re.findall(r'data-i18n(?:-aria)?="([^"]+)"', markup))
        keys.update(re.findall(r"\b(?:t|th)\('([a-z.]+)'", script))
        for page in ("solar", "grid", "battery", "house", "car", "heat"):
            keys.update((f"device.{page}", f"chart.{page}"))
        self.assertEqual(keys - pack["messages"].keys(), set())
        self.assertEqual(pack["locale"], "en-GB")
        self.assertEqual(pack["messages"]["settings.save"], "Save")
        german = json.loads((PACKS / "de.json").read_text(encoding="utf-8"))
        self.assertEqual(german["messages"].keys(), pack["messages"].keys())
        self.assertEqual(load_language("auto", ha_language="de-AT")["messages"]["settings.save"], "Speichern")
        self.assertEqual(load_language("en", ha_language="de")["messages"]["settings.save"], "Save")
        self.assertEqual(load_language("auto", ha_language="es"), pack)

    def test_optional_pack_merges_and_invalid_language_falls_back(self):
        with temporary_project_directory() as directory:
            english = load_language()
            (directory / "en.json").write_text(json.dumps(english), encoding="utf-8")
            partial = {"locale": "fr-FR", "messages": {"settings.save": "Enregistrer"}}
            (directory / "fr.json").write_text(json.dumps(partial), encoding="utf-8")
            selected = load_language("auto", directory, ha_language="fr-CA")
            self.assertEqual(selected["locale"], "fr-FR")
            self.assertEqual(selected["messages"]["settings.save"], "Enregistrer")
            self.assertEqual(selected["messages"]["nav.overview"], english["messages"]["nav.overview"])
            self.assertEqual(load_language("../fr", directory), english)
            self.assertEqual(load_language("es", directory), english)


if __name__ == "__main__":
    unittest.main()

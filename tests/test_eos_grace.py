"""Transient EOS outages must not interrupt an already authorized charge immediately."""
from copy import deepcopy
from datetime import timedelta
import unittest
from unittest.mock import Mock
from custom_components.eos_energiezentrale.energy.controller import Controller
from custom_components.eos_energiezentrale.const import DEFAULTS
from custom_components.eos_energiezentrale.energy.settings import Configuration
from test_energy import NOW,instruction,temporary_project_directory


class EOSGraceRequirements(unittest.TestCase):
    def controller(self):
        directory=self.enterContext(temporary_project_directory())
        config=Configuration(dict(DEFAULTS),Mock(),directory)
        config.eos=Mock()
        config.eos.solution.return_value={}
        app=Controller(Mock(),config)
        return app,config.eos

    def plan(self,when=NOW,mode="GRID_SUPPORT_IMPORT"):
        return {"generated_at":when.isoformat(),"instructions":[instruction(when,"NON_EXPORT"),
                {**instruction(when,mode),"resource_id":"ev1"}]}

    def test_timeout_keeps_last_plan_for_five_minutes_without_sliding_deadline(self):
        app,eos=self.controller()
        eos.plan.return_value=self.plan()
        app.update_eos(NOW,0)
        eos.plan.side_effect=TimeoutError("offline")
        app.update_eos(NOW+timedelta(seconds=15),15)
        for elapsed in (30,150,314):
            app.update_eos(NOW+timedelta(seconds=elapsed),elapsed)
            self.assertEqual(app.order_for("ev1",NOW+timedelta(seconds=elapsed)).mode,"GRID_SUPPORT_IMPORT")
        self.assertIsNone(app.order_for("ev1",NOW+timedelta(seconds=315)))

    def test_incomplete_or_empty_responses_do_not_replace_the_valid_vehicle_instruction(self):
        app,eos=self.controller()
        original=self.plan()
        eos.plan.return_value=original
        app.update_eos(NOW,0)
        # Even a subsequently mutated response cannot modify the cached plan.
        original["instructions"].clear()
        for elapsed,reply in ((15,None),(30,{"generated_at":NOW.isoformat(),"instructions":[]}),
                              (45,{"generated_at":NOW.isoformat(),"instructions":[instruction(NOW,"IDLE")]})):
            eos.plan.return_value=reply
            app.update_eos(NOW+timedelta(seconds=elapsed),elapsed)
            self.assertEqual(app.order_for("ev1",NOW+timedelta(seconds=elapsed)).mode,"GRID_SUPPORT_IMPORT")
        self.assertIsNone(app.order_for("ev1",NOW+timedelta(seconds=315)))

    def test_new_stop_instruction_is_effective_without_waiting_for_grace(self):
        app,eos=self.controller()
        eos.plan.return_value=self.plan()
        app.update_eos(NOW,0)
        eos.plan.side_effect=TimeoutError()
        app.update_eos(NOW+timedelta(seconds=15),15)
        eos.plan.side_effect=None
        eos.plan.return_value=self.plan(NOW+timedelta(seconds=30),"IDLE")
        app.update_eos(NOW+timedelta(seconds=30),30)
        self.assertEqual(app.order_for("ev1",NOW+timedelta(seconds=30)).mode,"IDLE")
        self.assertNotIn("ev1",app.snapshot(NOW+timedelta(seconds=30))["eos_cache"])

    def test_scheduled_stop_in_cached_plan_and_explicit_expiry_are_still_honored(self):
        app,eos=self.controller()
        plan=self.plan()
        plan["instructions"].append({**instruction(NOW+timedelta(seconds=45),"IDLE"),"resource_id":"ev1"})
        plan["valid_until"]=(NOW+timedelta(seconds=60)).isoformat()
        eos.plan.return_value=plan
        app.update_eos(NOW,0)
        eos.plan.side_effect=TimeoutError()
        app.update_eos(NOW+timedelta(seconds=15),15)
        self.assertEqual(app.order_for("ev1",NOW+timedelta(seconds=45)).mode,"IDLE")
        self.assertIsNone(app.order_for("ev1",NOW+timedelta(seconds=60)))

    def test_initial_start_without_a_previous_plan_does_not_invent_charging(self):
        app,eos=self.controller()
        eos.plan.side_effect=TimeoutError()
        app.update_eos(NOW,0)
        self.assertIsNone(app.order_for("ev1",NOW))
        self.assertEqual(app.snapshot(NOW)["eos_cache"],{})

    def test_old_response_cannot_undo_a_newer_stop_plan(self):
        app,eos=self.controller()
        eos.plan.return_value=self.plan(NOW,"IDLE")
        app.update_eos(NOW,0)
        eos.plan.return_value=self.plan(NOW-timedelta(seconds=30),"GRID_SUPPORT_IMPORT")
        app.update_eos(NOW+timedelta(seconds=15),15)
        self.assertEqual(app.order_for("ev1",NOW+timedelta(seconds=15)).mode,"IDLE")

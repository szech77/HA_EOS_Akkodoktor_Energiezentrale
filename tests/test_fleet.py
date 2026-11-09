"""Fleet requirements: distinct resources, shared budgets and independent settings."""
from copy import deepcopy
from datetime import timedelta
import json
import unittest
from unittest.mock import Mock

from custom_components.eos_energiezentrale.const import DEFAULTS
from custom_components.eos_energiezentrale.energy.fleet import create_controller, vehicle_options, reserved_grid
from custom_components.eos_energiezentrale.energy.drivers import Fronius
from custom_components.eos_energiezentrale.validation import validate_options
from test_energy import NOW, instruction, temporary_project_directory


def definitions():
    return [{"id":key,"name":"Auto "+key,"resource":"ev"+str(i),"soc_entity":"sensor.soc_"+key,
             "wallbox_parameters":{"power":"sensor."+key+"_power","status":"sensor."+key+"_status",
                "enable":"switch."+key+"_enabled","current":"number."+key+"_current","phases":"number."+key+"_phases"}}
            for i,key in enumerate(("first","second"),1)]


class LocalHA:
    def __init__(self,options):
        self.rows={}
        self.writes=[]
        def put(entity,value,unit=None,**attrs):
            self.rows[entity]={"state":str(value),"attributes":{**attrs,**({"unit_of_measurement":unit} if unit else {})},
                "last_reported":NOW.isoformat(),"last_updated":NOW.isoformat()}
        for entity,value in ((options["pv_entity"],7500),(options["grid_entity"],-6000),(options["house_entity"],1500)):
            put(entity,value,"W")
        for entity,value,unit in ((Fronius.defaults["soc"],60,"%"),(Fronius.defaults["charge_power"],0,"W"),
                                  (Fronius.defaults["discharge_power"],0,"W"),(Fronius.defaults["mode"],"Auto",None)):
            put(entity,value,unit)
        for row in definitions():
            ids=row["wallbox_parameters"]
            put(ids["power"],0,"W")
            put(ids["status"],"connected")
            put(ids["enable"],"off")
            put(ids["current"],6,"A",step=.1,max=16)
            put(ids["phases"],1)
            put(row["soc_entity"],.4)
    def states(self):
        return deepcopy(self.rows)
    def state(self,entity):
        return deepcopy(self.rows.get(entity,{}))
    def set(self,entity,value):
        self.writes.append((entity,value))
        self.rows[entity]["state"]=("on" if value else "off") if isinstance(value,bool) else str(value)


class FleetRequirements(unittest.TestCase):
    def setup_fleet(self):
        directory=self.enterContext(temporary_project_directory())
        opts={**DEFAULTS,"vehicles":json.dumps(definitions()),"heat_entity":"","phase_wait_s":10}
        ha=LocalHA(opts)
        app=create_controller(ha,opts,directory)
        app.config.eos=Mock()
        app.config.eos.plan.return_value={"generated_at":NOW.isoformat(),"instructions":[instruction(NOW,"NON_EXPORT")]+[
            {**instruction(NOW,"NON_EXPORT"),"resource_id":row["resource"]} for row in definitions()]}
        app.config.eos.solution.return_value={}
        app.battery_driver.apply=Mock()
        app.battery_driver.release=Mock()
        return app,ha,opts,directory

    def test_duplicate_wallbox_or_eos_resource_is_rejected(self):
        for key in ("resource","wallbox_parameters"):
            rows=definitions()
            rows[1][key]=rows[0][key]
            with self.subTest(key=key),self.assertRaises(ValueError):
                validate_options({**DEFAULTS,"vehicles":json.dumps(rows)})

    def test_pending_increases_are_reserved_but_unconfirmed_reductions_are_not_spent(self):
        self.assertEqual(reserved_grid(-6000,{"a":0,"b":0},{"a":3680},"b"),-2320)
        self.assertEqual(reserved_grid(-1000,{"a":3000,"b":0},{"a":0},"b"),-1000)
        self.assertEqual(reserved_grid(-1000,{"a":3000},{"a":3680},"a"),-1000)

    def test_two_pv_chargers_share_surplus_even_before_their_power_meters_catch_up(self):
        app,ha,_,_=self.setup_fleet()
        for key,_,_ in app.controllers:
            app.change_vehicle_settings(key,{"pv":True,"phase_auto":False})
        app.set_armed(True)
        app.tick(NOW,0)
        app.tick(NOW+timedelta(seconds=20),20)
        self.assertGreater(app.targets["first"],0)
        self.assertGreater(app.targets["second"],0)
        self.assertLessEqual(sum(app.targets.values()),6000)
        # Meter values intentionally remain zero after both commands.
        app.tick(NOW+timedelta(seconds=25),25)
        self.assertLessEqual(sum(app.targets.values()),6000)
        self.assertEqual(len(app.snapshot(NOW)["vehicles"]),2)
        app.battery_driver.apply.assert_called()

    def test_settings_and_soc_are_independent_and_survive_restart(self):
        app,ha,opts,directory=self.setup_fleet()
        app.change_vehicle_settings("first",{"target_soc":70})
        app.change_vehicle_settings("second",{"target_soc":90})
        ha.rows["sensor.soc_second"]["state"]="0.6"
        app.tick(NOW,0)
        vehicles=app.snapshot(NOW)["vehicles"]
        self.assertEqual([v["live"]["car_soc"] for v in vehicles],[40,60])
        self.assertEqual([v["settings"]["target_soc"] for v in vehicles],[70,90])
        restored=create_controller(ha,opts,directory)
        self.assertEqual([child.config.daily["target_soc"] for _,child,_ in restored.controllers],[70,90])
        with self.assertRaises(ValueError):
            app.change_vehicle_settings("missing",{"target_soc":50})

    def test_house_subtracts_all_vehicle_measurements_once(self):
        app,ha,opts,_=self.setup_fleet()
        ha.rows[opts["house_entity"]]["state"]="5000"
        ha.rows["sensor.first_power"]["state"]="1000"
        ha.rows["sensor.second_power"]["state"]="2000"
        app.tick(NOW,0)
        self.assertEqual(app.live["house"],2000)
        self.assertEqual(app.live["car"],3000)

    def test_disarm_attempts_every_charger_and_releases_storage(self):
        app,ha,_,_=self.setup_fleet()
        app.set_armed(True)
        app.owned=True
        for row in definitions():
            ha.rows[row["wallbox_parameters"]["enable"]]["state"]="on"
        app.set_armed(False)
        switches={entity for entity,value in ha.writes if value is False}
        self.assertEqual(switches,{"switch.first_enabled","switch.second_enabled"})
        app.battery_driver.release.assert_called_once()

    def test_grid_plans_share_connection_headroom(self):
        app,ha,opts,_=self.setup_fleet()
        ha.rows[opts["grid_entity"]]["state"]="12000"
        plan={"generated_at":NOW.isoformat(),"instructions":[instruction(NOW,"NON_EXPORT")]+[
            {**instruction(NOW,"GRID_SUPPORT_IMPORT"),"resource_id":row["resource"]} for row in definitions()]}
        app.config.eos.plan.return_value=plan
        for _,child,_ in app.controllers:
            child.sync_goal=Mock(return_value=True)
            child.goal_at=NOW-timedelta(minutes=3)
            child.config.daily["phase_auto"]=False
        app.set_armed(True)
        app.tick(NOW,0)
        self.assertLessEqual(sum(app.targets.values()),opts["grid_limit_w"]-12000)
        self.assertGreater(sum(app.targets.values()),0)

    def test_reordering_vehicle_list_keeps_settings_bound_to_vehicle_identity(self):
        app,ha,opts,directory=self.setup_fleet()
        app.change_vehicle_settings("first",{"target_soc":70})
        app.change_vehicle_settings("second",{"target_soc":90})
        opts["vehicles"]=json.dumps(list(reversed(definitions())))
        restored=create_controller(ha,opts,directory)
        self.assertEqual({key:child.config.daily["target_soc"] for key,child,_ in restored.controllers},{"first":70,"second":90})

    def test_invalid_vehicle_settings_do_not_partially_save(self):
        app,_,_,_=self.setup_fleet()
        before=[deepcopy(child.config.daily) for _,child,_ in app.controllers]
        with self.assertRaises(ValueError):
            app.change_vehicle_settings("second",{"target_soc":70,"battery_min_soc":100})
        self.assertEqual([child.config.daily for _,child,_ in app.controllers],before)

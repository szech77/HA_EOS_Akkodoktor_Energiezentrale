"""Fleet requirements: distinct resources, shared budgets and independent settings."""
from copy import deepcopy
from datetime import timedelta
import json
import unittest
from dataclasses import replace
from unittest.mock import Mock

from custom_components.eos_energiezentrale.const import DEFAULTS
from custom_components.eos_energiezentrale.energy.fleet import create_controller, vehicle_options, reserved_grid
from custom_components.eos_energiezentrale.energy.drivers import Fronius
from custom_components.eos_energiezentrale.validation import validate_options
from test_energy import NOW, instruction, temporary_project_directory
from custom_components.eos_energiezentrale.energy.contracts import Measurement


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

    def test_plugin_grid_meter_keeps_shared_reservations_without_a_grid_sensor(self):
        app,ha,_,_=self.setup_fleet()
        for key,child,_ in app.controllers:
            child.config.options['grid_entity']=''
            app.change_vehicle_settings(key,{"pv":True,"phase_auto":False})
        driver=app.battery_driver
        driver.measurement_keys=driver.measurement_keys+('grid',)
        original_read=driver.read
        driver.read=lambda rows,now:replace(original_read(rows,now),measurements={'grid':Measurement(-6000,now)})
        app.set_armed(True)
        for clock in (0,20,25):
            app.tick(NOW+timedelta(seconds=clock),clock)
        self.assertGreater(app.targets['first'],0)
        self.assertGreater(app.targets['second'],0)
        self.assertLessEqual(sum(app.targets.values()),6000)
        self.assertEqual(app.live['grid'],-6000)
        self.assertEqual(app.snapshot(NOW)['source_configuration']['sources']['grid']['source']['type'],'plugin')
        ha.rows['sensor.second_power']['state']='unavailable'
        app.tick(NOW+timedelta(seconds=35),35)
        self.assertTrue(all(target==0 for target in app.targets.values()))
        self.assertTrue(all(ha.rows[proxy.ids['enable']]['state']=='off' for _,_,proxy in app.controllers))
        self.assertTrue(app.snapshot(NOW)['source_configuration']['sources']['grid']['available'])

    def test_vehicle_soc_from_plugins_is_never_shared_between_vehicles(self):
        app,_,_,_=self.setup_fleet()
        for index,(_,child,_) in enumerate(app.controllers):
            child.config.options['car_soc_entity']=''
            box=child.config.wallbox
            box.measurement_keys=box.measurement_keys+('car_soc',)
            original=box.read
            percent=40+index*20
            box.read=lambda rows,now,original=original,percent=percent:replace(
                original(rows,now),measurements={'car_soc':Measurement(percent,now)})
        app.tick(NOW,0)
        self.assertEqual([item['live']['car_soc'] for item in app.snapshot(NOW)['vehicles']],[40,60])
        self.assertIsNone(app.live['car_soc'])

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

    def test_release_failure_of_one_charger_does_not_prevent_attempts_for_the_others(self):
        app,ha,_,_=self.setup_fleet()
        for row in definitions():
            ha.rows[row["wallbox_parameters"]["enable"]]["state"]="on"
        original_set=ha.set
        def fail_first(entity,value):
            if entity=="switch.first_enabled":
                raise OSError("charger offline")
            return original_set(entity,value)
        ha.set=fail_first
        with self.assertRaises(OSError):
            app.release(ha.states(),NOW)
        self.assertIn(("switch.second_enabled",False),ha.writes)
        app.battery_driver.release.assert_called_once()

    def test_each_vehicle_updates_its_own_eos_goal(self):
        app,_,_,_=self.setup_fleet()
        deadline=NOW+timedelta(hours=4)
        for index,(identity,child,_) in enumerate(app.controllers):
            if child is not app:
                child.config.eos=Mock()
            app.change_vehicle_settings(identity,{"schedule":"once","departure":deadline.isoformat(),"target_soc":70+index*20})
        app.set_armed(True)
        app.tick(NOW,0)
        for index,(_,child,_) in enumerate(app.controllers):
            child.config.eos.set_vehicle_goal.assert_called_once_with("ev"+str(index+1),70+index*20,deadline)

    def test_vehicle_histories_remain_distinct_when_aggregate_power_is_written(self):
        app,ha,_,_=self.setup_fleet()
        ha.rows["sensor.first_power"]["state"]="1000"
        ha.rows["sensor.second_power"]["state"]="2000"
        app.tick(NOW,0)
        histories=app.vehicle_histories(NOW)
        self.assertEqual(histories["first"][-1]["car"],1000)
        self.assertEqual(histories["second"][-1]["car"],2000)
        self.assertEqual(app.history.read(NOW)[-1]["car"],3000)
        self.assertNotIn("history",app.snapshot(NOW)["vehicles"][0])

    def test_retained_fleet_power_sums_all_chargers_without_filling_live_measurements(self):
        app,ha,opts,_=self.setup_fleet()
        ha.rows[opts["house_entity"]]["state"]="5000"
        ha.rows["sensor.first_power"]["state"]="1000"
        ha.rows["sensor.second_power"]["state"]="2000"
        app.tick(NOW,0)
        ha.rows["sensor.first_power"]["state"]="unavailable"
        ha.rows["sensor.second_power"]["state"]="unavailable"
        app.tick(NOW+timedelta(seconds=30),30)
        result=app.snapshot(NOW+timedelta(seconds=30))
        self.assertIsNone(result["live"]["car"])
        self.assertEqual(result["display"]["car"]["value"],3000)
        self.assertEqual(result["display"]["house"]["value"],2000)

    def test_missing_second_vehicle_plan_keeps_only_its_own_last_instruction_for_grace(self):
        app,_,_,_=self.setup_fleet()
        app.tick(NOW,0)
        later=NOW+timedelta(seconds=15)
        app.config.eos.plan.return_value={"generated_at":later.isoformat(),"instructions":[
            instruction(later,"NON_EXPORT"),{**instruction(later,"IDLE"),"resource_id":"ev1"}]}
        app.tick(later,15)
        self.assertEqual(app.order_for("ev1",later).mode,"IDLE")
        second=app.controllers[1][1]
        self.assertEqual(second.order_for("ev2",later).mode,"NON_EXPORT")
        self.assertIsNone(second.order_for("ev2",NOW+timedelta(seconds=315)))

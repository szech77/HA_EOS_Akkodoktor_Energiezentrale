"""Plugin requirements: discovery, contract failures, capability safety and HA I/O."""
from dataclasses import replace
from datetime import timedelta
import importlib
import json
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch
from uuid import uuid4

from custom_components.eos_energiezentrale.energy.contracts import (
    BatteryReading, WallboxReading, WallboxFeatures, PluginInfo, PluginContractError, UnsupportedFeature)
from custom_components.eos_energiezentrale.energy.drivers import BATTERY_DRIVERS, WALLBOX_DRIVERS, NRGkick
from custom_components.eos_energiezentrale.energy.plugin_registry import validate_class, PluginFactory, load_plugins, describe
from custom_components.eos_energiezentrale.energy.plugins.generic_wallbox import GenericWallbox
from custom_components.eos_energiezentrale.energy.plugins.generic_battery import GenericBattery
from custom_components.eos_energiezentrale.energy.sanitiser import battery_reading, wallbox_reading
from custom_components.eos_energiezentrale.energy.domain import BatteryCommand
from test_energy import NOW, temporary_project_directory
from test_requirements import wallbox
import test_requirements as requirements


class EntityHA:
    def __init__(self,rows): self.rows=rows;self.commands=[]
    def state(self,entity): return self.rows.get(entity,{})
    def set(self,entity,value):
        self.commands.append((entity,value))
        self.rows[entity]['state']='on' if value is True else 'off' if value is False else str(value)


def row(value,unit=None,**attributes):
    return {'state':str(value),'last_reported':NOW.isoformat(),'attributes':{**attributes,**({'unit_of_measurement':unit} if unit else {})}}


def generic_wallbox():
    params={'power':'sensor.ev_w','plugged':'binary_sensor.ev_plugged','enable':'input_boolean.ev_enable',
            'current':'input_number.ev_current','phases':'sensor.ev_phases','phase_switching':False}
    rows={'sensor.ev_w':row(0,'W'),'binary_sensor.ev_plugged':row('on'),
          'input_boolean.ev_enable':row('off'),'input_number.ev_current':row(6,'A',step=.1,max=16),
          'sensor.ev_phases':row(3)}
    return params,EntityHA(rows)


class PluginRequirements(unittest.TestCase):
    def test_registry_discovers_names_schemas_and_both_generic_types(self):
        self.assertTrue({'fronius','generic'}.issubset(BATTERY_DRIVERS))
        self.assertTrue({'nrgkick','generic','none'}.issubset(WALLBOX_DRIVERS))
        self.assertTrue(WALLBOX_DRIVERS['generic'].configuration)
        self.assertIn('Home Assistant',BATTERY_DRIVERS['generic'].info.name)

    def test_local_modules_are_discovered_without_editing_a_registry_and_bad_module_is_quarantined(self):
        with temporary_project_directory() as directory:
            package='plugin_fixture_'+uuid4().hex
            folder=directory/package;folder.mkdir();(folder/'__init__.py').write_text('')
            common='from custom_components.eos_energiezentrale.energy.plugins.nrgkick import NRGkick\nfrom custom_components.eos_energiezentrale.energy.contracts import PluginInfo\n'
            (folder/'good.py').write_text(common+'class TestBox(NRGkick):\n info=PluginInfo("discovered","Discovered wallbox","wallbox")\nPLUGINS=(TestBox,)\n')
            (folder/'broken.py').write_text('PLUGINS=(object,)')
            sys.path.insert(0,str(directory));importlib.invalidate_caches()
            try:
                batteries,boxes,errors=load_plugins(package)
                self.assertIn('discovered',boxes)
                self.assertEqual(boxes['discovered'](None,{}).info.name,'Discovered wallbox')
                self.assertIn('broken',errors)
            finally:
                sys.path.remove(str(directory))
                for name in list(sys.modules):
                    if name==package or name.startswith(package+'.'):sys.modules.pop(name)

    def test_incompatible_version_wrong_signature_and_sanitiser_bypass_are_rejected(self):
        class WrongVersion(NRGkick):info=PluginInfo('wrong','Wrong','wallbox',99)
        class WrongSignature(NRGkick):
            def _read(self,states): return None
        class UnsafeRead(NRGkick):
            def read(self,states,now): return None
        for plugin in (WrongVersion,WrongSignature,UnsafeRead,object):
            with self.subTest(plugin=plugin),self.assertRaises(PluginContractError):validate_class(plugin)

    def test_invalid_features_are_rejected_before_a_device_is_used(self):
        class WrongFeatures(NRGkick):features=WallboxFeatures(phase_switching='yes')
        with self.assertRaises(PluginContractError):PluginFactory(WrongFeatures)(None,{})

    def test_duplicate_plugin_identifiers_do_not_replace_an_existing_driver(self):
        from types import ModuleType
        first=ModuleType('first');first.PLUGINS=(NRGkick,)
        second=ModuleType('second');second.PLUGINS=(NRGkick,)
        package=SimpleNamespace(__path__=[])
        with patch('custom_components.eos_energiezentrale.energy.plugin_registry.import_module',side_effect=[package,first,second]),patch('custom_components.eos_energiezentrale.energy.plugin_registry.pkgutil.iter_modules',return_value=[SimpleNamespace(name='first',ispkg=False),SimpleNamespace(name='second',ispkg=False)]):
            _,boxes,errors=load_plugins('fixture')
        self.assertIs(boxes['nrgkick'].plugin_class,NRGkick)
        self.assertIn('second',errors)

    def test_bad_numeric_measurements_become_missing_not_zero(self):
        self.assertEqual(battery_reading(BatteryReading(101,float('nan'),-10)),BatteryReading(None,None,None))
        for value in (float('inf'),True,'500',-1,10**1000):
            reading=wallbox_reading(WallboxReading(value,' CHARGING ',True,3,6,.1,16,NOW),NOW)
            self.assertIsNone(reading.watts)
            self.assertEqual(reading.status,'charging')
        with self.assertRaises(PluginContractError):battery_reading({'soc':50})
        with self.assertRaises(PluginContractError):wallbox_reading(WallboxReading(0,'connected','on',3,6,.1,16,NOW))

    def test_stale_future_and_naive_wallbox_samples_are_not_used_as_current_power(self):
        for stamp in (NOW-timedelta(minutes=3),NOW+timedelta(seconds=1),NOW.replace(tzinfo=None)):
            with self.subTest(stamp=stamp):
                result=wallbox_reading(WallboxReading(7000,'charging',True,3,10,.1,16,stamp),NOW)
                self.assertIsNone(result.watts)
                self.assertIsNone(result.sample)

    def test_generic_wallbox_reads_helpers_and_blocks_unsupported_phase_switches(self):
        params,ha=generic_wallbox();box=WALLBOX_DRIVERS['generic'](ha,params)
        reading=box.read(ha.rows,NOW)
        self.assertEqual((reading.status,reading.phases,reading.amps),('connected',3,6))
        box.charge(6.2,reading)
        self.assertEqual(ha.commands,[('input_number.ev_current',6.2),('input_boolean.ev_enable',True)])
        with self.assertRaises(UnsupportedFeature):box.phase(1,reading)
        self.assertEqual(len(ha.commands),2)
        self.assertFalse(describe(box)['features']['phase_switching'])

    def test_generic_wallbox_rejects_wrong_entities_units_and_invalid_current(self):
        params,ha=generic_wallbox()
        with self.assertRaises(ValueError):WALLBOX_DRIVERS['generic'](ha,{**params,'enable':'sensor.cannot_write'})
        with self.assertRaises(ValueError):WALLBOX_DRIVERS['generic'](ha,{**params,'unknown':1})
        box=WALLBOX_DRIVERS['generic'](ha,params)
        state=box.read(ha.rows,NOW)
        for amps in (float('nan'),5,17,6.25):
            with self.subTest(amps=amps),self.assertRaises(PluginContractError):box.charge(amps,state)
        self.assertEqual(ha.commands,[])
        ha.rows['input_number.ev_current']['attributes']['unit_of_measurement']='W'
        self.assertIsNone(box.read(ha.rows,NOW).amps)

    def test_generic_phase_switch_waits_for_stop_and_two_new_zero_samples(self):
        params,ha=generic_wallbox()
        params.update(phases='input_select.ev_phases',phase_feedback='sensor.ev_phases',phase_switching=True)
        ha.rows['input_select.ev_phases']=row('3',options=['1','3'])
        ha.rows['input_boolean.ev_enable']=row('on')
        box=WALLBOX_DRIVERS['generic'](ha,params)
        reading=box.read(ha.rows,NOW)
        with patch('custom_components.eos_energiezentrale.energy.entity_wallbox.datetime') as clock:
            clock.now.return_value=NOW
            self.assertFalse(box.phase(1,reading))
        self.assertEqual(ha.commands,[('input_boolean.ev_enable',False)])
        # Old zero measurements cannot prove that the relay has opened.
        self.assertFalse(box.phase(1,replace(reading,enabled=False,status='connected')))
        for seconds in (1,2):
            self.assertFalse(box.phase(1,replace(reading,enabled=False,status='connected',sample=NOW+timedelta(seconds=seconds))))
        self.assertEqual(len(ha.commands),1)
        self.assertFalse(box.phase(1,replace(reading,enabled=False,status='connected',sample=NOW+timedelta(seconds=4))))
        self.assertEqual(ha.commands[-1],('input_select.ev_phases','1'))

    def test_generic_battery_maps_normalized_commands_to_helpers_with_kw_conversion(self):
        params={'soc':'sensor.soc','soc_scale':'factor','charge_power':'sensor.charge','discharge_power':'sensor.discharge',
                'mode':'input_select.battery_mode','charge_limit':'input_number.charge','discharge_limit':'input_number.discharge'}
        ha=EntityHA({'sensor.soc':row(.6),'sensor.charge':row(1,'kW'),'sensor.discharge':row(0,'W'),
            'input_select.battery_mode':row('auto',options=['auto','limits','block_discharge','grid_charge','grid_discharge']),
            'input_number.charge':row(0,'kW',min=0,max=10,step=.01),
            'input_number.discharge':row(0,'W',min=0,max=10000,step=10)})
        battery=BATTERY_DRIVERS['generic'](ha,params)
        self.assertEqual(battery.read(ha.rows,NOW),BatteryReading(60,1000,0))
        battery.apply(BatteryCommand('limits',4760,1000),ha.rows)
        self.assertAlmostEqual(float(ha.rows['input_number.charge']['state']),4.76)
        self.assertEqual(ha.rows['input_select.battery_mode']['state'],'limits')
        ha.commands.clear()
        with self.assertRaises(UnsupportedFeature):battery.apply(BatteryCommand('grid_discharge',0,1000),ha.rows)
        self.assertEqual(ha.commands,[])
        battery.release(ha.rows)
        self.assertEqual(ha.rows['input_select.battery_mode']['state'],'auto')


class CapabilityRegulation(unittest.TestCase):
    def test_regulator_cannot_request_phase_switch_on_a_fixed_three_phase_wallbox(self):
        fixture=requirements.ControllerRequirements();fixture.setUp()
        try:
            fixture.box.features=WallboxFeatures(phase_switching=False)
            fixture.app.regulate_car(wallbox(watts=6900,enabled=True,status='charging',phases=3,amps=10),
                {'grid':-1000,'solar':10000,'battery_discharge':0},5000,False,NOW,0,fixture.states())
            fixture.box.phase.assert_not_called()
            amps=fixture.box.charge.call_args.args[0]
            self.assertGreaterEqual(amps,6)
            self.assertLessEqual(amps*3*230,5000)
        finally:fixture.doCleanups()

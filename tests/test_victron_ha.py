"""Victron HACS entity contracts: signed telemetry, bounded ESS writes and release."""
from copy import deepcopy
from datetime import datetime,timedelta,timezone
from unittest import TestCase
from unittest.mock import patch

from custom_components.eos_energiezentrale.energy.contracts import UnsupportedFeature
from custom_components.eos_energiezentrale.energy.device_io import DeviceConfirmationError,DeviceNotReady,ScopedHardwareAdapter
from custom_components.eos_energiezentrale.energy.devices import DeviceSite
from custom_components.eos_energiezentrale.energy.domain import BatteryCommand
from custom_components.eos_energiezentrale.energy.drivers import BATTERY_DRIVERS
from custom_components.eos_energiezentrale.energy.measurement_sources import resolve_sources
from custom_components.eos_energiezentrale.energy.sanitiser import battery_reading


class HA:
    def __init__(self):
        self.now=datetime.now(timezone.utc);self.rows={};self.writes=[];self.ignore=set()
        for key,value,unit in (('soc',60,'%'),('battery',0,'W'),('voltage',50,'V'),('grid',1000,'W'),('solar',2000,'W'),('house',3000,'W')):
            self.rows['sensor.'+key]={'state':str(value),'attributes':{'unit_of_measurement':unit},'last_reported':self.now.isoformat()}
        for key,value,low,high,step,unit in (('setpoint',50,-10000,10000,10,'W'),('charge',60,-1,100,1,'A'),('discharge',4500,-1,5000,50,'W')):
            self.rows['number.'+key]={'state':str(value),'attributes':{'unit_of_measurement':unit,'min':low,'max':high,'step':step},'last_reported':self.now.isoformat()}
        self.rows['select.ess']={'state':'optimized_no_battery_life','attributes':{'options':['optimized_no_battery_life','optimized_battery_life','external_control']}}
    def state(self,entity): return deepcopy(self.rows.get(entity,{}))
    def set(self,entity,value):
        self.writes.append((entity,value))
        if entity not in self.ignore:self.rows[entity]['state']=str(value)


class VictronTests(TestCase):
    plugin_id='victron_ha'
    def setUp(self):
        self.ha=HA()
        self.params={'soc':'sensor.soc','battery_power':'sensor.battery','battery_voltage':'sensor.voltage','grid':'sensor.grid',
            'solar':'sensor.solar','house_total':'sensor.house','ess_mode':'select.ess','grid_setpoint':'number.setpoint',
            'charge_limit':'number.charge','discharge_limit':'number.discharge','release_charge_limit':60,'release_discharge_limit':4500,
            'charge_efficiency':1,'discharge_efficiency':1,'control_enabled':True}
        self.scope=ScopedHardwareAdapter(self.ha)
        self.driver=BATTERY_DRIVERS[self.plugin_id](self.scope,self.params)
        self.scope.bind(self.driver.ids.values())

    def command(self,mode='limits',charge=5000,discharge=3000,**extra):
        return BatteryCommand(mode,charge,discharge,min_soc=20,max_soc=90,**extra)

    def test_reading_splits_signed_battery_power_and_supplies_pv_grid_and_house(self):
        self.ha.rows['sensor.battery']['state']='-1500'
        sample=self.driver.read(self.ha.rows,self.ha.now)
        self.assertEqual((sample.soc,sample.charge,sample.discharge),(60,0,1500))
        self.assertEqual(sample.measurements['house_total'].value,3000)
        self.assertEqual(sample.measurements['grid'].value,1000)
        self.assertEqual(sample.measurements['solar'].value,2000)
        self.assertFalse(self.driver.ids['charge_power'])
        self.assertFalse(self.ha.writes)

    def test_dc_ac_efficiencies_are_applied_once_and_kw_is_supported(self):
        driver=BATTERY_DRIVERS[self.plugin_id](self.ha,{**self.params,'charge_efficiency':.8,'discharge_efficiency':.9})
        self.ha.rows['sensor.battery']['state']='1'
        self.ha.rows['sensor.battery']['attributes']['unit_of_measurement']='kW'
        self.assertEqual(driver.read(self.ha.rows,self.ha.now).charge,1250)
        self.ha.rows['sensor.battery']['state']='-1'
        self.assertEqual(driver.read(self.ha.rows,self.ha.now).discharge,900)

    def test_slow_soc_reports_remain_bounded_and_work_through_the_device_manager(self):
        self.ha.rows['sensor.soc']['last_reported']=(self.ha.now-timedelta(seconds=200)).isoformat()
        self.assertEqual(self.driver.read(self.ha.rows,self.ha.now).soc,60)
        self.assertIsNone(battery_reading(self.driver.read(self.ha.rows,self.ha.now),self.ha.now).soc)
        self.assertEqual(self.driver.read(self.ha.rows,self.ha.now).soc_sample,self.ha.now-timedelta(seconds=200))
        site=DeviceSite(self.scope,[{'id':'gx','name':'GX','kind':'battery','plugin':self.plugin_id,'parameters':self.params,
            'capacity_wh':10000,'charge_w':5000,'discharge_w':5000,'grid_source':True}])
        self.assertEqual(site.read(self.ha.rows,self.ha.now).soc,60)
        self.assertEqual(site.read(self.ha.rows,self.ha.now).measurements['house_total'].value,3000)
        self.ha.rows['sensor.soc']['last_reported']=(self.ha.now-timedelta(seconds=361)).isoformat()
        self.assertIsNone(self.driver.read(self.ha.rows,self.ha.now).soc)

    def test_direct_site_consumption_and_optional_sources_preserve_missing_data_and_sensor_priority(self):
        site=DeviceSite(self.ha,[{'id':'gx','name':'GX','kind':'battery','plugin':self.plugin_id,'parameters':self.params,
            'capacity_wh':10000,'charge_w':5000,'discharge_w':5000,'grid_source':True}])
        sample=site.read(self.ha.rows,self.ha.now)
        options,states,report=resolve_sources({},self.ha.rows,[(site,sample)],self.ha.now,keys={'solar','grid','house_total'})
        self.assertFalse(report['missing']);self.assertFalse(report['unavailable'])
        self.assertEqual(states[options['house_entity']]['state'],3000)
        options,_,report=resolve_sources({'house_entity':'sensor.external'},self.ha.rows,[(site,sample)],self.ha.now,keys={'house_total'})
        self.assertEqual(options['house_entity'],'sensor.external')
        self.assertEqual(report['unavailable'],['house_total'])
        self.ha.rows['sensor.house']['state']='unavailable'
        self.assertIsNone(site.read(self.ha.rows,self.ha.now).measurements['house_total'].value)

    def test_read_only_default_has_no_write_capability(self):
        driver=BATTERY_DRIVERS[self.plugin_id](self.scope,{'soc':'sensor.soc','battery_power':'sensor.battery'})
        self.assertFalse(driver.features.grid_charge);self.assertFalse(driver.features.charge_limit)
        driver.release(self.ha.rows)
        with self.assertRaises(UnsupportedFeature):driver.apply(self.command(),self.ha.rows)
        self.assertFalse(self.ha.writes)

    def test_two_gx_devices_receive_bounded_dispatch_including_neutral_phase(self):
        other=HA()
        self.ha.rows.update({'%s.other_%s'%tuple(key.split('.',1)):value for key,value in other.rows.items()})
        other_params={key:('%s.other_%s'%tuple(value.split('.',1)) if isinstance(value,str) and value.startswith(('sensor.','select.','number.')) else value)
                      for key,value in self.params.items()}
        rows=[{'id':name,'name':name,'kind':'battery','plugin':self.plugin_id,'parameters':params,
               'capacity_wh':10000,'charge_w':3000,'discharge_w':3000,'grid_source':index==0}
              for index,(name,params) in enumerate((('one',self.params),('two',other_params)))]
        site=DeviceSite(self.ha,rows)
        site.apply(self.command('grid_charge',4000,0),self.ha.rows)
        self.assertEqual(float(self.ha.rows['number.charge']['state']),40)
        self.assertEqual(float(self.ha.rows['number.other_charge']['state']),40)
        self.assertEqual(float(self.ha.rows['number.setpoint']['state']),3000)
        self.assertEqual(float(self.ha.rows['number.other_setpoint']['state']),3000)

    def test_grid_charge_sets_amp_and_discharge_caps_before_the_grid_target(self):
        self.driver.apply(self.command('grid_charge',2000,0),self.ha.rows)
        self.assertEqual(self.ha.writes,[('number.charge',40),('number.discharge',0),('number.setpoint',3000)])
        self.driver.apply(self.command('grid_charge',2000,0),self.ha.rows)
        self.assertEqual(len(self.ha.writes),3)

    def test_self_consumption_and_block_discharge_use_the_grid_balance(self):
        self.driver.apply(self.command(),self.ha.rows)
        self.assertEqual(float(self.ha.rows['number.setpoint']['state']),0)
        self.ha.writes.clear()
        self.driver.apply(self.command('block_discharge'),self.ha.rows)
        self.assertEqual(float(self.ha.rows['number.discharge']['state']),0)
        self.assertEqual(float(self.ha.rows['number.setpoint']['state']),1000)

    def test_forced_export_requires_explicit_opt_in(self):
        with self.assertRaises(UnsupportedFeature):self.driver.apply(self.command('grid_discharge',0,2000),self.ha.rows)
        driver=BATTERY_DRIVERS[self.plugin_id](self.scope,{**self.params,'grid_discharge_supported':True})
        driver.apply(self.command('grid_discharge',0,2000),self.ha.rows)
        self.assertEqual(float(self.ha.rows['number.setpoint']['state']),-1000)

    def test_fresh_voltage_and_entity_bounds_limit_charge_current(self):
        self.ha.rows['sensor.voltage']['state']='60'
        self.assertEqual(self.driver.power_limits(self.ha.rows),(6000,5000))
        self.driver.apply(self.command('grid_charge',5000,0),self.ha.rows)
        self.assertEqual(float(self.ha.rows['number.charge']['state']),83)
        self.assertEqual(float(self.ha.rows['number.setpoint']['state']),5980)

    def test_watt_charge_limits_work_without_a_voltage_sensor(self):
        self.ha.rows['number.charge'].update(state='3000',attributes={'unit_of_measurement':'W','min':-1,'max':6000,'step':50})
        driver=BATTERY_DRIVERS[self.plugin_id](self.scope,{**self.params,'battery_voltage':'','release_charge_limit':3000})
        driver.apply(self.command('grid_charge',2200,0),self.ha.rows)
        self.assertEqual(float(self.ha.rows['number.charge']['state']),2200)

    def test_soc_bounds_and_required_support_are_honoured_before_writes(self):
        self.ha.rows['sensor.soc']['state']='20'
        with self.assertRaises(ValueError):self.driver.apply(self.command(required_discharge_w=1000),self.ha.rows)
        self.assertFalse(self.ha.writes)
        self.ha.rows['sensor.soc']['state']='90'
        self.driver.apply(self.command('grid_charge',2000,0),self.ha.rows)
        self.assertEqual(float(self.ha.rows['number.charge']['state']),0)

    def test_stale_and_wrong_mode_or_units_never_trigger_new_writes(self):
        for key in ('grid','battery'):
            with self.subTest(key=key):
                old=self.ha.rows['sensor.'+key]['last_reported']
                self.ha.rows['sensor.'+key]['last_reported']=(self.ha.now-timedelta(seconds=121)).isoformat()
                with self.assertRaises(DeviceNotReady):self.driver.apply(self.command(),{})
                self.ha.rows['sensor.'+key]['last_reported']=old
        self.ha.rows['select.ess']['state']='external_control'
        with self.assertRaises(ValueError):self.driver.apply(self.command(),{})
        self.ha.rows['select.ess']['state']='optimized_no_battery_life'
        self.ha.rows['number.setpoint']['attributes']['unit_of_measurement']='A'
        with self.assertRaises(ValueError):self.driver.apply(self.command(),{})
        self.assertFalse(self.ha.writes)

    def test_unconfirmed_limit_stops_before_setting_a_new_grid_target(self):
        self.ha.ignore.add('number.charge')
        with patch('custom_components.eos_energiezentrale.energy.device_io.monotonic',side_effect=[0,6]):
            with self.assertRaises(DeviceConfirmationError):self.driver.apply(self.command('grid_charge',2000,0),{})
        self.assertEqual(self.ha.writes,[('number.charge',40)])

    def test_release_uses_explicit_native_values_even_after_restart_and_without_telemetry(self):
        self.ha.rows['number.charge']['state']='0';self.ha.rows['number.discharge']['state']='0';self.ha.rows['number.setpoint']['state']='3000'
        self.ha.rows['sensor.voltage']['state']='unavailable'
        restarted=BATTERY_DRIVERS[self.plugin_id](self.scope,self.params)
        restarted.release({})
        self.assertEqual(self.ha.writes,[('number.setpoint',50),('number.charge',60),('number.discharge',4500)])

    def test_invalid_control_configuration_is_rejected_without_network_or_writes(self):
        for changes in ({'release_charge_limit':None},{'grid':''},{'charge_efficiency':0},{'discharge_limit':'number.charge'},
                        {'ess_mode_option':'external_control'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                BATTERY_DRIVERS[self.plugin_id](None,{**self.params,**changes})
        self.assertFalse(self.ha.writes)

    def test_invalid_release_bounds_and_units_are_checked_before_writes(self):
        self.ha.rows['number.discharge']['attributes']['max']=4000
        with self.assertRaises(ValueError):self.driver.apply(self.command(),{})
        with self.assertRaises(ValueError):self.driver.release({})
        self.ha.rows['number.discharge']['attributes']['max']=5000
        self.ha.rows['number.discharge']['attributes']['unit_of_measurement']='A'
        with self.assertRaises(ValueError):self.driver.release({})
        self.assertFalse(self.ha.writes)

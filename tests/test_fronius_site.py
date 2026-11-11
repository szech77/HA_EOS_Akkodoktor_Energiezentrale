"""Multi-inverter telemetry and storage dispatch over real local Modbus TCP."""
from contextlib import contextmanager, ExitStack
from dataclasses import replace
from datetime import timedelta
import struct
from unittest.mock import patch

import pytest

from custom_components.eos_energiezentrale.energy.drivers import BATTERY_DRIVERS
from custom_components.eos_energiezentrale.energy.domain import BatteryCommand
from custom_components.eos_energiezentrale.energy._modbus_tcp import ModbusError
from custom_components.eos_energiezentrale.energy.contracts import PluginContractError
from test_fronius_modbus import inverter
from test_energy import NOW


def ac(server,value):
    server.registers[40181],server.registers[40182]=struct.unpack('>HH',struct.pack('>f',value))


def pv_only(server,mppt=True):
    server.registers[server.base-2]=65535  # No storage model 124.
    if mppt:
        server.registers[40070]=48
        server.registers[40077]=2
        server.registers[40119],server.registers[40120]=999,38
        server.registers[40090],server.registers[40110]=500,700
    else:
        server.registers[40069]=999
        server.registers[40197],server.registers[40198]=struct.unpack('>HH',struct.pack('>f',1200.))
    ac(server,1200)


@contextmanager
def site(multiple_batteries=False,mppt=True,export=False):
    with ExitStack() as stack:
        _,primary=stack.enter_context(inverter())
        _,pv=stack.enter_context(inverter())
        pv_only(pv,mppt)
        params={'host':'127.0.0.1','port':primary.server_address[1],
                'battery_capacity_wh':10000,'grid_discharge_supported':export,
                'additional_inverters':{'roof':{'host':'127.0.0.1','port':pv.server_address[1]}}}
        battery=None
        if multiple_batteries:
            _,battery=stack.enter_context(inverter())
            params['additional_inverters']['garage']={'host':'127.0.0.1','port':battery.server_address[1],
                                                       'battery':True,'capacity_wh':20000}
        driver=BATTERY_DRIVERS['fronius_modbus'](None,params)
        yield driver,primary,pv,battery


@pytest.mark.parametrize('mppt',[True,False])
def test_pv_only_inverter_without_storage_model_is_included_and_never_written(mppt):
    with site(mppt=mppt) as (driver,primary,pv,_):
        measured=driver.read({},NOW)
        assert (measured.soc,measured.charge,measured.discharge)==(55,1500,0)
        assert measured.measurements['solar'].value==3200
        assert measured.measurements['house_total'].value==2700
        assert measured.measurements['grid'].value==1000
        assert not primary.writes and not pv.writes
        assert all(unit==1 for _,unit,_,_ in pv.requests)
        assert all(address!=pv.base-2 for function,_,address,count in pv.requests if function==3 and count==26)
        driver.apply(BatteryCommand('grid_charge',1000),{})
        driver.release({})
        assert primary.writes and not pv.writes


def test_shared_grid_meter_is_read_once_per_poll():
    with site() as (driver,primary,pv,_):
        driver.read({},NOW)
        assert primary.requests.count((3,200,40087,5))==1
        assert all(unit!=200 for _,unit,_,_ in pv.requests)


def test_common_meter_may_be_reached_through_another_inverter_gateway():
    with site() as (_driver,primary,pv,_):
        primary.meters[200][40087]=9999
        driver=BATTERY_DRIVERS['fronius_modbus'](None,{
            'host':'127.0.0.1','port':primary.server_address[1],
            'grid_meter_host':'127.0.0.1','grid_meter_port':pv.server_address[1],
            'additional_inverters':{'roof':{'host':'127.0.0.1','port':pv.server_address[1]}}})
        reading=driver.read({},NOW)
        assert reading.measurements['grid'].value==1000
        assert reading.measurements['house_total'].value==2700
        assert all(unit!=200 for _,unit,_,_ in primary.requests)
        assert pv.requests.count((3,200,40087,5))==1


def test_integer_pv_model_without_mppt_or_storage_uses_signed_dc_power_and_scale():
    with site(mppt=False) as (driver,_primary,pv,_):
        pv.registers[40159],pv.registers[40160]=103,50
        pv.registers[40211],pv.registers[40212]=999,pv.base-2-40213
        pv.registers[40173],pv.registers[40174]=12000,65535
        pv.registers[40190],pv.registers[40191]=12000,65535
        assert driver.read({},NOW).measurements['solar'].value==3200
        pv.registers[40190]=32768
        reading=driver.read({},NOW+timedelta(seconds=5))
        assert reading.measurements['solar'].value is None
        assert reading.measurements['house_total'].value==2700


def test_a_pv_only_device_reporting_storage_activity_is_not_silently_treated_as_pv():
    with site() as (driver,_primary,pv,_):
        # Restore the four-channel MPPT layout while leaving storage unconfigured.
        pv.registers[40070],pv.registers[40077]=88,4
        pv.registers[40119],pv.registers[40139]=3,4
        pv.registers[40130],pv.registers[40150]=100,0
        assert driver.read({},NOW).measurements['solar'].value is None
        assert not pv.writes


def test_multiple_storage_soc_is_capacity_weighted_and_powers_are_summed():
    with site(True) as (driver,primary,_pv,battery):
        primary.registers[primary.base+6]=2000
        battery.registers[battery.base+6]=8000
        battery.registers[40130]=500
        battery.registers[40150]=700
        ac(battery,2200)
        measured=driver.read({},NOW)
        assert (measured.soc,measured.charge,measured.discharge)==(60,2000,700)
        assert measured.measurements['solar'].value==5200
        assert measured.measurements['house_total'].value==4900
        assert driver.site_summary['capacity_wh']==30000
        assert driver.site_summary['battery_count']==2
        assert len(driver.site_summary['devices'])==3


def test_missing_pv_inverter_never_becomes_zero_or_a_partial_site_sum():
    with site() as (driver,_primary,pv,_):
        assert driver.read({},NOW).measurements['solar'].value==3200
        pv.reject=True
        measured=driver.read({},NOW+timedelta(seconds=5))
        assert measured.soc==55 and measured.charge==1500
        assert measured.measurements['grid'].value==1000
        assert measured.measurements['solar'].value is None
        assert measured.measurements['house_total'].value is None
        assert driver.site_summary['devices'][1]['available'] is False
        pv.reject=False
        assert driver.read({},NOW+timedelta(seconds=10)).measurements['solar'].value==3200


def test_unknown_storage_soc_does_not_produce_a_partial_weighted_soc_or_control():
    with site(True) as (driver,primary,_pv,battery):
        battery.registers[battery.base+6]=65535
        measured=driver.read({},NOW)
        assert measured.soc is None and measured.soc_sample is None
        assert measured.charge==3000
        with pytest.raises(ModbusError):
            driver.apply(BatteryCommand('grid_charge',2000,min_soc=20,max_soc=90),{})
        assert not primary.writes and not battery.writes


def test_individual_soc_guards_and_device_caps_limit_the_combined_command():
    with site(True) as (driver,primary,pv,battery):
        primary.registers[primary.base+6]=2000
        battery.registers[battery.base+6]=8000
        driver.apply(BatteryCommand('limits',discharge_w=8000,min_soc=20,max_soc=90),{})
        assert primary.registers[primary.base+10]==0
        assert battery.registers[battery.base+10]==10000
        assert not pv.writes
        # The full battery must not be charged even when the weighted site SoC is low.
        battery.registers[battery.base+6]=9000
        driver.apply(BatteryCommand('grid_charge',4000,min_soc=20,max_soc=90),{})
        assert primary.registers[primary.base+11]==8000
        assert battery.registers[battery.base+11]==0


def test_dispatch_weights_use_available_energy_and_free_capacity():
    with site(True) as (driver,primary,_pv,battery):
        primary.registers[primary.base+6]=5000
        battery.registers[battery.base+6]=8000
        driver.apply(BatteryCommand('limits',discharge_w=4000,min_soc=20,max_soc=90),{})
        assert primary.registers[primary.base+10]==1600
        assert battery.registers[battery.base+10]==6400
        driver.apply(BatteryCommand('grid_charge',3000,min_soc=20,max_soc=90),{})
        assert primary.registers[primary.base+11]==4000
        assert battery.registers[battery.base+11]==2000


@pytest.mark.parametrize('demand,charge,discharge',[(1000,0,1000),(-1200,1200,0),(0,0,0)])
def test_normal_operation_uses_one_direction_for_all_batteries(demand,charge,discharge):
    with site(True) as (driver,primary,_pv,battery):
        driver.apply(BatteryCommand('limits',4000,4000,20,90,demand),{})
        charge_sum=sum(server.registers[server.base+11]/10000*5000 for server in (primary,battery))
        discharge_sum=sum(server.registers[server.base+10]/10000*5000 for server in (primary,battery))
        assert charge_sum<=charge and discharge_sum<=discharge
        assert abs(charge_sum-charge)<1 and abs(discharge_sum-discharge)<1


def test_reductions_are_confirmed_before_a_larger_allocation_to_another_storage():
    with site(True) as (driver,primary,_pv,battery):
        primary.registers[primary.base+6]=5000
        battery.registers[battery.base+6]=5000
        command=BatteryCommand('grid_charge',4000,min_soc=20,max_soc=90)
        driver.apply(command,{})
        events=[]
        for device in driver.site.batteries:
            original=device.driver._apply_single
            def apply(value,states,original=original,name=device.name):
                events.append((name,value.charge_w))
                return original(value,states)
            device.driver._apply_single=apply
        primary.registers[primary.base+6]=8500
        driver.apply(command,{})
        assert events[0][0]=='primary'
        assert sum(value for _,value in events)<=4000.000001


def test_a_device_reset_reestablishes_neutral_limits_before_resuming_the_pool():
    with site(True) as (driver,primary,_pv,battery):
        command=BatteryCommand('grid_charge',3000,min_soc=20,max_soc=90)
        driver.apply(command,{})
        primary.registers[primary.base+3]=0  # Device reboot/expired external lease.
        primary.writes.clear();battery.writes.clear()
        driver.apply(command,{})
        assert (primary.base+10,[0,0]) in primary.writes
        assert (battery.base+10,[0,0]) in battery.writes


def test_pv_start_requires_enough_eligible_storage_power_before_any_enable():
    with site(True) as (driver,primary,pv,battery):
        primary.registers[primary.base+6]=5000
        battery.registers[battery.base+6]=5500
        with pytest.raises(ModbusError):
            driver.apply(BatteryCommand('limits',discharge_w=8000,min_soc=50,max_soc=90,
                                        net_demand_w=6000,required_discharge_w=6000),{})
        assert not primary.writes and not battery.writes and not pv.writes


def test_pv_support_uses_a_shared_deficit_instead_of_allowing_each_battery_the_whole_load():
    with site(True) as (driver,primary,_pv,battery):
        driver.apply(BatteryCommand('limits',discharge_w=8000,min_soc=20,max_soc=90,
                                    net_demand_w=880,required_discharge_w=880),{})
        output=sum(server.registers[server.base+10]/10000*5000 for server in (primary,battery))
        assert 879<=output<=880


def test_forced_export_requires_opt_in_and_does_not_charge_any_battery():
    from custom_components.eos_energiezentrale.energy.contracts import UnsupportedFeature
    with site(True) as (driver,primary,_pv,battery):
        with pytest.raises(UnsupportedFeature):
            driver.apply(BatteryCommand('grid_discharge',discharge_w=2000,min_soc=20,max_soc=90),{})
        assert not primary.writes and not battery.writes
    with site(True,export=True) as (driver,primary,pv,battery):
        driver.apply(BatteryCommand('grid_discharge',discharge_w=2000,min_soc=20,max_soc=90),{})
        assert primary.registers[primary.base+11]>32767
        assert battery.registers[battery.base+11]>32767
        assert not pv.writes


def test_release_and_write_failure_attempt_all_storage_units_but_never_pv_units():
    with site(True) as (driver,primary,pv,battery):
        driver.apply(BatteryCommand('grid_charge',3000,min_soc=20,max_soc=90),{})
        assert primary.registers[primary.base+3]==battery.registers[battery.base+3]==3
        battery.reject=True
        with pytest.raises(ModbusError): driver.release({})
        assert primary.registers[primary.base+3]==0
        assert not pv.writes
        battery.reject=False
        driver.release({})
        assert battery.registers[battery.base+3]==0


def test_partial_dispatch_failure_releases_every_battery_and_recovers():
    with site(True) as (driver,primary,pv,battery):
        secondary=driver.site.batteries[1].driver
        original=secondary._apply_single
        def fail(command,states):
            if command.charge_w:
                assert primary.registers[primary.base+11]>0
                raise ModbusError('Unconfirmed secondary command')
            return original(command,states)
        secondary._apply_single=fail
        command=BatteryCommand('grid_charge',3000,min_soc=20,max_soc=90)
        with pytest.raises(ModbusError,match='Unconfirmed secondary command'):
            driver.apply(command,{})
        assert primary.registers[primary.base+3]==battery.registers[battery.base+3]==0
        assert driver.site.direction is None and not driver.site.targets
        assert not pv.writes
        secondary._apply_single=original
        driver.apply(command,{})
        assert primary.registers[primary.base+3]==battery.registers[battery.base+3]==3


def test_missing_group_context_is_rejected_before_any_connection():
    with site(True) as (driver,_primary,_pv,_battery),patch('socket.create_connection') as connect:
        with pytest.raises(ValueError): driver.apply(BatteryCommand('limits',1000,1000),{})
        with pytest.raises(ValueError): driver.apply(BatteryCommand('limits',1000,1000,20,90),{})
        with pytest.raises(PluginContractError):
            driver.apply(BatteryCommand('limits',1000,min_soc=True,max_soc=90),{})
        connect.assert_not_called()


def test_group_controller_passes_individual_bounds_and_requests_combined_eos_capacity():
    from test_requirements import ControllerRequirements
    fixture=ControllerRequirements();fixture.setUp()
    try:
        with site(True) as (driver,_primary,_pv,_battery):
            fixture.config.battery=driver
            fixture.config.options.update(pv_entity='',grid_entity='',house_entity='')
            fixture.app.tick(NOW,0)
            fixture.eos.set_battery_limits.assert_called_with('battery1',20,100,30000,
                fixture.config.options['battery_charge_w'],fixture.config.options['battery_discharge_w'])
            snapshot=fixture.app.snapshot(NOW)
            assert snapshot['battery_group']['capacity_wh']==30000
            assert snapshot['battery_limits']['confirmed'] is True
            assert snapshot['live']['solar']==5200
            command=fixture.app.battery_dispatch(BatteryCommand('limits',2000,2000),
                                                {'grid':100,'battery_discharge':500,'battery_charge':0})
            assert (command.min_soc,command.max_soc,command.net_demand_w)==(20,100,600)
            supported=fixture.app.battery_dispatch(command,{'grid':0,'battery_discharge':500,'battery_charge':0},50)
            assert supported.min_soc==50
    finally:
        fixture.doCleanups()


def test_accounting_uses_the_configured_total_capacity_even_before_eos_sync():
    from custom_components.eos_energiezentrale.energy.accounting import Accounting
    from test_energy import temporary_project_directory
    from zoneinfo import ZoneInfo
    with temporary_project_directory() as directory:
        ledger=Accounting(directory,ZoneInfo('Europe/Berlin'))
        ledger.eos_battery={'capacity_wh':10000,'charge_efficiency':.95,'discharge_efficiency':.95}
        ledger.capacity_override=30000
        assert ledger.effective()['capacity_wh']==30000
        ledger.configure({'efficiency_source':'manual','capacity_wh':10000})
        assert ledger.effective()['capacity_wh']==30000


@pytest.mark.parametrize('entries,primary_size',[
    ({'roof':{'host':'main.local'}},0),
    ({'primary':{'host':'pv.local'}},0),
    ({'roof':{'host':'pv.local','battery':'false'}},0),
    ({'roof':{'host':'pv.local','capacity_wh':10000}},0),
    ({'garage':{'host':'battery.local','battery':True}},10000),
    ({'garage':{'host':'battery.local','battery':True,'capacity_wh':20000}},0),
    ({'roof':{'host':'pv.local','unknown':True}},0),
])
def test_bad_site_configuration_fails_without_network_access(entries,primary_size):
    with patch('socket.create_connection') as connect,pytest.raises(ValueError):
        BATTERY_DRIVERS['fronius_modbus'](None,{'host':'main.local','battery_capacity_wh':primary_size,
                                              'additional_inverters':entries})
    connect.assert_not_called()

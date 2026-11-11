"""Deye register profile and remote control over a real local TCP gateway."""
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from custom_components.eos_energiezentrale.energy.drivers import BATTERY_DRIVERS,INVERTER_DRIVERS
from custom_components.eos_energiezentrale.energy._modbus_tcp import ModbusError
from custom_components.eos_energiezentrale.energy.contracts import UnsupportedFeature
from custom_components.eos_energiezentrale.energy.domain import BatteryCommand
from custom_components.eos_energiezentrale.energy.devices import DeviceSite
from test_energy import NOW
from test_fronius_modbus import inverter


def put32(server,low,high,value):
    server.registers[low]=value & 65535
    server.registers[high]=(value>>16) & 65535


@contextmanager
def deye(enabled=True,export=False,grid=True):
    with inverter() as (_,server):
        server.registers={address:0 for address in range(0,1122)}
        server.registers.update({0:0x0500,1:1,20:120000 & 65535,21:120000>>16,22:0x0203,
            98:1,108:240,109:240,212:100,213:100,587:5200,588:60,590:600,
            672:2000,673:3000})
        put32(server,625,690,1200)
        put32(server,636,694,5400)
        put32(server,653,659,6600)
        params={'host':'127.0.0.1','port':server.server_address[1],
                'remote_control':enabled,'grid_discharge_supported':export,'grid_meter_enabled':grid}
        driver=BATTERY_DRIVERS['deye_modbus'](None,params)
        yield driver,server,params


def test_direct_read_includes_soc_battery_pv_grid_ac_and_native_house_without_ha_sensors():
    with deye() as (driver,server,_):
        value=driver.read({},NOW)
        assert (value.soc,value.charge,value.discharge)==(60,0,600)
        assert {key:item.value for key,item in value.measurements.items()}=={
            'solar':5000,'grid':1200,'inverter_ac':5400,'house_total':6600}
        assert value.soc_sample==NOW and all(item.sample==NOW for item in value.measurements.values())
        assert not any(driver.ids.values()) and not server.writes


def test_signed_32_bit_grid_ac_and_large_house_values_are_not_truncated():
    with deye() as (driver,server,_):
        server.registers[590]=(-1500)&65535
        put32(server,625,690,-72000)
        put32(server,636,694,-600)
        put32(server,653,659,85000)
        value=driver.read({},NOW)
        assert (value.charge,value.discharge)==(1500,0)
        assert value.measurements['grid'].value==-72000
        assert value.measurements['inverter_ac'].value==-600
        assert value.measurements['house_total'].value==85000


@pytest.mark.parametrize('address,value,key',[(588,65535,'soc'),(587,0,'soc'),(672,65535,'solar')])
def test_missing_measurements_are_not_reported_as_zero(address,value,key):
    with deye() as (driver,server,_):
        server.registers[address]=value
        reading=driver.read({},NOW)
        assert (reading.soc if key=='soc' else reading.measurements[key].value) is None
        assert reading.measurements['grid'].value==1200


@pytest.mark.parametrize('address,value',[(0,0x0600),(20,0),(22,0x0403),(24,2),(1,2)])
def test_wrong_profile_is_rejected_before_any_write(address,value):
    with deye() as (driver,server,_):
        server.registers[address]=value
        with pytest.raises(ModbusError): driver.apply(BatteryCommand('grid_charge',1200),{})
        assert not server.writes


@pytest.mark.parametrize('mode,charge,discharge,expected',[
    ('grid_charge',2400,0,-200),('grid_discharge',0,2400,200),
    ('limits',3000,3000,150),('block_discharge',3000,3000,0),('limits',0,0,0)])
def test_remote_power_is_scaled_signed_confirmed_and_activated_last(mode,charge,discharge,expected):
    with deye(export=True) as (driver,server,_):
        driver.apply(BatteryCommand(mode,charge,discharge),{})
        assert server.registers[1109]==expected & 65535
        assert (server.registers[1100],server.registers[1101],server.registers[1104],server.registers[1105])==(1,300,1,2)
        assert server.writes[-1]==(1100,[1])
        assert server.writes.index((1101,[300]))<server.writes.index((1100,[1]))
        # No battery type, current, ToU, sell, protection or grid-code settings.
        assert {address for address,_ in server.writes}<={1100,1101,1104,1105,1109}
        driver.release({})
        assert server.registers[1100]==0 and not driver.owns_remote


def test_local_feedback_follows_export_and_quantises_towards_zero():
    with deye() as (driver,server,_):
        put32(server,625,690,-3000)
        driver.apply(BatteryCommand('limits',3000,3000),{})
        assert server.registers[1109]==(-200)&65535  # 600 W battery - 3000 W grid.
        driver.apply(BatteryCommand('grid_charge',1000),{})
        assert server.registers[1109]==(-83)&65535  # 996 W, never exceeds 1000 W.


def test_lease_is_renewed_on_unchanged_commands_and_reestablished_after_expiry():
    with deye() as (driver,server,_):
        command=BatteryCommand('grid_charge',2400)
        driver.apply(command,{})
        server.writes.clear()
        driver.apply(command,{})
        assert server.writes==[(1101,[300]),(1109,[(-200)&65535]),(1100,[1])]
        server.registers[1100]=0  # Firmware watchdog expired while HA was stopped.
        server.registers[1104]=0
        driver.apply(command,{})
        assert server.registers[1104]==1 and server.registers[1100]==1


def test_current_soc_and_bms_caps_limit_commands_and_report_available_power():
    with deye(export=True) as (driver,server,_):
        assert driver.power_limits({})==(5200,5200)
        server.registers[212]=20
        driver.apply(BatteryCommand('grid_charge',5000),{})
        assert server.registers[1109]==(-86)&65535  # floor(1040 W / 12 W).
        server.registers[588]=90
        driver.apply(BatteryCommand('grid_charge',5000,max_soc=90),{})
        assert server.registers[1109]==0
        server.registers[588]=50
        driver.apply(BatteryCommand('grid_discharge',discharge_w=5000,min_soc=50),{})
        assert server.registers[1109]==0
        server.registers[108]=65535
        with pytest.raises(ModbusError): driver.power_limits({})


def test_unsupported_or_foreign_remote_mode_and_export_opt_in_fail_without_writes():
    with deye() as (driver,server,_):
        for mode in (1,2,65535):
            server.registers[1100]=mode
            with pytest.raises(ModbusError): driver.apply(BatteryCommand('grid_charge',1000),{})
            with pytest.raises(ModbusError): driver.release({})
        with pytest.raises(UnsupportedFeature): driver.apply(BatteryCommand('grid_discharge',discharge_w=1000),{})
        assert not server.writes


@pytest.mark.parametrize('register,value',[(1104,2),(1101,65535)])
def test_changed_owned_remote_configuration_returns_to_auto_and_reports_conflict(register,value):
    with deye() as (driver,server,_):
        driver.apply(BatteryCommand('grid_charge',1200),{})
        server.registers[register]=value
        with pytest.raises(ModbusError,match='changed outside'):
            driver.apply(BatteryCommand('grid_charge',1200),{})
        assert server.registers[1100]==0


def test_lost_activation_acknowledgement_releases_the_partially_applied_command():
    with deye() as (driver,server,_):
        write=driver.client.write
        def lost_ack(address,values):
            write(address,values)
            if address==1100 and values==[1]: raise ModbusError('Lost activation acknowledgement')
        with patch.object(driver.client,'write',side_effect=lost_ack):
            with pytest.raises(ModbusError,match='Lost activation'):
                driver.apply(BatteryCommand('grid_charge',1200),{})
        assert server.registers[1100]==0 and not driver.owns_remote
        assert server.writes[-1]==(1100,[0])


def test_device_no_battery_mode_keeps_generation_but_suppresses_storage_readings():
    with deye() as (driver,server,_):
        server.registers[111]=2
        value=driver.read({},NOW)
        assert (value.soc,value.charge,value.discharge)==(None,None,None)
        assert value.measurements['solar'].value==5000
        with pytest.raises(ModbusError): driver.power_limits({})
        assert not server.writes


def test_unconfirmed_command_is_not_successful_and_failed_release_remains_pending():
    with deye() as (driver,server,_):
        server.ignore_writes=True
        with pytest.raises(ModbusError): driver.apply(BatteryCommand('grid_charge',1200),{})
        assert server.registers[1100]==0
        server.ignore_writes=False
        driver.apply(BatteryCommand('grid_charge',1200),{})
        server.ignore_writes=True
        with pytest.raises(ModbusError): driver.release({})
        assert driver.owns_remote
        server.ignore_writes=False
        driver.release({})
        assert not driver.owns_remote


def test_read_only_configuration_never_touches_remote_registers_and_pv_plugin_has_no_commands():
    with deye(enabled=False) as (driver,server,params):
        driver.read({},NOW)
        driver.release({})
        with pytest.raises(UnsupportedFeature): driver.apply(BatteryCommand('limits'),{})
        assert not server.writes
        assert all(address<1100 for function,_,address,_ in server.requests if function==3)
        pv=INVERTER_DRIVERS['deye_modbus'](None,{key:value for key,value in params.items()
            if key not in {'remote_control','grid_discharge_supported'}})
        server.registers[587]=0
        assert pv.read({},NOW).measurements['solar'].value==5000
        assert not hasattr(pv,'apply') and not server.writes


def test_common_demand_can_be_provided_by_another_plugin_and_neutral_needs_no_meter():
    with deye(grid=False) as (driver,server,_):
        driver.apply(BatteryCommand('limits'),{})
        driver.apply(BatteryCommand('limits',discharge_w=1200,min_soc=20,max_soc=90,net_demand_w=900),{})
        assert server.registers[1109]==75
        assert 'grid' not in driver.measurement_keys
        with pytest.raises(ModbusError): driver.apply(BatteryCommand('limits',discharge_w=1200),{})
        assert server.registers[1100]==0


def test_required_pv_support_is_checked_against_fresh_individual_soc_and_power():
    with deye() as (driver,server,_):
        server.registers[588]=50
        with pytest.raises(ModbusError,match='Insufficient'):
            driver.apply(BatteryCommand('limits',discharge_w=4000,min_soc=50,max_soc=90,
                net_demand_w=880,required_discharge_w=880),{})
        assert not server.writes
        server.registers[588]=60
        driver.apply(BatteryCommand('limits',discharge_w=4000,min_soc=50,max_soc=90,
            net_demand_w=880,required_discharge_w=880),{})
        assert server.registers[1109]>=73


def test_single_device_manager_preserves_daily_soc_context_for_deye():
    from test_requirements import ControllerRequirements
    fixture=ControllerRequirements();fixture.setUp()
    try:
        with deye() as (driver,_server,params):
            site=DeviceSite(None,[{'id':'deye','name':'Deye','kind':'battery','plugin':'deye_modbus',
                'parameters':params,'charge_w':5000,'discharge_w':5000,'capacity_wh':10000,'grid_source':True}])
            fixture.config.battery=site
            command=fixture.app.battery_dispatch(BatteryCommand('limits',2000,2000),
                {'grid':100,'battery_discharge':500,'battery_charge':0},50)
            assert (command.min_soc,command.max_soc,command.net_demand_w)==(50,100,600)
            assert fixture.app.battery_group_capacity() is None
    finally: fixture.doCleanups()


def test_deye_and_fronius_can_share_the_device_group_and_a_single_grid_meter():
    with deye() as (_,deye_server,deye_params),inverter() as (_,fronius):
        rows=[{'id':'deye','name':'Deye','kind':'battery','plugin':'deye_modbus','parameters':deye_params,
               'capacity_wh':10000,'charge_w':5000,'discharge_w':5000},
              {'id':'fronius','name':'Fronius','kind':'battery','plugin':'fronius_modbus',
               'parameters':{'host':'127.0.0.1','port':fronius.server_address[1]},'grid_source':True,
               'capacity_wh':10000,'charge_w':5000,'discharge_w':5000}]
        site=DeviceSite(None,rows)
        value=site.read({},NOW)
        assert value.soc==57.5 and value.charge==1500 and value.discharge==600
        assert value.measurements['solar'].value==7000
        assert value.measurements['grid'].value==1000
        assert value.measurements['house_total'].value==6900
        site.apply(BatteryCommand('limits',discharge_w=1800,min_soc=20,max_soc=90,net_demand_w=1800),{})
        assert deye_server.registers[1109]==80  # Its allocated share: 960 W.
        assert fronius.registers[fronius.base+10]==1680  # Other share: 840 W.
        site.release({})
        assert deye_server.registers[1100]==0 and fronius.registers[fronius.base+3]==0


@pytest.mark.parametrize('params',[{'host':'http://gateway'},{'host':'gateway.local','port':0},
    {'host':'gateway.local','unit_id':1.5},{'host':'gateway.local','minimum_soc':101},
    {'host':'gateway.local','remote_control':'true'}])
def test_invalid_parameters_fail_without_network_access(params):
    with patch('socket.create_connection') as connect,pytest.raises(ValueError):
        BATTERY_DRIVERS['deye_modbus'](None,params)
    connect.assert_not_called()

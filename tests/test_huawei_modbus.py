"""Huawei SUN2000 / LUNA2000 register profile and control over a local Modbus TCP emulator."""
from contextlib import contextmanager
from unittest.mock import patch

import pytest

from custom_components.eos_energiezentrale.energy import _modbus_tcp
from custom_components.eos_energiezentrale.energy.drivers import BATTERY_DRIVERS,INVERTER_DRIVERS
from custom_components.eos_energiezentrale.energy._modbus_tcp import ModbusError
from custom_components.eos_energiezentrale.energy.contracts import UnsupportedFeature
from custom_components.eos_energiezentrale.energy.domain import BatteryCommand
from custom_components.eos_energiezentrale.energy.plugins import huawei_modbus
from test_energy import NOW
from test_fronius_modbus import inverter


def put32(server,address,value):
    value&=0xFFFFFFFF
    server.registers[address]=value>>16
    server.registers[address+1]=value & 65535


def get32(server,address):
    return server.registers[address]<<16 | server.registers[address+1]


def load(server):
    server.registers={}
    name=b'SUN2000-10KTL-M1'.ljust(30,b'\0')
    server.registers.update({30000+index:int.from_bytes(name[2*index:2*index+2],'big') for index in range(15)})
    server.registers[30071]=2
    put32(server,30073,10000)
    # PV1 400.0 V x 5.00 A, PV2 350.0 V x 10.00 A.
    server.registers.update({32016:4000,32017:500,32018:3500,32019:1000})
    put32(server,32080,4000)
    server.registers[37100]=1
    put32(server,37113,-1200)  # The meter reports import as negative.
    server.registers[37760]=605
    server.registers[37762]=2
    put32(server,37765,-1500)  # Negative storage power discharges.
    put32(server,37046,5000)
    put32(server,37048,4500)
    server.registers[47000]=2
    put32(server,47075,5000)
    put32(server,47077,4500)
    server.registers.update({47083:0,47086:2,47087:1,47100:0,47246:0})
    put32(server,47247,0)
    put32(server,47249,0)


@contextmanager
def huawei(enabled=True,export=False,grid=True,invert=False):
    with inverter() as (_,server),patch.object(huawei_modbus,'CONNECT_DELAY_S',0):
        load(server)
        params={'host':'127.0.0.1','port':server.server_address[1],'remote_control':enabled,
                'grid_discharge_supported':export,'grid_meter_enabled':grid,'grid_meter_invert':invert}
        driver=BATTERY_DRIVERS['huawei_modbus'](None,params)
        yield driver,server,params


def written(server):
    return {address for address,_ in server.writes}


def test_direct_read_includes_soc_battery_pv_grid_ac_and_house_without_ha_sensors():
    with huawei() as (driver,server,_):
        value=driver.read({},NOW)
        assert (value.soc,value.charge,value.discharge)==(60.5,0,1500)
        assert {key:item.value for key,item in value.measurements.items()}=={
            'solar':5500,'grid':1200,'inverter_ac':4000,'house_total':5200}
        assert value.soc_sample==NOW and all(item.sample==NOW for item in value.measurements.values())
        assert not any(driver.ids.values()) and not server.writes


def test_charging_power_export_and_inverted_meter_keep_canonical_signs():
    with huawei() as (driver,server,_):
        put32(server,37765,2000)
        put32(server,37113,800)
        put32(server,32080,-300)
        value=driver.read({},NOW)
        assert (value.charge,value.discharge)==(2000,0)
        assert value.measurements['grid'].value==-800
        assert value.measurements['inverter_ac'].value==-300
    with huawei(invert=True) as (driver,_,_params):
        assert driver.read({},NOW).measurements['grid'].value==-1200


@pytest.mark.parametrize('status',[0,3])
def test_offline_or_faulted_storage_is_not_reported_while_generation_stays(status):
    with huawei() as (driver,server,_):
        server.registers[37762]=status
        value=driver.read({},NOW)
        assert (value.soc,value.charge,value.discharge)==(None,None,None)
        assert value.measurements['solar'].value==5500
        assert driver._source_problems['battery_soc']['address']==37762


def test_offline_meter_hides_grid_and_house_but_keeps_battery():
    with huawei() as (driver,server,_):
        server.registers[37100]=0
        value=driver.read({},NOW)
        assert value.measurements['grid'].value is None and value.measurements['house_total'].value is None
        assert value.soc==60.5 and value.measurements['solar'].value==5500
    with huawei(grid=False) as (driver,_,_params):
        assert 'grid' not in driver.read({},NOW).measurements and 'grid' not in driver.measurement_keys


def test_rejected_meter_request_is_a_partial_failure():
    with huawei() as (driver,_,_params):
        with patch.object(driver.connection,'meter',side_effect=ModbusError('Illegal address',exception_code=2)):
            value=driver.read({},NOW)
        assert value.measurements['grid'].value is None and value.soc==60.5
        assert driver._source_problems['grid']['address']==37100


def test_device_site_reads_huawei_as_grid_source():
    from custom_components.eos_energiezentrale.energy.devices import DeviceSite
    with huawei() as (_,_server,params):
        site=DeviceSite(None,[{'id':'huawei','name':'Huawei','kind':'battery','plugin':'huawei_modbus',
            'parameters':params,'charge_w':5000,'discharge_w':4500,'capacity_wh':10000,'grid_source':True}])
        value=site.read({},NOW)
        assert value.soc==60.5 and value.measurements['grid'].value==1200


@pytest.mark.parametrize('address,value',[(30000,0x4142),(30071,0),(30073,0),(47000,0)])
def test_wrong_device_or_missing_luna2000_is_rejected_before_any_write(address,value):
    with huawei() as (driver,server,_):
        if address==30073: put32(server,address,value)
        else: server.registers[address]=value
        with pytest.raises(ModbusError): driver.apply(BatteryCommand('limits',1000,1000),{})
        assert not server.writes


def test_pv_variant_reads_an_inverter_without_battery_and_has_no_commands():
    with huawei(enabled=False) as (_,server,params):
        server.registers[47000]=0
        pv=INVERTER_DRIVERS['huawei_modbus'](None,{key:value for key,value in params.items()
            if key not in {'remote_control','grid_discharge_supported'}})
        value=pv.read({},NOW)
        assert value.measurements['solar'].value==5500 and value.measurements['house_total'].value==5200
        assert not hasattr(pv,'apply') and not server.writes
        assert all(address<37700 for function,_,address,_ in server.requests if function==3)


def test_identity_is_read_once_per_connection():
    with huawei() as (driver,server,_):
        driver.read({},NOW)
        driver.read({},NOW)
        assert sum(1 for _,_,address,_ in server.requests if address==30000)==1
        driver.client.close()
        driver.read({},NOW)
        assert sum(1 for _,_,address,_ in server.requests if address==30000)==2


def test_new_connections_wait_before_the_first_request():
    with inverter() as (_,server),patch.object(_modbus_tcp,'sleep') as sleep:
        load(server)
        driver=BATTERY_DRIVERS['huawei_modbus'](None,{'host':'127.0.0.1','port':server.server_address[1]})
        driver.read({},NOW)
        driver.read({},NOW)
        sleep.assert_called_once_with(1.0)


@pytest.mark.parametrize('mode,charge,discharge,expected',[
    ('limits',3000,2000,(3000,2000)),('limits',999999,1234.9,(5000,1234)),
    ('block_discharge',3000,3000,(3000,0)),('limits',0,0,(0,0))])
def test_limits_set_maximum_powers_only(mode,charge,discharge,expected):
    with huawei() as (driver,server,_):
        driver.apply(BatteryCommand(mode,charge,discharge),{})
        assert (get32(server,47075),get32(server,47077))==expected
        assert written(server)<={47075,47077} and server.registers[47100]==0


def test_unchanged_limits_are_not_written_again():
    with huawei() as (driver,server,_):
        command=BatteryCommand('limits',3000,2000)
        driver.apply(command,{})
        server.writes.clear()
        driver.apply(command,{})
        assert not server.writes


def test_grid_charge_uses_a_renewed_forcible_period_and_starts_last():
    with huawei() as (driver,server,_):
        command=BatteryCommand('grid_charge',2500)
        driver.apply(command,{})
        assert server.registers[47100]==1 and server.registers[47083]==5 and server.registers[47246]==0
        assert get32(server,47247)==2500 and get32(server,47077)==0
        assert server.writes[-1]==(47100,[1])
        server.writes.clear()
        driver.apply(command,{})
        assert server.writes==[(47083,[5]),(47100,[1])]
        driver.apply(BatteryCommand('limits',3000,3000),{})
        assert server.registers[47100]==0 and not driver.owns_forcible


def test_grid_charge_requires_the_inverter_grid_charge_function():
    with huawei() as (driver,server,_):
        server.registers[47087]=0
        with pytest.raises(ModbusError,match='grid'): driver.apply(BatteryCommand('grid_charge',2500),{})
        assert not server.writes


def test_grid_discharge_needs_opt_in_and_uses_forcible_discharge():
    with huawei() as (driver,server,_):
        with pytest.raises(UnsupportedFeature): driver.apply(BatteryCommand('grid_discharge',discharge_w=2000),{})
        assert not server.writes
    with huawei(export=True) as (driver,server,_):
        driver.apply(BatteryCommand('grid_discharge',discharge_w=9000),{})
        assert server.registers[47100]==2 and get32(server,47249)==4500 and get32(server,47075)==0


@pytest.mark.parametrize('register,value',[(47086,5),(47100,1),(47100,7)])
def test_foreign_working_mode_or_forcible_command_fails_without_writes(register,value):
    with huawei() as (driver,server,_):
        server.registers[register]=value
        with pytest.raises(ModbusError): driver.apply(BatteryCommand('limits',1000,1000),{})
        assert not server.writes
        driver.release({})
        assert not server.writes and server.registers[register]==value


def test_release_restores_battery_maxima_after_control():
    with huawei() as (driver,server,_):
        driver.apply(BatteryCommand('grid_charge',2000),{})
        driver.release({})
        assert server.registers[47100]==0
        assert (get32(server,47075),get32(server,47077))==(5000,4500)
        server.writes.clear()
        put32(server,47075,3000)  # A setting chosen elsewhere is kept.
        driver.release({})
        assert not server.writes


def test_release_after_restart_restores_a_leftover_zero_limit():
    with huawei() as (driver,server,_):
        put32(server,47077,0)
        driver.release({})
        assert get32(server,47077)==4500 and get32(server,47075)==5000


def test_lost_start_acknowledgement_stops_the_forcible_command():
    with huawei() as (driver,server,_):
        write=driver.client.write
        def lost_ack(address,values):
            write(address,values)
            if address==47100 and values==[1]: raise ModbusError('Lost start acknowledgement')
        with patch.object(driver.client,'write',side_effect=lost_ack):
            with pytest.raises(ModbusError,match='Lost start'):
                driver.apply(BatteryCommand('grid_charge',1200),{})
        assert server.registers[47100]==0 and not driver.owns_forcible
        assert server.writes[-1]==(47100,[0])


def test_unconfirmed_writes_are_not_successful():
    with huawei() as (driver,server,_):
        server.ignore_writes=True
        with pytest.raises(ModbusError): driver.apply(BatteryCommand('limits',1000,1000),{})
        assert get32(server,47075)==5000


def test_missing_battery_telemetry_blocks_commands():
    with huawei() as (driver,server,_):
        server.registers[37762]=3
        with pytest.raises(ModbusError,match='telemetry'): driver.apply(BatteryCommand('limits',1000,1000),{})
        assert not server.writes


def test_power_limits_come_from_the_battery():
    with huawei() as (driver,server,_):
        assert driver.power_limits({})==(5000,4500)
        put32(server,37048,0)
        with pytest.raises(ModbusError): driver.power_limits({})


def test_read_only_configuration_never_writes():
    with huawei(enabled=False) as (driver,server,_):
        driver.read({},NOW)
        driver.release({})
        with pytest.raises(UnsupportedFeature): driver.apply(BatteryCommand('limits'),{})
        assert not server.writes


@pytest.mark.parametrize('params',[{'host':'http://dongle'},{'host':'dongle.local','port':0},
    {'host':'dongle.local','unit_id':0},{'host':'dongle.local','unit_id':1.5},
    {'host':'dongle.local','remote_control':'true'}])
def test_invalid_parameters_fail_without_network_access(params):
    with patch('socket.create_connection') as connect,pytest.raises(ValueError):
        BATTERY_DRIVERS['huawei_modbus'](None,params)
    connect.assert_not_called()

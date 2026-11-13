"""Direct GX protocol behavior against a fragmented Modbus TCP server."""
from contextlib import contextmanager
import struct
from unittest.mock import patch

import pytest

from custom_components.eos_energiezentrale.energy._modbus_tcp import ModbusError
from custom_components.eos_energiezentrale.energy.contracts import UnsupportedFeature
from custom_components.eos_energiezentrale.energy.devices import DeviceSite
from custom_components.eos_energiezentrale.energy.domain import BatteryCommand
from custom_components.eos_energiezentrale.energy.drivers import BATTERY_DRIVERS
from test_energy import NOW
from test_fronius_modbus import inverter


@contextmanager
def gx(**options):
    with inverter() as (_,server):
        server.registers={800+i:value for i,value in enumerate(struct.unpack('>6H',b'c0619ab01234'))}
        server.registers.update({834:0x0350,840:500,841:0,842:0,843:60,850:2000,826:1,
            2704:450,2705:60,2716:0,2717:50,2900:10,2901:200,2902:1,5423:0})
        for address in range(808,823):server.registers[address]=0
        server.registers.update({808:400,811:600,817:1000,818:2000,819:3000,820:1000})
        server.meters[100]=server.registers
        params={'host':'127.0.0.1','port':server.server_address[1],'control_enabled':True,
            'release_charge_current':60,'release_discharge_power':4500,
            'charge_efficiency':1,'discharge_efficiency':1,**options}
        driver=BATTERY_DRIVERS['victron_modbus'](None,params)
        yield driver,server,params


def command(mode='limits',charge=5000,discharge=3000,**extra):
    return BatteryCommand(mode,charge,discharge,min_soc=20,max_soc=90,**extra)


def target(server):
    raw=server.registers[2716]<<16|server.registers[2717]
    return raw-2**32 if raw>=2**31 else raw


def test_reads_system_totals_signed_dc_power_and_configured_pv_without_entities():
    with gx(ac_pv_input_enabled=True,ac_pv_output_enabled=True) as (driver,server,_):
        server.registers[842]=(-1500)&65535
        server.registers[821]=(-300)&65535
        sample=driver.read({},NOW)
        assert (sample.soc,sample.charge,sample.discharge)==(60,0,1500)
        assert {key:item.value for key,item in sample.measurements.items()}=={'solar':3000,'grid':700,'house_total':6000}
        assert sample.soc_sample==NOW
        assert all(item.sample==NOW for item in sample.measurements.values())
        assert not any(driver.ids.values()) and not server.writes
        assert set(server.read_units)=={100}


def test_phase_and_source_selection_does_not_invent_missing_sources():
    with gx(phases='1',dc_pv_enabled=False,grid_meter_enabled=False) as (driver,server,_):
        sample=driver.read({},NOW)
        assert not sample.measurements
        assert not {'solar','grid','house_total'}&set(driver.measurement_keys)
        assert all(address not in (850,817,820) for _,_,address,_ in server.requests)
        # Even without publishing the common grid source, control uses its own meter.
        driver.apply(command('grid_charge',2000,0),{})
        assert target(server)==3000


def test_read_only_default_has_no_control_and_release_never_writes():
    with gx(control_enabled=False) as (driver,server,_):
        assert not driver.features.grid_charge and driver.power_limits({}) is None
        with pytest.raises(UnsupportedFeature):driver.apply(command(),{})
        driver.release({})
        assert not server.requests and not server.writes


@pytest.mark.parametrize('mode,charge,discharge,grid,battery,amps,outgoing,expected',[
    ('grid_charge',2000,0,1000,0,40,0,3000),
    ('limits',5000,3000,1000,0,100,300,0),
    ('block_discharge',5000,3000,1000,0,100,0,1000),
    ('grid_discharge',0,2000,1000,0,0,200,-1000),
    ('limits',2000,3000,-1200,0,40,300,0),
    ('limits',0,0,1000,-500,0,0,1500),
])
def test_mode_budgets_scaling_and_signed_32bit_setpoint(mode,charge,discharge,grid,battery,amps,outgoing,expected):
    with gx(grid_discharge_supported=True) as (driver,server,_):
        server.registers[820]=grid&65535;server.registers[842]=battery&65535
        driver.apply(command(mode,charge,discharge),{})
        assert server.registers[2705]==amps
        assert server.registers[2704]==outgoing
        assert target(server)==expected
        assert {address for address,_ in server.writes}<={2704,2705,2716}
        assert server.writes[-1][0]==2716 or expected==50
        before=list(server.writes)
        driver.apply(command(mode,charge,discharge),{})
        assert server.writes==before


def test_efficiencies_current_caps_and_voltage_are_used_before_rounding():
    with gx(charge_efficiency=.8,discharge_efficiency=.9,max_charge_current=35) as (driver,server,_):
        server.registers[840]=600;server.registers[842]=1000
        assert driver.power_limits({})==(2625,5000)
        assert driver.read({},NOW).charge==1250
        driver.apply(command('grid_charge',2500,0),{})
        assert server.registers[2705]==33  # 2475 W AC at 60 V / 0.8
        assert target(server)==2225  # pre-battery demand = 1000 - 1250


def test_soc_and_configured_limits_prevent_unsupported_battery_power():
    with gx(max_discharge_power=1500) as (driver,server,_):
        with pytest.raises(ValueError):driver.apply(command(required_discharge_w=2000),{})
        assert not server.writes
        server.registers[843]=20
        with pytest.raises(ValueError):driver.apply(command(required_discharge_w=1000),{})
        assert not server.writes
        server.registers[843]=90
        driver.apply(command('grid_charge',2000,0),{})
        assert server.registers[2705]==0 and target(server)==1000


@pytest.mark.parametrize('address,value',[(800,0),(834,0x0349),(840,0),(843,65535),(842,32767),(842,32766),
    (820,32768),(820,32766),(850,65535),(850,65534),(2902,3),(2900,9),(5423,1),(826,240)])
def test_invalid_telemetry_identity_or_control_state_rejects_all_new_writes(address,value):
    with gx() as (driver,server,_):
        server.registers[address]=value
        with pytest.raises(ModbusError):driver.apply(command(),{})
        assert not server.writes


def test_slow_snapshot_is_not_a_valid_control_basis():
    with gx() as (driver,server,_):
        with patch('custom_components.eos_energiezentrale.energy.plugins.victron_modbus.monotonic',side_effect=[0,11]):
            with pytest.raises(ModbusError):driver.apply(command(),{})
        assert not server.writes


def test_connection_errors_do_not_reuse_a_cached_reading_and_recovery_needs_no_restart():
    with gx() as (driver,server,_):
        assert driver.read({},NOW).soc==60
        server.reject=True
        with pytest.raises(ModbusError):driver.read({},NOW)
        with pytest.raises(ModbusError):driver.apply(command(),{})
        assert not server.writes
        server.reject=False;server.registers[843]=65
        assert driver.read({},NOW).soc==65


def test_forced_export_requires_separate_permission_before_any_io():
    with gx() as (driver,server,_):
        with pytest.raises(UnsupportedFeature):driver.apply(command('grid_discharge',0,2000),{})
        assert not server.requests and not server.writes


def test_unconfirmed_write_stops_before_the_next_limit_or_setpoint():
    with gx() as (driver,server,_):
        server.ignore_writes=True
        with pytest.raises(ModbusError):driver.apply(command('grid_charge',2000,0),{})
        assert server.writes==[(2705,[40])]


def test_release_restores_explicit_values_after_restart_without_battery_telemetry():
    with gx(release_charge_current=-1) as (_,server,params):
        server.registers.update({840:0,2705:0,2704:0,2717:3000})
        restarted=BATTERY_DRIVERS['victron_modbus'](None,params)
        restarted.release({})
        assert server.writes==[(2716,[0,50]),(2705,[65535]),(2704,[450])]
        assert not any(address==840 for _,_,address,_ in server.requests)
        server.ignore_writes=True
        server.registers[2717]=3000
        with pytest.raises(ModbusError):restarted.release({})


def test_direct_consumption_flows_through_device_manager_and_duplicate_gx_is_rejected():
    with gx() as (_,server,params):
        row={'id':'gx','name':'GX','kind':'battery','plugin':'victron_modbus','parameters':params,
             'capacity_wh':10000,'charge_w':5000,'discharge_w':5000,'grid_source':True}
        site=DeviceSite(None,[row])
        assert site.read({},NOW).measurements['house_total'].value==6000
        site.apply(command('grid_charge',2000,0),{})
        assert target(server)==3000
        with pytest.raises(ValueError):DeviceSite(None,[row,{**row,'id':'second'}])


@pytest.mark.parametrize('address,invalid,stage,count',[
    (800,0,'identity',6),(834,0x0349,'firmware',1),(840,0,'battery',4),
    (850,65535,'dc_pv',1),(820,32767,'grid',3),(817,65535,'consumption',3),
])
def test_device_read_failure_identifies_register_and_clears_after_recovery(address,invalid,stage,count):
    with gx(control_enabled=False) as (_,server,params):
        row={'id':'gx','name':'Private installation','kind':'battery','plugin':'victron_modbus',
             'parameters':params,'capacity_wh':32000,'charge_w':5000,'discharge_w':5000,'grid_source':True}
        site=DeviceSite(None,[row])
        original=server.registers[address];server.registers[address]=invalid
        sample=site.read({},NOW)
        assert sample.soc is None and sample.measurements['solar'].value is None
        failed=site.site_summary['devices'][0]
        assert not failed['available'] and failed['read_error']=='ModbusError'
        assert failed['read_diagnostics']['failure']=={'type':'ModbusError','stage':stage,
            'unit':100,'address':address,'count':count,'exception_code':None}
        server.registers[address]=original
        assert site.read({},NOW).soc==60
        recovered=site.site_summary['devices'][0]
        assert recovered['available'] and recovered['read_error'] is None
        assert recovered['read_diagnostics']['failure'] is None
        assert failed['read_diagnostics']['failure']['address']==address
        assert not server.writes


def test_modbus_rejection_and_transport_errors_are_diagnostic_without_raw_messages():
    with gx(control_enabled=False) as (driver,server,_):
        server.reject=True
        with pytest.raises(ModbusError):driver.read({},NOW)
        assert driver.read_diagnostics['failure']=={'type':'ModbusError','stage':'identity',
            'unit':100,'address':800,'count':6,'exception_code':3}
        with patch.object(driver.client,'read',side_effect=TimeoutError('private-host / private data')):
            with pytest.raises(TimeoutError):driver.read({},NOW)
        assert driver.read_diagnostics['failure']['type']=='TimeoutError'
        assert driver.read_diagnostics['failure']['exception_code'] is None
        assert 'private' not in repr(driver.read_diagnostics)
        server.reject=False
        assert driver.read({},NOW).soc==60
        assert driver.read_diagnostics['failure'] is None


def test_ac_output_pv_on_three_phases_does_not_require_dc_pv():
    with gx(control_enabled=False,dc_pv_enabled=False,ac_pv_output_enabled=True) as (driver,server,_):
        server.registers.update({850:65535,808:1000,809:2000,810:3000})
        sample=driver.read({},NOW)
        assert sample.soc==60 and sample.measurements['solar'].value==6000
        assert driver.read_diagnostics=={'phases':3,'control_enabled':False,'grid_meter_enabled':True,
            'read_consumption':True,'dc_pv_enabled':False,'ac_pv_input_enabled':False,
            'ac_pv_output_enabled':True,'failure':None}
        assert not any(address in (850,811) for _,_,address,_ in server.requests)
        assert not server.writes


def test_slow_read_reports_snapshot_timeout_without_blame_on_last_register():
    with gx(control_enabled=False) as (driver,_,_):
        with patch('custom_components.eos_energiezentrale.energy.plugins.victron_modbus.monotonic',side_effect=[0,11]):
            with pytest.raises(ModbusError):driver.read({},NOW)
        assert driver.read_diagnostics['failure']=={'type':'ModbusError','stage':'snapshot_timeout','exception_code':None}


@pytest.mark.parametrize('changes',[{'host':'http://gx.local'},{'port':1.5},{'phases':'2'},
    {'release_discharge_power':-1},{'release_discharge_power':4501},{'release_charge_current':None},
    {'charge_efficiency':0},{'max_charge_current':40000}])
def test_invalid_configuration_is_rejected_without_connecting(changes):
    with patch('socket.create_connection') as connect:
        with pytest.raises(ValueError):BATTERY_DRIVERS['victron_modbus'](None,{
            'host':'gx.local','control_enabled':True,'release_charge_current':60,'release_discharge_power':4500,**changes})
        connect.assert_not_called()

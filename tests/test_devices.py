"""Mixed plugin sites and guided device configuration without device I/O."""
from copy import deepcopy
from datetime import timedelta
import json
from unittest.mock import patch

import pytest

from custom_components.eos_energiezentrale.const import DEFAULTS
from custom_components.eos_energiezentrale.energy.contracts import InverterDriver, PluginContractError
from custom_components.eos_energiezentrale.energy.devices import DeviceSite, device_rows
from custom_components.eos_energiezentrale.energy.domain import BatteryCommand
from custom_components.eos_energiezentrale.energy.drivers import INVERTER_DRIVERS
from custom_components.eos_energiezentrale.energy.plugin_registry import validate_class
from test_energy import NOW
from test_fronius_modbus import inverter
from test_fronius_site import pv_only
from test_plugins import EntityHA, row


def storage():
    params={'soc':'sensor.soc','charge_power':'sensor.charge','discharge_power':'sensor.discharge',
            'mode':'input_select.mode','charge_limit':'input_number.charge','discharge_limit':'input_number.discharge',
            'solar':'sensor.pv','inverter_ac':'sensor.ac'}
    states={'sensor.soc':row(80,'%'),'sensor.charge':row(0,'W'),'sensor.discharge':row(0,'W'),
            'sensor.pv':row(1000,'W'),'sensor.ac':row(900,'W'),
            'input_select.mode':row('auto',options=['auto','limits','block_discharge','grid_charge','grid_discharge']),
            'input_number.charge':row(0,'W',min=0,max=2000,step=1),
            'input_number.discharge':row(0,'W',min=0,max=2000,step=1)}
    return {'id':'storage','name':'Other battery','kind':'battery','plugin':'generic','parameters':params,
            'capacity_wh':20000,'charge_w':2000,'discharge_w':2000},EntityHA(states)


def primary(server):
    return {'id':'main','name':'Main inverter','kind':'battery','plugin':'fronius_modbus',
            'parameters':{'host':'127.0.0.1','port':server.server_address[1]},
            'capacity_wh':10000,'charge_w':5000,'discharge_w':5000,'grid_source':True}


def test_mixed_storage_plugins_sum_capacity_soc_generation_and_house_balance():
    extra,ha=storage()
    with inverter() as (_,server):
        server.registers[server.base+6]=2000
        site=DeviceSite(ha,[primary(server),extra])
        value=site.read(ha.rows,NOW)
        assert value.soc==60
        assert value.measurements['solar'].value==3000
        assert value.measurements['grid'].value==1000
        assert value.measurements['house_total'].value==2400
        assert site.site_summary['capacity_wh']==30000
        assert {item['plugin']['identifier'] for item in site.site_summary['devices']}=={'fronius_modbus','generic'}
        assert site.site_summary['approximate']


def test_mixed_storage_dispatch_respects_individual_soc_and_hardware_caps():
    extra,ha=storage()
    extra['charge_w']=10000  # Actual HA helper advertises only 2 kW.
    with inverter() as (_,server),patch('custom_components.eos_energiezentrale.energy.devices.datetime') as clock:
        clock.now.return_value=NOW
        site=DeviceSite(ha,[primary(server),extra])
        site.apply(BatteryCommand('grid_charge',7000,min_soc=20,max_soc=90),ha.rows)
        assert float(ha.rows['input_number.charge']['state'])==2000
        assert server.registers[server.base+11]==10000
        server.registers[server.base+6]=9000
        site.apply(BatteryCommand('grid_charge',7000,min_soc=20,max_soc=90),ha.rows)
        assert server.registers[server.base+11]==0
        assert float(ha.rows['input_number.charge']['state'])==2000


def test_read_only_inverter_plugins_can_be_mixed_without_storage_or_writes():
    params={'solar':'sensor.pv','inverter_ac':'sensor.ac'}
    ha=EntityHA({'sensor.pv':row(1.2,'kW'),'sensor.ac':row(-.1,'kW')})
    with inverter() as (_,server):
        pv_only(server)
        rows=[{'id':'fronius','name':'Roof','kind':'inverter','plugin':'fronius_modbus',
               'parameters':{'host':'127.0.0.1','port':server.server_address[1]}},
              {'id':'other','name':'Other PV','kind':'inverter','plugin':'generic','parameters':params}]
        site=DeviceSite(ha,rows)
        value=site.read(ha.rows,NOW)
        assert value.measurements['solar'].value==2400
        assert not server.writes and not ha.commands
        assert site.site_summary['devices'][1]['ac']==-100
        assert 'grid' not in site.measurement_keys and 'house_total' not in site.measurement_keys
        assert all(unit!=200 for _,unit,_,_ in server.requests)
        site.release(ha.rows)
        assert not server.writes


def test_missing_pv_or_stale_ac_is_not_a_complete_site_sum():
    extra,ha=storage()
    with inverter() as (_,server):
        site=DeviceSite(ha,[primary(server),extra])
        ha.rows['sensor.pv']['state']='unavailable'
        ha.rows['sensor.ac']['last_reported']=(NOW-timedelta(seconds=46)).isoformat()
        value=site.read(ha.rows,NOW)
        assert value.measurements['solar'].value is None
        assert value.measurements['house_total'].value is None
        assert value.soc is not None and value.measurements['grid'].value==1000


def test_storage_failure_is_reported_and_releases_other_plugins():
    extra,ha=storage()
    with inverter() as (_,server),patch('custom_components.eos_energiezentrale.energy.devices.datetime') as clock:
        clock.now.return_value=NOW
        site=DeviceSite(ha,[primary(server),extra])
        site.apply(BatteryCommand('grid_charge',3000,min_soc=20,max_soc=90),ha.rows)
        ha.rows['sensor.soc']['state']='unavailable'
        with pytest.raises(ValueError,match='telemetry'):
            site.apply(BatteryCommand('grid_charge',3000,min_soc=20,max_soc=90),ha.rows)
        assert server.registers[server.base+3]==0
        assert ha.rows['input_select.mode']['state']=='auto'


def test_mixed_pool_rejects_pv_support_above_eligible_hardware_power():
    extra,ha=storage()
    with inverter() as (_,server),patch('custom_components.eos_energiezentrale.energy.devices.datetime') as clock:
        clock.now.return_value=NOW
        server.registers[server.base+6]=2000
        site=DeviceSite(ha,[primary(server),extra])
        with pytest.raises(ValueError,match='Insufficient storage support'):
            site.apply(BatteryCommand('limits',discharge_w=7000,min_soc=20,max_soc=90,
                net_demand_w=3000,required_discharge_w=3000),ha.rows)
        assert not server.writes and not ha.commands


def test_migration_preserves_each_legacy_fronius_and_its_own_parameters():
    params={'host':'main.local','battery_capacity_wh':10000,'grid_meter_host':'meter.local','grid_discharge_supported':True,
            'additional_inverters':{'pv':{'host':'pv.local'},
                'garage':{'host':'garage.local','battery':True,'capacity_wh':20000}}}
    options={**DEFAULTS,'battery_type':'fronius_modbus','battery_parameters':json.dumps(params)}
    before=deepcopy(options)
    rows=device_rows(options)
    assert [item['kind'] for item in rows]==['battery','inverter','battery']
    assert [item['parameters']['host'] for item in rows]==['main.local','pv.local','garage.local']
    assert rows[0]['parameters']['grid_meter_host']=='meter.local'
    assert rows[0]['grid_source'] and not rows[1]['grid_source']
    assert rows[2]['parameters']['grid_discharge_supported'] is True
    with patch('socket.create_connection') as connect: DeviceSite(None,rows)
    connect.assert_not_called()
    assert options==before


@pytest.mark.parametrize('change',[
    {'id':'bad id'}, {'plugin':'missing'}, {'kind':'wallbox'}, {'capacity_wh':True},
    {'parameters':{'additional_inverters':{'nested':{}}}}, {'grid_source':'yes'},
])
def test_invalid_device_configuration_is_rejected_before_network_access(change):
    extra,_=storage();extra.update(change)
    with patch('socket.create_connection') as connect,pytest.raises((ValueError,TypeError)):
        DeviceSite(None,[extra])
    connect.assert_not_called()


def test_duplicate_endpoints_and_shared_entities_are_rejected():
    extra,_=storage()
    other={**deepcopy(extra),'id':'second'}
    with pytest.raises(ValueError,match='shared'): DeviceSite(None,[extra,other])
    with inverter() as (_,server):
        first=primary(server);second={**deepcopy(first),'id':'second','grid_source':False}
        with pytest.raises(ValueError,match='Duplicate physical'): DeviceSite(None,[first,second])


def test_inverter_plugins_cannot_bypass_sanitising_and_never_expose_commands():
    factory=INVERTER_DRIVERS['generic']
    assert not hasattr(factory(None,{'solar':'sensor.pv','inverter_ac':'sensor.ac'}),'apply')
    class Unsafe(factory.plugin_class):
        def read(self,states,now): return None
    with pytest.raises(PluginContractError): validate_class(Unsafe)
    assert issubclass(factory.plugin_class,InverterDriver)

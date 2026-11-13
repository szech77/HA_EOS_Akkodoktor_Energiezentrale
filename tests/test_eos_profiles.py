"""EOS profile API regression contracts (dev2611122196862169 / 7e10f640).

The fixture exposes the documented writable fields and computed outputs;
it rejects computed/obsolete input and resolves the chosen profile's caps.
No EOS dependency or live installation is needed.
"""
from copy import deepcopy
from unittest.mock import patch

import pytest

from custom_components.eos_energiezentrale.energy.clients import EOS


class ProfileAPI:
    def __init__(self):
        self.rows={kind:{name:{'device_id':name,'battery_profile':'generic-lfp',
            'profile_adjustment':{'nominal_capacity_wh':capacity,'max_charge_power_w':power,
                                  'max_discharge_power_w':power,'full_charge_interval_days':21},
            'min_soc_percentage':0,'max_soc_percentage':100,'charge_rates':[0.,1.],
            'min_charge_power_w':50,'min_soc_deadline_datetime':None,'min_soc_max_duration_h':None}
            for name,capacity,power in devices}
            for kind,devices in (('batteries',[('bat',10000,5000),('other',20000,6000)]),
                                 ('electric_vehicles',[('ev1',77000,11000),('ev2',40000,7000)]))}
        self.puts=[];self.ignore=False;self.profile_cap=1000000;self.resolved=True

    def request(self,url,*,method='GET',payload=None):
        if method=='PUT':
            collection=url.rsplit('/',1)[-1]
            for row in payload.values():
                if any(key.startswith(('effective_','measurement_')) or key in
                       ('capacity_wh','max_charge_power_w','max_discharge_power_w','charging_efficiency','discharging_efficiency') for key in row):
                    raise ValueError('Read-only or obsolete battery setting')
                for key in ('nominal_capacity_wh','max_charge_power_w','max_discharge_power_w'):
                    value=row['profile_adjustment'].get(key)
                    if value is not None and value<=0:raise ValueError('Positive profile adjustment required')
            self.puts.append((collection,deepcopy(payload)))
            if not self.ignore:self.rows[collection]=deepcopy(payload)
        devices=deepcopy(self.rows)
        for collection in devices.values():
            for row in collection.values():
                adjustment=row['profile_adjustment']
                row.update(effective_nominal_capacity_wh=adjustment.get('nominal_capacity_wh') if self.resolved else None,
                    effective_max_charge_power_w=min(self.profile_cap,adjustment['max_charge_power_w']) if self.resolved else None,
                    effective_max_discharge_power_w=min(self.profile_cap,adjustment['max_discharge_power_w']) if self.resolved else None,
                    effective_charging_efficiency=.95 if self.resolved else None,
                    effective_discharging_efficiency=.94 if self.resolved else None,
                    measurement_key_soc_factor=row['device_id']+'-soc-factor',measurement_keys=['private-measurement-key'])
        return {'devices':devices}


def test_vehicle_limits_use_profile_adjustment_and_preserve_other_resources():
    api=ProfileAPI();before=deepcopy(api.rows)
    with patch('custom_components.eos_energiezentrale.energy.clients.request',side_effect=api.request):
        client=EOS('http://eos')
        client.set_vehicle_charging_limits('ev1',2300,1380,(0.,.6,1.),True)
        row=api.rows['electric_vehicles']['ev1']
        assert row['profile_adjustment']['max_charge_power_w']==2300
        assert row['profile_adjustment']['nominal_capacity_wh']==77000
        assert row['profile_adjustment']['full_charge_interval_days']==21
        assert row['battery_profile']=='generic-lfp' and row['charge_rates']==[0.,.6,1.]
        assert row['min_charge_power_w']==1380
        assert api.rows['electric_vehicles']['ev2']==before['electric_vehicles']['ev2']
        assert api.rows['batteries']==before['batteries']
        client.set_vehicle_charging_limits('ev1',2300,1380,(0.,.6,1.),True)
        assert len(api.puts)==1


def test_absent_vehicle_has_zero_rates_and_no_charge_goal_but_a_valid_profile_range():
    api=ProfileAPI()
    api.rows['electric_vehicles']['ev1'].update(min_soc_percentage=80,max_soc_percentage=80,min_soc_max_duration_h=6)
    with patch('custom_components.eos_energiezentrale.energy.clients.request',side_effect=api.request):
        client=EOS('http://eos')
        client.set_vehicle_charging_limits('ev1',None,None,(0.,),False)
        row=api.rows['electric_vehicles']['ev1']
        assert row['charge_rates']==[0.]
        assert row['min_soc_percentage']==0 and row['max_soc_percentage']==100
        assert row['min_soc_max_duration_h'] is None
        assert row['profile_adjustment']['max_charge_power_w']==11000
        client.set_vehicle_charging_limits('ev1',11040,4140,(0.,.375,1.),True)


def test_stationary_limits_merge_capacity_and_both_powers_into_existing_adjustments():
    api=ProfileAPI();other=deepcopy(api.rows['batteries']['other'])
    with patch('custom_components.eos_energiezentrale.energy.clients.request',side_effect=api.request):
        client=EOS('http://eos')
        client.set_battery_limits('bat',20,90,30000,8000,9000)
        row=api.rows['batteries']['bat']
        assert row['profile_adjustment']=={'nominal_capacity_wh':30000,'max_charge_power_w':8000,
                                         'max_discharge_power_w':9000,'full_charge_interval_days':21}
        assert (row['min_soc_percentage'],row['max_soc_percentage'])==(20,90)
        assert api.rows['batteries']['other']==other
        client.set_battery_limits('bat',20,90,30000,8000,9000)
        assert len(api.puts)==1


def test_profile_accounting_uses_resolved_values_and_never_fabricates_missing_efficiencies():
    api=ProfileAPI()
    with patch('custom_components.eos_energiezentrale.energy.clients.request',side_effect=api.request):
        client=EOS('http://eos')
        assert client.battery_accounting('bat')=={'capacity_wh':10000,'charge_efficiency':.95,'discharge_efficiency':.94}
        api.resolved=False
        with pytest.raises(ValueError):client.battery_accounting('bat')


def test_goal_update_preserves_profile_and_never_echoes_computed_fields():
    api=ProfileAPI()
    with patch('custom_components.eos_energiezentrale.energy.clients.request',side_effect=api.request):
        client=EOS('http://eos')
        client.set_vehicle_goal('ev1',80,None)
        assert api.rows['electric_vehicles']['ev1']['min_soc_percentage']==80
        assert api.rows['electric_vehicles']['ev1']['profile_adjustment']['nominal_capacity_wh']==77000
        client.set_vehicle_goal('ev1',80,None)
        assert len(api.puts)==1


@pytest.mark.parametrize('kind',['battery','vehicle'])
@pytest.mark.parametrize('failure',['ignored','profile_cap','unresolved'])
def test_unconfirmed_or_effectively_different_limits_remain_an_error(kind,failure):
    api=ProfileAPI()
    api.ignore=failure=='ignored';api.profile_cap=1000 if failure=='profile_cap' else 1000000;api.resolved=failure!='unresolved'
    with patch('custom_components.eos_energiezentrale.energy.clients.request',side_effect=api.request):
        client=EOS('http://eos')
        with pytest.raises(ValueError):
            if kind=='battery':client.set_battery_limits('bat',20,90,30000,8000,9000)
            else:client.set_vehicle_charging_limits('ev1',2300,1380,(0.,.6,1.),True)


@pytest.mark.parametrize('charge,discharge',[(0,9000),(8000,0),(0,0)])
def test_zero_profile_power_is_rejected_before_mutation_instead_of_replaced_with_one(charge,discharge):
    api=ProfileAPI()
    with patch('custom_components.eos_energiezentrale.energy.clients.request',side_effect=api.request):
        with pytest.raises(ValueError):EOS('http://eos').set_battery_limits('bat',20,90,30000,charge,discharge)
    assert not api.puts

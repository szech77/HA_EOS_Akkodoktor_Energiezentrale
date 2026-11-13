"""Translate EOS battery configuration without changing its selected profile.

Profile API: EOS 7e10f640 / 0.3.0.dev2611122196862169. Detect fields rather
than comparing unstable development version strings. No network access here.
"""
from copy import deepcopy
from math import isclose

from .domain import number


def profiled(device):
    return any(key in device for key in ('battery_profile','profile_adjustment','effective_nominal_capacity_wh'))


def limits_patch(device,desired):
    """Convert canonical legacy input names into this resource's writable schema."""
    patch=dict(desired)
    if not profiled(device):
        if 'nominal_capacity_wh' in device and 'capacity_wh' not in device and 'capacity_wh' in patch:
            patch['nominal_capacity_wh']=patch.pop('capacity_wh')
        return patch
    if not isinstance(device.get('profile_adjustment',{}),dict):
        raise ValueError('Invalid EOS battery profile adjustment')
    adjustments={}
    for old,new in (('capacity_wh','nominal_capacity_wh'),('max_charge_power_w','max_charge_power_w'),
                    ('max_discharge_power_w','max_discharge_power_w')):
        if old in patch:
            value=patch.pop(old)
            # The profile API requires strictly positive power adjustments.
            # Zero must stay unconfirmed, never become a fictitious 1 W limit.
            if value<=0: raise ValueError('EOS profile power limits must be positive')
            adjustments[new]=value
    if adjustments: patch['profile_adjustment']=adjustments
    return patch


def matches(device,desired):
    if not isinstance(device,dict): return False
    return all(matches(device.get(key),value) if isinstance(value,dict) else device.get(key)==value
               for key,value in desired.items())


def confirmed(device,desired):
    if not matches(device,desired): raise ValueError('EOS did not confirm battery settings')
    if profiled(device):
        # Merely echoing an adjustment does not prove it is usable: the chosen
        # profile may be unavailable or cap the effective power to another value.
        for key,value in desired.get('profile_adjustment',{}).items():
            actual=number(device.get('effective_'+key))
            if actual is None or not isclose(actual,value,rel_tol=1e-9,abs_tol=1e-6):
                raise ValueError('EOS effective battery profile limits differ or are unavailable')


def updated_collection(devices,resource,patch):
    """Preserve every writable field/resource, omit read-only response outputs."""
    result={}
    for name,device in devices.items():
        if not isinstance(device,dict): raise ValueError('Invalid EOS battery collection')
        result[name]={key:deepcopy(value) for key,value in device.items()
                      if not key.startswith(('effective_','measurement_'))}
    selected=result[resource]
    for key,value in patch.items():
        selected[key]={**selected.get(key,{}),**value} if isinstance(value,dict) else deepcopy(value)
    return result


def accounting_values(device):
    if profiled(device):
        keys=('effective_nominal_capacity_wh','effective_charging_efficiency','effective_discharging_efficiency')
    else:
        keys=('capacity_wh' if 'capacity_wh' in device else 'nominal_capacity_wh','charging_efficiency','discharging_efficiency')
    values=[number(device.get(key)) for key in keys]
    if any(value is None for value in values): raise ValueError('Battery capacity/efficiencies missing')
    return dict(zip(('capacity_wh','charge_efficiency','discharge_efficiency'),values))

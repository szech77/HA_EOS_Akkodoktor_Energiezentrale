"""Central validation of every plugin reading and every public command."""
from dataclasses import replace
from datetime import datetime
from math import isfinite

from .contracts import BatteryReading, WallboxReading, PluginContractError
from .domain import BatteryCommand


def bounded(value, low, high):
    if isinstance(value,bool) or not isinstance(value,(float,int)):
        return None
    return float(value) if low <= value <= high and isfinite(value) else None


def battery_reading(value, now=None):
    if not isinstance(value, BatteryReading):
        raise PluginContractError("Battery plugin must return BatteryReading")

    def validated_sample(measurement, timestamp, maximum):
        reading = bounded(measurement, 0, maximum)
        if now is None:
            return reading
        if not isinstance(timestamp, datetime) or timestamp.utcoffset() is None:
            return None
        return reading if 0 <= (now - timestamp).total_seconds() < 120 else None

    return replace(value,
        soc=validated_sample(value.soc, value.soc_sample, 100),
        charge=validated_sample(value.charge, value.charge_sample, 1000000),
        discharge=validated_sample(value.discharge, value.discharge_sample, 1000000))


def wallbox_reading(value, now=None):
    if not isinstance(value,WallboxReading):
        raise PluginContractError("Wallbox plugin must return WallboxReading")
    if type(value.enabled) is not bool:
        raise PluginContractError("Wallbox enabled must be boolean")
    status = value.status.strip().lower() if isinstance(value.status,str) else "unknown"
    if status not in {"connected","charging","wakeup","disconnected","unknown","unavailable","error"}:
        status = "unknown"
    sample = value.sample
    if not isinstance(sample,datetime) or sample.utcoffset() is None:
        sample = None
    watts = bounded(value.watts,0,1000000)
    if now is not None and (sample is None or not 0 <= (now-sample).total_seconds() < 120):
        sample,watts = None,None
    step = bounded(value.step,.001,32)
    maximum = bounded(value.maximum,6,80)
    amps = bounded(value.amps,0,80)
    # A retained setpoint can exceed a newly detected adapter limit. Preserve
    # the observed value so control can lower it; charging_current enforces the
    # current hardware limit on every new command.
    return replace(value,watts=watts,status=status,phases=value.phases if type(value.phases) is int and value.phases in (1,3) else None,
                   amps=amps,step=step,maximum=maximum,sample=sample,
                   max_phases=value.max_phases if type(value.max_phases) is int and value.max_phases in (1,3) else None,
                   nominal_voltage=bounded(value.nominal_voltage,100,260))


def battery_command(value):
    if not isinstance(value,BatteryCommand) or value.mode not in {"limits","block_discharge","grid_charge","grid_discharge"}:
        raise PluginContractError("Invalid battery command")
    charge,discharge = bounded(value.charge_w,0,1000000),bounded(value.discharge_w,0,1000000)
    if charge is None or discharge is None:
        raise PluginContractError("Invalid battery power")
    return BatteryCommand(value.mode,charge,discharge)


def charging_current(value,state):
    amps = bounded(value,6,80)
    if amps is None or state.maximum is None or state.step is None or amps>state.maximum:
        raise PluginContractError("Invalid charging current")
    if abs(amps/state.step-round(amps/state.step))>1e-6:
        raise PluginContractError("Charging current does not match supported step")
    return amps

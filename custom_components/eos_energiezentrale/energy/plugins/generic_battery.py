"""Generic battery: normalized mode and power helpers can trigger HA automations."""
from math import floor

from ..contracts import BatteryDriver, BatteryFeatures, BatteryReading, PluginInfo, PluginField, Measurement
from ..clients import reading, report_time
from ..domain import number
from ..device_io import confirmed_state
from ..plugin_parameters import parameters


class GenericBattery(BatteryDriver):
    info = PluginInfo("generic","Generic Home Assistant battery/inverter","battery")
    configuration = (
        PluginField("soc","Battery SoC",domains=("sensor",)),
        PluginField("soc_scale","SoC unit","choice",default="percent",choices=("percent","factor")),
        PluginField("charge_power","Charging power",domains=("sensor",)),
        PluginField("discharge_power","Discharging power",domains=("sensor",)),
        PluginField("mode","Control mode",domains=("select","input_select")),
        PluginField("charge_limit","Charge power limit",domains=("number","input_number")),
        PluginField("discharge_limit","Discharge power limit",domains=("number","input_number")),
        PluginField('solar','PV power (optional)',required=False,default='',domains=('sensor',)),
        PluginField('inverter_ac','Signed inverter AC power (optional)',required=False,default='',domains=('sensor',)),
        PluginField('grid','Signed grid power (optional)',required=False,default='',domains=('sensor',)),
        PluginField("grid_charge_supported","Supports forced grid charging","boolean",default=True),
        PluginField("grid_discharge_supported","Supports forced grid export","boolean",default=False),
        PluginField("mode_map","Mode mapping","json",default={"auto":"auto","limits":"limits","block_discharge":"block_discharge","grid_charge":"grid_charge","grid_discharge":"grid_discharge"}),
    )

    def __init__(self,ha,params):
        values = parameters(self.configuration,params)
        self.ha = ha
        self.ids = {key:values[key] for key in ("soc","charge_power","discharge_power","mode","discharge_limit")}
        self.ids.update(pv_limit=values["charge_limit"],grid_charge=values["charge_limit"],grid_discharge=values["discharge_limit"])
        self.ids.update({key:values[key] for key in ('solar','inverter_ac','grid') if values[key]})
        self.measurement_keys=BatteryDriver.measurement_keys+tuple(key for key in ('solar','inverter_ac','grid') if values[key])
        self.features = BatteryFeatures(grid_charge=values["grid_charge_supported"],grid_discharge=values["grid_discharge_supported"])
        self.soc_scale = values["soc_scale"]
        self.modes = values["mode_map"]
        if self.modes.keys() != {"auto","limits","block_discharge","grid_charge","grid_discharge"} or any(not isinstance(value,str) or not 1<=len(value)<=80 or any(ord(c)<32 for c in value) for value in self.modes.values()):
            raise ValueError("Invalid battery mode mapping")

    def _read(self,states,now):
        soc = reading(states,self.ids["soc"],now,"soc",120)
        unit = states.get(self.ids["soc"],{}).get("attributes",{}).get("unit_of_measurement")
        if unit not in ({None,"1"} if self.soc_scale=="factor" else {None,"%"}): soc = None
        if soc is not None and self.soc_scale=="factor": soc *= 100
        return BatteryReading(soc,reading(states,self.ids["charge_power"],now,"power",120),
                              reading(states,self.ids["discharge_power"],now,"power",120),
                              report_time(states,self.ids["soc"]),
                              report_time(states,self.ids["charge_power"]),
                              report_time(states,self.ids["discharge_power"]),
                              {key:Measurement(reading(states,self.ids[key],now,'power',45),report_time(states,self.ids[key]))
                               for key in ('solar','inverter_ac','grid') if key in self.ids})

    def power_limits(self,states):
        result=[]
        for key in ('pv_limit','discharge_limit'):
            attrs=self.ha.state(self.ids[key]).get('attributes',{})
            scale={'W':1,'kW':1000}.get(attrs.get('unit_of_measurement'))
            maximum=number(attrs.get('max'))
            if scale is None or maximum is None or not 0<maximum*scale<=1000000:
                raise ValueError('Battery hardware power limit unavailable')
            result.append(maximum*scale)
        return tuple(result)

    def _mode(self,mode):
        entity = self.ids["mode"]
        desired = self.modes[mode]
        row = self.ha.state(entity)
        if desired not in row.get("attributes",{}).get("options",[]):
            raise ValueError("Configured battery mode is not an available option")
        if row.get("state") != desired:
            self.ha.set(entity,desired)
            confirmed_state(self.ha,entity,lambda value:value.get("state")==desired)

    def _power(self,entity,watts):
        row = self.ha.state(entity)
        attrs = row.get("attributes",{})
        scale = {"W":1,"kW":1000}.get(attrs.get("unit_of_measurement"))
        maximum,minimum,step = number(attrs.get("max")),number(attrs.get("min")),number(attrs.get("step"))
        if scale is None or minimum is None or maximum is None or step is None or minimum>0 or maximum<=0 or step<=0:
            raise ValueError("Battery power entity requires W/kW, min<=0, max>0 and step>0")
        target = floor(min(maximum,watts/scale)/step+1e-9)*step
        if number(row.get("state")) is None:
            raise ValueError("Battery power limit unavailable")
        if abs(float(row["state"])-target)>=step/2:
            self.ha.set(entity,target)
            confirmed_state(self.ha,entity,lambda value:number(value.get("state")) is not None and abs(float(value["state"])-target)<step/2)

    def _apply(self,command,states):
        charge = command.charge_w if command.mode!="grid_discharge" else 0
        discharge = command.discharge_w if command.mode not in {"block_discharge","grid_charge"} else 0
        self._power(self.ids["pv_limit"],charge)
        self._power(self.ids["discharge_limit"],discharge)
        self._mode(command.mode)

    def _release(self,states):
        self._mode("auto")

PLUGINS = (GenericBattery,)

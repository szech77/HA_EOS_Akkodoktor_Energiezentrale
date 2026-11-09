"""Generic wallbox: HA entities/helpers drive HA automations or hardware entities."""
from dataclasses import replace

from ..contracts import PluginInfo, PluginField, WallboxFeatures
from ..entity_wallbox import EntityWallbox
from ..plugin_parameters import parameters
from ..domain import number


class GenericWallbox(EntityWallbox):
    info = PluginInfo("generic","Generic Home Assistant wallbox","wallbox")
    configuration = (
        PluginField("power","Charging power",domains=("sensor",)),
        PluginField("status","Wallbox status",required=False,default="",domains=("sensor","input_select")),
        PluginField("plugged","Plug connected",required=False,default="",domains=("binary_sensor","input_boolean")),
        PluginField("enable","Charge enable",domains=("switch","input_boolean")),
        PluginField("current","Charging current (A)",domains=("number","input_number")),
        PluginField("phases","Phase count",domains=("number","input_number","select","input_select","sensor")),
        PluginField("phase_feedback","Actual phase count (required with phase helpers)",required=False,default="",domains=("sensor","number","select")),
        PluginField("phase_switching","Supports phase switching","boolean",default=True),
        PluginField("status_map","Status mapping","json",default={"connected":"connected","charging":"charging","disconnected":"disconnected","wakeup":"wakeup","error":"error"}),
    )

    def __init__(self,ha,params):
        values = parameters(self.configuration,params)
        if not values["status"] and not values["plugged"]:
            raise ValueError("A status or plug sensor is required")
        if values["phase_switching"] and values["phases"].startswith('sensor.'):
            raise ValueError("Phase switching requires a writable phase entity")
        if values["phase_switching"] and values["phases"].split('.')[0] in {"input_number","input_select"} and not values["phase_feedback"]:
            raise ValueError("Phase helpers require an actual hardware phase feedback entity")
        self.ha = ha
        self.ids = {key:values[key] for key in ("power","status","plugged","enable","current","phases","phase_feedback")}
        self.features = WallboxFeatures(phase_switching=values["phase_switching"])
        self.status_map = {str(key).strip().lower():value for key,value in values["status_map"].items()}
        if any(value not in {"connected","charging","wakeup","disconnected","unknown","unavailable","error"} for value in self.status_map.values()):
            raise ValueError("Invalid normalized wallbox status")
        self.zero_sample = self.zero_after = self.phase_requested = None

    def _read(self,states,now):
        state = super()._read(states,now)
        if states.get(self.ids["enable"],{}).get("state") not in {"on","off"}:
            return replace(state,status="unknown")
        if states.get(self.ids["current"],{}).get("attributes",{}).get("unit_of_measurement") != "A":
            state = replace(state,amps=None)
        if self.ids["phase_feedback"]:
            actual = number(states.get(self.ids["phase_feedback"],{}).get("state"))
            state = replace(state,phases=int(actual) if actual in (1,3) else None)
        status = self.status_map.get(state.status,"unknown")
        if self.ids["plugged"]:
            plug = states.get(self.ids["plugged"],{}).get("state")
            if plug == "off": status = "disconnected"
            elif plug != "on": status = "unknown"
            elif not self.ids["status"]: status = "charging" if state.enabled and (state.watts or 0)>500 else "connected"
        return replace(state,status=status)

PLUGINS = (GenericWallbox,)

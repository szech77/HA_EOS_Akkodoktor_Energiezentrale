"""Generic wallbox: HA entities/helpers drive HA automations or hardware entities."""
from dataclasses import replace

from ..contracts import PluginInfo, PluginField, WallboxFeatures
from ..entity_wallbox import EntityWallbox
from ..plugin_parameters import parameters
from ..domain import number
from ..plugin_diagnostics import entity_reading, plugin_operation
from ..failures import PluginParameterError


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
            raise PluginParameterError("A status or plug sensor is required",'status')
        if values["phase_switching"] and values["phases"].startswith('sensor.'):
            raise PluginParameterError("Phase switching requires a writable phase entity",'phases')
        if values["phase_switching"] and values["phases"].split('.')[0] in {"input_number","input_select"} and not values["phase_feedback"]:
            raise PluginParameterError("Phase helpers require an actual hardware phase feedback entity",'phase_feedback')
        self.ha = ha
        self.ids = {key:values[key] for key in ("power","status","plugged","enable","current","phases","phase_feedback")}
        self.features = WallboxFeatures(phase_switching=values["phase_switching"])
        self.status_map = {str(key).strip().lower():value for key,value in values["status_map"].items()}
        if any(value not in {"connected","charging","wakeup","disconnected","unknown","unavailable","error"} for value in self.status_map.values()):
            raise PluginParameterError("Invalid normalized wallbox status",'status_map')
        self.zero_sample = self.zero_after = self.phase_requested = None

    def _read(self,states,now):
        self._source_problems={}
        self._control_problems=[]
        entity_reading(self,states,now,'power','power',120,('car',))
        for key in ('enable','current','status','plugged','phases','phase_feedback'):
            entity=self.ids[key]
            if not entity: continue
            row=states.get(entity,{})
            value=row.get('state')
            reason=('entity_missing' if entity not in states else 'state_unavailable' if value in (None,'unknown','unavailable') else None)
            if reason is None:
                if key in {'enable','plugged'} and value not in {'on','off'}: reason='invalid_value'
                elif key=='status' and self.status_map.get(str(value).strip().lower(),'unknown')=='unknown': reason='status_unmapped'
                elif key=='current' and row.get('attributes',{}).get('unit_of_measurement')!='A': reason='unit_invalid'
                elif key=='current' and number(value) is None: reason='invalid_value'
                elif key in {'phases','phase_feedback'} and number(value) not in (1,3): reason='invalid_value'
            if reason: self._control_problems.append({'parameter':key,'reason':reason})
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

    @plugin_operation('pause')
    def _pause(self,state): return super()._pause(state)

    @plugin_operation('charge')
    def _charge(self,amps,state): return super()._charge(amps,state)

    @plugin_operation('phase')
    def _phase(self,phases,state): return super()._phase(phases,state)

PLUGINS = (GenericWallbox,)

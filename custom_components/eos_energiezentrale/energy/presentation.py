"""Display-only power references and optional normalized heat-pump utilization."""
from .clients import reading
from .contracts import WallboxFeatures
from .domain import number


def heat_utilization(states,options,now):
    entity = options.get("heat_load_entity","")
    if not entity:
        return None
    value = reading(states,entity,now,"soc",options.get("display_hold_s",900))
    scale = options.get("heat_load_scale","percent")
    unit = states.get(entity,{}).get("attributes",{}).get("unit_of_measurement")
    if unit not in ({None,"1"} if scale=="factor" else {None,"%"}):
        return None
    limit = 1 if scale=="factor" else 100
    return value/limit if value is not None and 0<=value<=limit else None


def power_references(options,live,features):
    phases = live.get("phases") if isinstance(features,WallboxFeatures) and not features.phase_switching else 3
    current = number(options.get("max_current_a",16))
    car = min(11000,current*230*phases) if current is not None and phases in (1,3) else None
    return {"solar":options.get("pv_peak_w",10000),"car":car,
            "battery_charge":options.get("battery_charge_w"),"battery_discharge":options.get("battery_discharge_w")}

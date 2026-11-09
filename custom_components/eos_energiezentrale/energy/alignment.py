"""Align observed values for presentation without changing regulation inputs."""
from collections import deque
from datetime import timedelta
from .domain import instant,number,house_only


def report_times(states,options,battery_ids,wallbox_ids,now):
    sources={"solar":options.get("pv_entity"),"grid":options.get("grid_entity"),
             "house_total":options.get("house_entity"),"heat":options.get("heat_entity"),
             "car":wallbox_ids.get("power"),"battery_charge":battery_ids.get("charge_power"),
             "battery_discharge":battery_ids.get("discharge_power")}
    return {key:instant(states.get(entity,{}).get("last_reported") or states.get(entity,{}).get("last_updated"))
            if isinstance(entity,str) and entity else now for key,entity in sources.items()}


class FlowAlignment:
    def __init__(self,tolerance=10,hold=900):
        self.tolerance=tolerance
        self.hold=hold
        self.buffers={}
        self.last={}

    def update(self,live,times,now,car=True,heat=True,retained=None,cars=None):
        retained=retained or {}
        keys=["solar","grid","house_total","battery_charge","battery_discharge"]
        samples=dict(live)
        times=dict(times)
        car_keys=[]
        if cars is not None:
            for identity,(value,stamp) in cars.items():
                key="car:"+identity
                car_keys.append(key)
                samples[key]=value
                times[key]=stamp
            keys.extend(car_keys)
        elif car:
            keys.append("car")
        for key in [*keys,*( ["heat"] if heat else [])]:
            value=samples.get(key)
            stamp=times.get(key)
            if value is None and key in retained:
                value=retained[key]["value"]
                stamp=now-timedelta(seconds=retained[key]["age_s"])
            if number(value) is None or stamp is None or not 0<=(now-stamp).total_seconds()<=self.hold:
                continue
            rows=self.buffers.setdefault(key,deque(maxlen=256))
            if not rows or stamp>rows[-1][0]:
                rows.append((stamp,value))
            elif stamp==rows[-1][0]:
                rows[-1]=(stamp,value)
        if all(self.buffers.get(key) for key in keys):
            anchor=min(self.buffers[key][-1][0] for key in keys)
            selected={key:min(self.buffers[key],key=lambda row:abs((row[0]-anchor).total_seconds())) for key in keys}
            stamps=[stamp for stamp,_ in selected.values()]
            coherent=(max(stamps)-min(stamps)).total_seconds()<=self.tolerance
            if coherent and 0<=(now-anchor).total_seconds()<=self.hold:
                values={key:value for key,(_,value) in selected.items()}
                if car_keys:
                    values["car"]=sum(values.pop(key) for key in car_keys)
                values["battery"]=values["battery_charge"]-values["battery_discharge"]
                heat_row=min(self.buffers["heat"],key=lambda row:abs((row[0]-anchor).total_seconds())) if heat and self.buffers.get("heat") else None
                heat_value=heat_row[1] if heat_row and 0<=(now-heat_row[0]).total_seconds()<=self.hold else None
                if heat_value is not None:
                    values["heat"]=heat_value
                house=house_only(values["house_total"],values.get("car",0),heat_value if heat else 0)
                if house is not None:
                    values["house"]=house
                self.last={key:(value,min(anchor,heat_row[0]) if key in {"heat","house"} and heat_row else anchor)
                           for key,value in values.items()}
        return {key:{"value":value,"age_s":(now-stamp).total_seconds(),"estimated":True,"aligned":True}
                for key,(value,stamp) in self.last.items() if 0<=(now-stamp).total_seconds()<=self.hold}

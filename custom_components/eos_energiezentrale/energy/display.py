"""Bounded presentation cache; never supplies values to regulation or history."""
from .domain import instant, number, house_only
from .clients import reading


class DisplayValues:
    def __init__(self,seconds=900):
        self.seconds=seconds
        self.samples={}

    def remember(self,key,value,stamp,now):
        if number(value) is None or stamp is None or not 0 <= (now-stamp).total_seconds() <= self.seconds:
            return
        previous=self.samples.get(key)
        if previous is None or stamp>=previous[1]:
            self.samples[key]=(value,stamp)

    def retained(self,key,now):
        sample=self.samples.get(key)
        if sample is None:
            return None
        value,stamp=sample
        age=(now-stamp).total_seconds()
        return {"value":value,"age_s":age} if 0<=age<=self.seconds else None

    def update(self,states,live,options,battery_ids,wallbox_ids,now):
        sources={key:(options.get(option),kind) for key,option,kind in (
            ("solar","pv_entity","power"),("grid","grid_entity","power"),
            ("house_total","house_entity","power"),("heat","heat_entity","power"),
            ("price","price_entity","price"))}
        for key,field,kind in (("battery_charge","charge_power","power"),
                               ("battery_discharge","discharge_power","power"),
                               ("battery_soc","soc","soc")):
            sources[key]=(battery_ids.get(field),kind)
        if options.get("wallbox_type")!="none":
            sources["car"]=(wallbox_ids.get("power"),"power")
        stamps={}
        for key,(entity,kind) in sources.items():
            if not isinstance(entity,str) or not entity:
                continue
            row=states.get(entity,{})
            stamp=instant(row.get("last_reported") or row.get("last_updated"))
            stamps[key]=stamp
            value=reading(states,entity,now,kind)
            if key=="battery_soc" and (value is None or not 0<=value<=100):
                continue
            self.remember(key,value,stamp,now)
        for key,parents in (("battery",("battery_charge","battery_discharge")),
                            ("house",("house_total","car","heat"))):
            available=[stamps[parent] for parent in parents if stamps.get(parent) is not None]
            if available:
                stamps[key]=min(available)
        for key in ("solar","grid","house_total","heat","price","car","battery_soc","car_soc",
                    "battery_charge","battery_discharge","house","battery"):
            if live.get(key) is not None:
                self.remember(key,live[key],stamps.get(key) or now,now)
        result={key:sample for key in self.samples if live.get(key) is None
                and (sample:=self.retained(key,now)) is not None}
        def value(key):
            return live.get(key) if live.get(key) is not None else result.get(key,{}).get("value")
        def age(keys):
            return max((result.get(key,{}).get("age_s",0) for key in keys),default=0)
        if live.get("battery") is None and value("battery_charge") is not None and value("battery_discharge") is not None:
            result["battery"]={"value":value("battery_charge")-value("battery_discharge"),
                               "age_s":age(("battery_charge","battery_discharge")),"estimated":True}
        car=value("car") if options.get("wallbox_type")!="none" else 0
        heat=value("heat") if options.get("heat_entity") else 0
        if live.get("house") is None:
            house=house_only(value("house_total"),car,heat)
            if house is not None:
                result["house"]={"value":house,"age_s":age(("house_total","car","heat")),"estimated":True}
        return result

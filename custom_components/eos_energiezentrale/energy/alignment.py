"""Brief display-only hold when charging demand arrives before charger telemetry."""
from datetime import timedelta
from .domain import instant,number,house_only


def report_times(states,options,battery_ids,wallbox_ids,now):
    sources={"solar":options.get("pv_entity"),"grid":options.get("grid_entity"),
             "house_total":options.get("house_entity"),"heat":options.get("heat_entity"),
             "car":wallbox_ids.get("power"),"battery_charge":battery_ids.get("charge_power"),
             "battery_discharge":battery_ids.get("discharge_power")}
    return {key:instant(states.get(entity,{}).get("last_reported") or states.get(entity,{}).get("last_updated"))
            if isinstance(entity,str) and entity else now for key,entity in sources.items()}


class ChargeTransitionDisplay:
    def __init__(self,hold=900,transition=30):
        self.hold=hold
        self.transition=transition
        self.last={}
        self.command_at=None
        self.pending=None

    @staticmethod
    def supplied(values):
        keys=("solar","grid","battery_charge","battery_discharge")
        if not all(key in values for key in keys):
            return None
        return values["solar"]+values["grid"]-values["battery_charge"]+values["battery_discharge"]

    def update(self,live,times,now,car=True,heat=True,retained=None,cars=None,expected_car_w=None,command_at=None):
        retained=retained or {}
        samples={}
        keys=("solar","grid","house_total","battery_charge","battery_discharge","car","heat")
        for key in keys:
            value=live.get(key)
            stamp=times.get(key)
            if value is None and key in retained:
                value=retained[key]["value"]
                stamp=now-timedelta(seconds=retained[key]["age_s"])
            if number(value) is not None and stamp and 0<=(now-stamp).total_seconds()<=self.hold:
                samples[key]=(value,stamp)
        values={key:value for key,(value,_) in samples.items()}
        if all(key in samples for key in ("battery_charge","battery_discharge")):
            samples["battery"]=(values["battery_charge"]-values["battery_discharge"],min(samples["battery_charge"][1],samples["battery_discharge"][1]))
        house=house_only(values.get("house_total"),values.get("car") if car else 0,values.get("heat") if heat else 0)
        if house is not None:
            stamps=[samples[key][1] for key in ("house_total","car","heat") if key in samples]
            samples["house"]=(house,min(stamps))
        baseline={key:value for key,(value,_) in self.last.items()}
        if not car or expected_car_w is None or expected_car_w<=0 or not self.transition:
            self.pending=None
        elif command_at is not None and command_at!=self.command_at:
            self.command_at=command_at
            old_car=baseline.get("car")
            if old_car is not None and expected_car_w-old_car>=300:
                if self.pending and self.pending["since"] is not None and not self.pending["done"]:
                    self.pending["target"]=expected_car_w
                else:
                    self.pending={"baseline":dict(self.last),"target":expected_car_w,"since":None,"done":False}
            else:
                self.pending=None
        pending=self.pending
        if pending and not pending["done"]:
            base={key:value for key,(value,_) in pending["baseline"].items()}
            measured=values.get("car")
            reached=measured is not None and measured>=pending["target"]-max(250,pending["target"]*.15)
            before,after=self.supplied(base),self.supplied(values)
            source_rise=(after-before if before is not None and after is not None else 0)
            house_rise=values.get("house_total",base.get("house_total",0))-base.get("house_total",0)
            if reached:
                pending["done"]=True
            elif max(source_rise,house_rise)>=300:
                if pending["since"] is None:
                    pending["since"]=now
                if (now-pending["since"]).total_seconds()<self.transition:
                    return {key:{"value":value,"age_s":(now-stamp).total_seconds(),"estimated":True,"transition_held":True}
                            for key,(value,stamp) in pending["baseline"].items() if 0<=(now-stamp).total_seconds()<=self.hold}
                pending["done"]=True
            elif pending["since"] is not None:
                # Source increase disappeared; show the actual values again.
                pending["done"]=True
        self.last=samples
        return {}

"""Multiple independently planned vehicles sharing one metered grid connection."""
from copy import deepcopy
import json
import re

from .clients import reading
from .controller import Controller
from .domain import battery_command, current_instruction, house_only, instant
from .drivers import WALLBOX_DRIVERS
from .settings import Configuration, daily_settings, save
from .history import History
from .display import DisplayValues
from .alignment import FlowAlignment, report_times


def vehicle_options(options):
    raw=options.get("vehicles", "[]")
    rows=json.loads(raw) if isinstance(raw,str) else raw
    if not isinstance(rows,list) or len(rows)>8:
        raise ValueError("Up to eight vehicles are supported")
    result=[]
    resources={options["battery_resource"]}
    identities=set()
    controls=set()
    allowed={"id","name","resource","soc_entity","soc_scale","capacity_wh",
             "charging_efficiency","max_current_a","wallbox_type","wallbox_parameters"}
    for row in rows:
        if not isinstance(row,dict) or row.keys()-allowed:
            raise ValueError("Invalid vehicle definition")
        identity=row.get("id")
        if not isinstance(identity,str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,32}",identity) or identity in identities:
            raise ValueError("Vehicle IDs must be unique")
        identities.add(identity)
        values={**options,"vehicles":"[]","vehicle_name":row.get("name","E-Auto"),
                "vehicle_resource":row.get("resource",identity),"car_soc_entity":row.get("soc_entity",""),
                "car_soc_scale":row.get("soc_scale","factor"),"wallbox_type":row.get("wallbox_type","nrgkick"),
                "wallbox_parameters":json.dumps(row.get("wallbox_parameters",{}))}
        for key in ("capacity_wh","charging_efficiency","max_current_a"):
            if key in row:
                values[key]=row[key]
        if values["vehicle_resource"] in resources:
            raise ValueError("Each vehicle needs its own EOS resource")
        resources.add(values["vehicle_resource"])
        if values["wallbox_type"] == "none" or values["wallbox_type"] not in WALLBOX_DRIVERS:
            raise ValueError("Each vehicle needs a supported wallbox")
        driver=WALLBOX_DRIVERS[values["wallbox_type"]](None,json.loads(values["wallbox_parameters"]))
        ids={driver.ids[key] for key in ("enable","current","phases","power")}
        if ids & controls:
            raise ValueError("Wallbox control entities cannot be shared by vehicles")
        controls.update(ids)
        result.append((identity,values))
    return result


def reserved_grid(grid, actual, targets, current):
    """Reserve unobserved increases; never spend unconfirmed reductions."""
    return grid+sum(max(0,watts-actual.get(key,0)) for key,watts in targets.items() if key!=current)


class MeteredAdapter:
    def __init__(self,ha,options,identity,targets):
        self.ha,self.options,self.identity,self.targets=ha,options,identity,targets
        self.rows=None
        self.commanded={}
        self.ids=WALLBOX_DRIVERS[options["wallbox_type"]](None,json.loads(options["wallbox_parameters"])).ids
    def states(self):
        return deepcopy(self.rows) if self.rows is not None else self.ha.states()
    def state(self,entity):
        return self.ha.state(entity)
    def set(self,entity,value):
        self.ha.set(entity,value)
        if entity in {self.ids["enable"],self.ids["current"],self.ids["phases"]}:
            self.commanded[entity]=value
            enabled=self.commanded.get(self.ids["enable"],self.ha.state(self.ids["enable"]).get("state")=="on")
            if not enabled:
                self.targets[self.identity]=0
            else:
                try:
                    amps=float(self.commanded.get(self.ids["current"],self.ha.state(self.ids["current"]).get("state")))
                    phases=float(self.commanded.get(self.ids["phases"],self.ha.state(self.ids["phases"]).get("state")))
                    self.targets[self.identity]=amps*phases*230
                except (KeyError,ValueError,TypeError):
                    raise ValueError("Wallbox setpoint cannot be reserved") from None
    def publish_soc(self,*args):
        pass


class MeterOnlyBattery:
    def __init__(self,driver):
        self.driver,self.ids=driver,driver.ids
    def read(self,*args):
        return self.driver.read(*args)
    def apply(self,*args):
        pass
    def release(self,*args):
        pass


def create_controller(ha,options,directory):
    vehicles=vehicle_options(options)
    if not vehicles:
        return Controller(ha,Configuration(options,ha,directory))
    return FleetController(ha,options,directory,vehicles)


class FleetController(Controller):
    def __init__(self,ha,options,directory,vehicles):
        self.real_ha,self.targets,self.controllers=ha,{},[]
        self.vehicle_snapshots=[]
        self.global_options=options
        self.primary_history=None
        self.fleet_display_values=DisplayValues(options.get("display_hold_s",900))
        self.fleet_alignment=FlowAlignment(options.get("sensor_alignment_s",10),options.get("display_hold_s",900))
        for index,(identity,values) in enumerate(vehicles):
            child_dir=directory if index==0 else directory/"vehicles"/identity
            child_dir.mkdir(parents=True,exist_ok=True)
            proxy=MeteredAdapter(ha,values,identity,self.targets)
            config=Configuration(values,proxy,child_dir)
            if index==0:
                self.battery_driver=config.battery
                config.battery=MeterOnlyBattery(self.battery_driver)
                super().__init__(proxy,config)
                controller=self
                vehicle_dir=directory/"vehicles"/identity
                vehicle_dir.mkdir(parents=True,exist_ok=True)
                self.primary_history=History(vehicle_dir/"history.sqlite3")
                self.primary_settings_path=vehicle_dir/"daily.json"
                if self.primary_settings_path.exists():
                    saved=json.loads(self.primary_settings_path.read_text(encoding="utf-8"))
                    shared_keys={"battery_min_soc","battery_max_soc","battery_pv_support","_battery_limits_managed"}
                    config.daily=daily_settings({**config.daily,**{key:value for key,value in saved.items() if key not in shared_keys},"fast":False},values["regulation_interval_s"])
            else:
                config.battery=MeterOnlyBattery(self.battery_driver)
                controller=Controller(proxy,config)
                controller.update_eos=lambda now,clock,child=controller:self._share_plan(child)
            self.controllers.append((identity,controller,proxy))

    def _share_plan(self,child):
        child.plan=self.plan
        child.forecast=[{key:value for key,value in row.items() if key not in {"car","car_soc"}} for row in self.forecast]

    def persist_primary_settings(self):
        save(self.primary_settings_path,{**self.config.daily,"fast":False})

    def change_vehicle_settings(self,identity,values):
        controller=next((app for key,app,_ in self.controllers if key==identity),None)
        if controller is None:
            raise ValueError("Unknown vehicle")
        # Battery bounds and support are one shared policy, not per-wallbox settings.
        shared={key:values[key] for key in ("battery_min_soc","battery_max_soc","battery_pv_support") if key in values}
        specific={key:value for key,value in values.items() if key not in shared}
        shared_checked=daily_settings({**self.config.daily,**shared},self.config.options["regulation_interval_s"])
        merged=daily_settings({**controller.config.daily,**specific},controller.config.options["regulation_interval_s"])
        controller.config.update(merged)
        if controller is self:
            self.persist_primary_settings()
        if shared:
            self.config.update({**self.config.daily,**{key:shared_checked[key] for key in shared}},manage_battery_limits=bool(shared.keys() & {"battery_min_soc","battery_max_soc"}))

    def tick(self,now,clock):
        rows=self.real_ha.states()
        opts=self.config.options
        grid=reading(rows,opts["grid_entity"],now,"power",45)
        actual={key:app.config.wallbox.read(rows,now).watts for key,app,_ in self.controllers}
        complete=all(value is not None for value in actual.values())
        snapshots=[]
        for key,app,proxy in self.controllers:
            box=app.config.wallbox.read(rows,now)
            if not box.plugged:
                self.targets[key]=0
            proxy.rows=deepcopy(rows)
            # If any charger meter is unavailable, adding new load is inhibited.
            if grid is not None and complete:
                effective=reserved_grid(grid,actual,self.targets,key)
                proxy.rows[opts["grid_entity"]]={**rows[opts["grid_entity"]],"state":str(effective),
                    "attributes":{**rows[opts["grid_entity"]].get("attributes",{}),"unit_of_measurement":"W"}}
            elif not complete:
                proxy.rows.pop(opts["grid_entity"],None)
            if app is not self:
                app.armed=self.armed
                if self.restore_pending:
                    app.restore_pending=True
            try:
                Controller.tick(app,now,clock)
            finally:
                self.owned=any(child.owned for _,child,_ in self.controllers)
            payload=Controller.snapshot(app,now)
            # The legacy EOS solution only identifies one EV curve. Never assign
            # this curve to several vehicles without resource identifiers.
            payload["forecast"]=[{k:v for k,v in row.items() if k not in {"car","car_soc"}} for row in payload["forecast"]]
            vehicle_history=self.primary_history if app is self else app.history
            if app is self:
                vehicle_history.write(now,payload["live"])
            payload.update(id=key,name=app.config.options["vehicle_name"])
            snapshots.append(payload)
        self.vehicle_snapshots=snapshots
        self.live=dict(self.live)
        self.live["grid"]=grid
        self.live["car"]=sum(actual.values()) if complete else None
        self.live["car_soc"]=None
        self.live["house"]=house_only(self.live.get("house_total"),self.live["car"],
            self.live.get("heat") if opts["heat_entity"] else 0)
        self.display.pop("car",None)
        self.display.pop("house",None)
        if complete:
            stamps=[instant(rows[proxy.ids["power"]]["last_reported"])
                    for _,_,proxy in self.controllers if rows.get(proxy.ids["power"],{}).get("last_reported")]
            self.fleet_display_values.remember("car",self.live["car"],min(stamp for stamp in stamps if stamp is not None) if any(stamps) else now,now)
        else:
            values=[(payload["live"].get("car"),payload["display"].get("car")) for payload in snapshots]
            if all(value is not None or retained is not None for value,retained in values):
                self.display["car"]={"value":sum(value if value is not None else retained["value"] for value,retained in values),
                                     "age_s":max((retained["age_s"] if value is None else 0 for value,retained in values)),"estimated":True}
            elif (retained:=self.fleet_display_values.retained("car",now)) is not None:
                self.display["car"]=retained
        if self.live["house"] is not None:
            sources=[opts["house_entity"]]+([opts["heat_entity"]] if opts["heat_entity"] else [])
            stamps=[instant(rows.get(entity,{}).get("last_reported") or rows.get(entity,{}).get("last_updated")) for entity in sources]
            if "car" in self.fleet_display_values.samples:
                stamps.append(self.fleet_display_values.samples["car"][1])
            self.fleet_display_values.remember("house",self.live["house"],min(stamp for stamp in stamps if stamp is not None) if any(stamps) else now,now)
        else:
            values={key:self.live.get(key) if self.live.get(key) is not None else self.display.get(key,{}).get("value")
                    for key in ("house_total","car","heat")}
            estimate=house_only(values["house_total"],values["car"],values["heat"] if opts["heat_entity"] else 0)
            if estimate is not None:
                self.display["house"]={"value":estimate,"age_s":max((self.display.get(key,{}).get("age_s",0) for key in values)),"estimated":True}
            elif (retained:=self.fleet_display_values.retained("house",now)) is not None:
                self.display["house"]=retained
        times=report_times(rows,opts,self.battery_driver.ids,{},now)
        car_times=[instant(rows.get(proxy.ids["power"],{}).get("last_reported") or rows.get(proxy.ids["power"],{}).get("last_updated")) for _,_,proxy in self.controllers]
        times["car"]=min(car_times) if all(car_times) else None
        cars={identity:(actual[identity],instant(rows.get(proxy.ids["power"],{}).get("last_reported") or rows.get(proxy.ids["power"],{}).get("last_updated")))
              for identity,_,proxy in self.controllers}
        self.flow_display=self.fleet_alignment.update(self.live,times,now,True,bool(opts["heat_entity"]),self.display,cars=cars)
        for payload in snapshots:
            payload["live"]={**payload["live"],"grid":grid,"house":self.live["house"]}
        self.history.write(now,self.live)
        if not self.armed or not any(app.owned for _,app,_ in self.controllers):
            return
        self.control_step="battery_control"
        battery=self.battery_driver.read(rows,now)
        order=current_instruction(self.plan,opts["battery_resource"],now)
        command=battery_command(order,battery.soc,{**opts,"battery_min_soc":self.config.daily["battery_min_soc"],
            "battery_max_soc":self.config.daily["battery_max_soc"]},self.config.daily["battery_pv_support"] and
            any(app.pv_session and app.config.wallbox.read(rows,now).charging for _,app,_ in self.controllers),
            grid,battery.discharge,battery.charge)
        if command is None:
            self.battery_driver.release(rows)
        else:
            self.battery_driver.apply(command,rows)

    def release(self,states,now):
        errors=[]
        for key,app,_ in self.controllers:
            try:
                app.config.wallbox.pause(app.config.wallbox.read(states,now))
            except Exception as error:
                errors.append(error)
            app.pv_session=False
            app.phase_target=app.candidate=None
            self.targets[key]=0
        try:
            self.battery_driver.release(states)
        except Exception as error:
            errors.append(error)
        if errors:
            raise errors[0]
        for _,app,_ in self.controllers:
            app.owned=False

    def vehicle_histories(self,now):
        keys={"time","car","car_soc","car_actual_mode","car_mode","car_status","solar","price"}
        return {identity:[{key:value for key,value in row.items() if key in keys}
                          for row in (self.primary_history if app is self else app.history).read(now)]
                for identity,app,_ in self.controllers}

    def snapshot(self,now):
        result=Controller.snapshot(self,now)
        result["vehicles"]=self.vehicle_snapshots
        result["vehicle_name"]="E-Autos"
        result["forecast"]=[{k:v for k,v in row.items() if k not in {"car","car_soc"}} for row in result["forecast"]]
        return result

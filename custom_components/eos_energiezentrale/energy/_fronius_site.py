"""One metered Fronius site with read-only PV units and a storage pool."""
from dataclasses import dataclass
import ipaddress
from math import floor
import re
from datetime import datetime, timezone

from .contracts import BatteryReading, Measurement
from .domain import BatteryCommand
from ._modbus_tcp import ModbusError
from .sanitiser import bounded
from .storage_pool import distribute, total


def capacity(value, optional=False):
    result=bounded(value,0 if optional else 100,1000000)
    if result is None or 0<result<100:
        raise ValueError('Battery capacity must be 100..1000000 Wh')
    return result or None


def endpoint(driver):
    host=driver.client.host.lower()
    try:
        host=ipaddress.ip_address(host).compressed
    except ValueError:
        pass
    return host,driver.client.port,driver.client.unit


@dataclass(frozen=True)
class Device:
    name: str
    driver: object
    battery: bool
    capacity_wh: float | None



class FroniusSite:
    def __init__(self,primary,entries,primary_capacity,factory):
        if not isinstance(entries,dict) or not 1<=len(entries)<=7:
            raise ValueError('Configure up to seven additional inverters')
        self.primary=primary
        self.devices=[Device('primary',primary,True,primary_capacity)]
        seen={endpoint(primary)}
        allowed={'host','port','unit_id','battery','capacity_wh'}
        for name,settings in entries.items():
            if (not isinstance(name,str) or name=='primary' or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}',name)
                    or not isinstance(settings,dict) or settings.keys()-allowed):
                raise ValueError('Invalid inverter definition')
            battery=settings.get('battery',False)
            if type(battery) is not bool:
                raise ValueError('Inverter battery flag must be boolean')
            size=capacity(settings.get('capacity_wh')) if battery else None
            if not battery and 'capacity_wh' in settings:
                raise ValueError('PV-only inverters do not have a battery capacity')
            driver=factory(None,{**{key:settings[key] for key in ('host','port','unit_id') if key in settings},
                                 'grid_meter_enabled':False,
                                 'grid_discharge_supported':primary.features.grid_discharge})
            key=endpoint(driver)
            if key in seen: raise ValueError('Duplicate inverter endpoint')
            seen.add(key)
            self.devices.append(Device(name,driver,battery,size))
        self.batteries=[device for device in self.devices if device.battery]
        if len(self.batteries)>1 and primary_capacity is None:
            raise ValueError('Primary battery capacity is required for a storage pool')
        sizes=[device.capacity_wh for device in self.batteries]
        self.capacity_wh=total(sizes)
        if self.capacity_wh is not None and self.capacity_wh>1000000:
            raise ValueError('Combined battery capacity exceeds 1000000 Wh')
        self.summary={'inverter_count':len(self.devices),'battery_count':len(self.batteries),
                      'capacity_wh':self.capacity_wh,'devices':[], 'approximate':len(self.batteries)>1}
        self.direction=None
        self.targets={}
        self.control_states={}

    def read(self,states,now):
        snapshots=[]
        battery_values=[]
        solars,acs=[],[]
        for device in self.devices:
            driver=device.driver
            reading=None
            try:
                if device.battery:
                    reading=driver._read_single(states,now,include_grid=False)
                    solar=reading.measurements['solar'].value
                    ac=driver._ac_power()
                else:
                    solar,ac=driver._generation()
            except (OSError,ValueError):
                driver._invalidate()
                solar=ac=None
            if device.battery:
                battery_values.append((device,reading))
            solars.append(solar);acs.append(ac)
            snapshots.append({'name':device.name,'battery':device.battery,'capacity_wh':device.capacity_wh,
                              'solar':solar,'ac':ac,'soc':reading.soc if reading else None,
                              'available':solar is not None and ac is not None and
                                 (not device.battery or reading is not None and
                                  all(value is not None for value in (reading.soc,reading.charge,reading.discharge)))})
        self.summary['devices']=snapshots
        socs=[reading.soc if reading else None for _,reading in battery_values]
        if len(battery_values)==1:
            soc=socs[0]
        else:
            weighted=total([soc*device.capacity_wh if soc is not None else None
                            for (device,_),soc in zip(battery_values,socs)])
            soc=weighted/self.capacity_wh if weighted is not None else None
        charge=total([reading.charge if reading else None for _,reading in battery_values])
        discharge=total([reading.discharge if reading else None for _,reading in battery_values])
        solar=total(solars)
        extra={'solar':Measurement(solar,now if solar is not None else None)}
        if 'grid' in self.primary.measurement_keys:
            try:
                grid=self.primary._grid_power()
            except (OSError,ValueError):
                self.primary.grid_model=None
                grid=None
            ac=total(acs)
            house=ac+grid if ac is not None and grid is not None else None
            if house is not None and not 0<=house<=1000000: house=None
            extra.update(grid=Measurement(grid,now if grid is not None else None),
                         house_total=Measurement(house,now if house is not None else None))
        return BatteryReading(soc,charge,discharge,now if soc is not None else None,
                              now if charge is not None else None,now if discharge is not None else None,extra)

    def apply(self,command,states):
        if len(self.batteries)==1:
            return self.primary._apply_single(command,states)
        if command.min_soc is None or command.max_soc is None:
            raise ValueError('Storage pool requires per-device SoC bounds')
        if (command.mode=='limits' and command.charge_w>0 and command.discharge_w>0
                and command.net_demand_w is None):
            raise ValueError('Storage pool requires common net demand')
        try:
            self._dispatch(command,states)
        except Exception:
            # Attempt every storage device; an unreachable unit cannot mask an
            # unconfirmed command or prevent the other units returning to auto.
            try: self.release(states)
            except (OSError,ValueError): pass
            raise

    def _dispatch(self,command,states):
        readings=[];references=[];control_data=[]
        for device in self.batteries:
            reading=device.driver._read_single(states,datetime.now(timezone.utc),include_grid=False)
            if any(value is None for value in (reading.soc,reading.charge,reading.discharge)):
                raise ModbusError('Incomplete storage pool telemetry')
            data=device.driver._storage()
            reference=device.driver._scaled(data[0],data[16],1000000)
            if (reference is None or reference<=0 or data[3] not in (0,1,2,3)
                    or data[15] not in (0,1) or not -2<=signed_scale(data[23])<=0):
                raise ModbusError('Invalid storage control reference')
            readings.append(reading);references.append(reference)
            control_data.append(data)
        charging=command.charge_w
        discharging=command.discharge_w
        if command.mode=='block_discharge' or command.mode=='grid_charge': discharging=0
        if command.mode=='grid_discharge': charging=0
        if command.mode in ('limits','block_discharge') and command.net_demand_w is not None:
            charging=min(charging,max(0,-command.net_demand_w))
            discharging=min(discharging,max(0,command.net_demand_w))
        charge_caps=[limit if reading.soc<command.max_soc else 0 for reading,limit in zip(readings,references)]
        discharge_caps=[limit if reading.soc>command.min_soc else 0 for reading,limit in zip(readings,references)]
        charge=distribute(charging,charge_caps,[device.capacity_wh*max(0,command.max_soc-reading.soc)
                            for device,reading in zip(self.batteries,readings)])
        discharge=distribute(discharging,discharge_caps,[device.capacity_wh*max(0,reading.soc-command.min_soc)
                            for device,reading in zip(self.batteries,readings)])
        if sum(discharge)+.000001<command.required_discharge_w:
            raise ModbusError('Storage pool cannot provide required PV charging support')
        direction='charge' if charging>0 else 'discharge' if discharging>0 else 'hold'
        unchanged=all(self.control_states.get(device.name)==
                      (reference,data[3],data[10],data[11],data[15],data[23])
                      for device,reference,data in zip(self.batteries,references,control_data))
        if direction!=self.direction or not unchanged:
            for device in self.batteries:
                device.driver._apply_single(BatteryCommand('limits'),states)
        commands={device.name:BatteryCommand(command.mode if charge[index] or discharge[index] else 'limits',
                                             charge[index],discharge[index])
                  for index,device in enumerate(self.batteries)}
        # Confirm reductions before spending that budget on another battery.
        ordered=sorted(self.batteries,key=lambda device: commands[device.name].charge_w+
                       commands[device.name].discharge_w>self.targets.get(device.name,0))
        for device in ordered:
            device.driver._apply_single(commands[device.name],states)
        self.direction=direction
        self.targets={name:value.charge_w+value.discharge_w for name,value in commands.items()}
        self.control_states={}
        for device,reference,data in zip(self.batteries,references,control_data):
            requested=commands[device.name]
            scale=10**signed_scale(data[23])
            incoming=floor(min(100,requested.charge_w/reference*100)/scale+1e-9)
            outgoing=floor(min(100,requested.discharge_w/reference*100)/scale+1e-9)
            if requested.mode=='grid_charge': outgoing=-incoming
            if requested.mode=='grid_discharge': incoming=-outgoing
            self.control_states[device.name]=(reference,3,outgoing&65535,incoming&65535,
                                               int(requested.mode=='grid_charge'),data[23])

    def release(self,states):
        errors=[]
        for device in self.batteries:
            try: device.driver._release_single(states)
            except (OSError,ValueError) as error: errors.append(error)
        self.direction=None
        self.targets={}
        self.control_states={}
        if errors: raise errors[0]


def signed_scale(value):
    return value-65536 if value>=32768 else value

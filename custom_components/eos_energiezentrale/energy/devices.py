"""Plugin-independent device configuration and conservative storage dispatch."""
from copy import deepcopy
from dataclasses import fields, replace
from datetime import datetime, timezone
import json
import re

from .contracts import BatteryDriver, BatteryFeatures, BatteryReading, PluginInfo, Measurement
from .domain import BatteryCommand
from .drivers import BATTERY_DRIVERS, INVERTER_DRIVERS
from .plugin_registry import describe
from .plugin_parameters import parameters
from .sanitiser import bounded
from .storage_pool import distribute, total

REGISTRIES = {'battery': BATTERY_DRIVERS, 'inverter': INVERTER_DRIVERS}


def device_rows(options):
    """Convert legacy configuration for editing, never mutate saved options."""
    raw=options.get('devices', 'null')
    rows=json.loads(raw) if isinstance(raw,str) else deepcopy(raw)
    if rows is not None:
        return rows
    params=parameters(BATTERY_DRIVERS[options['battery_type']].configuration,json.loads(options['battery_parameters']))
    extras=params.pop('additional_inverters', {}) if options['battery_type']=='fronius_modbus' else {}
    size=params.pop('battery_capacity_wh', 0) if options['battery_type']=='fronius_modbus' else 0
    rows=[{'id':'primary','name':'Primary','kind':'battery','plugin':options['battery_type'],
           'parameters':params,'capacity_wh':size,
           'charge_w':options['battery_charge_w'],'discharge_w':options['battery_discharge_w'],
           'grid_source':options['battery_type']=='fronius_modbus' and params.get('grid_meter_enabled',True)}]
    for name, settings in extras.items():
        battery=settings.get('battery',False)
        rows.append({'id':name,'name':name,'kind':'battery' if battery else 'inverter','plugin':'fronius_modbus',
                     'parameters':{key:value for key,value in settings.items() if key in {'host','port','unit_id'}} |
                                  {'grid_meter_enabled':False} |
                                  ({'grid_discharge_supported':params.get('grid_discharge_supported',False)} if battery else {}),
                     **({'capacity_wh':settings['capacity_wh'],'charge_w':options['battery_charge_w'],
                         'discharge_w':options['battery_discharge_w']} if battery else {}), 'grid_source':False})
    return rows


class DeviceSite(BatteryDriver):
    info=PluginInfo('devices','Configured devices','battery')
    configuration=()
    ids=dict.fromkeys(('soc','charge_power','discharge_power','mode'),'')

    def __init__(self,ha,rows):
        if not isinstance(rows,list) or len(rows)>8:
            raise ValueError('Configure up to eight storage/inverter devices')
        self.devices=[]
        seen=set();entities=set();endpoints=set()
        for supplied in rows:
            if not isinstance(supplied,dict) or supplied.keys()-{
                'id','name','kind','plugin','parameters','capacity_wh','charge_w','discharge_w','grid_source'}:
                raise ValueError('Invalid device definition')
            row=deepcopy(supplied)
            identity=row.get('id');name=row.get('name')
            if (not isinstance(identity,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,32}',identity) or identity in seen
                    or not isinstance(name,str) or not 1<=len(name.strip())<=60 or any(ord(c)<32 or ord(c)==127 for c in name)):
                raise ValueError('Invalid device identity/name')
            seen.add(identity)
            registry=REGISTRIES.get(row.get('kind'),{})
            if row.get('plugin') not in registry or type(row.get('grid_source',False)) is not bool:
                raise ValueError('Invalid device plugin/source')
            params=row.get('parameters',{})
            if not isinstance(params,dict) or params.get('additional_inverters'):
                raise ValueError('Devices must be configured individually')
            if any(field.key=='grid_meter_enabled' for field in registry[row['plugin']].configuration):
                params={**params,'grid_meter_enabled':row.get('grid_source',False)}
            driver=registry[row['plugin']](ha,params)
            assigned={value for value in driver.ids.values() if value}
            if assigned & entities:
                raise ValueError('Device entities cannot be shared')
            entities|=assigned
            key=getattr(driver,'device_key',None)
            if key is not None:
                if key in endpoints: raise ValueError('Duplicate physical device')
                endpoints.add(key)
            if row.get('grid_source') and 'grid' not in driver.measurement_keys:
                raise ValueError('Device does not provide grid power')
            if row['kind']=='battery':
                for key in ('capacity_wh','charge_w','discharge_w'):
                    value=bounded(row.get(key,0),0,1000000)
                    if value is None or key=='capacity_wh' and 0<value<100:
                        raise ValueError('Invalid storage capacity/power')
                    row[key]=value
            self.devices.append((row,driver))
        self.batteries=[(row,driver) for row,driver in self.devices if row['kind']=='battery']
        self.requires_dispatch_context=len(self.batteries)>1
        self.uses_dispatch_context=any(driver.uses_dispatch_context for _,driver in self.batteries)
        sizes=[row['capacity_wh'] or None for row,_ in self.batteries]
        size=total(sizes)
        if self.requires_dispatch_context and size is None or size is not None and size>1000000:
            raise ValueError('Every pooled battery needs a capacity; combined limit is 1000000 Wh')
        self.grid_sources=[(row,driver) for row,driver in self.devices if row.get('grid_source')]
        if len(self.grid_sources)>1: raise ValueError('Choose one common grid meter')
        self.features=BatteryFeatures(**{field.name:bool(self.batteries) and all(
            getattr(driver.features,field.name) for _,driver in self.batteries) for field in fields(BatteryFeatures)})
        keys=set(BatteryDriver.measurement_keys if self.batteries else ())
        if any('solar' in driver.measurement_keys for _,driver in self.devices): keys.add('solar')
        if self.grid_sources:
            keys.add('grid')
            if all('inverter_ac' in driver.measurement_keys for _,driver in self.devices): keys.add('house_total')
        self.measurement_keys=tuple(sorted(keys))
        self.site_summary={'inverter_count':len(self.devices),'battery_count':len(self.batteries),
                           'capacity_wh':size,'devices':[],'approximate':self.requires_dispatch_context}

    def _read(self,states,now):
        samples=[];snapshots=[]
        for row,driver in self.devices:
            try: value=driver.read(states,now)
            except (OSError,ValueError): value=None
            measurements=value.measurements if value else {}
            def get(key):
                return measurements[key].value if key in measurements else None
            snapshots.append({'name':row['name'],'id':row['id'],'battery':row['kind']=='battery',
                'capacity_wh':row.get('capacity_wh'),'solar':get('solar'),'ac':get('inverter_ac'),
                'soc':value.soc if isinstance(value,BatteryReading) else None,
                'available':value is not None and all(item.value is not None for item in measurements.values()) and
                    (not isinstance(value,BatteryReading) or all(item is not None for item in (value.soc,value.charge,value.discharge))),
                'plugin':describe(driver)})
            samples.append((row,driver,value))
        self.site_summary['devices']=snapshots
        batteries=[(row,value) for row,_,value in samples if row['kind']=='battery']
        socs=[value.soc if value else None for _,value in batteries]
        soc=socs[0] if len(socs)==1 else None
        if len(socs)>1 and all(value is not None for value in socs):
            soc=sum(row['capacity_wh']*value for (row,_),value in zip(batteries,socs))/self.site_summary['capacity_wh']
        charge=total([value.charge if value else None for _,value in batteries])
        discharge=total([value.discharge if value else None for _,value in batteries])
        extra={}
        def values(key):
            return [value.measurements.get(key,Measurement(None,None)).value if value else None
                    for _,driver,value in samples if key in driver.measurement_keys]
        def sample_time(key):
            stamps=[value.measurements[key].sample for _,driver,value in samples
                    if key in driver.measurement_keys and value and key in value.measurements]
            return min(stamps) if stamps and all(stamp is not None for stamp in stamps) else None
        stamps={}
        if 'solar' in self.measurement_keys: extra['solar']=total(values('solar'))
        stamps['solar']=sample_time('solar')
        if self.grid_sources:
            extra['grid']=next((value.measurements.get('grid',Measurement(None,None)).value if value else None
                for row,_,value in samples if row.get('grid_source')))
            stamps['grid']=next((value.measurements.get('grid',Measurement(None,None)).sample if value else None
                for row,_,value in samples if row.get('grid_source')))
            if 'house_total' in self.measurement_keys:
                ac=total(values('inverter_ac'));grid=extra['grid']
                extra['house_total']=bounded(ac+grid,0,1000000) if ac is not None and grid is not None else None
                ac_time=sample_time('inverter_ac')
                stamps['house_total']=min(ac_time,stamps['grid']) if ac_time and stamps['grid'] else None
        def battery_time(key):
            times=[getattr(value,key) if value else None for _,value in batteries]
            return min(times) if times and all(stamp is not None for stamp in times) else None
        return BatteryReading(soc,charge,discharge,battery_time('soc_sample'),battery_time('charge_sample'),battery_time('discharge_sample'),
            {key:Measurement(value,stamps.get(key)) for key,value in extra.items()})

    def _apply(self,command,states):
        if not self.batteries: raise ValueError('No battery configured')
        if len(self.batteries)==1:
            row,driver=self.batteries[0]
            return driver.apply(replace(command,charge_w=min(command.charge_w,row['charge_w']),
                                        discharge_w=min(command.discharge_w,row['discharge_w'])),states)
        if command.min_soc is None or command.max_soc is None:
            raise ValueError('Storage group requires individual SoC bounds')
        try:
            now=datetime.now(timezone.utc)
            readings=[driver.read(states,now) for _,driver in self.batteries]
            if any(any(value is None for value in (reading.soc,reading.charge,reading.discharge)) for reading in readings):
                raise ValueError('Incomplete storage telemetry')
            caps=[]
            for row,driver in self.batteries:
                limits=driver.power_limits(states)
                if limits is None: limits=(row['charge_w'],row['discharge_w'])
                if len(limits)!=2 or any(bounded(value,0,1000000) is None for value in limits):
                    raise ValueError('Invalid storage power limits')
                caps.append((min(row['charge_w'],limits[0]),min(row['discharge_w'],limits[1])))
            charge=command.charge_w if command.mode!='grid_discharge' else 0
            discharge=command.discharge_w if command.mode not in {'grid_charge','block_discharge'} else 0
            if command.mode in {'limits','block_discharge'}:
                if charge and discharge and command.net_demand_w is None: raise ValueError('Common grid demand missing')
                if command.net_demand_w is not None:
                    charge=min(charge,max(0,-command.net_demand_w));discharge=min(discharge,max(0,command.net_demand_w))
            incoming=distribute(charge,[cap[0] if reading.soc<command.max_soc else 0
                for cap,reading in zip(caps,readings)],
                [row['capacity_wh']*max(0,command.max_soc-reading.soc) for (row,_),reading in zip(self.batteries,readings)])
            outgoing=distribute(discharge,[cap[1] if reading.soc>command.min_soc else 0
                for cap,reading in zip(caps,readings)],
                [row['capacity_wh']*max(0,reading.soc-command.min_soc) for (row,_),reading in zip(self.batteries,readings)])
            if sum(outgoing)+1e-6<command.required_discharge_w: raise ValueError('Insufficient storage support')
            # Across unrelated plugins no common hardware-state cache exists.
            # Confirm a neutral state everywhere before assigning a new budget.
            for _,driver in self.batteries: driver.apply(BatteryCommand('limits'),states)
            for index,(_,driver) in enumerate(self.batteries):
                driver.apply(replace(command,mode=command.mode if incoming[index] or outgoing[index] else 'limits',
                    charge_w=incoming[index],discharge_w=outgoing[index],required_discharge_w=0),states)
        except Exception:
            try: self._release(states)
            except (OSError,ValueError,RuntimeError): pass
            raise

    def _release(self,states):
        errors=[]
        for _,driver in self.batteries:
            try: driver.release(states)
            except (OSError,ValueError,RuntimeError) as error: errors.append(error)
        if errors: raise errors[0]


def battery_driver(options,ha):
    raw=options.get('devices','null')
    rows=json.loads(raw) if isinstance(raw,str) else raw
    return DeviceSite(ha,rows) if rows is not None else BATTERY_DRIVERS[options['battery_type']](ha,json.loads(options['battery_parameters']))

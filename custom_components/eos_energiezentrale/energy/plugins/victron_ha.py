"""Victron Venus MQTT (HACS) entity adapter, ESS Mode 2 only."""
from datetime import datetime,timezone
from math import ceil,floor

from ..clients import reading,report_time
from ..contracts import BatteryDriver,BatteryFeatures,BatteryReading,PluginInfo,PluginField,Measurement,UnsupportedFeature
from ..device_io import confirmed_state,DeviceNotReady
from ..domain import number
from ..plugin_parameters import parameters


class VictronHA(BatteryDriver):
    info=PluginInfo('victron_ha','Victron Venus MQTT / HACS (Home Assistant)','battery')
    uses_dispatch_context=True
    soc_max_age=360
    configuration=(
        PluginField('soc','Battery SoC (%)',domains=('sensor',)),
        PluginField('battery_power','Signed battery DC power (+ charging)',domains=('sensor',)),
        PluginField('battery_voltage','Battery voltage (required for A-based charge limit)',required=False,default='',domains=('sensor',)),
        PluginField('grid','Total grid power (+ import)',required=False,default='',domains=('sensor',)),
        PluginField('solar','Total PV power (optional)',required=False,default='',domains=('sensor',)),
        PluginField('house_total','Total AC consumption including EV/heat (optional)',required=False,default='',domains=('sensor',)),
        PluginField('inverter_ac','Signed inverter AC output (+ generation, optional)',required=False,default='',domains=('sensor',)),
        PluginField('control_enabled','Enable ESS Mode 2 control','boolean',default=False),
        PluginField('ess_mode','ESS user mode (optimized, not Hub4)',required=False,default='',domains=('select',)),
        PluginField('ess_mode_option','Required ESS user mode','choice',default='optimized_no_battery_life',choices=('optimized_no_battery_life','optimized_battery_life')),
        PluginField('grid_setpoint','ESS AC grid power setpoint (W)',required=False,default='',domains=('number',)),
        PluginField('charge_limit','ESS max charge current (A) or charge power (W)',required=False,default='',domains=('number',)),
        PluginField('discharge_limit','ESS max inverter power (W)',required=False,default='',domains=('number',)),
        PluginField('release_setpoint','Grid setpoint on release (W)','number',default=50),
        PluginField('release_charge_limit','Native charge limit on release (A or W/kW)','number',required=False,default=None),
        PluginField('release_discharge_limit','Native discharge limit on release (W/kW)','number',required=False,default=None),
        PluginField('charge_efficiency','AC/DC charge efficiency','number',default=.95),
        PluginField('discharge_efficiency','DC/AC discharge efficiency','number',default=.95),
        PluginField('grid_discharge_supported','Allow forced grid export','boolean',default=False),
    )

    def __init__(self,ha,params):
        self.ha=ha;self.values=parameters(self.configuration,params)
        self.ids={key:self.values[key] for key in ('soc','battery_power','battery_voltage','grid','solar','house_total','inverter_ac',
                                                   'ess_mode','grid_setpoint','charge_limit','discharge_limit')}
        # A signed DC sensor is not two independent AC history measurements.
        self.ids.update(charge_power='',discharge_power='',mode=self.ids['ess_mode'])
        self.enabled=self.values['control_enabled']
        self.provides_site_consumption=bool(self.ids['house_total'])
        for key in ('charge_efficiency','discharge_efficiency'):
            if not .1<=self.values[key]<=1: raise ValueError('Invalid Victron efficiency')
        if not -1000000<=self.values['release_setpoint']<=1000000: raise ValueError('Invalid release setpoint')
        if self.enabled:
            if any(not self.ids[key] for key in ('grid','ess_mode','grid_setpoint','charge_limit','discharge_limit')):
                raise ValueError('Victron ESS control entities are required')
            if any(self.values[key] is None or not -1<=self.values[key]<=1000000 for key in ('release_charge_limit','release_discharge_limit')):
                raise ValueError('Explicit native release limits are required')
        controls=[self.ids[key] for key in ('grid_setpoint','charge_limit','discharge_limit') if self.ids[key]]
        if len(controls)!=len(set(controls)): raise ValueError('Victron controls must be distinct')
        self.features=BatteryFeatures(charge_limit=self.enabled,discharge_limit=self.enabled,grid_charge=self.enabled,
                                      grid_discharge=self.enabled and self.values['grid_discharge_supported'])
        self.measurement_keys=BatteryDriver.measurement_keys+tuple(key for key in ('grid','solar','house_total','inverter_ac') if self.ids[key])

    def _read(self,states,now):
        soc=reading(states,self.ids['soc'],now,'soc',self.soc_max_age)
        if states.get(self.ids['soc'],{}).get('attributes',{}).get('unit_of_measurement')!='%': soc=None
        power=reading(states,self.ids['battery_power'],now,'power',120)
        sample=report_time(states,self.ids['battery_power'])
        return BatteryReading(soc,max(0,power)/self.values['charge_efficiency'] if power is not None else None,
            max(0,-power)*self.values['discharge_efficiency'] if power is not None else None,
            report_time(states,self.ids['soc']),sample,sample,
            {key:Measurement(reading(states,self.ids[key],now,'power',45),report_time(states,self.ids[key]))
             for key in ('grid','solar','house_total','inverter_ac') if self.ids[key]})

    def _number(self,key):
        entity=self.ids[key];row=self.ha.state(entity);attrs=row.get('attributes',{})
        value,low,high,step=(number(row.get('state')),number(attrs.get('min')),number(attrs.get('max')),number(attrs.get('step')))
        if value is None: raise DeviceNotReady(entity)
        if low is None or high is None or step is None or low>0 or high<=0 or step<=0 or step>high-low:
            raise ValueError('Victron control requires finite min/max/step')
        return row,value,low,high,step

    def _write(self,key,target,prepared=None):
        row,actual,low,high,step=prepared or self._number(key)
        if not low-1e-6<=target<=high+1e-6: raise ValueError('Victron control target outside entity bounds')
        if abs(actual-target)<min(step/2,.0001): return
        entity=self.ids[key];self.ha.set(entity,target)
        confirmed_state(self.ha,entity,lambda value:number(value.get('state')) is not None and abs(float(value['state'])-target)<min(step/2,.0001))

    def _voltage(self,states,now):
        entity=self.ids['battery_voltage']
        row=states.get(entity,{})
        value=reading(states,entity,now,'voltage',120)
        if row.get('attributes',{}).get('unit_of_measurement')!='V' or value is None or not 10<=value<=1000:
            raise DeviceNotReady(entity or self.ids['charge_limit'])
        return value

    def _limits(self,states,now):
        charge=self._number('charge_limit');discharge=self._number('discharge_limit')
        unit=charge[0].get('attributes',{}).get('unit_of_measurement')
        scale=self._voltage(states,now)/self.values['charge_efficiency'] if unit=='A' else {'W':1,'kW':1000}.get(unit)
        outgoing={'W':1,'kW':1000}.get(discharge[0].get('attributes',{}).get('unit_of_measurement'))
        if scale is None or outgoing is None: raise ValueError('Invalid Victron limit units')
        return charge,discharge,scale,outgoing

    def power_limits(self,states):
        if not self.enabled: return None
        charge,discharge,incoming,outgoing=self._limits(states,datetime.now(timezone.utc))
        return min(1000000,charge[3]*incoming),min(1000000,discharge[3]*outgoing)

    @staticmethod
    def _floor_limit(watts,scale,control):
        # Victron reserves -1 for unlimited. Rounding down must never produce it.
        return max(0,floor(min(control[3],watts/scale)/control[4]+1e-9)*control[4])

    def _apply(self,command,states):
        if not self.enabled: raise UnsupportedFeature('Victron is read-only')
        # Read one new state batch: stale input passed by a caller is never a write basis.
        states={entity:self.ha.state(entity) for entity in set(self.ids.values()) if entity}
        now=datetime.now(timezone.utc);reading_now=self.read(states,now)
        grid=reading(states,self.ids['grid'],now,'power',45)
        if any(value is None for value in (reading_now.soc,reading_now.charge,reading_now.discharge,grid)):
            raise DeviceNotReady(self.ids['battery_power'])
        mode=self.ha.state(self.ids['ess_mode'])
        if mode.get('state')!=self.values['ess_mode_option'] or mode.get('state') not in mode.get('attributes',{}).get('options',[]):
            raise ValueError('Victron requires the configured optimized ESS user mode')
        charge,discharge,incoming,outgoing=self._limits(states,now)
        setpoint=self._number('grid_setpoint')
        if setpoint[0].get('attributes',{}).get('unit_of_measurement')!='W': raise ValueError('Victron setpoint must use W')
        if command.min_soc is None or command.max_soc is None: raise ValueError('Victron requires SoC bounds')
        charge_w=command.charge_w if reading_now.soc<command.max_soc else 0
        discharge_w=command.discharge_w if reading_now.soc>command.min_soc else 0
        if command.mode in {'grid_charge','block_discharge'}: discharge_w=0
        if command.mode=='grid_discharge': charge_w=0
        charge_target=self._floor_limit(charge_w,incoming,charge)
        discharge_target=self._floor_limit(discharge_w,outgoing,discharge)
        if discharge_target*outgoing+1e-6<command.required_discharge_w: raise ValueError('Victron discharge support unavailable')
        demand=grid+reading_now.discharge-reading_now.charge
        if command.mode=='grid_charge': desired=-charge_target*incoming
        elif command.mode=='grid_discharge': desired=discharge_target*outgoing
        else: desired=min(discharge_target*outgoing,max(0,demand))-min(charge_target*incoming,max(0,-demand))
        target=demand-desired
        # Bias toward import: quantisation must never request more export.
        target=ceil(target/setpoint[4]-1e-9)*setpoint[4]
        if not setpoint[2]<=target<=setpoint[3]: raise ValueError('Victron setpoint cannot realise requested budget')
        # Validate all release values before taking ownership, including -1 sentinels.
        for key,control in (('release_charge_limit',charge),('release_discharge_limit',discharge),('release_setpoint',setpoint)):
            if not control[2]<=self.values[key]<=control[3]: raise ValueError('Invalid Victron release value')
        self._write('charge_limit',charge_target,charge)
        self._write('discharge_limit',discharge_target,discharge)
        self._write('grid_setpoint',target,setpoint)

    def _release(self,states):
        if not self.enabled: return
        # Explicit fallback values also work after a restart, when in-memory ownership is lost.
        controls={key:self._number(key) for key in ('grid_setpoint','charge_limit','discharge_limit')}
        values={'grid_setpoint':self.values['release_setpoint'],'charge_limit':self.values['release_charge_limit'],
                'discharge_limit':self.values['release_discharge_limit']}
        if (controls['grid_setpoint'][0].get('attributes',{}).get('unit_of_measurement')!='W'
                or controls['charge_limit'][0].get('attributes',{}).get('unit_of_measurement') not in {'A','W','kW'}
                or controls['discharge_limit'][0].get('attributes',{}).get('unit_of_measurement') not in {'W','kW'}):
            raise ValueError('Invalid Victron release units')
        for key,control in controls.items():
            if not control[2]<=values[key]<=control[3]: raise ValueError('Invalid Victron release value')
        self._write('grid_setpoint',values['grid_setpoint'],controls['grid_setpoint'])
        for key in ('charge_limit','discharge_limit'): self._write(key,values[key],controls[key])


PLUGINS=(VictronHA,)

"""Direct GX system registers / ESS Mode 2, Venus OS >= 3.50.

Register types/scales: Victron CCGX-Modbus-TCP-register-list-3.81.xlsx.
https://www.victronenergy.com/live/ess:ess_mode_2_and_3
No Mode 3, firmware changes, MQTT or Home Assistant entity dependency.
"""
from datetime import datetime,timezone
import ipaddress
from math import ceil,floor
import re
import struct
from time import monotonic

from .._modbus_tcp import ModbusTCP,ModbusError,checked_host
from ..contracts import BatteryDriver,BatteryFeatures,BatteryReading,Measurement,PluginField,PluginInfo
from ..plugin_parameters import parameters


def signed(word):
    return word-65536 if word>=32768 else word


class VictronModbus(BatteryDriver):
    info=PluginInfo('victron_modbus','Victron GX direct Modbus TCP','battery')
    uses_dispatch_context=True
    ids=dict.fromkeys(('soc','charge_power','discharge_power','mode'),'')
    configuration=(
        PluginField('host','GX hostname / IP','text'),
        PluginField('port','GX Modbus TCP port','number',default=502),
        PluginField('phases','System phases','choice',default='3',choices=('1','3')),
        PluginField('grid_meter_enabled','Provide common grid / consumption measurements','boolean',default=True),
        PluginField('read_consumption','Read system AC consumption','boolean',default=True),
        PluginField('dc_pv_enabled','Read DC-coupled PV','boolean',default=True),
        PluginField('ac_pv_input_enabled','Read AC PV on grid input','boolean',default=False),
        PluginField('ac_pv_output_enabled','Read AC PV on inverter output','boolean',default=False),
        PluginField('control_enabled','Enable ESS Mode 2 control (requires DVCC)','boolean',default=False),
        PluginField('max_charge_current','Allowed system charge current (A DC)','number',default=100),
        PluginField('max_discharge_power','Allowed inverter power (W, steps of 10)','number',default=5000),
        PluginField('release_setpoint','Native grid setpoint on release (W)','number',default=50),
        PluginField('release_charge_current','Native charge current on release (A DC, -1 unlimited)','number',required=False),
        PluginField('release_discharge_power','Native inverter limit on release (W, finite, steps of 10)','number',required=False),
        PluginField('charge_efficiency','AC/DC charge efficiency','number',default=.95),
        PluginField('discharge_efficiency','DC/AC discharge efficiency','number',default=.95),
        PluginField('grid_discharge_supported','Allow forced battery export','boolean',default=False),
    )

    def __init__(self,ha,params):
        self.values=v=parameters(self.configuration,params)
        host=checked_host(v['host'])
        if v['port']!=int(v['port']) or not 1<=v['port']<=65535: raise ValueError('Invalid Modbus port')
        self.client=ModbusTCP(host,int(v['port']),100)
        self.phases=int(v['phases']);self.enabled=v['control_enabled']
        for key in ('charge_efficiency','discharge_efficiency'):
            if not .1<=v[key]<=1: raise ValueError('Invalid Victron efficiency')
        for key,low,high,step in (('max_charge_current',1,32766,1),('max_discharge_power',10,327660,10),
                                  ('release_setpoint',-1000000,1000000,1),
                                  ('release_charge_current',-1,32766,1),('release_discharge_power',0,327660,10)):
            value=v[key]
            if value is None:
                if self.enabled: raise ValueError('Explicit Victron release limits are required')
            elif not low<=value<=high or value/step!=int(value/step): raise ValueError('Invalid Victron limit')
        self.features=BatteryFeatures(self.enabled,self.enabled,self.enabled,self.enabled and v['grid_discharge_supported'])
        self.provides_site_consumption=v['grid_meter_enabled'] and v['read_consumption']
        self.pv_sources=tuple((address,count) for key,address,count in (
            ('dc_pv_enabled',850,1),('ac_pv_input_enabled',811,self.phases),('ac_pv_output_enabled',808,self.phases)) if v[key])
        self.measurement_keys=BatteryDriver.measurement_keys+('solar',)*bool(self.pv_sources)+(
            ('grid',) if v['grid_meter_enabled'] else ())+('house_total',)*self.provides_site_consumption

    @property
    def device_key(self):
        host=self.client.host.lower()
        try: host=ipaddress.ip_address(host).compressed
        except ValueError: pass
        return f'modbus:{host}:{self.client.port}:100'

    def _identity(self):
        serial=struct.pack('>6H',*self.client.read(800,6)).decode('ascii',errors='replace')
        firmware=self.client.read(834,1)[0]
        if not re.fullmatch('[0-9a-fA-F]{12}',serial) or not 0x0350<=firmware<=0x0999:
            raise ModbusError('Expected Victron GX system / Venus OS >= 3.50')

    def _battery(self):
        voltage,_,power,soc=self.client.read(840,4)
        voltage/=10;power=signed(power)
        if not 10<=voltage<=1000 or not 0<=soc<=100 or not -32768<power<32766:
            raise ModbusError('Invalid or saturated GX battery telemetry')
        return voltage,power,soc

    def _power(self,address,count,signed_power=False):
        words=self.client.read(address,count)
        values=[signed(word) for word in words] if signed_power else words
        # The GX server can clamp to max-1; reject that endpoint as well.
        invalid=any(not -32768<value<32766 for value in values) if signed_power else any(value>=65534 for value in values)
        if invalid:
            raise ModbusError('Invalid or saturated GX phase power')
        return sum(values)

    def _telemetry(self,now,*,control=False):
        start=monotonic();self._identity()
        voltage,power,soc=self._battery()
        values={}
        if self.pv_sources:
            values['solar']=sum(self._power(address,count) for address,count in self.pv_sources)
        if self.values['grid_meter_enabled'] or control:
            values['grid']=self._power(820,self.phases,True)
        if self.provides_site_consumption:
            values['house_total']=self._power(817,self.phases)
        if monotonic()-start>10: raise ModbusError('GX telemetry snapshot took too long')
        charge=max(0,power)/self.values['charge_efficiency']
        discharge=max(0,-power)*self.values['discharge_efficiency']
        return voltage,BatteryReading(soc,charge,discharge,now,now,now,
            {key:Measurement(value,now) for key,value in values.items()})

    def _read(self,states,now):
        _,sample=self._telemetry(now)
        return sample

    def power_limits(self,states):
        if not self.enabled: return None
        self._identity();voltage,_,_=self._battery()
        return min(1000000,self.values['max_charge_current']*voltage/self.values['charge_efficiency']),self.values['max_discharge_power']

    def _guard(self,*,grid=False):
        settings=self.client.read(2900,3)
        if settings[2] not in (1,2) or settings[0] not in (*range(2,9),10,11,12):
            raise ModbusError('GX requires optimized ESS Mode 2')
        if self.client.read(5423,1)[0]!=0: raise ModbusError('Dynamic ESS must be disabled')
        if grid and self.client.read(826,1)[0]!=1: raise ModbusError('GX grid input is not connected')

    def _write(self,address,words):
        if self.client.read(address,len(words))!=words: self.client.write(address,words)

    def _setpoint(self,watts):
        raw=int(watts)&0xffffffff
        self._write(2716,[raw>>16,raw&65535])

    def _apply(self,command,states):
        voltage,sample=self._telemetry(datetime.now(timezone.utc),control=True)
        self._guard(grid=True)
        if command.min_soc is None or command.max_soc is None: raise ValueError('Victron requires SoC bounds')
        charge=command.charge_w if sample.soc<command.max_soc else 0
        discharge=command.discharge_w if sample.soc>command.min_soc else 0
        if command.mode in {'grid_charge','block_discharge'}: discharge=0
        if command.mode=='grid_discharge': charge=0
        amps=floor(min(self.values['max_charge_current'],charge*self.values['charge_efficiency']/voltage)+1e-9)
        outgoing=floor(min(self.values['max_discharge_power'],discharge)/10+1e-9)*10
        incoming=amps*voltage/self.values['charge_efficiency']
        if outgoing+1e-6<command.required_discharge_w: raise ValueError('Victron discharge support unavailable')
        demand=sample.measurements['grid'].value+sample.discharge-sample.charge
        if command.mode=='grid_charge': desired=-incoming
        elif command.mode=='grid_discharge': desired=outgoing
        else: desired=min(outgoing,max(0,demand))-min(incoming,max(0,-demand))
        target=ceil(demand-desired)
        if not -1000000<=target<=1000000: raise ValueError('GX setpoint outside supported range')
        self._write(2705,[amps])
        self._write(2704,[outgoing//10])
        self._setpoint(target)

    def _release(self,states):
        if not self.enabled: return
        self._identity();self._guard()
        # Explicit finite native power avoids the ambiguous -1 / 0.1 scaling
        # of legacy register 2704; no volatile process ownership is required.
        self._setpoint(self.values['release_setpoint'])
        self._write(2705,[int(self.values['release_charge_current'])&65535])
        self._write(2704,[int(self.values['release_discharge_power'])//10])


PLUGINS=(VictronModbus,)

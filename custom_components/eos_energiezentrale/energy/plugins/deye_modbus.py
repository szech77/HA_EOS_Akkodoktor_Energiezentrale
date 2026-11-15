"""Deye SUN-12K-SG04LP3-EU, three-phase LV register profile V104/V105.

Wire addresses follow the manufacturer's MODBUS.RTU.V105.4-20240814 table:
https://github.com/user-attachments/files/22990113/MODBUS.RTU.V105.4-20240814.pdf
Transport: standard Modbus TCP gateway translating to RTU, 9600 baud / 8N1.
"""
import ipaddress
from math import trunc
from datetime import datetime,timezone

from .._modbus_tcp import ModbusTCP, ModbusError, checked_host
from ..contracts import (BatteryDriver, BatteryFeatures, BatteryReading, InverterDriver,
                         InverterReading, PluginInfo, PluginField, Measurement)
from ..plugin_parameters import parameters
from ..sanitiser import bounded
from ..plugin_diagnostics import plugin_operation
from ..failures import PluginParameterError


CONNECTION = (
    PluginField('host','RS485 gateway host / IP','text'),
    PluginField('port','Modbus TCP gateway port','number',default=502),
    PluginField('unit_id','Inverter Modbus address','number',default=1),
    PluginField('grid_meter_enabled','Provide common grid meter','boolean',default=True),
    PluginField('grid_meter_invert','Invert grid meter sign','boolean',default=False),
)


def signed(value):
    return value-65536 if value>=32768 else value


def power32(low,high):
    value=low | high<<16
    return value-4294967296 if value>=2147483648 else value


class DeyeConnection:
    def __init__(self,values):
        try: host=checked_host(values['host'])
        except ValueError as error: raise PluginParameterError('Invalid Modbus host','host') from error
        for key,maximum in (('port',65535),('unit_id',247)):
            if values[key]!=int(values[key]) or not 1<=values[key]<=maximum:
                raise PluginParameterError('Invalid Modbus endpoint',key)
        self.client=ModbusTCP(host,int(values['port']),int(values['unit_id']))
        self.grid=values['grid_meter_enabled']
        self.invert=values['grid_meter_invert']
        self.owner=None
        self.diagnostics={'failure':None}
        self.problems={}

    def context(self,stage,address,count):
        context={'stage':stage,'unit':self.client.unit,'address':address,'count':count}
        if self.owner is not None: self.owner._operation_context=context
        return context

    def registers(self,address,count,stage):
        context=self.context(stage,address,count)
        try: return self.client.read(address,count)
        except (OSError,ValueError) as error:
            context['exception_code']=getattr(error,'exception_code',None)
            self.diagnostics['failure']={**context,'type':type(error).__name__}
            raise

    def write(self,address,values):
        context=self.context('write_confirmation',address,len(values))
        try: return self.client.write(address,values)
        except (OSError,ValueError) as error:
            context['exception_code']=getattr(error,'exception_code',None)
            raise

    @property
    def device_key(self):
        host=self.client.host.lower()
        try: host=ipaddress.ip_address(host).compressed
        except ValueError: pass
        return f'modbus:{host}:{self.client.port}:{self.client.unit}'

    def identity(self):
        data=self.registers(0,25,'identity')
        rated=(data[20] | data[21]<<16)*.1
        # Do not apply a 12 kW LV power scale to an HP3, single-phase or
        # differently rated inverter merely because some registers respond.
        if (data[0] not in (0x0005,0x0500) or data[1]!=self.client.unit
                or rated!=12000 or data[22]!=0x0203 or data[24] not in (0,1)):
            self.diagnostics['failure']={**self.context('identity',0,25),'type':'ModbusError'}
            raise ModbusError('Expected Deye 12 kW three-phase LV / two-MPPT profile')
        return rated

    def read(self,now):
        self.diagnostics['failure']=None
        self.problems.clear()
        self.identity()
        data=self.registers(587,108,'telemetry')
        def word(address): return data[address-587]
        voltage=word(587)*.01
        battery=bounded(signed(word(590)),-14400,14400)
        soc=bounded(word(588),0,100)
        battery_mode=self.registers(111,1,'battery_mode')[0]
        if not 35<=voltage<=65 or battery_mode not in (0,1): soc=battery=None
        solar=word(672)+word(673) if all(word(address)!=65535 for address in (672,673)) else None
        solar=bounded(solar,0,40000)
        grid=bounded(power32(word(625),word(690)),-1000000,1000000)
        if grid is not None and self.invert: grid=-grid
        ac=bounded(power32(word(636),word(694)),-14400,14400)
        house=bounded(power32(word(653),word(659)),0,1000000)
        values={'solar':solar,'inverter_ac':ac}
        if self.grid: values.update(grid=grid,house_total=house)
        # Retain rejected field locations, never register contents or values.
        for key,value,address,count in (('battery_soc',soc,588,1),('battery_charge',battery,590,1),
            ('battery_discharge',battery,590,1),('solar',solar,672,2),('inverter_ac',ac,636,1),
            ('grid',grid,625,1),('house_total',house,653,1)):
            if value is None:
                if key.startswith('battery_'):
                    if not 35<=voltage<=65: address=587
                    elif battery_mode not in (0,1): address=111
                self.problems[key]={'reason':'invalid_value','max_age_s':45 if key in {'solar','grid'} else 120,
                    'stage':key,'unit':self.client.unit,'address':address,'count':count}
        return soc,battery,{key:Measurement(value,now if value is not None else None) for key,value in values.items()}

    def limits(self):
        self.identity()
        voltage=self.registers(587,1,'battery_voltage')[0]*.01
        currents=self.registers(108,2,'current_limits')
        battery_type=self.registers(98,1,'battery_type')[0]
        battery_mode=self.registers(111,1,'battery_mode')[0]
        if not 35<=voltage<=65 or battery_type not in (0,1) or battery_mode not in (0,1):
            self.context('battery_configuration',587 if not 35<=voltage<=65 else 98 if battery_type not in (0,1) else 111,1)
            raise ModbusError('Battery voltage/type unavailable')
        if any(value>350 for value in currents):
            self.context('current_limits',108,2)
            raise ModbusError('Invalid battery current limits')
        if battery_type==1:
            bms=self.registers(212,2,'bms_limits')
            if any(value>350 for value in bms): raise ModbusError('Invalid BMS current limits')
            currents=[min(value,bms[index]) for index,value in enumerate(currents)]
        return tuple(min(12000,value*voltage) for value in currents)


class DeyeModbus(BatteryDriver):
    info=PluginInfo('deye_modbus','Deye SUN-12K-SG04LP3-EU / Modbus TCP gateway','battery')
    configuration=CONNECTION+(
        PluginField('remote_control','Enable supported remote-control firmware','boolean',default=False),
        PluginField('grid_discharge_supported','Allow forced battery export','boolean',default=False),
        PluginField('minimum_soc','Additional device minimum SoC (%)','number',default=10),
        PluginField('maximum_soc','Additional device maximum SoC (%)','number',default=100),
    )
    uses_dispatch_context=True
    ids=dict.fromkeys(('soc','charge_power','discharge_power','mode'),'')

    def __init__(self,ha,params):
        values=parameters(self.configuration,params)
        self.connection=DeyeConnection(values)
        self.connection.owner=self
        self.read_diagnostics=self.connection.diagnostics
        self._source_problems=self.connection.problems
        self.client=self.connection.client
        self.enabled=values['remote_control']
        self.minimum,self.maximum=values['minimum_soc'],values['maximum_soc']
        if not 0<=self.minimum<self.maximum<=100:
            raise PluginParameterError('Invalid device SoC bounds','maximum_soc' if not 0<self.maximum<=100 else 'minimum_soc')
        self.features=BatteryFeatures(self.enabled,self.enabled,self.enabled,
                                     self.enabled and values['grid_discharge_supported'])
        self.measurement_keys=BatteryDriver.measurement_keys+('solar','inverter_ac')+(
            ('grid','house_total') if self.connection.grid else ())
        self.owns_remote=False
        self.expected=None

    @property
    def device_key(self):
        return self.connection.device_key

    def _read(self,states,now):
        soc,power,measurements=self.connection.read(now)
        charge=max(0,-power) if power is not None else None
        discharge=max(0,power) if power is not None else None
        return BatteryReading(soc,charge,discharge,now if soc is not None else None,
                              now if charge is not None else None,now if discharge is not None else None,measurements)

    @plugin_operation('power_limits')
    def power_limits(self,states):
        return self.connection.limits()

    @plugin_operation('apply')
    def _apply(self,command,states):
        # The public contract checks the configured command features first.
        self.connection.identity()
        remote=self.connection.registers(1100,11,'remote_mode')
        if remote[0] not in (0,1) or remote[0]==1 and not self.owns_remote:
            raise ModbusError('Remote mode unsupported or already controlled elsewhere')
        try:
            if remote[0]==1 and (not 10<=remote[1]<=300 or (remote[4],remote[5],remote[9])!=self.expected):
                raise ModbusError('Remote configuration changed outside this plugin')
            soc,power,measurements=self.connection.read(datetime.now(timezone.utc))
            if soc is None or power is None:
                self._operation_context=dict(self.connection.problems['battery_soc' if soc is None else 'battery_charge'])
                raise ModbusError('Fresh battery telemetry required')
            charge,discharge=self.power_limits(states)
            self._operation_context={'stage':'dispatch'}
            minimum=max(self.minimum,command.min_soc if command.min_soc is not None else self.minimum)
            maximum=min(self.maximum,command.max_soc if command.max_soc is not None else self.maximum)
            charge=min(charge,command.charge_w) if soc<maximum else 0
            discharge=min(discharge,command.discharge_w) if soc>minimum else 0
            if command.mode in {'grid_charge','block_discharge'}: discharge=0
            if command.mode=='grid_discharge': charge=0
            if discharge+1e-6<command.required_discharge_w:
                raise ModbusError('Insufficient eligible Deye battery power')
            if charge==0 and discharge==0: target=0
            elif command.mode=='grid_charge': target=-charge
            elif command.mode=='grid_discharge': target=discharge
            else:
                grid=measurements.get('grid',Measurement(None,None)).value
                if self.connection.grid:
                    if grid is None:
                        self._operation_context=dict(self.connection.problems['grid'])
                        raise ModbusError('Fresh Deye grid power required for local feedback')
                    demand=power+grid
                elif command.net_demand_w is not None:
                    demand=command.net_demand_w
                else:
                    raise ModbusError('Common grid demand required when local meter is not selected')
                target=max(-charge,min(discharge,demand))
                # Before the EV starts, reserve its already calculated deficit.
                if command.required_discharge_w:
                    target=max(target,min(discharge,command.required_discharge_w))
            rate=trunc(target/12)  # 0.1% of the verified 12 kW rating; toward zero.
            self.owns_remote=True
            self.connection.write(1101,[300])
            if remote[0]==0:
                self.connection.write(1109,[0])
                self.connection.write(1104,[1])  # Battery side; leave PV free-running.
                self.connection.write(1105,[2])  # Battery constant-power mode.
            self.connection.write(1109,[rate & 65535])
            self.connection.write(1100,[1])
            self.expected=(1,2,rate & 65535)
        except Exception:
            if self.owns_remote:
                try: self._release(states)
                except (OSError,ValueError): pass
            raise

    @plugin_operation('release')
    def _release(self,states):
        if not self.enabled: return
        self.connection.identity()
        mode=self.connection.registers(1100,1,'remote_mode')[0]
        if mode!=0:
            if not self.owns_remote or mode!=1:
                raise ModbusError('Unconfirmed foreign or unsupported remote mode')
            self.connection.write(1100,[0])
        self.owns_remote=False
        self.expected=None


class DeyeInverter(InverterDriver):
    info=PluginInfo('deye_modbus','Deye SUN-12K-SG04LP3-EU / read-only Modbus gateway','inverter')
    configuration=CONNECTION

    def __init__(self,ha,params):
        self.connection=DeyeConnection(parameters(self.configuration,params))
        self.connection.owner=self
        self.read_diagnostics=self.connection.diagnostics
        self._source_problems=self.connection.problems
        self.ids={}
        self.measurement_keys=('solar','inverter_ac')+(('grid','house_total') if self.connection.grid else ())

    @property
    def device_key(self):
        return self.connection.device_key

    def _read(self,states,now):
        return InverterReading(self.connection.read(now)[2])


PLUGINS=(DeyeModbus,DeyeInverter)

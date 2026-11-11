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
        host=checked_host(values['host'])
        for key,maximum in (('port',65535),('unit_id',247)):
            if values[key]!=int(values[key]) or not 1<=values[key]<=maximum:
                raise ValueError('Invalid Modbus endpoint')
        self.client=ModbusTCP(host,int(values['port']),int(values['unit_id']))
        self.grid=values['grid_meter_enabled']
        self.invert=values['grid_meter_invert']

    @property
    def device_key(self):
        host=self.client.host.lower()
        try: host=ipaddress.ip_address(host).compressed
        except ValueError: pass
        return f'modbus:{host}:{self.client.port}:{self.client.unit}'

    def identity(self):
        data=self.client.read(0,25)
        rated=(data[20] | data[21]<<16)*.1
        # Do not apply a 12 kW LV power scale to an HP3, single-phase or
        # differently rated inverter merely because some registers respond.
        if (data[0] not in (0x0005,0x0500) or data[1]!=self.client.unit
                or rated!=12000 or data[22]!=0x0203 or data[24] not in (0,1)):
            raise ModbusError('Expected Deye 12 kW three-phase LV / two-MPPT profile')
        return rated

    def read(self,now):
        self.identity()
        data=self.client.read(587,108)
        def word(address): return data[address-587]
        voltage=word(587)*.01
        battery=bounded(signed(word(590)),-14400,14400)
        soc=bounded(word(588),0,100)
        battery_mode=self.client.read(111,1)[0]
        if not 35<=voltage<=65 or battery_mode not in (0,1): soc=battery=None
        solar=word(672)+word(673) if all(word(address)!=65535 for address in (672,673)) else None
        solar=bounded(solar,0,40000)
        grid=bounded(power32(word(625),word(690)),-1000000,1000000)
        if grid is not None and self.invert: grid=-grid
        ac=bounded(power32(word(636),word(694)),-14400,14400)
        house=bounded(power32(word(653),word(659)),0,1000000)
        values={'solar':solar,'inverter_ac':ac}
        if self.grid: values.update(grid=grid,house_total=house)
        return soc,battery,{key:Measurement(value,now if value is not None else None) for key,value in values.items()}

    def limits(self):
        self.identity()
        voltage=self.client.read(587,1)[0]*.01
        currents=self.client.read(108,2)
        battery_type=self.client.read(98,1)[0]
        battery_mode=self.client.read(111,1)[0]
        if not 35<=voltage<=65 or battery_type not in (0,1) or battery_mode not in (0,1):
            raise ModbusError('Battery voltage/type unavailable')
        if any(value>350 for value in currents): raise ModbusError('Invalid battery current limits')
        if battery_type==1:
            bms=self.client.read(212,2)
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
        self.client=self.connection.client
        self.enabled=values['remote_control']
        self.minimum,self.maximum=values['minimum_soc'],values['maximum_soc']
        if not 0<=self.minimum<self.maximum<=100: raise ValueError('Invalid device SoC bounds')
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

    def power_limits(self,states):
        return self.connection.limits()

    def _apply(self,command,states):
        # The public contract checks the configured command features first.
        self.connection.identity()
        remote=self.client.read(1100,11)
        if remote[0] not in (0,1) or remote[0]==1 and not self.owns_remote:
            raise ModbusError('Remote mode unsupported or already controlled elsewhere')
        try:
            if remote[0]==1 and (not 10<=remote[1]<=300 or (remote[4],remote[5],remote[9])!=self.expected):
                raise ModbusError('Remote configuration changed outside this plugin')
            soc,power,measurements=self.connection.read(datetime.now(timezone.utc))
            if soc is None or power is None: raise ModbusError('Fresh battery telemetry required')
            charge,discharge=self.power_limits(states)
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
                    if grid is None: raise ModbusError('Fresh Deye grid power required for local feedback')
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
            self.client.write(1101,[300])
            if remote[0]==0:
                self.client.write(1109,[0])
                self.client.write(1104,[1])  # Battery side; leave PV free-running.
                self.client.write(1105,[2])  # Battery constant-power mode.
            self.client.write(1109,[rate & 65535])
            self.client.write(1100,[1])
            self.expected=(1,2,rate & 65535)
        except Exception:
            if self.owns_remote:
                try: self._release(states)
                except (OSError,ValueError): pass
            raise

    def _release(self,states):
        if not self.enabled: return
        self.connection.identity()
        mode=self.client.read(1100,1)[0]
        if mode!=0:
            if not self.owns_remote or mode!=1:
                raise ModbusError('Unconfirmed foreign or unsupported remote mode')
            self.client.write(1100,[0])
        self.owns_remote=False
        self.expected=None


class DeyeInverter(InverterDriver):
    info=PluginInfo('deye_modbus','Deye SUN-12K-SG04LP3-EU / read-only Modbus gateway','inverter')
    configuration=CONNECTION

    def __init__(self,ha,params):
        self.connection=DeyeConnection(parameters(self.configuration,params))
        self.ids={}
        self.measurement_keys=('solar','inverter_ac')+(('grid','house_total') if self.connection.grid else ())

    @property
    def device_key(self):
        return self.connection.device_key

    def _read(self,states,now):
        return InverterReading(self.connection.read(now)[2])


PLUGINS=(DeyeModbus,DeyeInverter)

"""Huawei SUN2000 inverter with LUNA2000 storage over Modbus TCP (SDongle).

Register addresses follow Huawei's "Solar Inverter Modbus Interface Definitions":
inverter 30000-32089, power meter 37100-37114, storage 37046-37765 and
storage settings 47000-47249. Values are big-endian, high word first.
Inverter, power meter and battery share one register map, so one plugin serves
the storage and the read-only PV variant.
"""
import ipaddress
from math import floor

from .._modbus_tcp import ModbusTCP, ModbusError, checked_host
from ..contracts import (BatteryDriver, BatteryFeatures, BatteryReading, InverterDriver,
                         InverterReading, PluginInfo, PluginField, Measurement)
from ..plugin_parameters import parameters
from ..sanitiser import bounded
from ..plugin_diagnostics import plugin_operation, partial_read_failure
from ..failures import PluginParameterError

# The inverter ignores requests during the first second of a new connection.
CONNECT_DELAY_S = 1.0
TIMEOUT_S = 5
# Forcible charge/discharge ends on its own after this period unless renewed.
FORCIBLE_PERIOD_MIN = 5
SELF_CONSUMPTION = 2
LUNA2000 = 2
# Storage running status: standby, running, sleep. Offline (0) and fault (3) are not valid.
STORAGE_VALID = (1, 2, 4)

CONNECTION = (
    PluginField('host','SDongle host / IP','text'),
    PluginField('port','Modbus TCP port','number',default=502),
    PluginField('unit_id','Inverter Modbus address','number',default=1),
    PluginField('grid_meter_enabled','Provide common grid meter','boolean',default=True),
    PluginField('grid_meter_invert','Invert grid meter sign','boolean',default=False),
)


def signed16(value):
    return value-65536 if value>=32768 else value


def u32(words):
    return words[0]<<16 | words[1]


def i32(words):
    value=u32(words)
    return value-4294967296 if value>=2147483648 else value


def words32(value):
    return [value>>16 & 65535, value & 65535]


class HuaweiConnection:
    def __init__(self,values):
        try: host=checked_host(values['host'])
        except ValueError as error: raise PluginParameterError('Invalid Modbus host','host') from error
        for key,maximum in (('port',65535),('unit_id',247)):
            if values[key]!=int(values[key]) or not 1<=values[key]<=maximum:
                raise PluginParameterError('Invalid Modbus endpoint',key)
        self.client=ModbusTCP(host,int(values['port']),int(values['unit_id']),timeout=TIMEOUT_S,
                              connect_delay=CONNECT_DELAY_S)
        self.grid=values['grid_meter_enabled']
        self.invert=values['grid_meter_invert']
        self.owner=None
        self.diagnostics={'failure':None}
        self.problems={}
        self.identified=None
        self.identified_battery=False
        self.rated=None
        self.strings=None

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

    def write(self,address,values,stage):
        context=self.context(stage,address,len(values))
        try: return self.client.write(address,values)
        except (OSError,ValueError) as error:
            context['exception_code']=getattr(error,'exception_code',None)
            raise

    def update(self,address,values,stage):
        """Write a persistent setting only when it differs, to spare the device memory."""
        if self.registers(address,len(values),stage)!=list(values):
            self.write(address,values,stage)

    @property
    def device_key(self):
        host=self.client.host.lower()
        try: host=ipaddress.ip_address(host).compressed
        except ValueError: pass
        return f'modbus:{host}:{self.client.port}:{self.client.unit}'

    def fail(self,stage,address,count,message):
        self.diagnostics['failure']={**self.context(stage,address,count),'type':'ModbusError'}
        raise ModbusError(message)

    def identity(self,battery):
        """Verify model, rating and string count once per connection; a new one may be another device."""
        if self.identified==self.client.opened and self.client.connected and (not battery or self.identified_battery):
            return
        self.identified=None
        name=b''.join(word.to_bytes(2,'big') for word in self.registers(30000,15,'identity'))
        if not name.rstrip(b'\0 ').startswith(b'SUN2000'):
            self.fail('identity',30000,15,'Expected a Huawei SUN2000 inverter')
        strings=self.registers(30071,1,'identity')[0]
        rated=u32(self.registers(30073,2,'identity'))
        if not 1<=strings<=24 or not 0<rated<=200000:
            self.fail('identity',30071 if not 1<=strings<=24 else 30073,1 if not 1<=strings<=24 else 2,
                      'Unexpected SUN2000 rating or string count')
        self.identified_battery=False
        if battery:
            if self.registers(47000,1,'identity')[0]!=LUNA2000:
                self.fail('identity',47000,1,'No LUNA2000 storage on this inverter')
            self.identified_battery=True
        self.rated,self.strings=rated,strings
        self.identified=self.client.opened

    def problem(self,key,address,count,max_age=120):
        # Retain rejected field locations, never register contents or values.
        self.problems[key]={'reason':'invalid_value','max_age_s':max_age,'stage':key,
                            'unit':self.client.unit,'address':address,'count':count}

    def solar(self):
        data=self.registers(32016,2*self.strings,'pv_strings')
        total=0
        for index in range(self.strings):
            voltage,current=signed16(data[2*index])*.1,signed16(data[2*index+1])*.01
            total+=max(0,voltage)*max(0,current)
        return bounded(round(total),0,1000000)

    def meter(self):
        data=self.registers(37100,15,'power_meter')
        if data[0]!=1:
            return None
        # The meter reports feed-in as positive; import is canonical positive here.
        value=bounded(-i32(data[13:15]),-1000000,1000000)
        return -value if value is not None and self.invert else value

    def storage(self):
        soc=self.registers(37760,1,'battery_soc')[0]
        data=self.registers(37762,5,'battery_status')
        soc=bounded(soc*.1,0,100)
        # Positive storage power charges, negative discharges.
        power=bounded(i32(data[3:5]),-100000,100000)
        if data[0] not in STORAGE_VALID: soc=power=None
        return soc,power

    def read(self,now,battery):
        self.diagnostics['failure']=None
        self.problems.clear()
        self.identity(battery)
        solar=self.solar()
        ac=bounded(i32(self.registers(32080,2,'inverter_ac')),-1000000,1000000)
        values={'solar':solar,'inverter_ac':ac}
        if solar is None: self.problem('solar',32016,2*self.strings,45)
        if ac is None: self.problem('inverter_ac',32080,2)
        if self.grid:
            try:
                grid=self.meter()
            except (OSError,ValueError) as error:
                # A missing power meter must not hide healthy inverter and battery data.
                if self.owner is not None: partial_read_failure(self.owner,error,'grid')
                grid=None
            if grid is None: self.problem('grid',37100,15,45)
            house=ac+grid if ac is not None and grid is not None else None
            house=bounded(house,0,1000000) if house is not None else None
            if house is None: self.problem('house_total',32080,2)
            values.update(grid=grid,house_total=house)
        soc=power=None
        if battery:
            soc,power=self.storage()
            if soc is None:
                for key in ('battery_soc','battery_charge','battery_discharge'): self.problem(key,37762,5)
        return soc,power,{key:Measurement(value,now if value is not None else None) for key,value in values.items()}

    def limits(self):
        self.identity(True)
        charge,discharge=u32(self.registers(37046,2,'power_limits')),u32(self.registers(37048,2,'power_limits'))
        if not 0<charge<=100000 or not 0<discharge<=100000:
            self.fail('power_limits',37046,4,'Invalid LUNA2000 power limits')
        return charge,discharge


class HuaweiModbus(BatteryDriver):
    info=PluginInfo('huawei_modbus','Huawei SUN2000 with LUNA2000 / Modbus TCP','battery')
    configuration=CONNECTION+(
        PluginField('remote_control','Enable battery control','boolean',default=False),
        PluginField('grid_discharge_supported','Allow forced battery export','boolean',default=False),
    )
    ids=dict.fromkeys(('soc','charge_power','discharge_power','mode'),'')

    def __init__(self,ha,params):
        values=parameters(self.configuration,params)
        self.connection=HuaweiConnection(values)
        self.connection.owner=self
        self.read_diagnostics=self.connection.diagnostics
        self._source_problems=self.connection.problems
        self.client=self.connection.client
        self.enabled=values['remote_control']
        self.features=BatteryFeatures(self.enabled,self.enabled,self.enabled,
                                     self.enabled and values['grid_discharge_supported'])
        self.measurement_keys=BatteryDriver.measurement_keys+('solar','inverter_ac')+(
            ('grid','house_total') if self.connection.grid else ())
        self.owns_forcible=False
        self.limited=False

    @property
    def device_key(self):
        return self.connection.device_key

    def _read(self,states,now):
        soc,power,measurements=self.connection.read(now,True)
        charge=max(0,power) if power is not None else None
        discharge=max(0,-power) if power is not None else None
        return BatteryReading(soc,charge,discharge,now if soc is not None else None,
                              now if charge is not None else None,now if discharge is not None else None,measurements)

    @plugin_operation('power_limits')
    def power_limits(self,states):
        return self.connection.limits()

    @plugin_operation('apply')
    def _apply(self,command,states):
        # The public contract checks the configured command features first.
        connection=self.connection
        connection.identity(True)
        soc,power=connection.storage()
        if soc is None or power is None:
            connection.fail('battery_status',37762,5,'Fresh LUNA2000 telemetry required')
        mode,grid_charging=connection.registers(47086,2,'working_mode')
        if mode!=SELF_CONSUMPTION:
            connection.fail('working_mode',47086,1,'Storage working mode must be maximise self-consumption')
        forcible=connection.registers(47100,1,'forcible_state')[0]
        if forcible not in (0,1,2) or forcible and not self.owns_forcible:
            connection.fail('forcible_state',47100,1,'Forcible charge/discharge active outside this plugin')
        maximum_charge,maximum_discharge=connection.limits()
        self._operation_context={'stage':'dispatch'}
        charge=floor(min(maximum_charge,command.charge_w))
        discharge=floor(min(maximum_discharge,command.discharge_w))
        if command.mode in {'grid_charge','block_discharge'}: discharge=0
        if command.mode=='grid_discharge': charge=0
        target=1 if command.mode=='grid_charge' and charge>0 else 2 if command.mode=='grid_discharge' and discharge>0 else 0
        if target==1 and grid_charging!=1:
            connection.fail('grid_charge_function',47087,1,'Charging from the grid is disabled in the inverter')
        try:
            if forcible and forcible!=target:
                connection.write(47100,[0],'forcible_stop')
                self.owns_forcible=False
            self.limited=True
            connection.update(47075,words32(charge),'maximum_charge_power')
            connection.update(47077,words32(discharge),'maximum_discharge_power')
            if target:
                connection.update(47246,[0],'forcible_setting_mode')  # By duration, not target SoC.
                connection.update(47247 if target==1 else 47249,words32(charge if target==1 else discharge),
                                  'forcible_power')
                self.owns_forcible=True
                # Renew the period on every command; the battery stops by itself if HA does not.
                connection.write(47083,[FORCIBLE_PERIOD_MIN],'forcible_period')
                connection.write(47100,[target],'forcible_start')
        except Exception:
            if self.owns_forcible:
                try: self._stop_forcible()
                except (OSError,ValueError): pass
            raise

    def _stop_forcible(self):
        if self.connection.registers(47100,1,'forcible_state')[0]!=0:
            self.connection.write(47100,[0],'forcible_stop')
        self.owns_forcible=False

    @plugin_operation('release')
    def _release(self,states):
        if not self.enabled: return
        connection=self.connection
        connection.identity(True)
        # A forcible command from elsewhere is left alone; an own leftover from before a
        # restart ends with its period.
        if self.owns_forcible: self._stop_forcible()
        limits=[u32(connection.registers(address,2,'power_settings')) for address in (47075,47077)]
        if self.limited or 0 in limits:
            maximum_charge,maximum_discharge=connection.limits()
            connection.update(47075,words32(maximum_charge),'maximum_charge_power')
            connection.update(47077,words32(maximum_discharge),'maximum_discharge_power')
        self.limited=False


class HuaweiInverter(InverterDriver):
    info=PluginInfo('huawei_modbus','Huawei SUN2000 / read-only Modbus TCP','inverter')
    configuration=CONNECTION

    def __init__(self,ha,params):
        self.connection=HuaweiConnection(parameters(self.configuration,params))
        self.connection.owner=self
        self.read_diagnostics=self.connection.diagnostics
        self._source_problems=self.connection.problems
        self.ids={}
        self.measurement_keys=('solar','inverter_ac')+(('grid','house_total') if self.connection.grid else ())

    @property
    def device_key(self):
        return self.connection.device_key

    def _read(self,states,now):
        return InverterReading(self.connection.read(now,False)[2])


PLUGINS=(HuaweiModbus,HuaweiInverter)

"""Direct GX system telemetry and version-aware ESS Mode 2 control.

Register types/scales: Victron CCGX-Modbus-TCP-register-list-3.81.xlsx.
https://www.victronenergy.com/live/ess:ess_mode_2_and_3
No Mode 3, firmware changes, MQTT or Home Assistant entity dependency.
"""
from datetime import datetime,timezone
import ipaddress
import logging
from math import ceil,floor
import re
import struct
from time import monotonic

from .._modbus_tcp import ModbusTCP,ModbusError,checked_host
from ..contracts import BatteryDriver,BatteryFeatures,BatteryReading,Measurement,PluginField,PluginInfo
from ..plugin_parameters import parameters
from ..plugin_diagnostics import plugin_operation
from ..failures import PluginParameterError

_LOGGER=logging.getLogger(__name__)


def signed(word):
    return word-65536 if word>=32768 else word


def configured_firmware(value):
    if value in (None,''):return None
    match=re.fullmatch(r'v?([1-9])\.([0-9]{1,2})(?:~([0-9]{1,2}))?',value)
    if not match:raise PluginParameterError('Expected Venus OS version such as v3.66','firmware_version')
    major,minor,beta=match.groups()
    version=f'v{major}.{int(minor):02d}'+(f'~{int(beta)}' if beta is not None else '')
    return int(major+f'{int(minor):02d}',16),version


class VictronModbus(BatteryDriver):
    info=PluginInfo('victron_modbus','Victron GX direct Modbus TCP','battery')
    uses_dispatch_context=True
    ids=dict.fromkeys(('soc','charge_power','discharge_power','mode'),'')
    configuration=(
        PluginField('host','GX hostname / IP','text'),
        PluginField('port','GX Modbus TCP port','number',default=502),
        PluginField('firmware_version','Venus OS version if automatic detection is unavailable (e.g. v3.66)','text',required=False),
        PluginField('phases','System phases','choice',default='3',choices=('1','3')),
        PluginField('grid_meter_enabled','Provide common grid / consumption measurements','boolean',default=True),
        PluginField('read_consumption','Read system AC consumption','boolean',default=True),
        PluginField('dc_pv_enabled','Read DC-coupled PV','boolean',default=True),
        PluginField('ac_pv_input_enabled','Read AC PV on grid input','boolean',default=False),
        PluginField('ac_pv_output_enabled','Read AC PV on inverter output','boolean',default=False),
        PluginField('control_enabled','Enable ESS Mode 2 control (requires DVCC)','boolean',default=False),
        PluginField('legacy_control_enabled','Allow ESS control before Venus OS 3.50 (persistent writes; confirm Dynamic ESS is off)','boolean',default=False),
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
        try: host=checked_host(v['host'])
        except ValueError as error: raise PluginParameterError('Invalid Modbus host','host') from error
        if v['port']!=int(v['port']) or not 1<=v['port']<=65535: raise PluginParameterError('Invalid Modbus port','port')
        self.client=ModbusTCP(host,int(v['port']),100)
        self.phases=int(v['phases']);self.enabled=v['control_enabled']
        self._firmware=None;self._legacy_warning=False;self._legacy_guard_warning=False
        self._configured_firmware=configured_firmware(v['firmware_version'])
        self._firmware_notice=None
        self.read_diagnostics={'phases':self.phases,
            **{key:v[key] for key in ('control_enabled','legacy_control_enabled','grid_meter_enabled','read_consumption',
                'dc_pv_enabled','ac_pv_input_enabled','ac_pv_output_enabled')},'failure':None,
            'firmware':self._firmware_diagnostics()}
        for key in ('charge_efficiency','discharge_efficiency'):
            if not .1<=v[key]<=1: raise PluginParameterError('Invalid Victron efficiency',key)
        for key,low,high,step in (('max_charge_current',1,32766,1),('max_discharge_power',10,327660,10),
                                  ('release_setpoint',-1000000,1000000,1),
                                  ('release_charge_current',-1,32766,1),('release_discharge_power',0,327660,10)):
            value=v[key]
            if value in (None,''):
                if self.enabled: raise PluginParameterError('Explicit Victron release limits are required',key)
            elif not low<=value<=high or value/step!=int(value/step): raise PluginParameterError('Invalid Victron limit',key)
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

    def _registers(self,address,count,stage):
        # Keep protocol context only; never retain returned words or raw errors.
        self._read_context={'stage':stage,'unit':100,'address':address,'count':count}
        self._operation_context=dict(self._read_context)
        try: return self.client.read(address,count)
        except OSError as error:
            self._operation_context['exception_code']=getattr(error,'exception_code',None)
            raise

    def _firmware_diagnostics(self):
        return {'version':None,'source':'unknown','detected':None,
            'configured':self._configured_firmware[1] if self._configured_firmware else None,
            'register_status':'unread','raw_words':None}

    def _firmware_error(self,stage,message,*,parameter=None):
        self._read_context={'stage':stage,'unit':100,'address':834,'count':2}
        if parameter:self._read_context['parameter']=parameter
        self._operation_context=dict(self._read_context)
        raise ModbusError(message)

    def _identity(self,*,control=False):
        self._firmware=None
        details=self.read_diagnostics['firmware']=self._firmware_diagnostics()
        serial=struct.pack('>6H',*self._registers(800,6,'identity')).decode('ascii',errors='replace')
        if not re.fullmatch('[0-9a-fA-F]{12}',serial):
            raise ModbusError('Expected Victron GX system serial')
        # Register 834/835 was added in Venus 3.70, independently of the
        # volatile ESS setpoint introduced in 3.50. Older reserved ranges
        # return 0xffff words; this is not an old firmware version.
        try:
            words=self._registers(834,2,'firmware')
        except ModbusError as error:
            details['register_status']='unsupported' if error.exception_code==2 else 'transport_error'
            if error.exception_code!=2:raise
        except OSError:
            details['register_status']='transport_error'
            raise
        else:
            details['raw_words']=list(words)
            if words==[65535,65535]:
                details['register_status']='reserved'
            else:
                firmware,beta=words
                if (not 0x0100<=firmware<=0x0999 or any((firmware>>shift)&15>9 for shift in (0,4,8))
                        or beta>0x99 or any((beta>>shift)&15>9 for shift in (0,4))):
                    details['register_status']='invalid'
                    self._firmware_error('firmware_invalid','Invalid GX firmware version')
                self._firmware=firmware
                details.update(register_status='valid',source='detected',
                    detected=f'v{firmware>>8:x}.{firmware&255:02x}'+(f'~{beta:x}' if beta else ''))
                details['version']=details['detected']
        if self._firmware is None:
            if self._configured_firmware:
                self._firmware,details['version']=self._configured_firmware
                details['source']='configured'
            else:
                # Explicit compatibility default, not a detected exact version.
                self._firmware=0x0350
                details.update(version='v3.50–v3.69',source='assumed')
        notice=(details['register_status'],details['source'],details['version'])
        if notice!=self._firmware_notice:
            if details['register_status']!='valid' or self._firmware_notice is not None:
                _LOGGER.info('victron_modbus firmware_status: register=%s source=%s version=%s',*notice)
            self._firmware_notice=notice
        if control and self._firmware<0x0350 and not self.values['legacy_control_enabled']:
            self._firmware_error('firmware_legacy_opt_in_required','Older Venus OS requires explicit legacy ESS control permission')
        if control:
            # Do not take control if the configured native return value cannot
            # later be restored using the selected firmware's register format.
            self._setpoint_command(self.values['release_setpoint'],parameter='release_setpoint')

    def _battery(self):
        voltage,_,power,soc=self._registers(840,4,'battery')
        voltage/=10;power=signed(power)
        if not 10<=voltage<=1000 or not 0<=soc<=100 or not -32768<power<32766:
            raise ModbusError('Invalid or saturated GX battery telemetry')
        return voltage,power,soc

    def _power(self,address,count,signed_power=False):
        stage={850:'dc_pv',811:'ac_pv_input',808:'ac_pv_output',820:'grid',817:'consumption'}[address]
        words=self._registers(address,count,stage)
        values=[signed(word) for word in words] if signed_power else words
        # The GX server can clamp to max-1; reject that endpoint as well.
        invalid=any(not -32768<value<32766 for value in values) if signed_power else any(value>=65534 for value in values)
        if invalid:
            raise ModbusError('Invalid or saturated GX phase power')
        return sum(values)

    def _telemetry(self,now,*,control=False):
        start=monotonic();self._identity(control=control)
        voltage,power,soc=self._battery()
        values={}
        if self.pv_sources:
            values['solar']=sum(self._power(address,count) for address,count in self.pv_sources)
        if self.values['grid_meter_enabled'] or control:
            values['grid']=self._power(820,self.phases,True)
        if self.provides_site_consumption:
            values['house_total']=self._power(817,self.phases)
        if monotonic()-start>10:
            self._read_context={'stage':'snapshot_timeout'}
            self._operation_context=dict(self._read_context)
            raise ModbusError('GX telemetry snapshot took too long')
        charge=max(0,power)/self.values['charge_efficiency']
        discharge=max(0,-power)*self.values['discharge_efficiency']
        return voltage,BatteryReading(soc,charge,discharge,now,now,now,
            {key:Measurement(value,now) for key,value in values.items()})

    def _read(self,states,now):
        self.read_diagnostics['failure']=None
        self._read_context={}
        try:
            _,sample=self._telemetry(now)
        except (OSError,ValueError) as error:
            self.read_diagnostics['failure']={**self._read_context,'type':type(error).__name__,
                'exception_code':getattr(error,'exception_code',None)}
            raise
        return sample

    @plugin_operation('power_limits')
    def power_limits(self,states):
        if not self.enabled: return None
        self._identity(control=True);voltage,_,_=self._battery()
        return min(1000000,self.values['max_charge_current']*voltage/self.values['charge_efficiency']),self.values['max_discharge_power']

    def _guard(self,*,grid=False):
        settings=self._registers(2900,3,'ess_mode')
        if settings[2] not in (1,2) or settings[0] not in (*range(2,9),10,11,12):
            raise ModbusError('GX requires optimized ESS Mode 2')
        try:
            dynamic_ess=self._registers(5423,1,'dynamic_ess')[0]
        except ModbusError as error:
            # Some older servers predate this register even though ESS exists.
            # Only the explicit legacy opt-in confirms Dynamic ESS off manually.
            # Never reinterpret transport errors, unknown units or modern
            # missing registers as confirmation that another controller is off.
            if not (error.exception_code==2 and self._firmware<0x0350 and self.values['legacy_control_enabled']):
                raise
            if not self._legacy_guard_warning:
                _LOGGER.warning('victron_modbus legacy_dynamic_ess_manual: register 5423 unavailable; using explicit configuration confirmation that Dynamic ESS is disabled')
                self._legacy_guard_warning=True
        else:
            if dynamic_ess!=0: raise ModbusError('Dynamic ESS must be disabled')
        if grid and self._registers(826,1,'grid_connection')[0]!=1: raise ModbusError('GX grid input is not connected')

    def _write(self,address,words):
        if self._registers(address,len(words),'control_readback')!=words:
            self._operation_context={'stage':'write_confirmation','unit':100,'address':address,'count':len(words)}
            try: self.client.write(address,words)
            except OSError as error:
                self._operation_context['exception_code']=getattr(error,'exception_code',None)
                raise

    def _setpoint_command(self,watts,*,parameter=None):
        if self._firmware<0x0350:
            if not -32768<=watts<=32767:
                self._operation_context={'stage':'legacy_setpoint_range','unit':100,'address':2700,'count':1}
                if parameter:self._operation_context['parameter']=parameter
                raise ModbusError('Legacy GX grid setpoint must fit signed 16-bit watts')
            return 2700,[int(watts)&65535]
        raw=int(watts)&0xffffffff
        return 2716,[raw>>16,raw&65535]

    def _setpoint(self,watts):
        address,words=self._setpoint_command(watts)
        if address==2700 and not self._legacy_warning:
            _LOGGER.warning('victron_modbus legacy_persistent_setpoint: ESS uses register 2700 before Venus OS 3.50; changed setpoints are persistent and may cause flash writes and VRM logging')
            self._legacy_warning=True
        self._write(address,words)

    @plugin_operation('apply')
    def _apply(self,command,states):
        voltage,sample=self._telemetry(datetime.now(timezone.utc),control=True)
        self._guard(grid=True)
        self._operation_context={'stage':'dispatch'}
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
        self._setpoint_command(target)  # Reject legacy overflow before changing any limits.
        self._write(2705,[amps])
        self._write(2704,[outgoing//10])
        self._setpoint(target)

    @plugin_operation('release')
    def _release(self,states):
        if not self.enabled: return
        self._identity(control=True);self._guard()
        # Explicit finite native power avoids the ambiguous -1 / 0.1 scaling
        # of legacy register 2704; no volatile process ownership is required.
        self._setpoint(self.values['release_setpoint'])
        self._write(2705,[int(self.values['release_charge_current'])&65535])
        self._write(2704,[int(self.values['release_discharge_power'])//10])


PLUGINS=(VictronModbus,)

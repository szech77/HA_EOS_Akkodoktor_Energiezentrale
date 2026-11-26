"""Local go-e HTTP API v2 (firmware >= 051.4), independent of HA entities.

https://github.com/goecharger/go-eCharger-API-v2/blob/main/http-en.md
"""
from datetime import datetime, timezone
from http.client import HTTPException
import json
import logging
import re
from time import monotonic, sleep
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, ProxyHandler, build_opener

from ..clients import NoRedirect, RequestDeadline, base_url
from ..contracts import WallboxDriver, WallboxFeatures, WallboxReading, PluginInfo, PluginField
from ..plugin_parameters import parameters
from ..sanitiser import bounded
from ..failures import HardwareAPIError

REQUEST_GRACE_S=2  # Total exchange deadline beyond the socket inactivity timeout.
# Some vehicles end their session during a charging pause and then report "complete"
# (car=4) or wait without requesting power (car=3) although charging is allowed again.
# They only start after being unplugged.
STALLED_RESTART_S=60  # Released, idle and without power for this long.
STALLED_IDLE_W=30
STALLED_CAR_STATES=(3,4)
# At most this many restarts per vehicle session; each one pauses charging briefly.
MAX_UNPLUG_ATTEMPTS=2
# After frc=2 the charger can accept the release but hold charging for its own timed
# reason (modelStatus): 22 simulating unplugging (sumd), 23 phase switch, 24 minimum
# pause (mcpd), 29 reconnection delay. It may also answer slowly meanwhile.
SIMULATING_UNPLUG=22
RELEASE_PENDING=frozenset({SIMULATING_UNPLUG,23,24,29})
# The charger's reason (modelStatus) for not charging as a fixed notice cause.
IDLE_REASONS={1:'charger_overtemperature',2:'access_control',5:'charger_logic',6:'charger_logic',
    16:'charger_logic',17:'charger_logic',18:'charger_logic',22:'simulating_unplug',23:'phase_switch',
    24:'min_pause',26:'charger_error',27:'load_management',28:'ocpp',29:'reconnect_delay',30:'adapter',
    31:'grid_monitoring',32:'unbalanced_load',34:'grid_monitoring',35:'ocpp'}
RELEASE_CONFIRM_S=10
CONFIRM_S=4
# modelStatus, acs, lmo, sua and fwv only explain the charger's own decision (diagnostics).
STATUS_KEYS=('car','err','frc','alw','amp','ama','adi','cbl','var','nrg','psm','pnp','pha','fsp','mca',
             'modelStatus','acs','lmo','sua','fwv')
_LOGGER=logging.getLogger(__name__)
# Names from the go-e API v2 key reference (API_KEYS_FIRMWARE/apikeys-en.md).
CAR_STATES={0:'Unknown',1:'Idle',2:'Charging',3:'WaitCar',4:'Complete',5:'Error'}
FORCE_STATES={0:'Neutral',1:'Off',2:'On'}
ACCESS_CONTROL={0:'Open',1:'Wait'}
LOGIC_MODES={3:'Default',4:'Awattar',5:'AutomaticStop'}
MODEL_STATUS={0:'NotChargingBecauseNoChargeCtrlData',1:'NotChargingBecauseOvertemperature',
    2:'NotChargingBecauseAccessControlWait',3:'ChargingBecauseForceStateOn',4:'NotChargingBecauseForceStateOff',
    5:'NotChargingBecauseScheduler',6:'NotChargingBecauseEnergyLimit',7:'ChargingBecauseAwattarPriceLow',
    8:'ChargingBecauseAutomaticStopTestLadung',9:'ChargingBecauseAutomaticStopNotEnoughTime',
    10:'ChargingBecauseAutomaticStop',11:'ChargingBecauseAutomaticStopNoClock',12:'ChargingBecausePvSurplus',
    13:'ChargingBecauseFallbackGoEDefault',14:'ChargingBecauseFallbackGoEScheduler',15:'ChargingBecauseFallbackDefault',
    16:'NotChargingBecauseFallbackGoEAwattar',17:'NotChargingBecauseFallbackAwattar',
    18:'NotChargingBecauseFallbackAutomaticStop',19:'ChargingBecauseCarCompatibilityKeepAlive',
    20:'ChargingBecauseChargePauseNotAllowed',22:'NotChargingBecauseSimulateUnplugging',
    23:'NotChargingBecausePhaseSwitch',24:'NotChargingBecauseMinPauseDuration',26:'NotChargingBecauseError',
    27:'NotChargingBecauseLoadManagementDoesntWant',28:'NotChargingBecauseOcppDoesntWant',
    29:'NotChargingBecauseReconnectDelay',30:'NotChargingBecauseAdapterBlocking',
    31:'NotChargingBecauseUnderfrequencyControl',32:'NotChargingBecauseUnbalancedLoad',
    33:'ChargingBecauseDischargingPvBattery',34:'NotChargingBecauseGridMonitoring',35:'NotChargingBecauseOcppFallback'}


def charger_status(data):
    """The charger's own charging decision as fixed codes, without measurements or settings values."""
    def code(key,names,maximum=255):
        value=integer(data.get(key),0,maximum)
        return None if value is None else {'code':value,'name':names.get(value,'unknown')}
    firmware=data.get('fwv')
    return {'car':code('car',CAR_STATES),'force':code('frc',FORCE_STATES),
            'allowed':data.get('alw') if type(data.get('alw')) is bool else None,
            'reason':code('modelStatus',MODEL_STATUS),'access_control':code('acs',ACCESS_CONTROL),
            'logic_mode':code('lmo',LOGIC_MODES),'error':integer(data.get('err'),0,255),
            'simulate_unplugging_always':data.get('sua') if type(data.get('sua')) is bool else None,
            'firmware':firmware if isinstance(firmware,str) and re.fullmatch(r'[0-9A-Za-z._-]{1,32}',firmware) else None}


class GoEAPIError(HardwareAPIError):
    """Device errors without private response content or network locations."""


def integer(value,minimum,maximum):
    return value if type(value) is int and minimum<=value<=maximum else None


class GoEHTTPv2(WallboxDriver):
    info=PluginInfo('goe_http_v2','go-e Charger – lokale HTTP-API v2','wallbox')
    configuration=(
        PluginField('url','Local HTTP API v2 base URL','text',default='http://go-echarger.local'),
        PluginField('phase_switching','Enable supported 1-/3-phase switching','boolean',default=False),
        PluginField('nominal_voltage','Nominal phase-to-neutral voltage (V)','number',default=230),
        PluginField('simulate_unplugging','Simulate unplugging when a released vehicle does not resume charging',
                    'boolean',default=False),
    )

    def __init__(self,ha,params):
        values=parameters(self.configuration,params)
        self.url=base_url(values['url'])
        parsed=urlsplit(self.url)
        if parsed.port==0: raise ValueError('Invalid go-e API port')
        self.device_key=f'goe-v2:{parsed.scheme}://{parsed.hostname.lower()}:{parsed.port or (443 if parsed.scheme=="https" else 80)}'
        self.voltage=bounded(values['nominal_voltage'],100,260)
        if self.voltage is None: raise ValueError('Invalid nominal voltage')
        self.switching=values['phase_switching']
        self.unplugging=values['simulate_unplugging']
        # Monotonic start of the current stalled release; one restart per vehicle session.
        self.stalled_since=None
        self.unplug_attempts=0
        self.features=WallboxFeatures(phase_switching=self.switching,optional_connection=True)
        self.ids=dict.fromkeys(('power','status','enable','current','phases'),'')
        self.opener=None  # Certificate loading belongs to the first executor request.
        self.deadline=RequestDeadline('eos-goe-request')
        self.zero_after=self.zero_sample=self.phase_requested=None
        # Last charger decision for diagnostics; each change is logged at INFO.
        self.charger_status=None

    def _request(self,path,timeout=3):
        def exchange():
            if self.opener is None:
                self.opener=build_opener(ProxyHandler({}),NoRedirect())
            request=Request(self.url+path,headers={'Accept':'application/json','Cache-Control':'no-cache'})
            with self.opener.open(request,timeout=timeout) as response: return response.read(65537)
        try:
            raw=self.deadline.run(exchange,timeout+REQUEST_GRACE_S)
            if len(raw)>65536: raise ValueError('Oversized response')
            result=json.loads(raw)
            if not isinstance(result,dict): raise ValueError('Expected JSON object')
            return result
        except (OSError,HTTPException,ValueError,TypeError):
            raise GoEAPIError('go-e local HTTP API v2 request failed') from None

    def _status(self,keys=STATUS_KEYS,timeout=3):
        return self._request('/api/status?'+urlencode({'filter':','.join(keys)}),timeout)

    def _set(self,**values):
        if not values or values.keys()-{'amp','frc','psm','sua'}: raise ValueError('Invalid go-e setting')
        for key,value in values.items():
            if key=='sua':
                if value is not True: raise ValueError('Invalid go-e setting value')
            elif integer(value,6 if key=='amp' else 1,32 if key=='amp' else 2) is None:
                raise ValueError('Invalid go-e setting value')
        result=self._request('/api/set?'+urlencode({key:json.dumps(value) for key,value in values.items()}))
        if any(result.get(key) is not True for key in values):
            raise GoEAPIError('go-e rejected requested setting')
        release=values.get('frc')==2
        keys=tuple(values)+(('alw','modelStatus') if 'frc' in values else ())
        deadline=monotonic()+(RELEASE_CONFIRM_S if release else CONFIRM_S)
        while True:
            remaining=deadline-monotonic()
            if remaining<=0: raise GoEAPIError('go-e did not confirm requested setting')
            try: actual=self._status(keys,min(3,remaining))
            except GoEAPIError:
                # A slow answer during the charger's own transition is retried within the deadline.
                if deadline-monotonic()<=.25: raise
                sleep(.25)
                continue
            matches=all(type(actual.get(key)) is type(value) and actual[key]==value for key,value in values.items())
            if 'frc' in values:
                allowed=type(actual.get('alw')) is bool and actual['alw']==release
                # The release is accepted; the charger's own timed transition ends by itself.
                pending=release and actual.get('modelStatus') in RELEASE_PENDING
                matches=matches and (allowed or pending)
            if matches: return actual
            if deadline-monotonic()<=.25: raise GoEAPIError('go-e did not confirm requested setting')
            sleep(.25)  # The charger recalculates permission once per second.

    def _observe(self,now):
        data=self._status()
        self._record_status(data)
        if (integer(data.get('frc'),0,2) is None or type(data.get('alw')) is not bool
                or type(data.get('adi')) is not bool or integer(data.get('amp'),0,32) is None):
            raise GoEAPIError('Incomplete go-e control response')
        nrg=data.get('nrg')
        if not isinstance(nrg,list) or not 12<=len(nrg)<=64:
            raise GoEAPIError('Incomplete go-e API v2 power measurement')
        watts=bounded(nrg[11],0,25000)  # API v2 uses W; v1 has different scales.
        car=integer(data.get('car'),0,6)
        error=integer(data.get('err'),0,255)
        status={0:'unknown',1:'disconnected',2:'charging',3:'connected',4:'connected',5:'error',6:'unknown'}.get(car,'unknown')
        if error is None: status='unknown'
        elif error or car==5: status='error'
        rated={11:16,22:32}.get(integer(data.get('var'),0,255))
        maximum=integer(data.get('ama'),6,32)
        cable=integer(data.get('cbl'),6,32)
        caps=[rated,maximum,16 if data['adi'] else 32]
        if status!='disconnected': caps.append(cable)
        maximum=min(caps) if all(value is not None for value in caps) else None
        # The shared EOS/EV controller currently models a 6 A minimum.
        if integer(data.get('mca'),6,6) is None: maximum=None
        pha=data.get('pha')
        available=None
        if isinstance(pha,list) and len(pha)==6 and all(type(value) is bool for value in pha):
            available=max(sum(pha[:3]),sum(pha[3:]))
        if available in (None,0):
            voltages=[bounded(value,100,260) for value in nrg[:3]]
            available=sum(value is not None for value in voltages)
        if available not in (1,3): available=None
        mode=integer(data.get('psm'),0,2)
        reported=integer(data.get('pnp'),1,3)
        if reported==2: reported=None
        if reported is None and type(data.get('fsp')) is bool: reported=1 if data['fsp'] else 3
        phases={1:1,2:3}.get(mode,reported)
        if phases and available: phases=min(phases,available)
        else: phases=None
        self.features=WallboxFeatures(phase_switching=bool(self.switching and available==3 and mode is not None
                                                         and reported is not None),optional_connection=True)
        max_phases=available if self.features.phase_switching else phases
        sample=WallboxReading(watts,status,data['alw'],phases,data['amp'],1,maximum,
                             now if watts is not None else None,max_phases=max_phases,
                             nominal_voltage=self.voltage if available is not None else None)
        zero=watts is not None and watts<=30 and all(
            bounded(value,0,.2) is not None for value in nrg[4:7])
        return sample,data,reported,zero

    def _record_status(self,data):
        if data.get('car') not in STALLED_CAR_STATES:
            # Charging, unplugged or unknown: a later stall is a new situation.
            self.stalled_since=None
            self.unplug_attempts=0
        status=charger_status(data)
        if status!=self.charger_status:
            _LOGGER.info('go-e charger status: %s',json.dumps(status,sort_keys=True))
            self.charger_status=status

    def _read(self,states,now):
        try: return self._observe(now)[0]
        except GoEAPIError as error:
            from ..plugin_diagnostics import partial_read_failure
            partial_read_failure(self, error, 'telemetry')
            return WallboxReading(None,'unavailable',False,None,None,None,None,None)

    def _pause(self,state):
        self.zero_after=self.zero_sample=self.phase_requested=None
        # A stop is still sent while an abandoned telemetry exchange is open.
        with self.deadline.priority(): self._set(frc=1)

    def _phase(self,phases,state):
        fresh,data,reported,zero=self._observe(datetime.now(timezone.utc))
        desired={1:1,3:2}[phases]
        if not self.features.phase_switching:
            raise GoEAPIError('go-e phase switching is unavailable')
        if self.phase_requested is not None:
            target,started=self.phase_requested
            if fresh.enabled or data['frc']!=1:
                self._set(frc=1)
                return False
            if (data.get('psm')=={1:1,3:2}[target] and reported==target and not fresh.enabled
                    and data['frc']==1 and zero and fresh.status=='connected'):
                self.zero_after=self.zero_sample=self.phase_requested=None
                # Like evcc: some vehicles hang after a phase switch; allow one more restart.
                self.unplug_attempts=min(self.unplug_attempts,MAX_UNPLUG_ATTEMPTS-1)
                self.stalled_since=None
                return target==phases
            if monotonic()-started>=45: raise GoEAPIError('go-e phase switch was not confirmed')
            return False
        if data.get('psm')==desired and reported==phases: return True
        if fresh.enabled or data['frc']!=1 or self.zero_after is None:
            self._pause(fresh)
            self.zero_after=fresh.sample
            return False
        if (not zero or fresh.status!='connected' or fresh.sample is None or fresh.sample<=self.zero_after):
            self.zero_sample=None
            return False
        if self.zero_sample is None:
            self.zero_sample=fresh.sample
            return False
        if (fresh.sample-self.zero_sample).total_seconds()<3: return False
        self._set(psm=desired)
        self.phase_requested=(phases,monotonic())
        return False

    def _charge(self,amps,state):
        if self.phase_requested is not None: raise GoEAPIError('go-e phase switch is pending')
        try:
            fresh,data,_,_=self._observe(datetime.now(timezone.utc))
            if (fresh.maximum is None or amps>fresh.maximum or fresh.phases not in (1,3)
                    or fresh.phases!=state.phases or fresh.nominal_voltage!=state.nominal_voltage
                    or fresh.watts is None or fresh.status not in ('connected','charging')):
                raise GoEAPIError('go-e is not ready for requested charging current')
            if data['amp']!=int(amps): self._set(amp=int(amps))
            if data['frc']!=2 or not fresh.enabled: self._set(frc=2)
            elif self._stalled(data,fresh): self._simulate_unplugging(data)
        except GoEAPIError:
            try: self._pause(state)
            except GoEAPIError: pass
            raise

    def _hold(self,amps,state):
        if (not self.unplugging or self.unplug_attempts>=MAX_UNPLUG_ATTEMPTS or self.phase_requested is not None
                or not state.enabled or state.status!='connected' or state.watts is None or state.watts>STALLED_IDLE_W):
            self.stalled_since=None
            return
        try: fresh,data,_,_=self._observe(datetime.now(timezone.utc))
        except GoEAPIError: return  # The telemetry failure is reported by the regular read.
        if data['frc']!=2 or not fresh.enabled or not self._stalled(data,fresh): return
        try: self._simulate_unplugging(data)
        except GoEAPIError:
            try: self._pause(state)
            except GoEAPIError: pass
            raise

    def _stalled(self,data,fresh):
        """Charging stays released, but the connected vehicle takes no power."""
        if (not self.unplugging or self.unplug_attempts>=MAX_UNPLUG_ATTEMPTS or data.get('car') not in STALLED_CAR_STATES
                or fresh.watts is None or fresh.watts>STALLED_IDLE_W):
            self.stalled_since=None
            return False
        if self.stalled_since is None:
            self.stalled_since=monotonic()
            return False
        return monotonic()-self.stalled_since>=STALLED_RESTART_S

    def _simulate_unplugging(self,data):
        """Let the charger simulate unplugging and restart the released session."""
        self.unplug_attempts+=1
        self.stalled_since=None
        enabled=data.get('sua') is not True
        if enabled: self._set(sua=True)
        self._set(frc=1)
        self._set(frc=2)
        _LOGGER.info('go-e simulated unplugging: vehicle took no power while charging was released '
                     '(attempt %d of %d, car state %s, charger setting simulateUnpluggingAlways %s)',
                     self.unplug_attempts,MAX_UNPLUG_ATTEMPTS,CAR_STATES.get(data.get('car'),'unknown'),
                     'enabled' if enabled else 'already enabled')

    def idle_reason(self):
        """Why a released, connected vehicle takes no power, from the last charger status."""
        status=self.charger_status or {}
        reason=(status.get('reason') or {}).get('code')
        if reason in IDLE_REASONS: return IDLE_REASONS[reason]
        if status.get('error'): return 'charger_error'
        car=(status.get('car') or {}).get('code')
        return {4:'vehicle_complete',3:'vehicle_waiting'}.get(car)


PLUGINS=(GoEHTTPv2,)

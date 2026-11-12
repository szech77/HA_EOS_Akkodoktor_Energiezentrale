"""Local go-e HTTP API v2 (firmware >= 051.4), independent of HA entities.

https://github.com/goecharger/go-eCharger-API-v2/blob/main/http-en.md
"""
from datetime import datetime, timezone
from http.client import HTTPException
import json
from time import monotonic, sleep
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, ProxyHandler, build_opener

from ..clients import NoRedirect, base_url
from ..contracts import WallboxDriver, WallboxFeatures, WallboxReading, PluginInfo, PluginField
from ..plugin_parameters import parameters
from ..sanitiser import bounded

STATUS_KEYS=('car','err','frc','alw','amp','ama','adi','cbl','var','nrg','psm','pnp','pha','fsp','mca')


class GoEAPIError(OSError):
    """Device errors without private response content or network locations."""


def integer(value,minimum,maximum):
    return value if type(value) is int and minimum<=value<=maximum else None


class GoEHTTPv2(WallboxDriver):
    info=PluginInfo('goe_http_v2','go-e Charger – lokale HTTP-API v2','wallbox')
    configuration=(
        PluginField('url','Local HTTP API v2 base URL','text',default='http://go-echarger.local'),
        PluginField('phase_switching','Enable supported 1-/3-phase switching','boolean',default=False),
        PluginField('nominal_voltage','Nominal phase-to-neutral voltage (V)','number',default=230),
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
        self.features=WallboxFeatures(phase_switching=self.switching,optional_connection=True)
        self.ids=dict.fromkeys(('power','status','enable','current','phases'),'')
        self.opener=None  # Certificate loading belongs to the first executor request.
        self.zero_after=self.zero_sample=self.phase_requested=None

    def _request(self,path,timeout=3):
        try:
            if self.opener is None:
                self.opener=build_opener(ProxyHandler({}),NoRedirect())
            request=Request(self.url+path,headers={'Accept':'application/json','Cache-Control':'no-cache'})
            with self.opener.open(request,timeout=timeout) as response: raw=response.read(65537)
            if len(raw)>65536: raise ValueError('Oversized response')
            result=json.loads(raw)
            if not isinstance(result,dict): raise ValueError('Expected JSON object')
            return result
        except (OSError,HTTPException,ValueError,TypeError):
            raise GoEAPIError('go-e local HTTP API v2 request failed') from None

    def _status(self,keys=STATUS_KEYS,timeout=3):
        return self._request('/api/status?'+urlencode({'filter':','.join(keys)}),timeout)

    def _set(self,**values):
        if not values or values.keys()-{'amp','frc','psm'}: raise ValueError('Invalid go-e setting')
        for key,value in values.items():
            if integer(value,6 if key=='amp' else 1,32 if key=='amp' else 2) is None:
                raise ValueError('Invalid go-e setting value')
        result=self._request('/api/set?'+urlencode({key:json.dumps(value) for key,value in values.items()}))
        if any(result.get(key) is not True for key in values):
            raise GoEAPIError('go-e rejected requested setting')
        keys=tuple(values)+(('alw',) if 'frc' in values else ())
        deadline=monotonic()+4
        while True:
            remaining=deadline-monotonic()
            if remaining<=0: raise GoEAPIError('go-e did not confirm requested setting')
            actual=self._status(keys,min(3,remaining))
            matches=all(type(actual.get(key)) is type(value) and actual[key]==value for key,value in values.items())
            if 'frc' in values:
                matches=matches and type(actual.get('alw')) is bool and actual['alw']==(values['frc']==2)
            if matches: return actual
            if deadline-monotonic()<=.25: raise GoEAPIError('go-e did not confirm requested setting')
            sleep(.25)  # The charger recalculates permission once per second.

    def _observe(self,now):
        data=self._status()
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

    def _read(self,states,now):
        try: return self._observe(now)[0]
        except GoEAPIError:
            return WallboxReading(None,'unavailable',False,None,None,None,None,None)

    def _pause(self,state):
        self.zero_after=self.zero_sample=self.phase_requested=None
        self._set(frc=1)

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
        except GoEAPIError:
            try: self._pause(state)
            except GoEAPIError: pass
            raise


PLUGINS=(GoEHTTPv2,)

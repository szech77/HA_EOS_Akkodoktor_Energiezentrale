"""On-demand hourly HA weather, independent of the device control lock."""
import asyncio
from datetime import datetime, timedelta, timezone
from time import monotonic

from homeassistant.components.weather import WeatherEntityFeature
from homeassistant.exceptions import HomeAssistantError

from .energy.domain import instant, number
from .energy.presentation import WEATHER_CONDITIONS, weather_source


def bounded(value, minimum, maximum):
    value=number(value)
    return value if value is not None and minimum<=value<=maximum else None


def hourly_rows(raw, temperature_unit, precipitation_unit, now):
    """Keep missing fields unknown; do not turn daily data into hourly points."""
    if not isinstance(raw,list): return []
    rows={}
    for row in raw[:512]:
        if not isinstance(row,dict): continue
        stamp=instant(row.get('datetime'))
        if stamp is None or not now-timedelta(hours=1)<stamp<=now+timedelta(hours=24): continue
        temperature=number(row.get('temperature'))
        celsius=((temperature-32)*5/9 if temperature_unit=='°F' else temperature-273.15
                 if temperature_unit=='K' else temperature) if temperature is not None else None
        if temperature_unit not in {'°C','°F','K'} or celsius is None or not -100<=celsius<=70: temperature=None
        rain=bounded(row.get('precipitation'),0,10000) if precipitation_unit in {'mm','in'} else None
        if rain is not None and precipitation_unit=='in': rain*=25.4
        condition=row.get('condition')
        rows[stamp]={'time':stamp.astimezone(timezone.utc).isoformat(),'temperature':temperature,
                     'condition':condition if isinstance(condition,str) and condition in WEATHER_CONDITIONS else 'unknown',
                     'precipitation':rain,'precipitation_probability':bounded(row.get('precipitation_probability'),0,100)}
    stamps=sorted(rows)
    for index,stamp in enumerate(stamps):
        end=min(stamp+timedelta(hours=1),stamps[index+1]) if index+1<len(stamps) else stamp+timedelta(hours=1)
        rows[stamp]['end']=end.astimezone(timezone.utc).isoformat()
    return [rows[stamp] for stamp in stamps]


class WeatherForecast:
    def __init__(self,hass):
        self.hass=hass
        self.lock=asyncio.Lock()
        self.cached=None

    async def async_read(self,options):
        async with self.lock:
            states={state.entity_id:{'state':state.state} for state in self.hass.states.async_all('weather')}
            entity=weather_source(states,options)
            state=self.hass.states.get(entity) if entity else None
            result={'rows':[],'temperature_unit':'°C','precipitation_unit':'mm','source':None,'fetched_at':None}
            if state is None: return {**result,'status':'missing_source'}
            result['source']=state.name
            if state.state not in WEATHER_CONDITIONS: return {**result,'status':'unavailable'}
            features=state.attributes.get('supported_features',0)
            if not isinstance(features,int) or not features & WeatherEntityFeature.FORECAST_HOURLY:
                return {**result,'status':'unsupported'}
            unit=state.attributes.get('temperature_unit','°C')
            rain_unit=state.attributes.get('precipitation_unit')
            if not isinstance(unit,str): unit=None
            if not isinstance(rain_unit,str): rain_unit=None
            key=(entity,unit,rain_unit)
            if self.cached is not None and self.cached[0]==key and monotonic()-self.cached[1]<300:
                _,_,raw,fetched=self.cached
            else:
                try:
                    async with asyncio.timeout(12):
                        response=await self.hass.services.async_call('weather','get_forecasts',
                            {'entity_id':entity,'type':'hourly'},blocking=True,return_response=True)
                    payload=response.get(entity) if isinstance(response,dict) else None
                    raw=payload.get('forecast') if isinstance(payload,dict) else None
                    if not isinstance(raw,list): return {**result,'status':'unavailable'}
                except (HomeAssistantError,OSError,TimeoutError,ValueError,TypeError):
                    return {**result,'status':'unavailable'}
                fetched=datetime.now(timezone.utc).isoformat()
                self.cached=(key,monotonic(),raw,fetched)
            rows=hourly_rows(raw,unit,rain_unit,datetime.now(timezone.utc))
            return {**result,'rows':rows,'temperature_unit':unit if unit in {'°C','°F','K'} else '°C',
                    'status':'available' if rows else 'empty','fetched_at':fetched}

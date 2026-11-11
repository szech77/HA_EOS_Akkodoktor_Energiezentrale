"""Display forecasts use native hourly HA responses without affecting control."""
import asyncio
from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import patch

from homeassistant.core import HomeAssistant, SupportsResponse
from homeassistant.exceptions import HomeAssistantError

from custom_components.eos_energiezentrale.weather_forecast import WeatherForecast, hourly_rows
from test_energy import temporary_project_directory

NOW=datetime(2026,11,12,12,tzinfo=timezone.utc)


def row(offset=0,**values):
    return {'datetime':(NOW+timedelta(hours=offset)).isoformat(),'temperature':8,
            'condition':'rainy','precipitation':0,'precipitation_probability':10,**values}


class ForecastNormalizationTests(unittest.TestCase):
    def test_window_sorting_duplicates_and_gaps_are_bounded_to_hourly_intervals(self):
        raw=[row(2),row(-1),row(0),row(0,temperature=10),row(24),row(25),row(datetime='2026-11-12T12:00:00'),None]
        result=hourly_rows(raw,'°C','mm',NOW)
        self.assertEqual([item['temperature'] for item in result],[10,8,8])
        self.assertEqual(result[0]['end'],(NOW+timedelta(hours=1)).isoformat())
        self.assertEqual(result[1]['time'],(NOW+timedelta(hours=2)).isoformat())

    def test_units_zero_and_missing_fields_remain_distinct(self):
        result=hourly_rows([row(temperature=32,precipitation=1)],'°F','in',NOW)[0]
        self.assertEqual(result['temperature'],32)
        self.assertAlmostEqual(result['precipitation'],25.4)
        for temperature,unit in ((0,'°C'),(273.15,'K')):
            self.assertEqual(hourly_rows([row(temperature=temperature)],unit,'mm',NOW)[0]['temperature'],temperature)
        result=hourly_rows([row(temperature=None,precipitation=None,condition=['invalid'],precipitation_probability=101)],'°C','mm',NOW)[0]
        self.assertEqual((result['temperature'],result['precipitation'],result['precipitation_probability']),(None,None,None))
        self.assertEqual(result['condition'],'unknown')
        for raw in ([row(temperature=True,precipitation=-1)], [row(temperature=float('nan'),precipitation=float('inf'))]):
            result=hourly_rows(raw,'°C','mm',NOW)[0]
            self.assertIsNone(result['temperature']);self.assertIsNone(result['precipitation'])
        self.assertIsNone(hourly_rows([row()],'W','W',NOW)[0]['temperature'])
        self.assertIsNone(hourly_rows([row()],'°C','W',NOW)[0]['precipitation'])


class WeatherServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory=self.enterContext(temporary_project_directory())
        self.hass=HomeAssistant(str(self.directory))
        self.reader=WeatherForecast(self.hass)
        self.calls=[]
        async def forecast(call):
            self.calls.append(dict(call.data))
            return {call.data['entity_id']:{'forecast':[{'datetime':datetime.now(timezone.utc).isoformat(),
                'temperature':10,'condition':'sunny','precipitation':0}]}}
        self.hass.services.async_register('weather','get_forecasts',forecast,supports_response=SupportsResponse.ONLY)
        self.hass.states.async_set('weather.home','sunny',{'temperature_unit':'°C','precipitation_unit':'mm','supported_features':2})

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)

    async def test_native_hourly_response_and_concurrent_requests_share_a_five_minute_cache(self):
        first,second=await asyncio.gather(self.reader.async_read({}),self.reader.async_read({}))
        self.assertEqual(first['status'],'available');self.assertEqual(first,second)
        self.assertEqual(first['rows'][0]['temperature'],10)
        self.assertEqual(self.calls,[{'entity_id':'weather.home','type':'hourly'}])
        key,stamp,raw,fetched=self.reader.cached
        self.reader.cached=(key,stamp-301,raw,fetched)
        await self.reader.async_read({})
        self.assertEqual(len(self.calls),2)

    async def test_selected_source_is_never_replaced_and_daily_only_weather_stays_unsupported(self):
        result=await self.reader.async_read({'weather_entity':'weather.missing'})
        self.assertEqual(result['status'],'missing_source')
        self.hass.states.async_set('weather.daily','sunny',{'supported_features':1})
        result=await self.reader.async_read({'weather_entity':'weather.daily'})
        self.assertEqual(result['status'],'unsupported');self.assertFalse(result['rows'])
        self.assertFalse(self.calls)
        # Automatic selection follows the same alphabetical choice as the current-weather icon.
        self.hass.states.async_set('weather.daily','unavailable')
        result=await self.reader.async_read({})
        self.assertEqual(result['status'],'available')

    async def test_offline_service_and_malformed_responses_do_not_expose_provider_errors(self):
        for response in (None,{}, {'weather.home':{'forecast':None}}):
            with patch.object(type(self.hass.services),'async_call',return_value=response):
                result=await self.reader.async_read({})
            self.assertEqual(result['status'],'unavailable')
            self.assertIsNone(self.reader.cached)
        for error in (HomeAssistantError('private-provider-detail'),TimeoutError(),OSError()):
            with patch.object(type(self.hass.services),'async_call',side_effect=error):
                result=await self.reader.async_read({})
            self.assertEqual(result['status'],'unavailable')
            self.assertNotIn('private-provider-detail',str(result))

    async def test_empty_hourly_forecast_and_missing_units_are_explicit(self):
        with patch.object(type(self.hass.services),'async_call',return_value={'weather.home':{'forecast':[]}}):
            result=await self.reader.async_read({})
        self.assertEqual(result['status'],'empty')
        self.hass.states.async_set('weather.home','unknown',{'supported_features':2})
        self.assertEqual((await self.reader.async_read({'weather_entity':'weather.home'}))['status'],'unavailable')

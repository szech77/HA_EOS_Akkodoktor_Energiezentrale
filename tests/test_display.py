"""Presentation retention never fills missing regulation or historical samples."""
from datetime import timedelta
import unittest
from custom_components.eos_energiezentrale.energy.display import DisplayValues
from test_energy import NOW


class DisplayRetentionRequirements(unittest.TestCase):
    def test_last_zero_and_signed_values_survive_short_outages_then_expire(self):
        cache=DisplayValues(900)
        for key,value in (("solar",0),("grid",-470)):
            cache.remember(key,value,NOW,NOW)
            self.assertEqual(cache.retained(key,NOW+timedelta(minutes=10))["value"],value)
            cache.remember(key,None,NOW+timedelta(minutes=10),NOW+timedelta(minutes=10))
            self.assertEqual(cache.retained(key,NOW+timedelta(minutes=14))["age_s"],840)
            self.assertIsNone(cache.retained(key,NOW+timedelta(seconds=901)))

    def test_older_and_future_reports_do_not_replace_last_good_sample(self):
        cache=DisplayValues(900)
        cache.remember("grid",100,NOW,NOW)
        cache.remember("grid",200,NOW-timedelta(seconds=10),NOW)
        cache.remember("grid",300,NOW+timedelta(seconds=10),NOW)
        self.assertEqual(cache.retained("grid",NOW)["value"],100)

    def test_retention_does_not_modify_live_readings(self):
        cache=DisplayValues(900)
        states={"sensor.grid":{"state":"100","last_reported":NOW.isoformat(),"attributes":{"unit_of_measurement":"W"}}}
        options={"grid_entity":"sensor.grid","heat_entity":"","wallbox_type":"none"}
        live={"grid":100}
        cache.update(states,live,options,{}, {},NOW)
        missing={"grid":None}
        states["sensor.grid"]["state"]="unavailable"
        result=cache.update(states,missing,options,{}, {},NOW+timedelta(seconds=60))
        self.assertEqual(result["grid"],{"value":100,"age_s":60})
        self.assertIsNone(missing["grid"])

    def test_expired_first_seen_report_is_not_presented_as_new(self):
        cache=DisplayValues(900)
        cache.remember("grid",470,NOW-timedelta(hours=1),NOW)
        self.assertIsNone(cache.retained("grid",NOW))

"""Display-only utilization must not affect energy metering or control."""
from datetime import timedelta
import unittest

from custom_components.eos_energiezentrale.energy.presentation import heat_utilization, power_references
from custom_components.eos_energiezentrale.energy.contracts import WallboxFeatures
from custom_components.eos_energiezentrale.validation import validate_options
from custom_components.eos_energiezentrale.const import DEFAULTS
from test_energy import NOW


class PowerRingRequirements(unittest.TestCase):
    def test_percent_and_factor_sources_have_identical_meaning(self):
        for value,scale,unit in ((25,'percent','%'),(.25,'factor',None)):
            with self.subTest(scale=scale):
                states={'sensor.wp_load':{'state':str(value),'attributes':{'unit_of_measurement':unit},'last_reported':NOW.isoformat()}}
                self.assertEqual(heat_utilization(states,{'heat_load_entity':'sensor.wp_load','heat_load_scale':scale},NOW),.25)

    def test_missing_invalid_stale_or_wrong_unit_heat_utilization_stays_unknown(self):
        self.assertIsNone(heat_utilization({}, {}, NOW))
        for value,unit,age in (('unavailable','%',0),(101,'%',0),(-1,'%',0),(25,'W',0),(25,'%',901)):
            with self.subTest(value=value,unit=unit,age=age):
                states={'sensor.wp':{'state':str(value),'attributes':{'unit_of_measurement':unit},'last_reported':(NOW-timedelta(seconds=age)).isoformat()}}
                self.assertIsNone(heat_utilization(states,{'heat_load_entity':'sensor.wp'},NOW))

    def test_display_only_heat_load_uses_the_existing_longer_display_hold(self):
        states={'sensor.wp':{'state':'50','attributes':{'unit_of_measurement':'%'},'last_reported':(NOW-timedelta(minutes=5)).isoformat()}}
        self.assertEqual(heat_utilization(states,{'heat_load_entity':'sensor.wp','display_hold_s':900},NOW),.5)

    def test_references_use_device_limits_and_fixed_phase_capability(self):
        values={**DEFAULTS,'pv_peak_w':16000,'battery_charge_w':4760,'battery_discharge_w':4000}
        reference=power_references(values,{'phases':1},WallboxFeatures(phase_switching=False))
        self.assertEqual(reference,{'solar':16000,'car':3680,'battery_charge':4760,'battery_discharge':4000})
        self.assertEqual(power_references(values,{'phases':1},WallboxFeatures(phase_switching=True))['car'],11000)

    def test_invalid_visual_configuration_is_rejected(self):
        for changes in ({'pv_peak_w':0},{'pv_peak_w':float('nan')},{'heat_load_entity':'switch.wp'},{'heat_load_scale':'watts'}):
            with self.subTest(changes=changes),self.assertRaises(ValueError):validate_options({**DEFAULTS,**changes})

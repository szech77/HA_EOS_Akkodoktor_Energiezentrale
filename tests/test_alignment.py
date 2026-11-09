"""Hold a charging-related source jump, not a general historical time alignment."""
from datetime import timedelta
import unittest
from custom_components.eos_energiezentrale.energy.alignment import ChargeTransitionDisplay
from test_energy import NOW


class ChargeDisplayRequirements(unittest.TestCase):
    def baseline(self):
        return {"solar":7000,"grid":-5000,"house_total":2000,"car":0,"battery_charge":0,"battery_discharge":0,"heat":0}

    def update(self,display,values,seconds,expected=6000,command=NOW):
        now=NOW+timedelta(seconds=seconds)
        # Reports are all fresh, even when the charger still reports its old value.
        return display.update(values,{key:now for key in values},now,
                              expected_car_w=expected,command_at=command)

    def test_source_jump_waits_even_if_old_car_value_has_a_fresh_report_timestamp(self):
        display=ChargeTransitionDisplay()
        original=self.baseline()
        self.update(display,original,0,expected=None)
        source_first={**original,"grid":1000,"house_total":8000}
        result=self.update(display,source_first,5)
        self.assertEqual(result["house"]["value"],2000)
        self.assertEqual(result["grid"]["value"],-5000)
        self.assertEqual(result["car"]["value"],0)
        self.assertTrue(result["grid"]["transition_held"])
        self.assertEqual(source_first["grid"],1000)
        # Once the actual charger reading catches up, no projection overrides it.
        self.assertEqual(self.update(display,{**source_first,"car":6000},10),{})

    def test_hold_expires_30_seconds_after_source_jump_not_after_command(self):
        display=ChargeTransitionDisplay()
        original=self.baseline()
        self.update(display,original,0,expected=None)
        source_first={**original,"grid":1000,"house_total":8000}
        self.assertTrue(self.update(display,source_first,20))
        self.assertTrue(self.update(display,source_first,49))
        self.assertEqual(self.update(display,source_first,50),{})
        self.assertEqual(self.update(display,source_first,51),{})

    def test_new_command_cannot_extend_an_already_running_hold(self):
        display=ChargeTransitionDisplay()
        original=self.baseline()
        self.update(display,original,0,expected=None)
        source_first={**original,"grid":1000,"house_total":8000}
        self.update(display,source_first,5)
        self.assertTrue(self.update(display,source_first,25,expected=6500,command=NOW+timedelta(seconds=20)))
        self.assertEqual(self.update(display,source_first,35,expected=6500,command=NOW+timedelta(seconds=20)),{})

    def test_no_global_smoothing_without_expected_charging_increase(self):
        display=ChargeTransitionDisplay()
        original=self.baseline()
        self.update(display,original,0,expected=None)
        self.assertEqual(self.update(display,{**original,"house_total":4000,"grid":-3000},5,expected=None),{})
        # More sun balanced by more export is not a load increase.
        self.assertEqual(self.update(display,{**original,"solar":9000,"grid":-7000},10),{})

    def test_cancellation_or_disabled_vehicle_releases_display_immediately(self):
        display=ChargeTransitionDisplay()
        original=self.baseline()
        self.update(display,original,0,expected=None)
        source_first={**original,"grid":1000,"house_total":8000}
        self.assertTrue(self.update(display,source_first,5))
        self.assertEqual(self.update(display,source_first,6,expected=0),{})

    def test_actual_power_is_never_replaced_by_commanded_power(self):
        display=ChargeTransitionDisplay()
        original=self.baseline()
        self.update(display,original,0,expected=None)
        partial={**original,"grid":1000,"house_total":8000,"car":2000}
        result=self.update(display,partial,5)
        self.assertEqual(result["car"]["value"],0)
        self.assertNotEqual(result["car"]["value"],6000)
        self.assertEqual(self.update(display,partial,35),{})

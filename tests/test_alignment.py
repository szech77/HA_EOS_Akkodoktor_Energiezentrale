"""Asynchronous meter arrivals must not invent a spike in household usage."""
from datetime import timedelta
import unittest
from custom_components.eos_energiezentrale.energy.alignment import FlowAlignment
from test_energy import NOW


class AlignmentRequirements(unittest.TestCase):
    def baseline(self):
        return {"solar":7000,"grid":-5000,"house_total":2000,"car":0,"battery_charge":0,"battery_discharge":0,"heat":0}

    def test_net_meter_arrives_first_then_wallbox_catches_up_without_house_spike(self):
        align=FlowAlignment(2,900)
        original=self.baseline()
        times={key:NOW for key in original}
        align.update(original,times,NOW)
        later={**original,"grid":1000,"house_total":8000}
        times={key:NOW+timedelta(seconds=5) for key in original}
        times["car"]=NOW
        held=align.update(later,times,NOW+timedelta(seconds=5))
        self.assertEqual(held["house"]["value"],2000)
        self.assertEqual(held["grid"]["value"],-5000)
        self.assertEqual(held["car"]["value"],0)
        times={key:NOW+timedelta(seconds=10) for key in original}
        result=align.update({**later,"car":6000},times,NOW+timedelta(seconds=10))
        self.assertEqual(result["house"]["value"],2000)
        self.assertEqual(result["grid"]["value"],1000)
        self.assertEqual(result["car"]["value"],6000)
        self.assertEqual(later["house_total"],8000)

    def test_coherent_zero_readings_expire_and_do_not_become_fresh(self):
        align=FlowAlignment(2,60)
        values={key:0 for key in self.baseline()}
        times={key:NOW for key in values}
        result=align.update(values,times,NOW)
        self.assertEqual(result["car"]["value"],0)
        result=align.update({}, {},NOW+timedelta(seconds=30))
        self.assertEqual(result["car"]["age_s"],30)
        self.assertEqual(align.update({}, {},NOW+timedelta(seconds=61)),{})

    def test_absent_vehicle_is_not_required_for_alignment(self):
        values=self.baseline()
        values.pop("car")
        result=FlowAlignment().update(values,{key:NOW for key in values},NOW,car=False)
        self.assertEqual(result["house"]["value"],2000)
        self.assertNotIn("car",result)

    def test_fleet_waits_for_individual_charger_reports_instead_of_redating_their_sum(self):
        align=FlowAlignment(2,900)
        baseline=self.baseline()
        times={key:NOW for key in baseline}
        align.update(baseline,times,NOW,cars={"a":(0,NOW),"b":(0,NOW)})
        now=NOW+timedelta(seconds=5)
        live={**baseline,"grid":1000,"house_total":8000,"car":3000}
        times={key:now for key in baseline}
        result=align.update(live,times,now,cars={"a":(3000,now),"b":(0,NOW)})
        self.assertEqual(result["car"]["value"],0)
        self.assertEqual(result["house"]["value"],2000)
        now=NOW+timedelta(seconds=10)
        result=align.update({**live,"car":6000},{key:now for key in baseline},now,
                            cars={"a":(3000,now),"b":(3000,now)})
        self.assertEqual(result["car"]["value"],6000)
        self.assertEqual(result["house"]["value"],2000)

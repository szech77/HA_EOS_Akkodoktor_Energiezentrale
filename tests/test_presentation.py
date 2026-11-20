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


def test_node_problems_map_notices_to_flow_nodes_and_vehicles():
    from custom_components.eos_energiezentrale.energy.presentation import node_problems
    notices = [
        {'code':'sources_unavailable', 'severity':'warning', 'scope':'system', 'measurements':['solar', 'house_total']},
        {'code':'battery_read', 'severity':'error', 'scope':'system'},
        {'code':'battery_limits', 'severity':'warning', 'scope':'system'},
        {'code':'backup_power_active', 'severity':'info', 'scope':'system'},
        {'code':'wallbox_stop', 'severity':'error', 'scope':'system'},
        {'code':'goal', 'severity':'warning', 'scope':'vehicle/2'},
        {'code':'goal', 'severity':'warning', 'scope':'vehicle/9'},
    ]
    assert node_problems(notices) == {'solar':'warning', 'house':'warning', 'battery':'error', 'car':'error'}
    fleet = node_problems(notices, [{'id':'first'}, {'id':'second'}])
    assert fleet['car/first'] == 'error' and fleet['car/second'] == 'warning'
    assert 'car' not in fleet and 'grid' not in fleet


def test_plan_events_list_changes_milestones_and_prices_in_time_order():
    from datetime import datetime, timedelta, timezone
    from custom_components.eos_energiezentrale.energy.presentation import plan_events
    now = datetime(2026, 11, 18, 13, 32, tzinfo=timezone.utc)
    at = lambda minutes: (now + timedelta(minutes=minutes)).isoformat()
    forecast = [{'time':at(15*i), 'end':at(15*(i+1)), 'price':24.1 if i >= 50 else 30.4,
                 'battery_soc':min(95, 60 + 5*i), 'car_soc':min(80, 40 + i)} for i in range(100)]
    data = {'live':{'battery_mode':'NON_EXPORT', 'car_mode':'IDLE', 'battery_soc':60, 'car_soc':40},
            'settings':{'battery_max_soc':95}, 'charge_target_soc':80, 'forecast':forecast,
            'plan':{'battery':[{'time':at(-60), 'mode':'SELF_CONSUMPTION'}, {'time':at(90), 'mode':'NON_EXPORT'},
                               {'time':at(28), 'mode':'SELF_CONSUMPTION'}, {'time':at(60*30), 'mode':'IDLE'}],
                    'car':[{'time':at(12*60+30), 'mode':'FORCED_CHARGE'}]}}
    events = plan_events(data, now)
    assert [(row['kind'], row.get('device'), row.get('mode')) for row in events] == [
        ('mode', 'battery', 'SELF_CONSUMPTION'), ('mode', 'battery', 'NON_EXPORT'),
        ('battery_full', None, None), ('car_target', None, None), ('mode', 'car', 'FORCED_CHARGE')]
    assert events[0]['price_ct'] == 30.4 and events[-1]['price_ct'] == 24.1
    assert events[2]['soc'] == 95 and events[2]['time'] == at(105)
    assert all(now < datetime.fromisoformat(row['time']) <= now + timedelta(hours=24) for row in events if row['kind'] == 'mode')
    # Already full or without a target: no milestone; disabled wallbox: no car events.
    data['live']['battery_soc'] = 95
    data['features'] = {'car':False}
    assert [row['kind'] for row in plan_events(data, now)] == ['mode', 'mode']
    vehicles = {**data, 'features':{'car':True}, 'vehicles':[{'id':'a', 'name':'ID.4', 'live':{'car_mode':'IDLE', 'car_soc':40},
        'charge_target_soc':80, 'forecast':forecast, 'plan':{'car':[{'time':at(90), 'mode':'FORCED_CHARGE'}]}}]}
    fleet = plan_events(vehicles, now)
    assert {row['vehicle_id'] for row in fleet if row.get('device') == 'car' or row['kind'] == 'car_target'} == {'a'}
    assert len(plan_events(vehicles, now, limit=2)) == 2


def test_plan_events_skip_short_mode_blips_and_describe_the_forecast_battery_effect():
    from datetime import datetime, timedelta, timezone
    from custom_components.eos_energiezentrale.energy.presentation import battery_effect, plan_events
    now = datetime(2026, 11, 19, 4, 55, tzinfo=timezone.utc)
    at = lambda minutes: (now + timedelta(minutes=minutes)).isoformat()
    # Night: grid charging until 05:15, then the battery holds; PV charging starts at 08:00.
    def row(index):
        minutes = 15 * index
        battery = 2600 if minutes < 15 else 2000 if minutes >= 185 else 0
        return {'time':at(minutes), 'end':at(minutes + 15), 'price':28.1, 'battery':battery,
                'solar':3000 if minutes >= 185 else 0, 'battery_soc':93}
    forecast = [row(index) for index in range(40)]
    plan = [{'time':at(-30), 'mode':'FORCED_CHARGE'}, {'time':at(20), 'mode':'NON_EXPORT'},
            {'time':at(110), 'mode':'FORCED_CHARGE'}, {'time':at(125), 'mode':'NON_EXPORT'},
            {'time':at(140), 'mode':'SELF_CONSUMPTION'}, {'time':at(155), 'mode':'NON_EXPORT'}]
    data = {'live':{'battery_mode':'FORCED_CHARGE', 'battery_soc':93}, 'settings':{}, 'features':{'car':False},
            'forecast':forecast, 'plan':{'battery':plan}}
    events = plan_events(data, now)
    # The 15-minute blips at 06:45 and 07:15 are skipped; NON_EXPORT at night holds the charge level.
    assert [(row['mode'], row['effect'], row['time']) for row in events] == [('NON_EXPORT', 'hold', at(20))]
    assert battery_effect(forecast, now + timedelta(minutes=190), now + timedelta(minutes=300)) == 'charge_pv'
    assert battery_effect(forecast, now, now + timedelta(minutes=15)) == 'charge_grid'
    assert battery_effect([{'time':at(0), 'end':at(60), 'battery':-900}], now, now + timedelta(minutes=60)) == 'discharge'
    assert battery_effect([], now, now + timedelta(minutes=60)) is None

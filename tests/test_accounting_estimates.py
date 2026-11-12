"""Battery book value and explicitly approximate consumption survive missing telemetry."""
from copy import deepcopy
from contextlib import closing
from datetime import datetime,timedelta,timezone
import json
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock,patch
from zoneinfo import ZoneInfo

from custom_components.eos_energiezentrale.energy.accounting import Accounting,empty
from custom_components.eos_energiezentrale.energy.accounting_history import reconstruct
from test_accounting import sample
from test_energy import NOW,temporary_project_directory


def battery_sample(now=NOW,soc=50,power=3600):
    return sample(now,solar=0,grid=0,battery_charge=0,battery_discharge=power,battery_soc=soc,
                  house_total=power,house=power/2,heat=power/2,car=0)


class RobustEstimates(TestCase):
    def setUp(self):
        self.directory=self.enterContext(temporary_project_directory())
        self.zone=ZoneInfo('Europe/Berlin')
        self.model=Accounting(self.directory,self.zone)
        self.model.configure({'pv_price_source':'manual','pv_price_ct':8.1,'efficiency_source':'manual',
                              'capacity_wh':10000,'charge_efficiency':.9,'discharge_efficiency':.9,'initial_price_ct':20})

    def test_restart_interpolates_downtime_and_both_consumers_share_the_retained_price(self):
        self.model.observe(battery_sample())
        self.model.observe(battery_sample(NOW+timedelta(minutes=1),soc=49+1/3))
        restarted=Accounting(self.directory,self.zone)
        restarted.observe(battery_sample(NOW+timedelta(minutes=6),soc=46))
        report=restarted.report({'period':'day'},NOW)
        for key in ('house','heat'):
            amount=report['consumers'][key]['total']
            self.assertAlmostEqual(amount['kwh'],.18)
            self.assertAlmostEqual(amount['sources']['battery']['cost_eur']/amount['sources']['battery']['kwh'],.2/.9)
            self.assertEqual(amount['cost_unknown_kwh'],0)
            self.assertAlmostEqual(amount['estimated_seconds'],300)
        self.assertAlmostEqual(restarted.stock['cost'],.92)
        self.assertEqual(restarted.stock['unknown'],0)

    def test_trapezoid_interpolation_tracks_rising_load_and_observed_soc(self):
        self.model.observe(battery_sample(power=0))
        self.model.observe(battery_sample(NOW+timedelta(minutes=10),soc=43+1/3,power=7200))
        report=self.model.report({'period':'day'},NOW)
        for key in ('house','heat'):
            amount=report['consumers'][key]['total']
            self.assertAlmostEqual(amount['kwh'],.3)
            self.assertAlmostEqual(amount['estimated_kwh'],.3)
        self.assertAlmostEqual(self.model.stock['kwh'],(43+1/3)/10)
        self.assertAlmostEqual(self.model.stock['cost']/self.model.stock['kwh'],.2)

    def test_missing_battery_power_uses_balance_without_erasing_the_book_value(self):
        first=battery_sample();first.update(battery_charge=None,battery_discharge=None)
        self.model.observe(first)
        self.model.observe(battery_sample(NOW+timedelta(minutes=1),soc=49+1/3))
        amount=self.model.report({'period':'day'},NOW)['consumers']['heat']['total']
        self.assertGreater(amount['cost_eur'],0)
        self.assertAlmostEqual(amount['cost_eur']/amount['kwh'],.2/.9)
        self.assertEqual(self.model.stock['unknown'],0)

    def test_long_outage_preserves_price_and_soc_without_fabricating_days_of_consumption(self):
        self.model.observe(battery_sample())
        self.model.observe(battery_sample(NOW+timedelta(hours=24),soc=60))
        self.assertAlmostEqual(self.model.stock['cost'],1.2)
        self.assertFalse(self.model.report({'period':'day'},NOW)['consumers'])
        self.model.observe(battery_sample(NOW+timedelta(hours=24,minutes=1),soc=59+1/3))
        amount=self.model.report({'period':'day'},NOW+timedelta(days=1))['consumers']['heat']['total']
        self.assertAlmostEqual(amount['cost_eur']/amount['kwh'],.2/.9)
        self.assertGreater(amount['estimated_kwh'],0)

    def test_exhausted_inventory_extrapolates_the_last_price_instead_of_free_discharge(self):
        self.model.stock={'kwh':.001,'cost':.0002,'unknown':0}
        row=battery_sample();row['consumers']={'heat':3600}
        amount=self.model.allocate(row,1/60000,self.model.effective())['heat']
        self.assertAlmostEqual(amount['cost_eur']/amount['kwh'],.2/.9)
        self.assertGreater(amount['estimated_kwh'],0)
        self.assertEqual(self.model.stock['kwh'],0)

    def test_restart_retains_last_valid_eos_parameters_for_display_only(self):
        self.model.configure({'efficiency_source':'eos'})
        self.model.eos_battery={'capacity_wh':10000,'charge_efficiency':.9,'discharge_efficiency':.9}
        self.model.observe(battery_sample())
        restarted=Accounting(self.directory,self.zone)
        self.assertIsNone(restarted.eos_battery)
        self.assertEqual(restarted.effective()['discharge_efficiency'],.9)
        restarted.observe(battery_sample(NOW+timedelta(minutes=1),soc=49+1/3))
        self.assertGreater(restarted.report({'period':'day'},NOW)['consumers']['heat']['total']['estimated_kwh'],0)

    def test_observed_grid_charging_replaces_initial_assumptions_for_later_soc_corrections(self):
        self.model.stock={'kwh':0.,'cost':0.,'unknown':0.}
        row=sample(solar=0,grid=1000,battery_charge=1000,battery_discharge=0,house_total=0,price=30)
        row['consumers']={}
        self.model.allocate(row,.001,self.model.effective())
        self.assertAlmostEqual(self.model.last_rate,.3/.9)
        self.model.reconcile_stock({'battery_soc':18,'time':NOW.isoformat()},self.model.effective())
        self.assertAlmostEqual(self.model.stock['cost'],.6)
        self.assertEqual(self.model.stock['unknown'],0)

    def test_unpriced_legacy_battery_rows_are_estimated_in_reports_without_overwriting_history(self):
        self.model.stock={'kwh':5,'cost':1,'unknown':0}
        amount=empty();amount.update(kwh=1,cost_unknown_kwh=1)
        amount['sources']['battery'].update(kwh=1,cost_unknown_kwh=1)
        day=NOW.astimezone(self.zone).date().isoformat()
        with closing(self.model.connect()) as db,db:
            db.execute('INSERT INTO energy VALUES (?,?,?,?)',(int(NOW.timestamp())//3600*3600,day,'heat',json.dumps(amount)))
        result=self.model.report({'period':'day'},NOW)['consumers']['heat']['total']
        self.assertAlmostEqual(result['cost_eur'],.2/.9)
        self.assertEqual(result['cost_unknown_kwh'],0)
        self.assertEqual(result['estimated_kwh'],1)
        with closing(self.model.connect()) as db:
            original=json.loads(db.execute('SELECT payload FROM energy').fetchone()[0])
        self.assertEqual(original['cost_eur'],0)
        self.assertEqual(original['cost_unknown_kwh'],1)

    def test_sql_failure_rolls_back_inventory_and_sample_so_retry_cannot_double_count(self):
        self.model.observe(battery_sample())
        before=deepcopy(self.model.stock)
        following=battery_sample(NOW+timedelta(minutes=1),soc=49+1/3)
        with patch.object(self.model,'_persist',side_effect=OSError('write failed')),self.assertRaises(OSError):
            self.model.observe(following)
        self.assertEqual(self.model.stock,before)
        self.assertEqual(self.model.previous[0],NOW)
        self.model.observe(following)
        result=self.model.report({'period':'day'},NOW)['consumers']['heat']['total']
        self.assertAlmostEqual(result['kwh'],.03)

    def test_restart_across_midnight_splits_interpolated_energy_into_both_days(self):
        start=datetime(2026,11,11,22,59,30,tzinfo=timezone.utc)
        self.model.observe(battery_sample(start))
        restarted=Accounting(self.directory,self.zone)
        restarted.observe(battery_sample(start+timedelta(minutes=2),soc=48+2/3))
        result=restarted.report({'period':'month','date':'2026-11-01'},start)['consumers']['heat']['bins']
        self.assertEqual([item['time'] for item in result],['2026-11-11','2026-11-12'])
        self.assertAlmostEqual(result[0]['kwh'],.015)
        self.assertAlmostEqual(result[1]['kwh'],.045)

    def test_historical_gaps_and_initial_stock_share_the_estimated_battery_price(self):
        start=datetime(2026,11,12,0,tzinfo=self.zone)
        report=self.model.report({'period':'day','date':'2026-11-12'},start)
        options={key+'_entity':'sensor.'+key for key in ('pv','house','grid','heat','price')}
        config=SimpleNamespace(options={**options,'wallbox_type':'none'},zone=self.zone,
            battery=SimpleNamespace(ids={'charge_power':'sensor.charge','discharge_power':'sensor.discharge','soc':'sensor.soc'}),
            wallbox=SimpleNamespace(ids={}),influx=Mock(url='http://influx'))
        values={'pv':0,'house':3600,'grid':0,'heat':1800,'price':30,'charge':0,'discharge':3600,'soc':50}
        config.influx.history.side_effect=lambda entity,*args,**kwargs:[[(start+timedelta(minutes=minute)).isoformat(),values[entity.split('.')[1]]] for minute in (0,20)]
        result=reconstruct(config,report,start+timedelta(minutes=25))
        for key in ('house','heat'):
            amount=result[key]['total']
            self.assertAlmostEqual(amount['kwh'],.75)
            self.assertAlmostEqual(amount['cost_eur']/amount['kwh'],.2/.9)
            self.assertEqual(amount['cost_unknown_kwh'],0)
            self.assertAlmostEqual(amount['estimated_kwh'],.75)

    def test_known_historical_tariff_steps_override_interpolated_endpoint_prices(self):
        start=datetime(2026,11,12,0,tzinfo=self.zone)
        report=self.model.report({'period':'day','date':'2026-11-12'},start)
        options={key+'_entity':'sensor.'+key for key in ('pv','house','grid','price')}
        config=SimpleNamespace(options={**options,'wallbox_type':'none','heat_entity':''},zone=self.zone,
            battery=SimpleNamespace(ids={'charge_power':'sensor.charge','discharge_power':'sensor.discharge'}),
            wallbox=SimpleNamespace(ids={}),influx=Mock(url='http://influx'))
        values={'pv':0,'house':3600,'grid':3600,'charge':0,'discharge':0}
        def history(entity,*args,**kwargs):
            if entity=='sensor.price':return [[(start+timedelta(minutes=m)).isoformat(),value] for m,value in ((0,0),(22,60),(40,0),(60,0))]
            return [[(start+timedelta(minutes=m)).isoformat(),values[entity.split('.')[1]]] for m in (0,60)]
        config.influx.history.side_effect=history
        amount=reconstruct(config,report,start+timedelta(hours=1))['house']['total']
        self.assertAlmostEqual(amount['kwh'],3.6)
        self.assertAlmostEqual(amount['cost_eur'],.648)

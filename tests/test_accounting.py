"""Business tests: energy conservation, cost provenance, gaps and calendar reports."""
from datetime import datetime, timedelta, timezone
from unittest import TestCase
from unittest.mock import Mock
from zoneinfo import ZoneInfo

from custom_components.eos_energiezentrale.energy.accounting import Accounting, checked_settings
from custom_components.eos_energiezentrale.energy.clients import EOS
from test_energy import NOW, temporary_project_directory


def sample(now=NOW, **changes):
    return {"time":now.isoformat(),"solar":1800,"grid":1800,"battery_charge":0,
            "battery_discharge":0,"battery_soc":0,"house_total":3600,
            "house":1800,"heat":900,"car":900,"price":30,**changes}


class EnergyAccountingRequirements(TestCase):
    def setUp(self):
        self.directory=self.enterContext(temporary_project_directory())
        self.ledger=Accounting(self.directory,ZoneInfo("Europe/Berlin"))
        self.ledger.configure({"pv_price_source":"manual","efficiency_source":"manual","capacity_wh":10000,
                               "charge_efficiency":.9,"discharge_efficiency":1.})

    def report_minute(self, **values):
        self.ledger.observe(sample(**values))
        self.ledger.observe(sample(NOW+timedelta(minutes=1),**values))
        return self.ledger.report({"period":"day"},NOW)["consumers"]

    def test_concurrent_consumers_share_sources_without_double_counting(self):
        result=self.report_minute()
        self.assertAlmostEqual(sum(result[key]["total"]["kwh"] for key in ("house","heat","car")),.06)
        for key in ("house","heat","car"):
            amount=result[key]["total"]
            self.assertAlmostEqual(amount["sources"]["pv"]["kwh"],amount["kwh"]/2)
            self.assertAlmostEqual(amount["cost_eur"],amount["kwh"]*.15)
            self.assertEqual(amount["cost_unknown_kwh"],0)

    def test_mixed_battery_charge_retains_weighted_price_and_losses(self):
        self.ledger.stock={"kwh":0.,"cost":0.,"unknown":0.}
        row=sample(solar=5000,grid=5000,battery_charge=10000,house_total=0,house=0,heat=0,car=0)
        row["consumers"]={"house":0}
        self.ledger.allocate(row,.001,self.ledger.effective())
        self.assertAlmostEqual(self.ledger.stock["kwh"],9.)
        self.assertAlmostEqual(self.ledger.stock["cost"],1.5)
        row=sample(solar=0,grid=0,battery_discharge=9000,house_total=9000)
        row["consumers"]={"car":9000}
        amount=self.ledger.allocate(row,.001,self.ledger.effective())["car"]
        self.assertAlmostEqual(amount["sources"]["battery"]["kwh"],9.)
        self.assertAlmostEqual(amount["cost_eur"],1.5)
        self.assertEqual(amount["cost_unknown_kwh"],0)
        self.assertAlmostEqual(self.ledger.stock["kwh"],0.)

    def test_charge_and_discharge_losses_are_applied_once(self):
        self.ledger.configure({"discharge_efficiency":.9})
        self.ledger.stock={"kwh":0.,"cost":0.,"unknown":0.}
        row=sample(solar=0,grid=10000,battery_charge=10000,house_total=0)
        row["consumers"]={}
        self.ledger.allocate(row,.001,self.ledger.effective())
        row=sample(solar=0,grid=0,battery_discharge=8100,house_total=8100)
        row["consumers"]={"heat":8100}
        result=self.ledger.allocate(row,.001,self.ledger.effective())["heat"]
        self.assertAlmostEqual(result["kwh"],8.1)
        self.assertAlmostEqual(result["cost_eur"],3.)

    def test_missing_price_and_initial_storage_do_not_become_free_energy(self):
        self.ledger.configure({"pv_price_source":"eos"})
        result=self.report_minute(solar=0,grid=1800,battery_discharge=1800,battery_soc=50,price=None)
        for key in result:
            amount=result[key]["total"]
            self.assertAlmostEqual(amount["cost_unknown_kwh"],amount["kwh"])

    def test_missing_or_inconsistent_sources_keep_consumption_but_not_fake_attribution(self):
        for solar in (None,9000):
            with self.subTest(solar=solar):
                row=sample(solar=solar)
                row["consumers"]={"house":3600}
                amount=self.ledger.allocate(row,.001,self.ledger.effective())["house"]
                self.assertEqual(amount["kwh"],3.6)
                self.assertEqual(amount["sources"]["unknown"]["kwh"],3.6)
                self.assertEqual(amount["cost_unknown_kwh"],3.6)

    def test_initial_stock_is_estimated_as_pv_including_both_losses(self):
        self.ledger.configure({"pv_price_ct":8.1,"discharge_efficiency":.9})
        report=self.report_minute(solar=0,grid=0,battery_discharge=3600,battery_soc=50)
        for entry in report.values():
            amount=entry["total"]
            self.assertAlmostEqual(amount["cost_eur"]/amount["kwh"],.1)
            self.assertEqual(amount["cost_unknown_kwh"],0)

    def test_legacy_unknown_stock_is_valued_once_preserving_known_cost(self):
        self.ledger.stock={"kwh":5.,"cost":.6,"unknown":2.}
        self.ledger.configure({"pv_price_ct":9})
        self.report_minute(battery_soc=50)
        self.assertAlmostEqual(self.ledger.stock["cost"],.8)
        restarted=Accounting(self.directory,self.ledger.zone)
        self.assertTrue(restarted.initial_pv_valued)
        restarted.configure({"pv_price_ct":30})
        restarted.observe(sample(NOW+timedelta(minutes=2),battery_soc=50))
        restarted.observe(sample(NOW+timedelta(minutes=3),battery_soc=50))
        self.assertAlmostEqual(restarted.stock["cost"],.8)
        # Later gaps preserve the established weighted book price, not a new PV price.
        restarted.observe(sample(NOW+timedelta(minutes=10),battery_soc=50))
        restarted.observe(sample(NOW+timedelta(minutes=11),battery_soc=50))
        self.assertEqual(restarted.stock["unknown"],0.)
        self.assertAlmostEqual(restarted.stock['cost'],.8)
        self.assertAlmostEqual(restarted.stock['estimated'],5.)

    def test_initial_estimate_waits_for_tariff_and_accepts_zero_and_negative(self):
        for price in (0,-9,9):
            with self.subTest(price=price):
                self.ledger.stock=None
                self.ledger.previous=None
                self.ledger.last_rate=None
                self.ledger.initial_pv_valued=False
                self.ledger.configure({"pv_price_source":"eos"})
                self.ledger.pv_tariff=None
                self.report_minute(battery_soc=50)
                self.assertEqual(self.ledger.stock["unknown"],5.)
                self.ledger.pv_tariff={"constant_ct":price}
                self.ledger.observe(sample(NOW+timedelta(minutes=2),battery_soc=50))
                self.assertEqual(self.ledger.stock["unknown"],0.)
                self.assertAlmostEqual(self.ledger.stock["cost"],5/.9*price/100)

    def test_negative_tariffs_and_future_settings_do_not_rewrite_history(self):
        self.report_minute(solar=0,grid=3600,price=-10)
        before=self.ledger.report({"period":"day"},NOW)["consumers"]["house"]["total"]
        self.assertAlmostEqual(before["cost_eur"],-.003)
        self.ledger.configure({"pv_price_ct":10})
        after=self.ledger.report({"period":"day"},NOW)["consumers"]["house"]["total"]
        self.assertEqual(before,after)

    def test_calendar_midnight_splits_energy_and_cost_into_correct_days(self):
        start=datetime(2026,11,8,22,59,30,tzinfo=timezone.utc)
        self.ledger.observe(sample(start))
        self.ledger.observe(sample(start+timedelta(seconds=60)))
        report=self.ledger.report({"period":"month","date":"2026-11-01"},start)
        bins=report["consumers"]["house"]["bins"]
        self.assertEqual([row["time"] for row in bins],["2026-11-08","2026-11-09"])
        self.assertAlmostEqual(bins[0]["kwh"],.015)
        self.assertAlmostEqual(bins[1]["kwh"],.015)

    def test_dst_day_has_23_or_25_distinct_hour_slots(self):
        for selected,count in (("2026-03-29",23),("2026-10-25",25)):
            report=self.ledger.report({"period":"day","date":selected},NOW)
            self.assertEqual(len(report["hours"]),count)
            self.assertEqual(len(set(report["hours"])),count)

    def test_gaps_and_restart_interpolate_consumption_and_flag_the_estimated_share(self):
        self.report_minute()
        self.ledger.observe(sample(NOW+timedelta(minutes=10)))
        before=self.ledger.report({"period":"year"},NOW)
        self.assertAlmostEqual(before["consumers"]["house"]["total"]["kwh"],.3)
        restarted=Accounting(self.directory,self.ledger.zone)
        restarted.observe(sample(NOW+timedelta(hours=1)))
        after=restarted.report({"period":"year"},NOW)
        self.assertAlmostEqual(after['consumers']['house']['total']['kwh'],1.8)
        self.assertAlmostEqual(after['consumers']['house']['total']['estimated_kwh'],1.77)

    def test_battery_book_value_survives_restart_with_unchanged_soc(self):
        self.ledger.configure({"initial_price_ct":20})
        self.report_minute(solar=0,grid=3600,battery_soc=50)
        restarted=Accounting(self.directory,self.ledger.zone)
        restarted.observe(sample(NOW+timedelta(minutes=2),battery_soc=50))
        restarted.observe(sample(NOW+timedelta(minutes=3),battery_soc=50))
        self.assertAlmostEqual(restarted.stock["cost"],1.)
        self.assertAlmostEqual(restarted.stock["unknown"],0.)

    def test_each_vehicle_gets_its_own_share_of_aggregate_vehicle_energy(self):
        for elapsed in (0,60):
            now=NOW+timedelta(seconds=elapsed)
            vehicles=[{"id":"one","live":{"car":300}},{"id":"two","live":{"car":600}}]
            self.ledger.observe(sample(now),vehicles)
        result=self.ledger.report({"period":"day"},NOW)["consumers"]
        self.assertAlmostEqual(result["car/one"]["total"]["kwh"]+result["car/two"]["total"]["kwh"],result["car"]["total"]["kwh"])

    def test_eos_data_is_cached_but_missing_efficiency_is_not_defaulted(self):
        eos=Mock()
        eos.battery_accounting.return_value={"charge_efficiency":.9}
        self.ledger.configure({"efficiency_source":"eos"})
        self.ledger.refresh_eos(eos,"battery1",NOW)
        self.assertIsNone(self.ledger.effective())
        eos.battery_accounting.return_value={"charge_efficiency":.96,"discharge_efficiency":.94,"capacity_wh":11059}
        self.ledger.refresh_eos(eos,"battery1",NOW+timedelta(hours=1))
        self.assertEqual(self.ledger.effective()["capacity_wh"],11059)
        eos.battery_accounting.side_effect=TimeoutError()
        self.ledger.refresh_eos(eos,"battery1",NOW+timedelta(hours=2))
        self.assertEqual(self.ledger.effective()["charge_efficiency"],.96)

    def test_invalid_settings_and_report_input_are_rejected(self):
        for values in ({"charge_efficiency":0},{"pv_price_ct":float('nan')},{"capacity_wh":True},{"extra":1}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                checked_settings(values)
        for values in ({"period":"week"},{"date":"bad"},{"date":"1900-01-01"},{"sql":"DROP TABLE energy"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                self.ledger.report(values,NOW)

    def test_eos_capacity_and_efficiency_are_read_without_writing_configuration(self):
        from unittest.mock import patch
        with patch('custom_components.eos_energiezentrale.energy.clients.request',return_value={"devices":{"batteries":{"battery1":{"capacity_wh":11059,"charging_efficiency":.95,"discharging_efficiency":.96}}}}) as request:
            values=EOS('http://eos:8503').battery_accounting('battery1')
        self.assertEqual(values,{"capacity_wh":11059,"charge_efficiency":.95,"discharge_efficiency":.96})
        request.assert_called_once_with('http://eos:8503/v1/config')


    def test_influx_reconstruction_clips_at_live_recording_without_double_counting(self):
        from types import SimpleNamespace
        from custom_components.eos_energiezentrale.energy.accounting_history import reconstruct, merge_reconstruction
        start=datetime(2026,11,9,0,0,tzinfo=ZoneInfo("Europe/Berlin"))
        live_start=start+timedelta(minutes=2)
        self.ledger.observe(sample(live_start))
        self.ledger.observe(sample(live_start+timedelta(minutes=1)))
        report=self.ledger.report({"period":"day","date":"2026-11-09"},live_start)
        config=SimpleNamespace(options={key+"_entity":"sensor."+key for key in ("pv","house","grid","heat","price")},zone=self.ledger.zone,
            battery=SimpleNamespace(ids={"charge_power":"sensor.charge","discharge_power":"sensor.discharge","soc":"sensor.soc"}),
            wallbox=SimpleNamespace(ids={"power":"sensor.car"}),influx=Mock(url='http://influx:8086'))
        values={"pv":1800,"house":3600,"grid":1800,"heat":900,"price":30,"charge":0,"discharge":0,"soc":0,"car":900}
        config.influx.history.side_effect=lambda entity,*args,**kwargs:[[start.isoformat(),values[entity.split('.')[1]]]]
        historical=reconstruct(config,report,live_start+timedelta(minutes=1))
        result=merge_reconstruction(report,historical)
        # Two reconstructed minutes plus one live minute, never the full five-minute bucket.
        self.assertAlmostEqual(result["consumers"]["house"]["total"]["kwh"],.09)
        self.assertAlmostEqual(result["consumers"]["house"]["total"]["seconds"],180)
        self.assertTrue(result["reconstructed"])

    def test_influx_range_is_validated_before_interpolating_query(self):
        from urllib.parse import parse_qs,urlsplit
        from unittest.mock import patch
        from custom_components.eos_energiezentrale.energy.clients import Influx
        client=Influx('http://influx:8086','homeassistant','','')
        with patch('custom_components.eos_energiezentrale.energy.clients.request',return_value={"results":[{}]}) as request:
            client.history('sensor.pv',[("W",1)],start='2026-11-01T00:00:00+00:00',end='2026-12-01T00:00:00+00:00')
            query=parse_qs(urlsplit(request.call_args.args[0]).query)['q'][0]
            self.assertIn("time >= '2026-11-01T00:00:00+00:00'",query)
            self.assertIn("time < '2026-12-01T00:00:00+00:00'",query)
            with self.assertRaises(ValueError):
                client.history('sensor.pv',[("W",1)],start="' OR true",end='2026-12-01T00:00:00+00:00')

    def test_out_of_order_samples_do_not_duplicate_energy(self):
        self.ledger.observe(sample(NOW))
        self.ledger.observe(sample(NOW+timedelta(seconds=60)))
        self.ledger.observe(sample(NOW+timedelta(seconds=30)))
        self.ledger.observe(sample(NOW+timedelta(seconds=90)))
        report=self.ledger.report({"period":"day"},NOW)
        self.assertAlmostEqual(report["consumers"]["house"]["total"]["kwh"],.045)


    def test_hourly_tariff_remains_valid_between_historical_power_buckets(self):
        from types import SimpleNamespace
        from custom_components.eos_energiezentrale.energy.accounting_history import reconstruct
        start=datetime(2026,11,9,0,0,tzinfo=ZoneInfo("Europe/Berlin"))
        report=self.ledger.report({"period":"day","date":"2026-11-09"},start)
        config=SimpleNamespace(options={**{key+"_entity":"sensor."+key for key in ("pv","house","grid","price")},"heat_entity":"","wallbox_type":"none"},
            zone=self.ledger.zone,battery=SimpleNamespace(ids={"charge_power":"sensor.charge","discharge_power":"sensor.discharge"}),
            wallbox=SimpleNamespace(ids={}),influx=Mock(url='http://influx:8086'))
        def read(entity,*args,**kwargs):
            if entity=='sensor.price':return [[start.isoformat(),30]]
            values={"pv":0,"house":3600,"grid":3600,"charge":0,"discharge":0}
            return [[(start+timedelta(minutes=offset)).isoformat(),values[entity.split('.')[1]]] for offset in (0,5,10)]
        config.influx.history.side_effect=read
        result=reconstruct(config,report,start+timedelta(minutes=15))["house"]["total"]
        self.assertAlmostEqual(result["kwh"],.9)
        self.assertAlmostEqual(result["cost_eur"],.27)
        self.assertAlmostEqual(result["cost_unknown_kwh"],0)


    def test_eos_fixed_feed_in_tariff_is_converted_from_eur_to_cent(self):
        from unittest.mock import patch
        tariff={"feedintariff":{"provider":"FeedInTariffFixed","feedintarifffixed":{"feed_in_tariff_amt_kwh":{"windows":[{"start_time":"00:00:00.000000","duration":"1 day","value":.082}]}}}}
        with patch('custom_components.eos_energiezentrale.energy.clients.request',return_value=tariff) as request:
            values=EOS('http://eos:8503').feedin_accounting(NOW)
        self.assertAlmostEqual(values["constant_ct"],8.2)
        request.assert_called_once_with('http://eos:8503/v1/config')

    def test_eos_tariff_prices_direct_pv_and_pv_charged_storage(self):
        self.ledger.configure({"pv_price_source":"eos"})
        eos=Mock();eos.feedin_accounting.return_value={"constant_ct":8.2}
        self.ledger.refresh_tariff(eos,NOW)
        self.ledger.stock={"kwh":0.,"cost":0.,"unknown":0.}
        row=sample(solar=10000,grid=0,battery_charge=5000,house_total=5000)
        row["consumers"]={"house":5000}
        amount=self.ledger.allocate(row,.001,self.ledger.effective())["house"]
        self.assertAlmostEqual(amount["cost_eur"],.41)
        self.assertAlmostEqual(self.ledger.stock["cost"],.41)
        row=sample(solar=0,grid=0,battery_discharge=4500,house_total=4500)
        row["consumers"]={"car":4500}
        amount=self.ledger.allocate(row,.001,self.ledger.effective())["car"]
        self.assertAlmostEqual(amount["cost_eur"],.41)

    def test_unavailable_pv_price_is_unknown_but_explicit_zero_is_known(self):
        self.ledger.configure({"pv_price_source":"eos"})
        row=sample(solar=3600,grid=0);row["consumers"]={"house":3600}
        amount=self.ledger.allocate(row,.001,self.ledger.effective())["house"]
        self.assertEqual(amount["cost_unknown_kwh"],3.6)
        self.ledger.pv_tariff={"constant_ct":0}
        amount=self.ledger.allocate(row,.001,self.ledger.effective())["house"]
        self.assertEqual(amount["cost_unknown_kwh"],0)
        self.assertEqual(amount["cost_eur"],0)

    def test_manual_pv_price_overrides_eos_and_tariff_errors_keep_last_valid_value(self):
        eos=Mock();eos.feedin_accounting.return_value={"constant_ct":8.2}
        self.ledger.configure({"pv_price_source":"eos"})
        self.ledger.refresh_tariff(eos,NOW)
        eos.feedin_accounting.side_effect=TimeoutError()
        self.ledger.refresh_tariff(eos,NOW+timedelta(minutes=5))
        self.assertEqual(self.ledger.pv_price(NOW.isoformat()),8.2)
        self.ledger.configure({"pv_price_source":"manual","pv_price_ct":10})
        self.assertEqual(self.ledger.pv_price(NOW.isoformat()),10)

    def test_variable_feed_in_prices_use_exact_intervals_and_do_not_extend_forever(self):
        from unittest.mock import patch
        start=NOW.replace(minute=0,second=0,microsecond=0)
        series={"data":{start.isoformat():.000082,(start+timedelta(minutes=15)).isoformat():-.00001}}
        with patch('custom_components.eos_energiezentrale.energy.clients.request',side_effect=[{"feedintariff":{"provider":"FeedInTariffImport"}},series]):
            tariff=EOS('http://eos:8503').feedin_accounting(start)
        self.ledger.configure({"pv_price_source":"eos"});self.ledger.pv_tariff=tariff
        self.assertAlmostEqual(self.ledger.pv_price(start.isoformat()),8.2)
        self.assertAlmostEqual(self.ledger.pv_price((start+timedelta(minutes=15)).isoformat()),-1)
        self.assertIsNone(self.ledger.pv_price((start+timedelta(hours=1)).isoformat()))

    def test_legacy_zero_default_migrates_to_eos_but_nonzero_override_is_preserved(self):
        import json
        from contextlib import closing
        for price,expected in ((0,'eos'),(9,'manual')):
            with self.subTest(price=price):
                with closing(self.ledger.connect()) as db,db:
                    db.execute("INSERT OR REPLACE INTO meta VALUES ('settings',?)",(json.dumps({"pv_price_ct":price}),))
                migrated=Accounting(self.directory,self.ledger.zone)
                self.assertEqual(migrated.settings['pv_price_source'],expected)



class TariffCostBasisRequirements(TestCase):
    def test_fixed_eos_tariff_and_battery_losses_produce_real_per_kwh_prices(self):
        from unittest.mock import patch
        configuration={"feedintariff":{"provider":"FeedInTariffFixed","feedintarifffixed":{
            "feed_in_tariff_amt_kwh":{"windows":[{"start_time":"00:00:00.000000",
                "duration":"1 day","end_time":None,"day_of_week":None,"date":None,
                "month":None,"locale":None,"value":.082}]}}}}
        with patch("custom_components.eos_energiezentrale.energy.clients.request",return_value=configuration):
            tariff=EOS("http://eos:8503").feedin_accounting(NOW)
        self.assertAlmostEqual(tariff["constant_ct"],8.2)
        with temporary_project_directory() as directory:
            ledger=Accounting(directory,ZoneInfo("Europe/Berlin"))
            ledger.configure({"pv_price_source":"eos","efficiency_source":"manual",
                              "charge_efficiency":.95,"discharge_efficiency":.95})
            ledger.pv_tariff=tariff
            for source,input_price in (("pv",.082),("grid",.30)):
                with self.subTest(source=source):
                    ledger.stock={"kwh":0.,"cost":0.,"unknown":0.}
                    row=sample(solar=1000 if source=="pv" else 0,grid=1000 if source=="grid" else 0,
                               battery_charge=1000,house_total=0,price=30)
                    row["consumers"]={}
                    ledger.allocate(row,.001,ledger.effective())
                    out=sample(solar=0,grid=0,battery_charge=0,battery_discharge=902.5,house_total=902.5)
                    out["consumers"]={"house":902.5}
                    result=ledger.allocate(out,.001,ledger.effective())["house"]
                    self.assertAlmostEqual(result["cost_eur"],input_price)
                    self.assertAlmostEqual(result["kwh"],.9025)
                    self.assertAlmostEqual(result["cost_eur"]/result["kwh"],input_price/(.95*.95))
                    self.assertAlmostEqual(result["cost_unknown_kwh"],0)

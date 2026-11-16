"""Overnight PV noise up to 2 W is valid; stale higher production stays invalid."""
from datetime import timedelta
from types import SimpleNamespace

import pytest

from custom_components.eos_energiezentrale.energy.clients import reading
from custom_components.eos_energiezentrale.energy.contracts import Measurement
from custom_components.eos_energiezentrale.energy.measurement_sources import checked_measurements, resolve_sources
from custom_components.eos_energiezentrale.energy.plugin_diagnostics import entity_reading
from custom_components.eos_energiezentrale.energy.status import view_state
from test_energy import NOW
import test_requirements as requirements
from test_requirements import state


@pytest.mark.parametrize('age,valid', [(46,True),(3600,True),(43199,True),(43200,False),(-1,False)])
@pytest.mark.parametrize('watts',[0,1,2])
@pytest.mark.parametrize('unit',['W','kW'])
def test_zero_pv_age_is_bounded_and_reports_the_same_limit(age, valid, watts, unit):
    stamp=NOW-timedelta(seconds=age)
    rows={'sensor.pv':state(watts/1000 if unit=='kW' else watts,unit=unit,when=stamp)}
    _,_,report=resolve_sources({'pv_entity':'sensor.pv','wallbox_type':'none'},rows,(),NOW)
    assert report['sources']['solar']['max_age_s']==43200
    assert report['sources']['solar']['available'] is valid
    assert (reading(rows,'sensor.pv',NOW,'solar',45)==watts) is valid
    sample=checked_measurements({'solar':Measurement(watts,stamp)},('solar',),NOW)['solar']
    assert (sample.value==watts) is valid


def test_positive_power_unknown_units_and_missing_values_keep_normal_validation():
    old=NOW-timedelta(minutes=5)
    for value in (2.01,3,1000,'unknown',None):
        assert reading({'sensor.pv':state(value,when=old)},'sensor.pv',NOW,'solar',45) is None
    assert reading({'sensor.pv':state(0,unit='bad',when=old)},'sensor.pv',NOW,'solar',45) is None
    assert reading({'sensor.grid':state(0,when=old)},'sensor.grid',NOW,'power',45) is None
    assert reading({'sensor.pv':state(.003,unit='kW',when=old)},'sensor.pv',NOW,'solar',45) is None


@pytest.mark.parametrize('watts',[0,1,2])
@pytest.mark.parametrize('unit',['W','kW'])
def test_generic_plugin_zero_has_no_false_stale_diagnostic(watts,unit):
    plugin=SimpleNamespace(ids={'solar':'sensor.pv'},_source_problems={})
    rows={'sensor.pv':state(watts/1000 if unit=='kW' else watts,unit=unit,when=NOW-timedelta(hours=11))}
    assert entity_reading(plugin,rows,NOW,'solar','power',45,('solar',))==watts
    assert plugin._source_problems=={}


def test_controller_accepts_overnight_zero_without_reusing_positive_production():
    fixture=requirements.ControllerRequirements();fixture.setUp()
    try:
        for value,expected in ((0,0),(1,1),(2,2),(2.01,None),(1000,None)):
            rows=fixture.states()
            rows['sensor.pv']=state(value,when=NOW-timedelta(hours=11))
            fixture.ha.states.return_value=rows
            fixture.app.tick(NOW,0)
            assert fixture.app.live['solar']==expected
            assert ('solar' not in fixture.app.source_configuration['unavailable']) is (expected is not None)
    finally:
        fixture.doCleanups()


def test_missing_pv_after_small_value_keeps_labelled_display_without_becoming_control_input():
    fixture=requirements.ControllerRequirements();fixture.setUp()
    try:
        fixture.ha.states.return_value={**fixture.states(),'sensor.pv':state(2)}
        fixture.app.tick(NOW,0)
        for seconds in (60,3600,43199):
            now=NOW+timedelta(seconds=seconds)
            rows=fixture.states(when=now)
            rows['sensor.pv']=state('unavailable',when=now)
            fixture.ha.states.return_value=rows
            fixture.app.tick(now,seconds)
            snapshot=fixture.app.snapshot(now)
            assert snapshot['live']['solar'] is None
            assert snapshot['display']['solar']=={'value':2,'age_s':seconds}
            assert snapshot['source_configuration']['sources']['solar']['available'] is False
            assert not any('solar' in notice.get('measurements',[]) for notice in view_state(snapshot,now)['notices'])
        expired=fixture.app.snapshot(NOW+timedelta(hours=12))
        assert any('solar' in notice.get('measurements',[]) for notice in view_state(expired,NOW+timedelta(hours=12))['notices'])
    finally:
        fixture.doCleanups()


def test_pv_failure_after_production_gets_five_minutes_warning_delay_without_sliding():
    from custom_components.eos_energiezentrale.energy.pv_availability import PVAvailability
    tracker=PVAvailability()
    tracker.observe({'sensor.pv':state(3000)},'sensor.pv',NOW)
    for seconds in (60,120,359,360):
        now=NOW+timedelta(seconds=seconds)
        rows={'sensor.pv':state('unavailable',when=now)}
        tracker.observe(rows,'sensor.pv',now)
        _,_,report=resolve_sources({'pv_entity':'sensor.pv'},rows,(),now)
        report=tracker.decorate(report,now)
        assert tracker.retained(now) is None
        notices=view_state({'source_configuration':report},now)['notices']
        assert any('solar' in notice.get('measurements',[]) for notice in notices) is (seconds>=360)


def test_fronius_modbus_missing_mppt_value_stays_invalid_but_recent_night_value_delays_warning():
    from custom_components.eos_energiezentrale.energy.pv_availability import PVAvailability
    from test_fronius_modbus import inverter
    tracker=PVAvailability()
    with inverter() as (driver,server):
        for index in (0,1):server.registers[server.mppt+10+index*20+11]=1
        first=driver.read({},NOW)
        opts,rows,_=resolve_sources({'pv_entity':''},{},((driver,first),),NOW,keys=('solar',))
        tracker.observe(rows,opts['pv_entity'],NOW)
        now=NOW+timedelta(minutes=1)
        server.registers[server.mppt+10+11]=65535
        missing=driver.read({},now)
        assert missing.measurements['solar'].value is None
        opts,rows,report=resolve_sources({'pv_entity':''},{},((driver,missing),),now,keys=('solar',))
        tracker.observe(rows,opts['pv_entity'],now)
        assert tracker.retained(now)['value']==2
        assert not view_state({'source_configuration':tracker.decorate(report,now)},now)['notices']
        assert not server.writes


def test_pv_warning_delay_does_not_hide_bad_units_or_reuse_zero_after_real_production():
    from custom_components.eos_energiezentrale.energy.pv_availability import PVAvailability
    tracker=PVAvailability()
    tracker.observe({'sensor.pv':state(2)},'sensor.pv',NOW)
    invalid={'unavailable':['solar'],'sources':{'solar':{'source':{'name':'PV'},
        'available':False,'reason':'unit_invalid','warning_after':(NOW+timedelta(days=1)).isoformat()}}}
    assert view_state({'source_configuration':tracker.decorate(invalid,NOW)},NOW)['notices']
    tracker.observe({'sensor.pv':state(3000,when=NOW+timedelta(seconds=5))},'sensor.pv',NOW+timedelta(seconds=5))
    assert tracker.retained(NOW+timedelta(seconds=5)) is None
    tracker.observe({'sensor.other':state('unavailable')},'sensor.other',NOW+timedelta(seconds=10))
    assert tracker.retained(NOW+timedelta(seconds=10)) is None


def test_expired_small_pv_value_does_not_get_another_five_minute_extension():
    from custom_components.eos_energiezentrale.energy.pv_availability import PVAvailability
    tracker=PVAvailability()
    rows={'sensor.pv':state(2)}
    tracker.observe(rows,'sensor.pv',NOW)
    now=NOW+timedelta(hours=12)
    tracker.observe(rows,'sensor.pv',now)
    _,_,report=resolve_sources({'pv_entity':'sensor.pv'},rows,(),now)
    assert any('solar' in notice.get('measurements',[]) for notice in
        view_state({'source_configuration':tracker.decorate(report,now)},now)['notices'])

"""Vehicle SoC warnings depend on missing values rather than update age."""
from datetime import timedelta

import pytest

from test_energy import NOW


@pytest.fixture
def control():
    from test_requirements import ControllerRequirements
    fixture = ControllerRequirements()
    fixture.setUp()
    try:
        yield fixture
    finally:
        fixture.doCleanups()


def poll(control, second, value, *, scale='factor'):
    from test_requirements import state
    now = NOW + timedelta(seconds=second)
    control.config.options['car_soc_scale'] = scale
    rows = control.states(when=now)
    if value is None:
        rows.pop('sensor.soc')
    else:
        # The sensor deliberately keeps the same timestamp for an entire day.
        rows['sensor.soc'] = state(value, when=NOW-timedelta(days=1))
    control.ha.states.return_value = rows
    control.app.tick(now, second)
    return control.app.snapshot(now)['source_configuration']


def warns(report):
    return 'car_soc' in report['missing'] or 'car_soc' in report['unavailable']


@pytest.mark.parametrize('value,scale',[(.4,'factor'),(40,'percent'),(0,'factor'),(0,'percent')])
def test_existing_unchanged_soc_does_not_warn_regardless_of_its_timestamp(control,value,scale):
    for second in (0,301,3600):
        report = poll(control,second,value,scale=scale)
        assert not warns(report)
        assert report['sources']['car_soc']['available'] is True
    assert control.app.soc == (value*100 if scale=='factor' else value)


@pytest.mark.parametrize('value',[None,'unknown','unavailable','bad',float('nan'),float('inf'),-1,1.01])
def test_only_more_than_five_minutes_without_a_valid_value_warns(control,value):
    assert not warns(control.app.snapshot(NOW)['source_configuration'])
    for second in (0,299,300):
        assert not warns(poll(control,second,value))
    report = poll(control,301,value)
    assert 'car_soc' in report['unavailable']
    assert report['sources']['car_soc']['available'] is False


def test_recovery_clears_warning_and_a_new_outage_gets_a_full_grace_period(control):
    poll(control,0,None)
    assert warns(poll(control,301,None))
    assert not warns(poll(control,302,.4))
    for second in (310,600,610):
        assert not warns(poll(control,second,None))
    assert warns(poll(control,611,None))


def test_short_outage_does_not_count_towards_a_later_missing_value(control):
    poll(control,0,None)
    poll(control,100,.4)
    assert not warns(poll(control,200,None))
    assert not warns(poll(control,500,None))
    assert warns(poll(control,501,None))


def test_missing_source_configuration_has_the_same_five_minute_grace(control):
    control.config.options['car_soc_entity'] = ''
    assert not warns(poll(control,0,None))
    report = poll(control,301,None)
    assert 'car_soc' in report['missing']
    assert 'car_soc' not in report['unavailable']


def test_no_soc_warning_when_no_vehicle_is_configured(control):
    control.config.options['wallbox_type'] = 'none'
    for second in (0,301,3600):
        assert not warns(poll(control,second,None))


def test_each_vehicle_has_its_own_missing_value_timer():
    from test_fleet import FleetRequirements
    fixture = FleetRequirements()
    try:
        app,ha,_opts,_directory = fixture.setup_fleet()
        ha.rows['sensor.soc_first']['last_updated'] = (NOW-timedelta(days=1)).isoformat()
        ha.rows['sensor.soc_first']['last_reported'] = (NOW-timedelta(days=1)).isoformat()
        ha.rows['sensor.soc_second']['state'] = 'unavailable'
        app.tick(NOW,0)
        assert all(not warns(item['source_configuration']) for item in app.snapshot(NOW)['vehicles'])
        later = NOW + timedelta(seconds=301)
        app.tick(later,301)
        first,second = app.snapshot(later)['vehicles']
        assert not warns(first['source_configuration'])
        assert warns(second['source_configuration'])
    finally:
        fixture.doCleanups()


def test_soc_report_beyond_the_age_limit_is_no_charging_basis_and_warns(control):
    from custom_components.eos_energiezentrale.energy.controller import CAR_SOC_MAX_AGE_S
    from custom_components.eos_energiezentrale.energy.settings import daily_settings
    from test_requirements import state
    control.config.daily = daily_settings({'fast':True, 'target_soc':80}, 20)
    control.app.set_armed(True)
    for second, age in ((0, CAR_SOC_MAX_AGE_S), (301, CAR_SOC_MAX_AGE_S + 301)):
        now = NOW + timedelta(seconds=second)
        rows = control.states(when=now)
        rows['sensor.soc'] = state(.4, when=now - timedelta(seconds=age))
        control.ha.states.return_value = rows
        control.app.tick(now, second)
        assert control.app.soc is None
    control.box.charge.assert_not_called()
    report = control.app.snapshot(now)['source_configuration']
    assert warns(report) and report['sources']['car_soc']['available'] is False
    now = NOW + timedelta(seconds=320)
    rows = control.states(when=now)
    rows['sensor.soc'] = state(.4, when=now - timedelta(seconds=CAR_SOC_MAX_AGE_S - 1))
    control.ha.states.return_value = rows
    control.app.tick(now, 320)
    assert control.app.soc == 40
    assert not warns(control.app.snapshot(now)['source_configuration'])
    control.box.charge.assert_called()


def test_diagnostics_use_the_same_vehicle_soc_age_limit_as_control(control):
    from custom_components.eos_energiezentrale.energy.measurement_sources import CAR_SOC_MAX_AGE_S
    from test_requirements import state
    for age, available in ((7200, True), (CAR_SOC_MAX_AGE_S + 1, False)):
        rows = control.states(when=NOW)
        rows['sensor.soc'] = state(.4, when=NOW - timedelta(seconds=age))
        control.ha.states.return_value = rows
        control.app.tick(NOW, 0)
        source = control.app.snapshot(NOW)['source_configuration']['sources']['car_soc']
        assert source['available'] is available
        assert source['reason'] == (None if available else 'stale')
        assert source['max_age_s'] == CAR_SOC_MAX_AGE_S

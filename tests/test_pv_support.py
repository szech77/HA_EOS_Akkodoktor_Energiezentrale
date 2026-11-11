"""Battery-assisted PV starts, hysteresis, safety and unchanged opt-out behavior."""
from datetime import timedelta
from unittest.mock import Mock

import pytest

from custom_components.eos_energiezentrale.energy.contracts import BatteryFeatures, BatteryReading, WallboxFeatures, WallboxReading
from custom_components.eos_energiezentrale.energy.settings import daily_settings
from test_energy import NOW


@pytest.fixture
def control():
    from test_requirements import ControllerRequirements
    fixture=ControllerRequirements()
    fixture.setUp()
    fixture.config.daily=daily_settings({'pv':True,'phase_auto':False,'battery_pv_start':True,
                                         'battery_pv_min_soc':50,'battery_pv_wait_s':60},20)
    fixture.battery.features=BatteryFeatures()
    fixture.box.features=WallboxFeatures(phase_switching=False)
    fixture.app.set_armed(True)
    try:
        yield fixture
    finally:
        fixture.doCleanups()


def sample(control, seconds, *, soc=53, grid=-500, watts=0, discharge=0, charge=0,
           enabled=False, phases=1, amps=6):
    now=NOW+timedelta(seconds=seconds)
    control.ha.states.return_value=control.states(grid=grid,when=now)
    control.battery.read.return_value=BatteryReading(soc,charge,discharge)
    control.box.read.return_value=WallboxReading(watts,'charging' if enabled else 'connected',
                                                enabled,phases,amps,.1,16,now)
    control.eos.plan.return_value=control.plan(generated=now)
    control.app.tick(now,seconds)


def start(control):
    for second in (0,20,40,60): sample(control,second)


def test_start_waits_for_continuous_surplus_and_prepares_battery_before_car(control):
    events=[]
    control.battery.apply.side_effect=lambda command,_states:events.append(('battery',command))
    control.box.charge.side_effect=lambda amps,_box:events.append(('car',amps))
    for second in (0,20,40,59): sample(control,second)
    control.box.charge.assert_not_called()
    events.clear()
    sample(control,60)
    assert events[0][0]=='battery' and events[0][1].charge_w==0
    assert events[0][1].discharge_w==control.config.options['battery_discharge_w']
    assert events[1]==('car',6)
    assert control.app.pv_support.active
    assert control.app.live['car_control']=='pv_battery'
    assert control.app.snapshot(NOW)['pv_battery_support']['required_w']==880


def test_two_percentage_point_hysteresis_and_stop_at_floor(control):
    for second in (0,20,40,60): sample(control,second,soc=51.9)
    control.box.charge.assert_not_called()
    for second in (80,100,120,140): sample(control,second,soc=52)
    assert control.app.pv_support.active
    sample(control,160,soc=51,grid=0,watts=1380,discharge=880,enabled=True)
    assert control.app.pv_support.active
    control.box.pause.reset_mock()
    sample(control,165,soc=50,grid=0,watts=1380,discharge=880,enabled=True)
    control.box.pause.assert_called_once()
    assert not control.app.pv_support.active
    assert control.app.commanded_car_w==0


@pytest.mark.parametrize('key,value',[('battery_pv_start',False),('battery_pv_support',False),
                                    ('pv',False),('fast',True)])
def test_feature_is_opt_in_and_respects_other_modes(control,key,value):
    control.config.daily[key]=value
    for second in (0,20,40,60): sample(control,second)
    assert not control.app.pv_support.active
    if key!='fast': control.box.charge.assert_not_called()


def test_interruption_resets_the_surplus_wait(control):
    for second in (0,20): sample(control,second)
    sample(control,40,grid=0)
    for second in (60,80,100): sample(control,second)
    control.box.charge.assert_not_called()
    sample(control,120)
    assert control.app.pv_support.active


@pytest.mark.parametrize('reason',['off','missing','soc','capacity','unsupported','unplugged','gap'])
def test_loss_of_conditions_stops_assistance_without_waiting_for_regulation_interval(control,reason):
    start(control)
    control.box.pause.reset_mock()
    control.box.charge.reset_mock()
    kwargs=dict(grid=0,watts=1380,discharge=880,enabled=True)
    if reason=='off': control.config.daily['battery_pv_start']=False
    if reason=='missing': kwargs['discharge']=None
    if reason=='soc': kwargs['soc']=None
    if reason=='capacity': control.config.options['battery_discharge_w']=500
    if reason=='unsupported': control.battery.features=BatteryFeatures(discharge_limit=False)
    if reason=='unplugged': kwargs.update(watts=None,enabled=False)
    sample(control,110 if reason=='gap' else 65,**kwargs)
    assert not control.app.pv_support.active
    control.box.pause.assert_called_once()
    control.box.charge.assert_not_called()


def test_sustained_grid_import_stops_a_battery_that_does_not_deliver(control):
    start(control)
    for second in (65,70):
        sample(control,second,grid=880,watts=1380,enabled=True)
        assert control.app.pv_support.active
    control.box.pause.reset_mock()
    sample(control,75,grid=880,watts=1380,enabled=True)
    assert not control.app.pv_support.active
    control.box.pause.assert_called_once()


def test_no_start_without_surplus_or_sufficient_battery_power(control):
    for second in (0,20,40,60): sample(control,second,grid=0)
    control.box.charge.assert_not_called()
    control.config.options['battery_discharge_w']=500
    for second in (80,100,120,140): sample(control,second)
    control.box.charge.assert_not_called()


def test_battery_charging_power_is_available_pv_and_three_phase_minimum_is_respected(control):
    for second in (0,20,40,60):
        sample(control,second,grid=0,charge=500,phases=3)
    assert control.app.pv_support.active
    assert control.app.pv_support.required_w==3640
    control.box.charge.assert_called_once()
    assert control.box.charge.call_args.args[0]==6


def test_battery_prepare_failure_never_starts_car(control):
    for second in (0,20,40): sample(control,second)
    control.box.pause.reset_mock()
    control.battery.apply.side_effect=OSError('battery unavailable')
    with pytest.raises(OSError): sample(control,60)
    control.box.charge.assert_not_called()
    control.box.pause.assert_called_once()
    assert not control.app.pv_support.active


def test_general_battery_floor_and_configured_wait_remain_binding(control):
    control.config.daily.update(battery_min_soc=60,battery_pv_wait_s=30)
    for second in (0,20,40): sample(control,second,soc=61)
    control.box.charge.assert_not_called()
    sample(control,50,soc=62)
    sample(control,79,soc=62)
    control.box.charge.assert_not_called()
    sample(control,80,soc=62)
    assert control.app.pv_support.active


def test_floor_also_stops_a_pv_session_started_before_assistance_was_latched(control):
    sample(control,0,soc=50,grid=0,watts=4140,discharge=2140,enabled=True,phases=3)
    assert not control.app.pv_support.active
    control.box.pause.assert_called_once()
    assert control.app.commanded_car_w==0


def test_full_pv_surplus_returns_to_normal_pv_charging(control):
    start(control)
    control.box.pause.reset_mock()
    sample(control,85,grid=-620,watts=1380,enabled=True)
    assert not control.app.pv_support.active
    control.box.pause.assert_not_called()


def test_shared_battery_budget_does_not_start_two_cars_on_the_same_small_surplus():
    from test_fleet import FleetRequirements
    fixture=FleetRequirements()
    try:
        app,ha,opts,directory=fixture.setup_fleet()
        for key,_,_ in app.controllers:
            app.change_vehicle_settings(key,{'pv':True,'phase_auto':False})
        app.change_vehicle_settings('second',{'battery_pv_start':True,'battery_pv_wait_s':20,
                                               'battery_pv_min_soc':40})
        ha.rows[opts['grid_entity']]['state']='-500'
        app.set_armed(True)
        for second in (0,10,20): app.tick(NOW+timedelta(seconds=second),second)
        assert all(child.config.daily['battery_pv_min_soc']==40 for _,child,_ in app.controllers)
        assert sum(child.pv_support.active for _,child,_ in app.controllers)==1
        assert app.targets['first']==1380 and app.targets.get('second',0)==0
        command=app.battery_driver.apply.call_args.args[0]
        assert command.charge_w==0 and command.discharge_w==opts['battery_discharge_w']
        from custom_components.eos_energiezentrale.energy.fleet import create_controller
        restored=create_controller(ha,opts,directory)
        assert restored.config.daily['battery_pv_start'] is True
        assert restored.config.daily['battery_pv_min_soc']==40
        assert not any(child.pv_support.active for _,child,_ in restored.controllers)
        app.change_vehicle_settings('second',{'battery_pv_start':False})
        app.tick(NOW+timedelta(seconds=25),25)
        assert not any(child.pv_support.active for _,child,_ in app.controllers)
        assert all(value==0 for value in app.targets.values())
    finally:
        fixture.doCleanups()


def test_assistance_defaults_and_invalid_values():
    assert daily_settings({},20)['battery_pv_start'] is False
    assert daily_settings({},20)['battery_pv_wait_s']==60
    for values in ({'battery_pv_start':1},{'battery_pv_min_soc':99},
                   {'battery_pv_min_soc':-1},{'battery_pv_wait_s':9},{'battery_pv_wait_s':True}):
        with pytest.raises(ValueError): daily_settings(values,20)

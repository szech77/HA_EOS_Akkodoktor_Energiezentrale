"""EOS EV predictions belong to resource IDs, never vehicle list positions."""
from datetime import timedelta
import json
from unittest.mock import Mock

import pytest

from custom_components.eos_energiezentrale.const import DEFAULTS
from custom_components.eos_energiezentrale.energy.fleet import create_controller
from custom_components.eos_energiezentrale.energy.history import forecast_rows,forecast_vehicle_resource
from test_energy import NOW,instruction,temporary_project_directory
from test_fleet import LocalHA,definitions


def solution(resource='ev1',now=NOW):
    return {'start_solution_datetime':now.isoformat(),'interval_seconds':900,
        'parameters':{'ev':{'device_id':resource,'capacity_wh':10000,'charging_efficiency':1},
            'ems':{'pv_forecast_wh':[250,500,750,1000]}},
        'ev_obj':{'device_id':resource},'result':{'ev_soc_per_hour':[20,30,None,50]}}


@pytest.fixture
def make_fleet():
    with temporary_project_directory() as directory:
        def make(rows=None):
            rows=definitions() if rows is None else rows
            opts={**DEFAULTS,'vehicles':json.dumps(rows),'heat_entity':''}
            ha=LocalHA(opts)
            app=create_controller(ha,opts,directory)
            app.config.eos=Mock()
            app.config.eos.plan.return_value={'generated_at':NOW.isoformat(),'instructions':[
                instruction(NOW),*[{**instruction(NOW),'resource_id':row['resource']} for row in rows]]}
            app.battery_driver.apply=Mock()
            app.battery_driver.release=Mock()
            return app,ha
        yield make


def test_single_managed_vehicle_has_soc_and_power_forecast_without_overwriting_live_soc(make_fleet):
    app,_=make_fleet(definitions()[:1])
    app.config.eos.solution.return_value=solution()
    app.tick(NOW,0)
    result=app.snapshot(NOW)
    vehicle=result['vehicles'][0]
    assert vehicle['id']=='first'  # Vehicle identity is deliberately not its EOS resource.
    assert vehicle['live']['car_soc']==40
    assert [row['car_soc'] for row in vehicle['forecast']]==[20,30,None,50]
    assert [row['car'] for row in vehicle['forecast']]==[4000,None,None,None]
    assert all('car_soc' not in row for row in result['forecast'])


@pytest.mark.parametrize('resource,identity',[('ev1','first'),('ev2','second')])
def test_eos_curve_is_delivered_only_to_its_resource_among_multiple_vehicles(make_fleet,resource,identity):
    app,_=make_fleet()
    app.config.eos.solution.return_value=solution(resource)
    app.tick(NOW,0)
    for vehicle in app.snapshot(NOW)['vehicles']:
        if vehicle['id']==identity:
            assert vehicle['forecast'][0]['car_soc']==20
            assert vehicle['forecast'][0]['car']==4000
        else:
            assert all('car_soc' not in row and 'car' not in row for row in vehicle['forecast'])
        assert vehicle['forecast'][0]['solar']==1000


def test_reordering_and_new_solution_owner_do_not_leave_predictions_on_previous_vehicle(make_fleet):
    app,_=make_fleet(list(reversed(definitions())))
    app.config.eos.solution.return_value=solution('ev1')
    app.tick(NOW,0)
    vehicles={row['id']:row for row in app.snapshot(NOW)['vehicles']}
    assert 'car_soc' not in vehicles['second']['forecast'][0]
    assert vehicles['first']['forecast'][0]['car_soc']==20
    later=NOW+timedelta(seconds=60)
    app.config.eos.solution.return_value=solution('ev2',later)
    app.tick(later,60)
    vehicles={row['id']:row for row in app.snapshot(later)['vehicles']}
    assert vehicles['second']['forecast'][0]['car_soc']==20
    assert 'car_soc' not in vehicles['first']['forecast'][0]


@pytest.mark.parametrize('params_owner,result_owner',[
    (None,None),('ev1','ev2'),('ev2','ev2'),('unconfigured','unconfigured'),
])
def test_missing_conflicting_or_foreign_ids_never_guess_a_curve_for_single_vehicle(make_fleet,params_owner,result_owner):
    app,_=make_fleet(definitions()[:1])
    data=solution()
    data['parameters']['ev'].pop('device_id')
    data.pop('ev_obj')
    if params_owner is not None:data['parameters']['ev']['device_id']=params_owner
    if result_owner is not None:data['ev_obj']={'device_id':result_owner}
    app.config.eos.solution.return_value=data
    app.tick(NOW,0)
    rows=app.snapshot(NOW)['vehicles'][0]['forecast']
    assert rows and rows[0]['solar']==1000
    assert all('car_soc' not in row and 'car' not in row for row in rows)


@pytest.mark.parametrize('source',['parameters','ev_obj','eauto_obj'])
def test_supported_eos_metadata_can_identify_vehicle_without_other_aliases(source):
    data=solution()
    data['parameters']['ev'].pop('device_id')
    data.pop('ev_obj')
    if source=='parameters':data['parameters']['ev']['device_id']='ev1'
    else:data[source]={'device_id':'ev1'}
    assert forecast_vehicle_resource(data)=='ev1'
    data['eauto_obj']={'device_id':None}
    assert forecast_vehicle_resource(data) is None


def test_forecast_failure_or_stale_solution_removes_all_vehicle_curves(make_fleet):
    app,_=make_fleet()
    app.config.eos.solution.return_value=solution()
    app.tick(NOW,0)
    assert app.snapshot(NOW)['vehicles'][0]['forecast'][0]['car_soc']==20
    app.config.eos.solution.side_effect=OSError('forecast unavailable')
    later=NOW+timedelta(seconds=60)
    app.tick(later,60)
    assert all(not row['forecast'] for row in app.snapshot(later)['vehicles'])
    assert all(child.forecast_vehicle_resource is None for _,child,_ in app.controllers)
    app.config.eos.solution.side_effect=None
    app.config.eos.solution.return_value=solution(now=NOW-timedelta(hours=2))
    later=NOW+timedelta(seconds=120)
    app.tick(later,120)
    assert all(not row['forecast'] for row in app.snapshot(later)['vehicles'])


def test_invalid_soc_samples_are_gaps_and_invalid_capacity_does_not_invent_power():
    data=solution()
    data['result']['ev_soc_per_hour']=[20,101,-1,float('nan')]
    rows=forecast_rows(data,NOW)
    assert [row['car_soc'] for row in rows]==[20,None,None,None]
    assert all(row['car'] is None for row in rows)
    data=solution()
    data['parameters']['ev']['capacity_wh']=-10000
    assert forecast_rows(data,NOW)[0]['car_soc']==20
    assert forecast_rows(data,NOW)[0]['car'] is None

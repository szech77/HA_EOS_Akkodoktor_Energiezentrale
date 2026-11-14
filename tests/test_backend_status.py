"""Backend notice decisions, privacy and state transitions without a browser."""
from datetime import timedelta
import json
import logging
from urllib.error import HTTPError, URLError

import pytest

from custom_components.eos_energiezentrale.energy.status import IssueLog, failure_details, view_state
from custom_components.eos_energiezentrale.energy.settings import daily_settings
from custom_components.eos_energiezentrale.energy.settings import settings_payload
from custom_components.eos_energiezentrale.energy._eos_battery import confirmed
from custom_components.eos_energiezentrale.energy.report_values import amount_values, current_day_values
from custom_components.eos_energiezentrale.energy.presentation import measured_pv_energy, mode_timeline
from test_energy import NOW


def test_backend_selects_pending_recovery_and_read_only_states():
    state = {'armed':True, 'vehicles':[{}, {'vehicle_planning':'plan_pending'}]}
    assert view_state(state, NOW)['control_status'] == 'planning_vehicle'
    state['vehicles'][1]['vehicle_planning'] = 'limits_pending'
    assert view_state(state, NOW)['control_status'] == 'syncing_vehicle'
    state['eos_cache'] = {'private-resource':{'remaining_s':200}}
    assert view_state(state, NOW)['control_status'] == 'cached_eos'
    state['control_waiting'] = True
    assert view_state(state, NOW)['control_status'] == 'waiting'
    state.update(control_waiting=False, armed=False)
    assert view_state(state, NOW)['control_status'] == 'read_only'


def test_visible_source_notices_have_matching_safe_transition_logs(caplog):
    source = {'missing':['grid'], 'unavailable':['solar'], 'sources':{
        'solar':{'reason':'stale', 'max_age_s':45, 'source':{'name':'private-sensor'}}}}
    state = {'source_configuration':source, 'vehicles':[{}, {'name':'private-car',
        'source_configuration':{'unavailable':['car_soc','grid']}, 'errors':{'goal':'TimeoutError'}}]}
    notices = view_state(state, NOW)['notices']
    assert len(notices) == 4
    assert notices[-1]['vehicle_name'] == 'private-car'
    assert notices[-1]['measurements'] == ['car_soc']
    log = IssueLog()
    caplog.set_level(logging.INFO, logger='custom_components.eos_energiezentrale')
    log.update('state', notices)
    assert len(caplog.records) == len(notices)
    log.update('state', notices)
    assert len(caplog.records) == len(notices)
    source['sources']['solar']['reason'] = 'unit_invalid'
    log.update('state', view_state(state,NOW)['notices'])
    assert log.events[-1]['state'] == 'changed'
    log.update('state', [])
    assert len([row for row in log.events if row['state'] == 'resolved']) == 4
    diagnostic = json.dumps(log.diagnostics())
    for private in ('private-sensor','private-car','private-resource'):
        assert private not in caplog.text + diagnostic
    assert 'stale' in caplog.text and 'unit_invalid' in caplog.text


def test_safe_failure_details_distinguish_http_status_connection_and_readback():
    error = HTTPError('http://private-host',503,'private-response',{},None)
    assert failure_details(error) == {'exception':'HTTPError', 'http_status':503}
    assert failure_details(URLError(TimeoutError('test-secret'))) == {'exception':'URLError', 'cause':'TimeoutError'}
    with pytest.raises(ValueError) as rejected:
        daily_settings({'battery_min_soc':90,'battery_max_soc':80},20)
    assert failure_details(rejected.value)['reason'] == 'battery_bounds'
    assert failure_details(rejected.value)['fields'] == ['battery_max_soc','battery_min_soc']
    with pytest.raises(ValueError) as mismatch:
        confirmed({'battery_profile':'generic', 'profile_adjustment':{'max_charge_power_w':5000},
            'effective_max_charge_power_w':4000}, {'profile_adjustment':{'max_charge_power_w':5000}})
    assert failure_details(mismatch.value)['reason'] == 'effective_limits_differ'
    assert failure_details(mismatch.value)['fields'] == ['max_charge_power_w']


def test_cached_plan_expiry_changes_notice_without_sliding_its_grace_period(caplog):
    state = {'armed':True, 'errors':{'eos':'TimeoutError'}, 'eos_cache':{'private':{'remaining_s':300}}}
    log = IssueLog()
    log.update('state', view_state(state,NOW)['notices'])
    state['eos_cache']['private']['remaining_s'] = 5
    log.update('state', view_state(state,NOW)['notices'])
    assert len(log.events) == 1
    state['eos_cache'] = {}
    log.update('state', view_state(state,NOW)['notices'])
    assert log.events[-1]['state'] == 'changed'
    assert log.events[-1]['code'] == 'eos'
    assert len(log.events) == 2


def test_issue_history_is_bounded_and_critical_stop_is_error(caplog):
    log = IssueLog()
    for _ in range(60):
        log.update('state',view_state({'errors':{'wallbox_stop':'StopUnconfirmed'}},NOW)['notices'])
        log.update('state',[])
    assert len(log.diagnostics()['history']) == 50
    assert any(record.levelno == logging.ERROR for record in caplog.records)


def test_report_totals_merge_history_once_and_preserve_unknown_price_policy():
    from custom_components.eos_energiezentrale.energy.accounting import empty
    first, old = empty(), empty()
    first.update(kwh=1,cost_eur=.2)
    old.update(kwh=5,cost_eur=1,cost_unknown_kwh=3,estimated_kwh=5)
    raw = {'date':'2026-11-14','consumers':{'house':{'total':first,'bins':[]}}}
    historical = {'date':raw['date'],'historical_consumers':{'house':old}}
    result = current_day_values(raw,historical)['overview']['total']
    assert result['kwh'] == 6 and result['average_price_ct'] == pytest.approx(40)
    assert result['estimated'] and result['cost_partial']
    assert current_day_values(raw,historical)['overview']['total'] == result
    assert raw['consumers']['house']['total']['kwh'] == 1
    assert amount_values({'kwh':1,'cost_eur':0,'cost_unknown_kwh':1})['average_price_ct'] is None
    assert not amount_values({'kwh':1,'cost_eur':0,'cost_unknown_kwh':1})['cost_available']


def test_pv_energy_uses_measurements_without_crossing_large_gaps_or_using_future_rows():
    def row(seconds, power):
        return {'time':(NOW+timedelta(seconds=seconds)).isoformat(),'solar':power}
    rows = [row(-120,1000),row(-60,1000),row(0,1000),row(60,100000)]
    assert measured_pv_energy(rows,[],NOW,'UTC') == pytest.approx(1/30)
    assert measured_pv_energy([row(-600,1000),row(0,1000)],[],NOW,'UTC') is None
    assert measured_pv_energy([row(-60,0),row(0,0)],[],NOW,'UTC') == 0


def test_mode_history_and_plan_gap_policy_is_computed_in_backend():
    data = {'plan_end':(NOW+timedelta(hours=1)).isoformat(), 'plan':{'car':[
        {'time':NOW.isoformat(),'mode':'FORCED_CHARGE'}]}}
    rows = [{'time':(NOW-timedelta(minutes=10)).isoformat(),'car_actual_mode':'CHARGING'}]
    bands = mode_timeline(data,rows,NOW)['car']
    charging = next(row for row in bands if row['mode'] == 'CHARGING')
    assert charging['end']-charging['start'] == 120000
    assert bands[-1]['kind'] == 'plan' and bands[-1]['mode'] is None
    assert bands[-2]['mode'] == 'FORCED_CHARGE'


def test_departure_form_input_uses_installation_timezone_and_rejects_nonexistent_dst_time():
    from zoneinfo import ZoneInfo
    zone = ZoneInfo('Europe/Berlin')
    raw = {'departure_local':'2026-11-14T07:30','schedule':'once'}
    result = settings_payload(raw, zone)
    assert result['departure'] == '2026-11-14T07:30:00+01:00'
    assert 'departure_local' not in result and 'departure_local' in raw
    assert settings_payload({'departure':'2026-11-14T06:30:00Z'},zone)['departure'].endswith('Z')
    for local in ('2026-03-29T02:30','2026-11-14T07:30+01:00','not-a-date'):
        with pytest.raises(ValueError):
            settings_payload({'departure_local':local},zone)


def test_http_debug_logs_operation_and_timing_without_urls_headers_or_bodies(monkeypatch, caplog):
    from io import BytesIO
    from unittest.mock import Mock
    from custom_components.eos_energiezentrale.energy import clients
    opened = Mock(return_value=BytesIO(b'{"private-reading":123}'))
    monkeypatch.setattr(clients.OPENER,'open',opened)
    caplog.set_level(logging.DEBUG,logger='custom_components.eos_energiezentrale.energy.clients')
    result = clients.request('http://private-host/v1/config?token=test-secret',
        headers={'Authorization':'Bearer test-secret'}, payload={'private-setting':'test-secret'})
    assert result == {'private-reading':123}
    opened.side_effect = TimeoutError('test-secret')
    with pytest.raises(TimeoutError):
        clients.request('http://private-host/v1/config')
    assert 'eos_config' in caplog.text and 'elapsed_ms' in caplog.text and 'TimeoutError' in caplog.text
    for private in ('private-host','test-secret','private-reading','private-setting','Authorization'):
        assert private not in caplog.text

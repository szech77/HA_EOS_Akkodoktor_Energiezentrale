"""EOS calculations are normal states, with non-sliding and fresh-status grace."""
from datetime import timedelta
from unittest.mock import Mock, patch
from urllib.error import HTTPError

from custom_components.eos_energiezentrale.energy.clients import EOS
from custom_components.eos_energiezentrale.energy.eos_status import EOSRunStatus
from custom_components.eos_energiezentrale.energy.controller import Controller
from custom_components.eos_energiezentrale.energy.settings import Configuration
from custom_components.eos_energiezentrale.energy.status import view_state
from custom_components.eos_energiezentrale.const import DEFAULTS
from test_energy import NOW, temporary_project_directory, instruction


def health(stage=None, started=NOW, finished=None):
    ems={'start_datetime':started.isoformat(),'last_run_datetime':finished.isoformat() if finished else None}
    if stage is not None:ems['stage']=stage
    return {'status':'alive','energy-management':ems}


def test_explicit_stage_and_timestamp_only_health_detect_running_and_completion():
    for start in (health('OPTIMIZATION'),health()):
        status=EOSRunStatus();status.update(start,NOW)
        assert status.snapshot(NOW)=={'state':'calculating','grace':True,'elapsed_s':0}
        status.update(health('IDLE',finished=NOW+timedelta(seconds=30)),NOW+timedelta(seconds=30))
        assert status.snapshot(NOW+timedelta(seconds=30))['state']=='idle'


def test_repeated_busy_status_cannot_extend_grace_and_stale_health_cannot_hide_errors():
    status=EOSRunStatus()
    for seconds in (0,30,120,240,299,301):
        now=NOW+timedelta(seconds=seconds)
        status.update(health('OPTIMIZATION'),now)
        assert status.snapshot(now)['grace'] is (seconds<300)
    assert status.snapshot(NOW+timedelta(seconds=346))['state']=='unknown'
    assert not status.snapshot(NOW+timedelta(seconds=346))['grace']
    status.update(None,NOW+timedelta(seconds=350))
    assert status.snapshot(NOW+timedelta(seconds=350))['state']=='unknown'


def test_timestamp_only_same_rounded_slot_uses_bounded_update_status_instead_of_claiming_a_run():
    status=EOSRunStatus()
    reply=health(started=NOW-timedelta(minutes=10),finished=NOW-timedelta(minutes=5))
    for seconds in (0,299,301):
        now=NOW+timedelta(seconds=seconds);status.update(reply,now)
        result=status.snapshot(now,NOW)
        assert result['state']=='updating'
        assert result['grace'] is (seconds<300)


def test_calculating_suppresses_transient_eos_errors_but_keeps_device_errors_and_plan_expiry():
    with temporary_project_directory() as directory:
        config=Configuration(dict(DEFAULTS),Mock(),directory)
        app=Controller(Mock(),config)
        plan={'generated_at':NOW.isoformat(),'valid_until':(NOW+timedelta(seconds=60)).isoformat(),
              'instructions':[instruction(NOW)]}
        app.apply_eos_plan(plan,NOW)
        app.apply_eos_health(health('OPTIMIZATION'),NOW)
        app.apply_eos_plan(None,NOW,TimeoutError())
        app.record_failure('battery_limits',HTTPError('http://eos',503,'busy',{},None))
        app.record_failure('wallbox',TimeoutError())
        result=app.snapshot(NOW)
        assert 'eos' not in result['errors'] and 'battery_limits' not in result['errors']
        assert result['errors']['wallbox']=='TimeoutError'
        assert view_state(result,NOW)['eos_status']=='calculating'
        assert app.errors['eos']=='TimeoutError'  # Raw diagnostics remain available.
        assert app.order_for('battery1',NOW+timedelta(seconds=60)) is None
        app.apply_eos_health(health('OPTIMIZATION'),NOW+timedelta(seconds=301))
        assert app.snapshot(NOW+timedelta(seconds=301))['errors']['eos']=='TimeoutError'


def test_health_client_uses_documented_read_only_endpoint():
    with patch('custom_components.eos_energiezentrale.energy.clients.request',return_value=health()) as request:
        EOS('http://eos').health()
    request.assert_called_once_with('http://eos/v1/health')

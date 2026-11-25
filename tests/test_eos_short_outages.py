"""EOS answers late while it optimizes: a longer, configurable timeout and a grace period
before a short communication failure becomes a notice."""
from datetime import timedelta
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError

import pytest

from custom_components.eos_energiezentrale.const import DEFAULTS
from custom_components.eos_energiezentrale.energy import clients
from custom_components.eos_energiezentrale.energy.clients import EOS, EOS_TIMEOUT_S, Influx, backend_timeout
from custom_components.eos_energiezentrale.energy.controller import Controller
from custom_components.eos_energiezentrale.energy.settings import Configuration
from custom_components.eos_energiezentrale.energy.status import EOS_ISSUE_GRACE_S, TransientGrace, failure_details
from custom_components.eos_energiezentrale.validation import validate_options
from test_energy import NOW, temporary_project_directory


def timeouts_used(url, count=1):
    """Socket timeouts and total deadlines of ``count`` requests to ``url``."""
    seen = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self, size):
            return b'{}'

    def opened(request, timeout):
        seen.append(timeout)
        return Response()

    deadlines = []
    run = clients.RequestDeadline.run

    def bounded(self, exchange, seconds):
        deadlines.append(seconds)
        return run(self, exchange, seconds)

    with patch.object(clients.OPENER, 'open', side_effect=opened), \
            patch.object(clients.RequestDeadline, 'run', bounded):
        for _ in range(count):
            clients.request(url)
    return seen, deadlines


def test_eos_waits_ten_seconds_by_default_and_other_backends_keep_five():
    assert DEFAULTS['eos_timeout_s'] == EOS_TIMEOUT_S == 10
    EOS('http://eos-default:8503', DEFAULTS['eos_timeout_s'])
    seen, deadlines = timeouts_used('http://eos-default:8503/v1/health')
    assert seen == [10] and deadlines == [40]
    Influx('http://influx-default:8086', 'homeassistant', '', '')
    seen, deadlines = timeouts_used('http://influx-default:8086/query')
    assert seen == [5] and deadlines == [30]


def test_the_configured_eos_timeout_applies_to_every_request_of_that_eos():
    eos = EOS('http://eos-configured:8503', 25)
    with patch.object(clients, 'request', return_value={'status': 'alive'}) as request:
        eos.health()
    request.assert_called_once_with('http://eos-configured:8503/v1/health')
    seen, deadlines = timeouts_used('http://eos-configured:8503/v1/config')
    assert seen == [25] and deadlines == [70]
    # Another port is another peer.
    assert backend_timeout('http://eos-configured:8504') == 5


@pytest.mark.parametrize('value', [2.9, 61, True, 'ten', None])
def test_an_eos_timeout_outside_three_to_sixty_seconds_is_rejected(value):
    with pytest.raises(ValueError):
        validate_options({**DEFAULTS, 'eos_timeout_s': value})


def test_validating_options_does_not_change_the_running_timeout():
    EOS('http://eos-validated:8503', 10)
    validate_options({**DEFAULTS, 'eos_url': 'http://eos-validated:8503', 'eos_timeout_s': 30})
    assert backend_timeout('http://eos-validated:8503') == 10


def error(value):
    try:
        raise value
    except Exception as raised:
        return failure_details(raised)


@pytest.mark.parametrize('failure', [TimeoutError('busy'), URLError(ConnectionRefusedError()),
                                     HTTPError('http://eos', 503, 'busy', {}, None), ConnectionResetError()])
def test_a_short_communication_failure_is_held_back_until_it_lasts_two_minutes(failure):
    grace = TransientGrace()
    details = error(failure)
    for elapsed in (0, 60, EOS_ISSUE_GRACE_S - 1):
        assert not grace.visible('eos', details, NOW + timedelta(seconds=elapsed))
    assert grace.visible('eos', details, NOW + timedelta(seconds=EOS_ISSUE_GRACE_S))


@pytest.mark.parametrize('failure', [HTTPError('http://eos', 404, 'missing', {}, None), ValueError('invalid')])
def test_other_failures_are_visible_at_once(failure):
    assert TransientGrace().visible('eos', error(failure), NOW)


def test_a_visible_failure_stays_visible_and_a_new_outage_gets_a_full_grace_period():
    grace = TransientGrace()
    assert grace.visible('eos', error(ValueError('invalid')), NOW)
    # The cause becomes a timeout: the notice does not disappear and reappear.
    assert grace.visible('eos', error(TimeoutError()), NOW + timedelta(seconds=10))
    grace.retain([])
    assert not grace.visible('eos', error(TimeoutError()), NOW + timedelta(seconds=20))
    assert not grace.visible('eos', error(TimeoutError()), NOW + timedelta(seconds=20 + EOS_ISSUE_GRACE_S - 1))


@pytest.fixture
def app():
    with temporary_project_directory() as directory:
        config = Configuration(dict(DEFAULTS), Mock(), directory)
        config.eos = Mock()
        yield Controller(Mock(), config)


def test_control_sees_a_short_eos_outage_at_once_but_the_notice_waits(app):
    app.record_failure('vehicle_limits', TimeoutError('busy'))
    assert app.errors['vehicle_limits'] == 'TimeoutError'
    assert 'vehicle_limits' not in app.visible_errors(NOW)
    assert 'vehicle_limits' not in app.visible_errors(NOW + timedelta(seconds=EOS_ISSUE_GRACE_S - 1))
    assert app.visible_errors(NOW + timedelta(seconds=EOS_ISSUE_GRACE_S))['vehicle_limits'] == 'TimeoutError'
    # Recovery ends the outage; the next one waits again.
    app.errors.pop('vehicle_limits')
    app.visible_errors(NOW + timedelta(seconds=200))
    app.record_failure('vehicle_limits', TimeoutError('busy'))
    assert 'vehicle_limits' not in app.visible_errors(NOW + timedelta(seconds=201))


def test_a_permanent_eos_error_and_device_errors_are_shown_at_once(app):
    app.record_failure('battery_limits', HTTPError('http://eos', 404, 'missing', {}, None))
    app.record_failure('wallbox', TimeoutError('charger'))
    errors = app.visible_errors(NOW)
    assert errors['battery_limits'] == 'HTTPError' and errors['wallbox'] == 'TimeoutError'


def test_an_eos_error_without_a_matching_recorded_exception_is_shown_at_once(app):
    app.record_failure('eos', TimeoutError('busy'))
    app.errors['eos'] = 'PlanIncomplete'
    assert app.visible_errors(NOW)['eos'] == 'PlanIncomplete'

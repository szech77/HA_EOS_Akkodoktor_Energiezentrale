"""Local device HTTP exchanges have a total deadline, not only socket inactivity."""
from contextlib import contextmanager
import socket
from threading import Event, Thread
from time import monotonic, sleep
from unittest.mock import patch

import pytest

from custom_components.eos_energiezentrale.energy.clients import RequestDeadline
from custom_components.eos_energiezentrale.energy.drivers import WALLBOX_DRIVERS
from custom_components.eos_energiezentrale.energy.plugins.goe_http_v2 import GoEAPIError
from custom_components.eos_energiezentrale.energy.plugins.nrgkick_local import NRGkickAPIError
from test_energy import NOW


@contextmanager
def trickling_device():
    """Send a header line every 50 ms: never idle long enough for a socket timeout."""
    stop = Event()
    listener = socket.create_server(('127.0.0.1', 0))
    listener.settimeout(.05)
    workers, paths = [], []

    def drip(connection):
        with connection:
            try:
                paths.append(connection.recv(4096).split(b' ')[1].decode())
                connection.sendall(b'HTTP/1.1 200 OK\r\n')
                while not stop.wait(.05):
                    connection.sendall(b'X-Padding: a\r\n')
            except (OSError, IndexError):
                pass

    def accept():
        while not stop.is_set():
            try:
                connection, _ = listener.accept()
            except (TimeoutError, OSError):
                continue
            worker = Thread(target=drip, args=(connection,), daemon=True)
            worker.start()
            workers.append(worker)

    acceptor = Thread(target=accept, daemon=True)
    acceptor.start()
    try:
        yield f'http://127.0.0.1:{listener.getsockname()[1]}', stop, paths
    finally:
        stop.set()
        acceptor.join(timeout=2)
        for worker in workers:
            worker.join(timeout=2)
        listener.close()


def settle(deadline):
    end = monotonic() + 5
    while deadline.open_exchanges and monotonic() < end:
        sleep(.02)
    assert deadline.open_exchanges == 0


def charging_state():
    from test_requirements import wallbox
    return wallbox(watts=2000, status='charging', enabled=True)


# go-e: 0.2 s inactivity timeout plus 0.2 s grace; NRGkick: 0.4 s total.
@pytest.mark.parametrize('plugin,error,setting,poll,stop_path', [
    ('nrgkick_local', NRGkickAPIError, ('nrgkick_local.REQUEST_DEADLINE_S', .4),
     lambda driver: driver.read({}, NOW), '/control?charge_pause=1'),
    ('goe_http_v2', GoEAPIError, ('goe_http_v2.REQUEST_GRACE_S', .2),
     lambda driver: driver._status(timeout=.2), '/api/set?frc=1'),
])
def test_trickled_response_is_bounded_and_a_stop_is_still_sent(plugin, error, setting, poll, stop_path):
    name, value = setting
    with trickling_device() as (url, stop, paths), patch(
            f'custom_components.eos_energiezentrale.energy.plugins.{name}', value):
        driver = WALLBOX_DRIVERS[plugin](None, {'url': url})
        started = monotonic()
        if plugin == 'nrgkick_local':
            # Telemetry failures are reported as an unavailable reading.
            assert poll(driver).status == 'unavailable'
        else:
            with pytest.raises(error):
                poll(driver)
        assert monotonic() - started < 2
        # Further polls fail fast while the abandoned exchange is open ...
        started = monotonic()
        with pytest.raises(error):
            driver._request('/control' if plugin == 'nrgkick_local' else '/api/status')
        assert monotonic() - started < .2
        # ... but a stop still reaches the device; unconfirmed, it stays an error.
        count = len(paths)
        with pytest.raises(error):
            driver.pause(charging_state())
        assert stop_path in paths[count:]
        stop.set()
        settle(driver.deadline)


def test_backend_requests_have_a_total_deadline():
    from custom_components.eos_energiezentrale.energy import clients
    with trickling_device() as (url, stop, _), patch.object(clients, 'BACKEND_DEADLINE_S', .3):
        started = monotonic()
        with pytest.raises(TimeoutError):
            clients.request(url + '/v1/health')
        assert monotonic() - started < 1
        with pytest.raises(TimeoutError, match='still open'):
            clients.request(url + '/v1/health')
        stop.set()
        settle(clients.backend_deadline(url))


def test_deadline_returns_values_and_reraises_errors_in_the_caller():
    deadline = RequestDeadline('test-request')
    assert deadline.run(lambda: b'{}', 1) == b'{}'
    with pytest.raises(ValueError, match='bad'):
        deadline.run(lambda: (_ for _ in ()).throw(ValueError('bad')), 1)


def test_abandoned_exchanges_are_bounded_with_one_reserved_for_priority_requests():
    deadline = RequestDeadline('test-request')
    release = Event()
    with pytest.raises(TimeoutError):
        deadline.run(release.wait, .05)
    started = monotonic()
    with pytest.raises(TimeoutError, match='still open'):
        deadline.run(lambda: 1, 1)
    assert monotonic() - started < .1
    with deadline.priority():
        assert deadline.run(lambda: 'stop', 1) == 'stop'
        with pytest.raises(TimeoutError):
            deadline.run(release.wait, .05)
        with pytest.raises(TimeoutError, match='still open'):
            deadline.run(lambda: 'stop', 1)
    assert deadline.open_exchanges == 2
    release.set()
    settle(deadline)
    assert deadline.run(lambda: 2, 1) == 2

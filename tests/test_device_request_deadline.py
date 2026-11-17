"""Local device HTTP exchanges have a total deadline, not only socket inactivity."""
from contextlib import contextmanager
import socket
from threading import Event, Thread
from time import monotonic
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
    workers = []

    def drip(connection):
        with connection:
            try:
                connection.recv(4096)
                connection.sendall(b'HTTP/1.1 200 OK\r\n')
                while not stop.wait(.05):
                    connection.sendall(b'X-Padding: a\r\n')
            except OSError:
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
        yield f'http://127.0.0.1:{listener.getsockname()[1]}', stop
    finally:
        stop.set()
        acceptor.join(timeout=2)
        for worker in workers:
            worker.join(timeout=2)
        listener.close()


def wait_for(driver):
    pending = driver.deadline._pending
    if pending is not None:
        pending.join(timeout=5)
        assert not pending.is_alive()


# go-e: 0.2 s inactivity timeout plus 0.2 s grace; NRGkick: 0.4 s total.
@pytest.mark.parametrize('plugin,error,setting,poll', [
    ('nrgkick_local', NRGkickAPIError, ('nrgkick_local.REQUEST_DEADLINE_S', .4), lambda driver: driver.read({}, NOW)),
    ('goe_http_v2', GoEAPIError, ('goe_http_v2.REQUEST_GRACE_S', .2),
     lambda driver: driver._status(timeout=.2)),
])
def test_trickled_response_cannot_hold_a_poll_or_the_stop_path_open(plugin, error, setting, poll):
    name, value = setting
    with trickling_device() as (url, stop), patch(
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
        # The still open exchange blocks no further caller, e.g. a stop request.
        started = monotonic()
        with pytest.raises(error):
            driver.pause(charging_state())
        assert monotonic() - started < .2
        stop.set()
        wait_for(driver)


def charging_state():
    from test_requirements import wallbox
    return wallbox(watts=2000, status='charging', enabled=True)


def test_deadline_returns_values_and_reraises_errors_in_the_caller():
    deadline = RequestDeadline('test-request')
    assert deadline.run(lambda: b'{}', 1) == b'{}'
    with pytest.raises(ValueError, match='bad'):
        deadline.run(lambda: (_ for _ in ()).throw(ValueError('bad')), 1)


def test_deadline_fails_fast_while_an_abandoned_exchange_is_open_and_recovers():
    deadline = RequestDeadline('test-request')
    release = Event()
    with pytest.raises(TimeoutError):
        deadline.run(release.wait, .05)
    started = monotonic()
    with pytest.raises(TimeoutError, match='still open'):
        deadline.run(lambda: 1, 1)
    assert monotonic() - started < .1
    release.set()
    deadline._pending.join(timeout=2)
    assert deadline.run(lambda: 2, 1) == 2

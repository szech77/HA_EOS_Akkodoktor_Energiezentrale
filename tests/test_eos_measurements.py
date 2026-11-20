"""Measured SoC and power reach the EOS measurement store, so EOS never plans from an assumed 0 %."""
from datetime import timedelta
import json
from types import SimpleNamespace
from urllib.parse import parse_qs, urlsplit

import pytest

from custom_components.eos_energiezentrale.energy.clients import EOS
from custom_components.eos_energiezentrale.energy.contracts import BatteryReading
from custom_components.eos_energiezentrale.energy.eos_measurements import (
    KEYS_INTERVAL_S, SYNC_INTERVAL_S, MeasurementSync, Sample, device_samples)
from custom_components.eos_energiezentrale.energy.status import view_state
from test_energy import NOW
from test_http_boundaries import FixtureHandler, transport
import test_requirements as requirements


class FakeEOS:
    """EOS measurement store: accepted keys and the values written to them."""

    def __init__(self, keys=('battery1-soc-factor', 'battery1-charge-power-w', 'battery1-discharge-power-w',
                             'ev1-soc-factor', 'ev1-charge-power-w')):
        self.keys = None if keys is None else frozenset(keys)
        self.writes = []
        self.key_reads = 0
        self.fail = None

    def measurement_keys(self):
        self.key_reads += 1
        return self.keys

    def put_measurement(self, key, value, when):
        if self.fail:
            raise self.fail
        self.writes.append((key, value, when))


def test_samples_carry_the_soc_as_factor_and_skip_invalid_values():
    assert device_samples('battery1', soc=62.345, charge_w=1500, discharge_w=0) == [
        Sample('battery1-soc-factor', .6234), Sample('battery1-charge-power-w', 1500), Sample('battery1-discharge-power-w', 0)]
    # Missing, invalid or out-of-range values are never replaced by zero.
    for soc in (None, -1, 101, float('nan'), True):
        assert device_samples('ev1', soc=soc) == []
    assert device_samples('ev1', soc=50, charge_w=-5) == [Sample('ev1-soc-factor', .5)]
    assert device_samples('', soc=50) == []


def test_only_keys_eos_knows_are_sent_and_unknown_keys_are_reported_once(caplog):
    eos, sync = FakeEOS(keys=('battery1-soc-factor',)), MeasurementSync()
    samples = [Sample('battery1-soc-factor', .6), Sample('ev9-soc-factor', .4)]
    with caplog.at_level('INFO'):
        assert sync.sync(eos, samples, NOW, 0) is True
        sync.sync(eos, samples, NOW, 70)
    assert [key for key, *_ in eos.writes] == ['battery1-soc-factor', 'battery1-soc-factor']
    assert caplog.text.count('eos_measurement_keys_missing') == 1 and 'ev9-soc-factor' in caplog.text
    assert sync.diagnostics() == {'supported': True, 'keys': ['battery1-soc-factor'], 'missing': ['ev9-soc-factor'], 'sent_at': NOW.isoformat()}


def test_values_are_refreshed_every_interval_and_a_soc_change_is_sent_at_once():
    eos, sync = FakeEOS(), MeasurementSync()
    sync.sync(eos, [Sample('battery1-soc-factor', .6), Sample('battery1-charge-power-w', 1500)], NOW, 0)
    eos.writes.clear()
    # Power changes every cycle; it is refreshed per interval, not per poll.
    assert sync.sync(eos, [Sample('battery1-soc-factor', .605), Sample('battery1-charge-power-w', 1700)], NOW, 5) is None
    assert sync.sync(eos, [Sample('battery1-soc-factor', .61), Sample('battery1-charge-power-w', 1700)], NOW, 10) is True
    assert eos.writes == [('battery1-soc-factor', .61, NOW)]
    sync.sync(eos, [Sample('battery1-soc-factor', .61), Sample('battery1-charge-power-w', 1700)], NOW, SYNC_INTERVAL_S)
    assert [key for key, *_ in eos.writes] == ['battery1-soc-factor', 'battery1-charge-power-w']


def test_an_eos_without_measurement_api_is_left_alone_and_rechecked_later(caplog):
    eos, sync = FakeEOS(keys=None), MeasurementSync()
    with caplog.at_level('INFO'):
        assert sync.sync(eos, [Sample('battery1-soc-factor', .6)], NOW, 0) is False
        assert sync.sync(eos, [Sample('battery1-soc-factor', .6)], NOW, 60) is False
    assert eos.writes == [] and eos.key_reads == 1
    assert caplog.text.count('eos_measurements_unsupported') == 1
    eos.keys = frozenset({'battery1-soc-factor'})
    assert sync.sync(eos, [Sample('battery1-soc-factor', .6)], NOW, KEYS_INTERVAL_S) is True


def test_a_failing_eos_is_retried_after_one_interval_not_every_cycle():
    eos, sync = FakeEOS(), MeasurementSync()
    eos.fail = TimeoutError('slow')
    with pytest.raises(TimeoutError):
        sync.sync(eos, [Sample('battery1-soc-factor', .6)], NOW, 0)
    assert sync.sync(eos, [Sample('battery1-soc-factor', .6)], NOW, 5) is None
    eos.fail = None
    assert sync.sync(eos, [Sample('battery1-soc-factor', .6)], NOW, SYNC_INTERVAL_S) is True


class MeasurementServer(FixtureHandler):
    def respond(self):
        self.server.requests.append((self.command, self.path))
        if self.path == '/v1/measurement/keys' and self.server.keys is not None:
            payload = self.server.keys
        elif self.path.startswith('/v1/measurement/value?') and self.command == 'PUT':
            payload = {'data': {}, 'dtype': 'float64', 'tz': 'UTC'}
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode())

    do_GET = do_PUT = respond


def test_the_client_uses_the_eos_measurement_api():
    requests = []
    with transport(eos=(MeasurementServer, {'keys': ['battery1-soc-factor'], 'requests': requests})):
        client = EOS('http://eos')
        assert client.measurement_keys() == frozenset({'battery1-soc-factor'})
        client.put_measurement('battery1-soc-factor', .62, NOW)
    method, path = requests[-1]
    query = parse_qs(urlsplit(path).query)
    assert method == 'PUT' and urlsplit(path).path == '/v1/measurement/value'
    assert query == {'key': ['battery1-soc-factor'], 'value': ['0.62'], 'datetime': [NOW.isoformat()]}
    with transport(eos=(MeasurementServer, {'keys': None, 'requests': []})):
        assert EOS('http://eos').measurement_keys() is None
    with pytest.raises(ValueError):
        EOS('http://eos').put_measurement('battery1-soc-factor', float('nan'), NOW)


@pytest.fixture
def control():
    fixture = requirements.ControllerRequirements()
    fixture.setUp()
    fixture.config.eos = fixture.eos = FakeEOS()
    fixture.eos.plan = lambda: fixture.plan()
    fixture.eos.solution = lambda: {}
    try:
        yield fixture
    finally:
        fixture.doCleanups()


def tick(control, second):
    now = NOW + timedelta(seconds=second)
    control.ha.states.return_value = control.states(soc=.4, when=now)
    control.app.tick(now, second)
    return control.app.snapshot(now)


def test_every_control_cycle_keeps_battery_and_vehicle_soc_current_in_eos(control):
    control.battery.read.return_value = BatteryReading(62, 1500, 0)
    control.box.read.return_value = requirements.wallbox(watts=3700, status='charging', enabled=True)
    tick(control, 0)
    written = {key: value for key, value, _ in control.eos.writes}
    assert written == {'battery1-soc-factor': .62, 'battery1-charge-power-w': 1500, 'battery1-discharge-power-w': 0,
                       'ev1-soc-factor': .4, 'ev1-charge-power-w': 3700}
    snapshot = tick(control, 5)
    assert snapshot['eos_measurements']['supported'] is True
    assert 'eos_measurements' not in control.app.errors


def test_a_missing_battery_soc_is_not_sent_and_a_failure_is_a_notice(control):
    control.battery.read.return_value = BatteryReading(None, None, None)
    tick(control, 0)
    assert not any(key.startswith('battery1') for key, *_ in control.eos.writes)
    control.eos.fail = TimeoutError('slow')
    snapshot = tick(control, SYNC_INTERVAL_S)
    assert control.app.errors['eos_measurements'] == 'TimeoutError'
    notices = view_state(snapshot, NOW)['notices']
    assert [(row['code'], row['severity'], row['message']) for row in notices if row['code'] == 'eos_measurements'] == [
        ('eos_measurements', 'warning', 'notice.eos_measurements')]
    control.eos.fail = None
    tick(control, 2 * SYNC_INTERVAL_S)
    assert 'eos_measurements' not in control.app.errors


def test_a_fleet_vehicle_controller_does_not_send_the_shared_battery(control):
    control.config.battery = SimpleNamespace(meter_only=True, read=control.battery.read, ids={})
    control.app.soc = 40
    samples = control.app.eos_measurement_samples(BatteryReading(62, 0, 0), requirements.wallbox(watts=0))
    assert [sample.key for sample in samples] == ['ev1-soc-factor', 'ev1-charge-power-w']

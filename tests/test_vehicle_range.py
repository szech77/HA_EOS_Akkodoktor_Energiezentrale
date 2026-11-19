"""The optional vehicle range sensor yields a range per SoC percent for display."""
import json
from datetime import timedelta

import pytest

from custom_components.eos_energiezentrale.energy.fleet import vehicle_options
from custom_components.eos_energiezentrale.energy.source_diagnostics import source_diagnostics
from custom_components.eos_energiezentrale.energy.vehicle_projection import car_range_view
from test_energy import NOW
import test_requirements as requirements
from test_fleet import definitions


@pytest.fixture
def control():
    fixture = requirements.ControllerRequirements()
    fixture.setUp()
    fixture.config.options['car_range_entity'] = 'sensor.range'
    try:
        yield fixture
    finally:
        fixture.doCleanups()


def poll(control, second, soc, distance, unit='km'):
    now = NOW + timedelta(seconds=second)
    rows = control.states(soc=soc, when=now)
    if distance is not None:
        rows['sensor.range'] = requirements.state(distance, unit, now)
    control.ha.states.return_value = rows
    control.app.tick(now, second)
    return control.app.snapshot(now)


def test_range_per_soc_is_learned_from_a_measured_soc_and_range(control):
    snapshot = poll(control, 0, .4, 200)
    live = snapshot['live']
    assert live['car_range'] == 200 and live['car_range_source'] == 'vehicle'
    assert live['car_range_per_soc'] == pytest.approx(5)
    rows = {row['key']: row for row in source_diagnostics(snapshot, NOW)['sources']}
    assert rows['car_range']['value'] == 200 and rows['car_range']['unit'] == 'km'
    # Without a current range report, the range follows the SoC with the learned factor.
    live = poll(control, 30, .5, None)['live']
    assert live['car_range'] == pytest.approx(250) and live['car_range_source'] == 'estimate'


def test_miles_are_converted_and_a_low_soc_keeps_the_last_factor(control):
    assert poll(control, 0, .5, 100, 'mi')['live']['car_range_per_soc'] == pytest.approx(3.218688)
    # 5 % with 30 km would give 6 km/% from heavily rounded values.
    live = poll(control, 30, .05, 30)['live']
    assert live['car_range'] == 30 and live['car_range_per_soc'] == pytest.approx(3.218688)


def test_invalid_range_reports_are_ignored(control):
    for value, unit in ((-5, 'km'), (100, 'm'), ('unknown', 'km')):
        live = poll(control, 0, .4, value, unit)['live']
        assert live['car_range'] is None and live['car_range_per_soc'] is None


def test_without_range_sensor_no_range_is_shown():
    assert car_range_view(None, 40, None) == {'car_range': None, 'car_range_source': None, 'car_range_per_soc': None}
    assert car_range_view(None, None, 4)['car_range'] is None


def test_each_vehicle_maps_its_own_range_sensor():
    rows = definitions()
    rows[0]['range_entity'] = 'sensor.range_first'
    values = dict(vehicle_options({**requirements.OPTIONS, 'vehicles': json.dumps(rows)}))
    assert values['first']['car_range_entity'] == 'sensor.range_first'
    assert values['second']['car_range_entity'] == ''

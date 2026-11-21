"""A vehicle with a single-phase on-board charger is planned and regulated on one phase."""
from dataclasses import replace
from datetime import timedelta
import json
from types import SimpleNamespace

import pytest

from custom_components.eos_energiezentrale.energy.contracts import WallboxReading
from custom_components.eos_energiezentrale.energy.fleet import vehicle_options
from custom_components.eos_energiezentrale.energy.settings import daily_settings
from custom_components.eos_energiezentrale.energy.vehicle_limits import charging_profile, vehicle_box
from custom_components.eos_energiezentrale.validation import validate_options
from sample_options import DEFAULTS
from test_energy import NOW
from test_fleet import definitions
import test_requirements as requirements

SWITCHING = SimpleNamespace(phase_switching=True, optional_connection=True)
FIXED = SimpleNamespace(phase_switching=False, optional_connection=True)


def box(phases=3, **values):
    return WallboxReading(0, 'connected', False, phases, 6, 1, 16, NOW, max_phases=3, nominal_voltage=230, **values)


def test_the_eos_profile_offers_only_single_phase_power():
    daily = daily_settings({'phase_auto': True}, 20)
    options = {'max_current_a': 16, 'max_phases': 1}
    for driver in (SimpleNamespace(features=SWITCHING), SimpleNamespace(features=FIXED)):
        maximum, minimum, rates, active = charging_profile(box(), driver, options, daily, True)
        assert (maximum, minimum, active) == (16 * 230, 6 * 230, True)
        assert rates[-1] == 1 and rates[1] == pytest.approx(6 / 16)
    # Three-phase vehicles keep the full profile.
    assert charging_profile(box(), SimpleNamespace(features=SWITCHING), {'max_current_a': 16}, daily, True)[0] == 16 * 3 * 230


def test_a_wallbox_without_phase_switching_counts_the_one_phase_the_vehicle_uses():
    options = {'max_phases': 1}
    assert vehicle_box(box(), SimpleNamespace(features=FIXED), options).phases == 1
    switching = vehicle_box(box(), SimpleNamespace(features=SWITCHING), options)
    # A switchable wallbox reports its real phases; the regulation moves it to one.
    assert (switching.phases, switching.max_phases) == (3, 1)
    assert vehicle_box(box(), SimpleNamespace(features=FIXED), {}) == box()


@pytest.fixture
def case():
    case = requirements.ControllerRequirements()
    case.setUp()
    case.box.features = SimpleNamespace(phase_switching=True, optional_connection=False)
    case.config.daily = daily_settings({'pv': True, 'phase_auto': True}, 20)
    phases(case, 1)
    try:
        yield case
    finally:
        case.doCleanups()


def phases(case, value):
    # The controller regulates with the options resolved at start; a reconfiguration restarts it.
    case.config.options['max_phases'] = case.app.input_options['max_phases'] = value


def regulate(case, reading, seconds):
    now = NOW + timedelta(seconds=seconds)
    fresh = replace(reading, sample=now)
    case.app.regulate_car(fresh, {'grid': -9000, 'solar': 12000, 'battery_discharge': 0},
                          0, True, now, seconds, case.states(when=now))
    return fresh


def test_a_large_surplus_never_switches_a_single_phase_vehicle_to_three_phases(case):
    charging = requirements.wallbox(watts=3680, status='charging', enabled=True, phases=1, amps=16)
    for seconds in (0, 100, 200):
        regulate(case, charging, seconds)
    assert all(call.args[0] == 1 for call in case.box.phase.call_args_list)
    # The same surplus switches a three-phase vehicle (control case).
    phases(case, 3)
    for seconds in (300, 400):
        fresh = regulate(case, charging, seconds)
    case.box.phase.assert_called_with(3, fresh)


def test_a_wallbox_on_three_phases_is_moved_to_one(case):
    three = requirements.wallbox(watts=4140, status='charging', enabled=True, phases=3, amps=6)
    for seconds in (0, 100):
        fresh = regulate(case, three, seconds)
    case.box.phase.assert_called_with(1, fresh)


def test_the_option_accepts_one_or_three_phases_for_single_vehicles_and_vehicle_lists():
    validate_options({**DEFAULTS, 'max_phases': 1})
    with pytest.raises(ValueError):
        validate_options({**DEFAULTS, 'max_phases': 2})
    rows = definitions()
    rows[0]['max_phases'] = 1
    vehicles = dict(vehicle_options({**DEFAULTS, 'vehicles': json.dumps(rows)}))
    assert vehicles['first']['max_phases'] == 1
    assert vehicles['second'].get('max_phases', 3) == 3

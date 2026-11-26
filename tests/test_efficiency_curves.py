"""Power-dependent battery and inverter efficiencies from EOS profiles in the cost accounting."""
from copy import deepcopy
import logging
from unittest.mock import patch
from urllib.error import HTTPError
from zoneinfo import ZoneInfo

import pytest

from custom_components.eos_energiezentrale.energy.accounting import Accounting
from custom_components.eos_energiezentrale.energy.clients import EOS
from custom_components.eos_energiezentrale.energy.efficiency_curves import (
    CurveError, battery_curves, checked_curve, efficiency, inverter_curves, lookup, summary)
from test_accounting import sample
from test_energy import NOW, temporary_project_directory

# Curves of the EOS profiles generic-lfp and generic-hybrid (Akkudoktor-EOS/EOS).
BATTERY_PROFILE = {
    'battery_model': 'Generic LFP home battery',
    'charge_efficiency': {'c_rate': [0.05, 0.1, 0.25, 0.5, 0.75, 1.0], 'efficiency': [0.975, 0.975, 0.97, 0.96, 0.95, 0.94],
                          'interpolation': 'linear', 'out_of_range_behavior': 'clamp_to_nearest'},
    'discharge_efficiency': {'c_rate': [0.05, 0.1, 0.25, 0.5], 'efficiency': [0.975, 0.975, 0.97, 0.96]},
}
INVERTER_PROFILE = {
    'inverter_model': 'Generic hybrid', 'nominal_power_w': 10000,
    'dc_to_ac_efficiency': {'load_fraction': [0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0],
                            'efficiency': [0.88, 0.93, 0.955, 0.965, 0.97, 0.968, 0.965]},
    'ac_to_dc_efficiency': {'load_fraction': [0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0],
                            'efficiency': [0.86, 0.92, 0.95, 0.96, 0.965, 0.963, 0.96]},
}
BATTERY = {'battery_profile': 'generic-lfp', 'effective_nominal_capacity_wh': 10000,
           'effective_charging_efficiency': .94, 'effective_discharging_efficiency': .96}
INVERTER = {'device_id': 'inverter1', 'battery_id': 'battery1', 'inverter_profile': 'generic-hybrid',
            'effective_nominal_power_w': 5000}


def curves(inverter=True):
    return {'battery': battery_curves(BATTERY_PROFILE),
            'inverter': inverter_curves(INVERTER_PROFILE, 5000) if inverter else None}


def effective(inverter=True):
    return {'capacity_wh': 10000., 'charge_efficiency': .94, 'discharge_efficiency': .96, 'curves': curves(inverter)}


def test_curves_are_read_like_eos_linear_inside_and_at_the_edge_outside():
    curve = checked_curve(BATTERY_PROFILE['charge_efficiency'], 'c_rate')
    assert lookup(curve, 0.01) == 0.975 and lookup(curve, 2.0) == 0.94
    assert lookup(curve, 0.375) == pytest.approx(0.965)
    nearest = checked_curve({**BATTERY_PROFILE['charge_efficiency'], 'interpolation': 'nearest'}, 'c_rate')
    # Exactly between two breakpoints the lower one wins, as in EOS.
    assert lookup(nearest, 0.375) == 0.97 and lookup(nearest, 0.4) == 0.96
    assert checked_curve({**BATTERY_PROFILE['charge_efficiency'], 'interpolation': 'none'}, 'c_rate')['mode'] == 'nearest'


@pytest.mark.parametrize('document', [
    None, {}, {'c_rate': [0.1, 0.1], 'efficiency': [0.9, 0.9]}, {'c_rate': [0.2, 0.1], 'efficiency': [0.9, 0.9]},
    {'c_rate': [0.1], 'efficiency': [1.2]}, {'c_rate': [0.1], 'efficiency': [0]}, {'c_rate': [0.1, 0.2], 'efficiency': [0.9]},
    {'c_rate': [True], 'efficiency': [0.9]}, {'c_rate': [float('nan')], 'efficiency': [0.9]},
    {'c_rate': [-0.1], 'efficiency': [0.9]}, {'c_rate': [0.1], 'efficiency': [0.9], 'interpolation': 'spline'},
    {'c_rate': [0.01 * index for index in range(65)], 'efficiency': [0.9] * 65},
])
def test_unusable_curves_are_rejected(document):
    with pytest.raises(CurveError):
        checked_curve(document, 'c_rate')


def test_the_efficiency_combines_inverter_and_battery_at_the_measured_ac_power():
    values = effective()
    # 500 W charging: inverter at 10 % load (0.92), the battery sees 460 W = 0.046 C (0.975).
    assert efficiency(values, 'charge', 500) == pytest.approx(0.92 * 0.975)
    # 2500 W: inverter at 50 % load (0.965), battery at 0.24125 C.
    battery = 0.975 + (0.24125 - 0.1) / 0.15 * (0.97 - 0.975)
    assert efficiency(values, 'charge', 2500) == pytest.approx(0.965 * battery)
    # Discharging draws more DC power than it delivers.
    assert efficiency(values, 'discharge', 2500) == pytest.approx(0.97 * lookup(values['curves']['battery']['discharge'], 2500 / 0.97 / 10000))
    assert efficiency(values, 'charge', 250) < efficiency(values, 'charge', 2500)
    # Without curves, power or inverter the existing constants or the battery curve alone apply.
    assert efficiency({**values, 'curves': None}, 'charge', 2500) == .94
    assert efficiency(values, 'charge', 0) == .94 and efficiency(values, 'discharge', None) == .96
    assert efficiency(effective(inverter=False), 'charge', 500) == 0.975


def test_the_displayed_range_covers_the_power_range():
    result = summary(effective())
    assert result['inverter'] is True
    low, high = result['charge']
    assert low == pytest.approx(round(0.86 * 0.975, 4), abs=0.01) and low < high <= 0.97
    assert summary({'capacity_wh': 10000., 'charge_efficiency': .94, 'discharge_efficiency': .96}) is None
    assert summary(effective(inverter=False))['inverter'] is False


class FakeEOS:
    """EOS configuration and profile endpoints."""

    def __init__(self, battery=BATTERY, inverters=None, profiles=None, profile_status=None):
        self.config = {'devices': {'batteries': {'battery1': dict(battery)},
                                   'inverters': {'inverter1': dict(INVERTER)} if inverters is None else inverters}}
        self.profiles = {'/v1/profile/battery/generic-lfp': BATTERY_PROFILE,
                         '/v1/profile/inverter/generic-hybrid': INVERTER_PROFILE, **(profiles or {})}
        self.profile_status = profile_status
        self.paths = []

    def request(self, url, **kwargs):
        path = url.removeprefix('http://eos:8503')
        self.paths.append(path)
        if path == '/v1/config':
            return deepcopy(self.config)
        if self.profile_status:
            raise HTTPError(url, self.profile_status, 'error', {}, None)
        if path not in self.profiles:
            raise HTTPError(url, 404, 'missing', {}, None)
        return deepcopy(self.profiles[path])


def accounting_values(fake):
    with patch('custom_components.eos_energiezentrale.energy.clients.request', side_effect=fake.request):
        return EOS('http://eos:8503').battery_accounting('battery1')


def test_the_battery_and_its_assigned_inverter_profile_are_read_without_writing():
    fake = FakeEOS()
    values = accounting_values(fake)
    assert values['curves_reason'] is None
    assert values['curves']['inverter']['nominal_power_w'] == 5000
    assert values['curves']['battery']['charge']['y'][-1] == 0.94
    assert fake.paths == ['/v1/config', '/v1/profile/battery/generic-lfp', '/v1/profile/inverter/generic-hybrid']


@pytest.mark.parametrize('fake,reason,battery_curve', [
    (FakeEOS(inverters={}), 'inverter_unassigned', True),
    (FakeEOS(profiles={'/v1/profile/inverter/generic-hybrid': {'nominal_power_w': 10000}}), 'inverter_profile_invalid', True),
    (FakeEOS(profile_status=404), 'profile_api_missing', False),
    (FakeEOS(profile_status=503), 'battery_profile_unavailable', False),
    (FakeEOS(profiles={'/v1/profile/battery/generic-lfp': {'charge_efficiency': None}}), 'battery_profile_invalid', False),
    (FakeEOS(battery={**BATTERY, 'battery_profile': '../../config'}), 'battery_profile_invalid', False),
])
def test_missing_or_invalid_profiles_fall_back_without_failing(fake, reason, battery_curve):
    values = accounting_values(fake)
    assert values['curves_reason'] == reason
    assert (values['curves'] is not None) is battery_curve
    assert values['charge_efficiency'] == .94
    # An unsafe profile name is never requested.
    assert not any('..' in path for path in fake.paths)


def test_an_inverter_without_effective_power_uses_the_profile_nominal_power():
    inverter = {key: value for key, value in INVERTER.items() if key != 'effective_nominal_power_w'}
    values = accounting_values(FakeEOS(inverters={'inverter1': inverter}))
    assert values['curves']['inverter']['nominal_power_w'] == 10000


@pytest.fixture
def ledger():
    with temporary_project_directory() as directory:
        ledger = Accounting(directory, ZoneInfo('Europe/Berlin'))
        ledger.configure({'pv_price_source': 'manual', 'efficiency_source': 'eos'})
        yield ledger


def refresh(ledger, fake):
    with patch('custom_components.eos_energiezentrale.energy.clients.request', side_effect=fake.request):
        ledger.last_eos_attempt = None
        ledger.refresh_eos(EOS('http://eos:8503'), 'battery1', NOW)


def charge(ledger, watts):
    ledger.stock = {'kwh': 0., 'cost': 0., 'unknown': 0.}
    row = sample(solar=watts, grid=0, battery_charge=watts, house_total=0, house=0, heat=0, car=0)
    row['consumers'] = {'house': 0}
    ledger.allocate(row, .001, ledger.effective())
    return ledger.stock['kwh'] / watts * 1000


def test_charging_at_low_power_stores_less_energy_than_at_medium_power(ledger, caplog):
    caplog.set_level(logging.INFO, 'custom_components.eos_energiezentrale.energy.accounting')
    refresh(ledger, FakeEOS())
    assert ledger.effective()['curves']['inverter'] is not None
    assert charge(ledger, 500) == pytest.approx(0.92 * 0.975)
    assert charge(ledger, 2500) > charge(ledger, 500)
    report = ledger.report({'period': 'day'}, NOW)
    assert report['efficiency_curves']['inverter'] is True and report['efficiency_curves_reason'] is None
    assert [record.getMessage() for record in caplog.records] == ['EOS efficiency model for accounting: battery_inverter']
    # Unchanged on the next refresh: no repeated log entry.
    refresh(ledger, FakeEOS())
    assert len(caplog.records) == 1


def test_discharging_withdraws_more_stored_energy_at_low_power(ledger):
    refresh(ledger, FakeEOS())
    def withdrawn(watts):
        ledger.stock = {'kwh': 10., 'cost': 1., 'unknown': 0.}
        row = sample(solar=0, grid=0, battery_discharge=watts, house_total=watts, house=watts, heat=0, car=0)
        row['consumers'] = {'house': watts}
        ledger.allocate(row, .001, ledger.effective())
        return (10. - ledger.stock['kwh']) / (watts / 1000)
    assert withdrawn(250) > withdrawn(2500) > 1


def test_incomplete_curves_are_logged_once_and_shown_with_their_reason(ledger, caplog):
    caplog.set_level(logging.INFO, 'custom_components.eos_energiezentrale.energy.accounting')
    refresh(ledger, FakeEOS(inverters={}))
    assert ledger.effective()['curves']['inverter'] is None
    assert charge(ledger, 500) == pytest.approx(0.975)
    report = ledger.report({'period': 'day'}, NOW)
    assert report['efficiency_curves']['inverter'] is False and report['efficiency_curves_reason'] == 'inverter_unassigned'
    refresh(ledger, FakeEOS(inverters={}))
    warnings = [record for record in caplog.records if record.levelno == logging.WARNING]
    assert len(warnings) == 1 and 'reason=inverter_unassigned' in warnings[0].getMessage()


def test_without_profiles_the_constant_eos_efficiencies_stay_in_use(ledger):
    refresh(ledger, FakeEOS(profile_status=404))
    assert 'curves' not in ledger.effective()
    assert charge(ledger, 500) == pytest.approx(.94)
    report = ledger.report({'period': 'day'}, NOW)
    assert report['efficiency_curves'] is None and report['efficiency_curves_reason'] == 'profile_api_missing'


def test_manual_efficiencies_ignore_curves(ledger):
    refresh(ledger, FakeEOS())
    ledger.configure({'efficiency_source': 'manual', 'charge_efficiency': .9, 'discharge_efficiency': .9})
    assert charge(ledger, 500) == pytest.approx(.9)
    report = ledger.report({'period': 'day'}, NOW)
    assert report['efficiency_curves'] is None and report['efficiency_curves_reason'] is None


def test_stored_curves_survive_a_restart_and_invalid_ones_are_dropped():
    with temporary_project_directory() as directory:
        ledger = Accounting(directory, ZoneInfo('Europe/Berlin'))
        ledger.configure({'pv_price_source': 'manual', 'efficiency_source': 'eos'})
        refresh(ledger, FakeEOS())
        ledger.observe(sample(battery_soc=50))
        restarted = Accounting(directory, ZoneInfo('Europe/Berlin'))
        assert restarted.effective()['curves']['inverter']['nominal_power_w'] == 5000
        import json, sqlite3
        with sqlite3.connect(directory / 'accounting.sqlite3') as db:
            broken = {**restarted.cached_effective, 'curves': {'battery': 'invalid'}}
            db.execute("INSERT OR REPLACE INTO meta VALUES ('effective',?)", (json.dumps(broken),))
        db.close()
        assert 'curves' not in Accounting(directory, ZoneInfo('Europe/Berlin')).effective()

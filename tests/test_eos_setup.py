"""Commissioning writes stay reviewed, bounded, confirmed and independent of device control."""
from copy import deepcopy
from datetime import timedelta
import json
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from custom_components.eos_energiezentrale.energy.clients import EOS
from custom_components.eos_energiezentrale.energy.eos_setup import EOSSetup, TTL, duration_seconds
from custom_components.eos_energiezentrale.energy.failures import BackendError
from custom_components.eos_energiezentrale.energy.settings import Configuration, save
from custom_components.eos_energiezentrale.energy.controller import Controller
from custom_components.eos_energiezentrale.const import DEFAULTS
from test_energy import NOW, instruction, temporary_project_directory

API = json.loads((Path(__file__).parent/'fixtures/eos_setup_api.json').read_text(encoding='utf-8'))
HARDWARE = [{'kind': 'batteries', 'resource': 'battery1', 'name': 'battery', 'capacity_wh': 10000,
             'charge_w': 5000, 'discharge_w': 4500, 'min_soc': 20, 'max_soc': 100},
            {'kind': 'electric_vehicles', 'resource': 'ev1', 'name': 'Vehicle', 'capacity_wh': 60000, 'charge_w': 11040}]
LOCATION = {'latitude': 0., 'longitude': 0., 'timezone': 'Europe/Berlin'}


def merge(target, changes):
    for key, value in changes.items():
        if isinstance(value, dict):
            if not isinstance(target.get(key), dict):
                target[key] = {}
            merge(target[key], value)
        else:
            target[key] = deepcopy(value)


class Backend:
    def __init__(self):
        self.current = {key: {} for key in ('general', 'devices', 'pvforecast', 'weather', 'elecprice',
                                           'elecfee', 'feedintariff', 'load', 'optimization', 'prediction', 'ems', 'adapter')}
        self.current['devices'] = {'batteries': None, 'electric_vehicles': None, 'inverters': None}
        self.current['elecprice'] = {'provider': 'ElecPriceTibber', 'tibber': {'access_token': 'secret-not-for-browser'}}
        self.current['weather']['provider'] = 'WeatherBrightSky'
        self.current['feedintariff']['provider'] = 'FeedInTariffFixed'
        self.current['load']['provider'] = 'LoadAkkudoktor'
        self.current['adapter'] = {'provider': ['HomeAssistant'], 'homeassistant': {'token': 'another-secret'}}
        self.current['server'] = {'port': 8503}
        self.calls = []
        self.api = deepcopy(API)
        self.saved = False
        self.fail_save = False
        self.confirm_limits = True

    def request(self, url, method='GET', payload=None):
        path = url.removeprefix('http://eos')
        self.calls.append((method, path, deepcopy(payload)))
        if path == '/openapi.json':
            return self.api
        if path == '/v1/profile/battery':
            return [{'name': 'generic-lfp'}, {'name': 'generic-nmc'}]
        if path == '/v1/profile/inverter':
            return [{'name': 'generic-hybrid'}]
        if path == '/v1/config' and method == 'PUT':
            merge(self.current, payload)
            for kind in ('batteries', 'electric_vehicles'):
                for row in (self.current['devices'].get(kind) or {}).values():
                    if self.confirm_limits:
                        row.update({'effective_' + key: value for key, value in row.get('profile_adjustment', {}).items()})
            for row in (self.current['devices'].get('inverters') or {}).values():
                row['effective_nominal_power_w'] = row.get('profile_adjustment', {}).get('nominal_power_w')
        if path == '/v1/config/file':
            if self.fail_save:
                raise TimeoutError('private server response')
            self.saved = True
        if path in ('/v1/config', '/v1/config/file'):
            response = deepcopy(self.current)
            # Real EOS serializes the supplied time windows with additional defaults,
            # times with microseconds and durations in words.
            def defaults(node):
                if isinstance(node, dict):
                    if 'windows' in node:
                        for row in node['windows']:
                            row.update(end_time=None, locale=None, start_time=eos_time(row['start_time']),
                                       duration=eos_duration(row['duration']))
                    for value in node.values():
                        defaults(value)
                elif isinstance(node, list):
                    for value in node:
                        defaults(value)
            defaults(response)
            return response
        raise AssertionError((method, path))


def eos_time(value):
    if ':' not in value:
        return value
    hour, minute, *rest = value.split(':')
    return f'{hour}:{minute}:{(rest or ["00"])[0].split(".")[0]}.000000'


def eos_duration(value):
    seconds = duration_seconds(value)
    days, rest = divmod(seconds, 86400)
    parts = [(days, 'day'), (rest // 3600, 'hour'), (rest // 60 % 60, 'minute')]
    return ' '.join(f'{amount} {unit}' + ('s' if amount != 1 else '') for amount, unit in parts if amount)


@pytest.fixture
def setup_backend():
    backend = Backend()
    with patch('custom_components.eos_energiezentrale.energy.eos_setup.request', side_effect=backend.request):
        yield EOSSetup(EOS('http://eos')), backend


def draft(setup):
    return setup.load(HARDWARE, LOCATION)['draft']


def test_load_is_read_only_exposes_no_credentials_and_maps_all_local_devices(setup_backend):
    setup, backend = setup_backend
    result = setup.load(HARDWARE, LOCATION)
    assert result['draft']['latitude'] == 0 and result['draft']['longitude'] == 0
    assert [row['resource'] for row in result['draft']['devices']] == ['battery1', 'ev1']
    assert result['draft']['price_provider'] == 'keep'
    assert all(method == 'GET' for method, _, _ in backend.calls)
    assert 'secret' not in json.dumps(result)


def test_review_then_apply_merges_only_wizard_fields_and_saves_permanently(setup_backend):
    setup, backend = setup_backend
    values = draft(setup)
    values.update(latitude=48.1, longitude=11.5, price_provider='ElecPriceFixed', price_zones=[{'start': '00:00', 'price_ct': 29.99}],
                  feedin_provider='FeedInTariffFixed', feedin_ct=8.2, load_provider='LoadAkkudoktor', annual_kwh=5500)
    preview = setup.preview(values, HARDWARE)
    assert not any(method == 'PUT' for method, _, _ in backend.calls)
    assert 'secret' not in json.dumps(preview)
    before_write = Mock()
    assert setup.apply(preview['token'], HARDWARE, before_write)['ok']
    before_write.assert_called_once_with()
    assert backend.saved
    assert backend.current['elecprice']['tibber']['access_token'] == 'secret-not-for-browser'
    assert backend.current['adapter']['homeassistant']['token'] == 'another-secret'
    assert backend.current['adapter']['provider'] == []
    assert backend.current['server']['port'] == 8503
    assert backend.current['elecfee']['elecfeefixed']['consumption_percent_amt']['windows'][0]['value'] == 0
    assert backend.current['elecprice']['elecpricefixed']['elecprice_marketprice_amt_kwh']['windows'][0]['value'] == .2999
    assert backend.current['devices']['electric_vehicles']['ev1']['charge_rates'] == [0.]
    assert [path for method, path, _ in backend.calls if method == 'PUT'] == ['/v1/config', '/v1/config/file']
    with pytest.raises(BackendError, match='rejected'):
        setup.apply(preview['token'], HARDWARE)


def test_dynamic_fees_are_separate_and_existing_secrets_stay_out_of_patch(setup_backend):
    setup, backend = setup_backend
    values = draft(setup)
    values.update(price_provider='ElecPriceEnergyCharts', fee_ct=15, vat_percent=19)
    preview = setup.preview(values, HARDWARE)
    setup.apply(preview['token'], HARDWARE)
    submitted = next(payload for method, path, payload in backend.calls if method == 'PUT')
    assert 'tibber' not in submitted['elecprice']
    assert submitted['elecfee']['elecfeefixed']['consumption_amt_kwh']['windows'][0]['value'] == .15
    assert submitted['elecfee']['elecfeefixed']['consumption_percent_amt']['windows'][0]['value'] == 19


OCTOPUS_GO = [{'start': '00:30', 'price_ct': 8.5}, {'start': '05:30', 'price_ct': 28}]


def fixed_windows(backend):
    """The windows as EOS returns them."""
    return backend.request('http://eos/v1/config')['elecprice']['elecpricefixed']['elecprice_marketprice_amt_kwh']['windows']


def test_a_fixed_tariff_with_daily_price_zones_is_written_without_windows_across_midnight(setup_backend):
    setup, backend = setup_backend
    values = draft(setup)
    values.update(price_provider='ElecPriceFixed', price_zones=list(reversed(OCTOPUS_GO)))
    preview = setup.preview(values, HARDWARE)
    change = next(row for row in preview['changes'] if row['path'].endswith('elecprice_marketprice_amt_kwh/windows'))
    assert change['after'] == [{'start': '00:00', 'end': '00:30', 'value': .28},
                               {'start': '00:30', 'end': '05:30', 'value': .085},
                               {'start': '05:30', 'end': '24:00', 'value': .28}]
    assert setup.apply(preview['token'], HARDWARE)['ok'] and backend.saved
    submitted = next(payload for method, path, payload in backend.calls if method == 'PUT')
    assert submitted['elecprice']['elecpricefixed']['elecprice_marketprice_amt_kwh']['windows'] == [
        {'start_time': '00:00:00', 'duration': 'PT30M', 'value': .28},
        {'start_time': '00:30:00', 'duration': 'PT5H', 'value': .085},
        {'start_time': '05:30:00', 'duration': 'PT18H30M', 'value': .28}]
    # The gross zone prices get no additional fees in EOS.
    assert submitted['elecfee']['elecfeefixed']['consumption_amt_kwh']['windows'][0]['value'] == 0
    # EOS returns the windows in its own notation; the wizard shows the same zones again.
    assert fixed_windows(backend)[2]['duration'] == '18 hours 30 minutes'
    assert draft(setup)['price_zones'] == OCTOPUS_GO
    values = draft(setup)
    values['price_provider'] = 'ElecPriceFixed'
    assert not any('elecprice_marketprice' in row['path'] for row in setup.preview(values, HARDWARE)['changes'])


def test_zones_starting_at_midnight_and_a_single_zone_keep_one_window_per_zone(setup_backend):
    setup, backend = setup_backend
    zones = [{'start': '00:00', 'price_ct': 21}, {'start': '05:00', 'price_ct': 31}]
    values = draft(setup)
    values.update(price_provider='ElecPriceFixed', price_zones=zones)
    setup.apply(setup.preview(values, HARDWARE)['token'], HARDWARE)
    assert [(row['start_time'], row['duration']) for row in fixed_windows(backend)] == [
        ('00:00:00.000000', '5 hours'), ('05:00:00.000000', '19 hours')]
    assert draft(setup)['price_zones'] == zones
    values = draft(setup)
    values.update(price_provider='ElecPriceFixed', price_zones=[{'start': '07:00', 'price_ct': 30}])
    setup.apply(setup.preview(values, HARDWARE)['token'], HARDWARE)
    assert [(row['start_time'], row['duration'], row['value']) for row in fixed_windows(backend)] == [
        ('00:00:00.000000', '1 day', .3)]


@pytest.mark.parametrize('windows', [
    [{'start_time': '00:00', 'duration': 'PT5H', 'value': .2}],
    [{'start_time': '00:00', 'duration': 'P1D', 'value': .2, 'day_of_week': 1}],
    [{'start_time': '00:00', 'duration': 'PT6H', 'value': .2}, {'start_time': '05:00', 'duration': 'PT19H', 'value': .3}],
    [{'start_time': 'noon', 'duration': 'P1D', 'value': .2}],
])
def test_tariff_windows_that_are_not_daily_zones_are_not_shown_as_zones(setup_backend, windows):
    setup, backend = setup_backend
    backend.current['elecprice'] = {'provider': 'ElecPriceFixed',
                                    'elecpricefixed': {'elecprice_marketprice_amt_kwh': {'windows': windows}}}
    result = setup.load(HARDWARE, LOCATION)
    assert result['draft']['price_provider'] == 'keep'
    assert result['draft']['price_zones'] == [{'start': '00:00', 'price_ct': 30}]


@pytest.mark.parametrize('zones', [
    [], [{'start': '24:00', 'price_ct': 20}], [{'start': '5:00', 'price_ct': 20}],
    [{'start': '01:00', 'price_ct': 20}, {'start': '01:00', 'price_ct': 30}],
    [{'start': '01:00', 'price_ct': -1}], [{'start': '01:00', 'price_ct': 20, 'end': '02:00'}],
    [{'start': f'{hour:02d}:00', 'price_ct': 20} for hour in range(13)], 'cheap'])
def test_invalid_price_zones_never_write_configuration(setup_backend, zones):
    setup, backend = setup_backend
    values = draft(setup)
    values.update(price_provider='ElecPriceFixed', price_zones=zones)
    with pytest.raises(BackendError) as error:
        setup.preview(values, HARDWARE)
    assert error.value.fields == ['price_zones']
    assert all(method == 'GET' for method, _, _ in backend.calls)


@pytest.mark.parametrize('field,value', [('latitude', True), ('longitude', float('nan')), ('price_provider', 'untrusted'),
                                        ('prediction_hours', 1), ('interval_seconds', 59), ('timezone', 'unknown/zone')])
def test_invalid_values_never_write_configuration(setup_backend, field, value):
    setup, backend = setup_backend
    values = draft(setup)
    values[field] = value
    with pytest.raises(BackendError):
        setup.preview(values, HARDWARE)
    assert all(method == 'GET' for method, _, _ in backend.calls)


def test_conflict_rejects_stale_review_but_unrelated_credentials_do_not_conflict(setup_backend):
    setup, backend = setup_backend
    values = draft(setup)
    preview = setup.preview(values, HARDWARE)
    backend.current['general']['latitude'] = 12
    with pytest.raises(BackendError) as error:
        setup.apply(preview['token'], HARDWARE)
    assert error.value.reason == 'setup_conflict'
    assert not backend.saved
    preview = setup.preview(values, HARDWARE)
    backend.current['elecprice']['tibber']['access_token'] = 'updated-private-token'
    setup.apply(preview['token'], HARDWARE)
    assert backend.current['elecprice']['tibber']['access_token'] == 'updated-private-token'


def test_expired_preview_or_changed_local_hardware_cannot_write(setup_backend):
    setup, backend = setup_backend
    preview = setup.preview(draft(setup), HARDWARE)
    setup.pending['at'] -= TTL + 1
    with pytest.raises(BackendError) as error:
        setup.apply(preview['token'], HARDWARE)
    assert error.value.reason == 'setup_preview_expired'
    preview = setup.preview(draft(setup), HARDWARE)
    with pytest.raises(BackendError):
        setup.apply(preview['token'], HARDWARE[:1])
    assert all(method == 'GET' for method, _, _ in backend.calls)


def test_unconfirmed_effective_limits_never_claim_success_or_persist(setup_backend):
    setup, backend = setup_backend
    preview = setup.preview(draft(setup), HARDWARE)
    backend.confirm_limits = False
    with pytest.raises(BackendError) as error:
        setup.apply(preview['token'], HARDWARE)
    assert error.value.reason == 'effective_limits_unavailable'
    assert not backend.saved
    assert setup.pending is None


def test_failed_persistence_is_explicit_and_not_automatically_retried(setup_backend):
    setup, backend = setup_backend
    preview = setup.preview(draft(setup), HARDWARE)
    backend.fail_save = True
    with pytest.raises(BackendError) as error:
        setup.apply(preview['token'], HARDWARE)
    assert error.value.reason == 'setup_save_failed'
    assert setup.pending is None
    assert len([call for call in backend.calls if call[0] == 'PUT']) == 2


def test_existing_devices_plane_metadata_and_profiles_are_preserved(setup_backend):
    setup, backend = setup_backend
    backend.current['devices']['batteries'] = {'unmanaged': {'device_id': 'unmanaged', 'battery_profile': 'custom'}}
    backend.current['pvforecast'] = {'provider': 'PVForecastAkkudoktor', 'max_planes': 1, 'planes': [
        {'name': 'Roof', 'peakpower': 5, 'surface_tilt': 30, 'surface_azimuth': 180, 'inverter_paco': 5000,
         'loss': 14, 'measurement_key': 'pv-production', 'learning_guard_key': 'guard'}]}
    values = draft(setup)
    values['planes'][0]['peakpower'] = 6
    preview = setup.preview(values, HARDWARE)
    setup.apply(preview['token'], HARDWARE)
    assert backend.current['devices']['batteries']['unmanaged']['battery_profile'] == 'custom'
    assert backend.current['pvforecast']['planes'][0]['learning_guard_key'] == 'guard'
    assert backend.current['pvforecast']['planes'][0]['peakpower'] == 6


def test_schema_without_required_api_is_rejected_before_writing(setup_backend):
    setup, backend = setup_backend
    del backend.api['paths']['/v1/config/file']
    with pytest.raises(BackendError) as error:
        draft(setup)
    assert error.value.reason == 'setup_unsupported'
    assert all(method == 'GET' for method, _, _ in backend.calls)


def test_removing_a_plane_preserves_the_remaining_planes_measurement_assignment(setup_backend):
    setup, backend = setup_backend
    backend.current['pvforecast'] = {'provider': 'PVForecastAkkudoktor', 'max_planes': 2, 'planes': [
        {'name': name, 'peakpower': 5, 'surface_tilt': 30, 'surface_azimuth': azimuth, 'inverter_paco': 5000,
         'loss': 14, 'measurement_key': meter} for name, azimuth, meter in (('East', 90, 'meter-east'), ('West', 270, 'meter-west'))]}
    values = draft(setup)
    values['planes'].pop(0)
    preview = setup.preview(values, HARDWARE)
    setup.apply(preview['token'], HARDWARE)
    assert backend.current['pvforecast']['planes'][0]['measurement_key'] == 'meter-west'


def test_concurrent_plane_changes_are_detected_before_creating_the_review(setup_backend):
    setup, backend = setup_backend
    backend.current['pvforecast'] = {'provider': 'PVForecastAkkudoktor', 'planes': [
        {'name': 'Roof', 'peakpower': 5, 'surface_tilt': 30, 'surface_azimuth': 180, 'inverter_paco': 5000, 'loss': 14}]}
    values = draft(setup)
    backend.current['pvforecast']['planes'][0]['measurement_key'] = 'changed-meter'
    with pytest.raises(BackendError) as error:
        setup.preview(values, HARDWARE)
    assert error.value.reason == 'setup_conflict'
    assert all(method == 'GET' for method, _, _ in backend.calls)


def test_device_mapping_is_not_supplied_by_the_browser(setup_backend):
    setup, backend = setup_backend
    values = draft(setup)
    values['devices'][0]['resource'] = 'other-device'
    with pytest.raises(BackendError):
        setup.preview(values, HARDWARE)
    assert all(method == 'GET' for method, _, _ in backend.calls)


def test_known_local_hardware_limits_cannot_be_overridden_in_eos_only(setup_backend):
    setup, backend = setup_backend
    values = draft(setup)
    values['devices'][0]['charge_w'] = 9000
    with pytest.raises(BackendError) as error:
        setup.preview(values, HARDWARE)
    assert error.value.fields == ['max_charge_power_w']
    assert all(method == 'GET' for method, _, _ in backend.calls)


def test_unknown_profiles_and_unsupported_fields_do_not_reach_eos_writes(setup_backend):
    setup, backend = setup_backend
    values = draft(setup)
    values['devices'][0]['profile'] = 'missing-profile'
    with pytest.raises(BackendError):
        setup.preview(values, HARDWARE)
    values = draft(setup)
    del backend.api['components']['schemas']['BatteriesCommonSettings-Input']['properties']['profile_adjustment']
    with pytest.raises(BackendError) as error:
        setup.preview(values, HARDWARE)
    assert error.value.reason == 'setup_unsupported'
    assert all(method == 'GET' for method, _, _ in backend.calls)


def test_plan_barrier_survives_restart_and_rejects_old_plans():
    with temporary_project_directory() as directory:
        save(directory/'eos_setup.json', {'at': NOW.isoformat()})
        config = Configuration(dict(DEFAULTS), Mock(), directory)
        app = Controller(Mock(), config)
        old = NOW - timedelta(minutes=1)
        app.apply_eos_plan({'generated_at': old.isoformat(), 'instructions': [instruction(NOW, 'NON_EXPORT')]}, NOW)
        assert not app.resource_plans
        assert app.error_details['eos']['reason'] == 'setup_plan_pending'
        app.apply_eos_plan({'generated_at': NOW.isoformat(), 'instructions': [instruction(NOW, 'NON_EXPORT')]}, NOW)
        assert 'battery1' in app.resource_plans


def test_an_existing_fixed_tariff_opens_with_its_zones_and_unchanged_applies_nothing_new(setup_backend):
    setup, backend = setup_backend
    values = draft(setup)
    values.update(price_provider='ElecPriceFixed', price_zones=OCTOPUS_GO)
    setup.apply(setup.preview(values, HARDWARE)['token'], HARDWARE)
    loaded = draft(setup)
    assert loaded['price_provider'] == 'ElecPriceFixed' and loaded['price_zones'] == OCTOPUS_GO
    changes = setup.preview(loaded, HARDWARE)['changes']
    assert not any(row['path'].startswith(('elecprice', 'elecfee')) for row in changes)


@pytest.mark.parametrize('fees', [
    {'provider': 'ElecFeeFixed', 'elecfeefixed': {'consumption_amt_kwh': {'windows': [{'start_time': '00:00', 'duration': 'P1D', 'value': .05}]},
                                                  'consumption_percent_amt': {'windows': [{'start_time': '00:00', 'duration': 'P1D', 'value': 0}]}}},
    {'provider': 'ElecFeeFixed', 'elecfeefixed': {}},
    {},
])
def test_a_fixed_tariff_with_other_fees_keeps_the_current_configuration(setup_backend, fees):
    setup, backend = setup_backend
    backend.current['elecprice'] = {'provider': 'ElecPriceFixed', 'elecpricefixed': {'elecprice_marketprice_amt_kwh': {
        'windows': [{'start_time': '00:00', 'duration': 'P1D', 'value': .3}]}}}
    backend.current['elecfee'] = fees
    loaded = draft(setup)
    # Selecting the fixed tariff would reset the fees to 0; the user decides that explicitly.
    assert loaded['price_provider'] == 'keep' and loaded['price_zones'] == [{'start': '00:00', 'price_ct': 30}]


def test_saved_fees_and_feed_in_are_shown_again_in_the_eos_notation(setup_backend):
    setup, backend = setup_backend
    values = draft(setup)
    values.update(price_provider='ElecPriceEnergyCharts', fee_ct=15, vat_percent=7, feedin_provider='FeedInTariffFixed', feedin_ct=6.5)
    setup.apply(setup.preview(values, HARDWARE)['token'], HARDWARE)
    assert backend.request('http://eos/v1/config')['elecfee']['elecfeefixed']['consumption_amt_kwh']['windows'][0]['start_time'] == '00:00:00.000000'
    loaded = draft(setup)
    assert (round(loaded['fee_ct'], 6), loaded['vat_percent'], round(loaded['feedin_ct'], 6)) == (15, 7, 6.5)

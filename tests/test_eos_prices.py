"""EOS gross-price fallback: real slots, precedence, expiry and consistent history."""
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import pytest

from custom_components.eos_energiezentrale.const import DEFAULTS
from custom_components.eos_energiezentrale.energy.clients import EOS, reading
from custom_components.eos_energiezentrale.energy.contracts import BatteryReading, Measurement
from custom_components.eos_energiezentrale.energy.eos_prices import EOSPrices, PRICE_MAX_AGE_S, price_intervals
from custom_components.eos_energiezentrale.energy.failures import BackendError
from custom_components.eos_energiezentrale.energy.measurement_sources import resolve_sources
from custom_components.eos_energiezentrale.energy.source_diagnostics import source_diagnostics
from custom_components.eos_energiezentrale.energy.status import view_state
from test_energy import NOW
from test_requirements import state


def series(values=(.0003, .0004, .0005, .0006, .0007), start=None, step=900):
    start = start or NOW.replace(minute=0, second=0, microsecond=0)
    return {'data': {(start + timedelta(seconds=index * step)).isoformat(): value for index, value in enumerate(values)}}


def cache(value=30, when=NOW):
    prices = EOSPrices()
    prices.update([{'time': NOW.isoformat(), 'end': (NOW + timedelta(hours=1)).isoformat(), 'price_ct': value}], when)
    return prices


def test_client_uses_raw_fee_inclusive_series_without_interpolation_or_extra_taxes():
    with patch('custom_components.eos_energiezentrale.energy.clients.request', return_value=series()) as call:
        rows = EOS('http://eos').electricity_prices(NOW)
    query = parse_qs(urlsplit(call.call_args.args[0]).query)
    assert urlsplit(call.call_args.args[0]).path == '/v1/prediction/series'
    assert query['key'] == ['elecprice_marketprice_wh']
    assert query['processing'] == ['raw'] and query['dropna'] == ['false']
    assert rows[0]['price_ct'] == pytest.approx(30)
    assert rows[0]['end'] == (NOW.replace(minute=0, second=0, microsecond=0) + timedelta(minutes=15)).isoformat()


@pytest.mark.parametrize('value,expected', [(0, 0), (-.0001, -10), (.000357, 35.7)])
def test_zero_negative_and_positive_prices_are_converted_once(value, expected):
    assert price_intervals(series((value, value)), NOW)[0]['price_ct'] == pytest.approx(expected)


@pytest.mark.parametrize('value', [None, True, float('nan'), float('inf'), .02, 'invalid'])
def test_unknown_or_implausible_current_prices_never_become_free_energy(value):
    with pytest.raises(BackendError) as error:
        price_intervals(series((value, .0004, .0005)), NOW)
    assert error.value.reason == 'price_unavailable'


def test_null_slots_and_missing_intervals_are_not_interpolated_or_extended():
    start = NOW.replace(minute=0, second=0, microsecond=0)
    with pytest.raises(BackendError):
        price_intervals(series((.0003, None, .0005)), start + timedelta(minutes=20))
    sparse = series()
    del sparse['data'][(start + timedelta(minutes=15)).isoformat()]
    with pytest.raises(BackendError):
        price_intervals(sparse, start + timedelta(minutes=20))
    with pytest.raises(BackendError):
        price_intervals(series((.0003, .0004)), start + timedelta(minutes=20))


def test_prices_for_past_or_future_slots_are_not_current_prices():
    for start in (NOW - timedelta(days=1), NOW + timedelta(hours=1)):
        with pytest.raises(BackendError):
            price_intervals(series(start=start), NOW)


def test_hourly_prices_remain_usable_during_the_whole_hour():
    rows = price_intervals(series(step=3600), NOW + timedelta(minutes=50))
    assert rows[0]['end'] == (NOW.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)).isoformat()


def test_eos_is_automatic_without_a_price_sensor_and_is_identified_in_diagnostics():
    prices = cache(35.7)
    opts, states, report = resolve_sources(DEFAULTS, {}, (), NOW, eos_prices=prices)
    assert opts['price_entity'] == '@eos:price'
    assert 'price' not in report['missing'] and 'price' not in report['unavailable']
    assert report['sources']['price']['source'] == {'type': 'eos', 'name': 'Akkudoktor EOS'}
    assert reading(states, opts['price_entity'], NOW, 'price', 3600) == 35.7
    diag = source_diagnostics({'live': {'price': 35.7}, 'source_configuration': report}, NOW)
    row = next(row for row in diag['sources'] if row['key'] == 'price')
    assert row['source_type'] == 'eos' and row['value'] == 35.7
    assert DEFAULTS['price_entity'] == ''


def test_unready_eos_is_unavailable_instead_of_missing_configuration():
    _, _, report = resolve_sources(DEFAULTS, {}, (), NOW)
    assert 'price' not in report['missing']
    assert 'price' in report['unavailable']
    notices = view_state({'source_configuration': report}, NOW)['notices']
    missing = [item for item in notices if item['code'] == 'sources_missing']
    assert all('price' not in item.get('measurements', []) for item in missing)


def test_cache_expiry_also_rejects_the_value_for_live_control_and_history():
    now = NOW + timedelta(seconds=PRICE_MAX_AGE_S)
    opts, states, report = resolve_sources(DEFAULTS, {}, (), now, eos_prices=cache())
    assert reading(states, opts['price_entity'], now, 'price', 3600) is None
    assert report['sources']['price']['reason'] == 'stale'
    assert report['sources']['price']['max_age_s'] == PRICE_MAX_AGE_S


def test_a_configured_sensor_or_declared_plugin_keeps_precedence_even_if_unavailable():
    prices = cache()
    options = {**DEFAULTS, 'price_entity': 'sensor.price'}
    opts, states, report = resolve_sources(options, {'sensor.price': state(.42, 'EUR/kWh')}, (), NOW, eos_prices=prices)
    assert reading(states, opts['price_entity'], NOW, 'price', 3600) == 42
    opts, states, report = resolve_sources(options, {}, (), NOW, eos_prices=prices)
    assert report['sources']['price']['source']['type'] == 'sensor'
    assert reading(states, opts['price_entity'], NOW, 'price', 3600) is None
    driver = SimpleNamespace(measurement_keys=('price',), info=SimpleNamespace(name='Price plugin'))
    for value in (25, None):
        sample = BatteryReading(50, 0, 0, measurements={'price': Measurement(value, NOW)})
        opts, states, report = resolve_sources(DEFAULTS, {}, ((driver, sample),), NOW, eos_prices=prices)
        assert report['sources']['price']['source']['type'] == 'plugin'
        assert reading(states, opts['price_entity'], NOW, 'price', 3600) == value


def test_controller_uses_eos_price_for_live_data_and_persisted_samples():
    from test_requirements import ControllerRequirements
    fixture = ControllerRequirements()
    fixture.setUp()
    try:
        fixture.config.options['price_entity'] = ''
        fixture.app.external_eos_polling = True
        fixture.app.apply_eos_prices([{'time': NOW.isoformat(), 'end': (NOW + timedelta(hours=1)).isoformat(), 'price_ct': 24.5}], NOW)
        fixture.app.tick(NOW, 0)
        assert fixture.app.live['price'] == 24.5
        assert fixture.app.history.read(NOW)[-1]['price'] == 24.5
        assert 'price' not in fixture.app.source_configuration['missing']
        fixture.app.tick(NOW + timedelta(seconds=PRICE_MAX_AGE_S), PRICE_MAX_AGE_S)
        assert fixture.app.live['price'] is None
        fixture.app.apply_eos_prices(None, NOW, TimeoutError())
        assert 'eos_price' in fixture.app.errors
    finally:
        fixture.doCleanups()

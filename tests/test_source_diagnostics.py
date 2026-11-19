from datetime import datetime, timedelta, timezone

from custom_components.eos_energiezentrale.energy.domain import energy_balance
from custom_components.eos_energiezentrale.energy.source_diagnostics import source_diagnostics

NOW = datetime(2026, 11, 18, 17, 50, tzinfo=timezone.utc)


def snapshot(**live):
    values = {'time': NOW.isoformat(), 'solar': 0, 'grid': 10, 'house_total': 940, 'house': 940, 'heat': 0, 'car': 0,
              'price': 42.0, 'battery_soc': 87.0, 'battery_charge': 0, 'battery_discharge': 510, 'heat_load': .25, **live}
    plugin = {'type': 'plugin', 'name': 'Configured devices'}
    return {'live': values, 'features': {'car': True, 'heat': True},
            'plugins': {'battery': {'name': 'Configured devices', 'measurements': ['battery_soc', 'battery_charge', 'battery_discharge', 'grid', 'house_total', 'solar']},
                        'wallbox': {'name': 'go-e', 'measurements': ['car']}},
            'source_configuration': {'missing': ['price'], 'unavailable': ['heat'], 'sources': {
                'solar': {'source': plugin, 'available': True, 'reason': None, 'max_age_s': 45, 'sample': (NOW - timedelta(seconds=3)).isoformat()},
                'grid': {'source': plugin, 'available': True, 'reason': None, 'max_age_s': 45, 'sample': NOW.isoformat()},
                'house_total': {'source': plugin, 'available': True, 'reason': None, 'max_age_s': 120, 'sample': NOW.isoformat()},
                'heat': {'source': {'type': 'sensor', 'name': 'sensor.heat_pump'}, 'available': False, 'reason': 'stale', 'max_age_s': 120,
                         'sample': (NOW - timedelta(minutes=5)).isoformat()},
                'price': {'source': None, 'available': False, 'reason': 'not_configured', 'max_age_s': 3600, 'sample': None},
                'car_soc': {'source': None, 'available': False, 'reason': 'not_configured', 'max_age_s': 3600, 'sample': None},
                'heat_load': {'source': {'type': 'sensor', 'name': 'sensor.load'}, 'available': True, 'reason': None, 'max_age_s': 120, 'sample': NOW.isoformat()}}},
            'battery_group': {'devices': [{'name': 'Victron', 'battery': True, 'available': True, 'read_error': None,
                                           'plugin': {'name': 'Victron GX direct Modbus TCP'}, 'soc': 87.0, 'charge': 0., 'discharge': 510.,
                                           'measurements': {'solar': 0., 'house_total': 940., 'grid': 10.}}]},
            'vehicles': [{'name': 'Leapmotor', 'live': {'car': 0, 'car_soc': 77, 'soc_source': 'vehicle', 'car_connected': True}}]}


def test_lists_configured_and_missing_required_sources_with_values_age_and_status():
    result = source_diagnostics(snapshot(), NOW)
    rows = {row['key']: row for row in result['sources']}
    # Unconfigured optional sources are omitted, missing required ones stay visible.
    assert 'car_soc' not in rows and rows['price']['reason'] == 'not_configured' and rows['price']['value'] is None
    assert rows['solar'] == {'key': 'solar', 'unit': 'W', 'value': 0, 'source_type': 'plugin', 'source': 'Configured devices',
                             'available': True, 'reason': None, 'age_s': 3., 'max_age_s': 45}
    # A stale sensor is not shown as a valid current value.
    assert rows['heat']['value'] is None and rows['heat']['reason'] == 'stale' and rows['heat']['age_s'] == 300.
    assert rows['heat']['source'] == 'sensor.heat_pump' and rows['heat_load']['value'] == 25.
    assert [rows[key]['value'] for key in ('battery_soc', 'battery_charge', 'battery_discharge', 'car')] == [87.0, 0, 510, 0]
    assert result['devices'][0]['values'] == {'solar': 0., 'grid': 10., 'house_total': 940., 'battery_soc': 87.,
                                              'battery_charge': 0., 'battery_discharge': 510.}
    assert result['vehicles'] == [{'name': 'Leapmotor', 'car': 0., 'car_soc': 77., 'soc_source': 'vehicle', 'connected': True,
                                   'car_range': None}]


def test_balance_reveals_a_site_total_that_exceeds_all_sources():
    # Issue #33: 10 W import + 510 W discharge cannot supply 940 W consumption.
    balance = source_diagnostics(snapshot(), NOW)['balance']
    assert balance == {'supplied_w': 520, 'consumed_w': 940, 'residual_w': -420, 'tolerance_w': 300, 'balanced': False}
    charging = source_diagnostics(snapshot(grid=9020, battery_charge=7900, battery_discharge=0, house_total=420), NOW)['balance']
    assert charging['balanced'] is True and charging['residual_w'] == 700
    assert source_diagnostics(snapshot(grid=None), NOW)['balance'] is None


def test_derived_house_matches_the_controller_formula_and_disabled_consumers_count_as_zero():
    data = snapshot(house_total=3000, car=1200, heat=800, house=1000)
    assert source_diagnostics(data, NOW)['derived'] == {'house': 1000., 'house_total': 3000., 'house_total_measured': 3000.,
                                                        'car': 1200., 'heat': 800.}
    data['features'] = {'car': False, 'heat': False}
    assert source_diagnostics(data, NOW)['derived']['car'] == 0 and source_diagnostics(data, NOW)['derived']['heat'] == 0


def test_empty_snapshot_is_safe():
    assert source_diagnostics({}, NOW) == {'time': None, 'sources': [], 'derived': {'house': None, 'house_total': None,
        'house_total_measured': None, 'car': 0., 'heat': 0.}, 'balance': None, 'complete': False, 'estimates': [],
        'deviation_since': None, 'devices': [], 'vehicles': []}


def test_balance_values_and_estimates_replace_the_measured_split():
    from custom_components.eos_energiezentrale.energy.consumption import ConsumptionBalance, apply_balance
    data = snapshot()
    balance = ConsumptionBalance()
    apply_balance(data['live'], balance.update(data['live'], NOW))
    result = source_diagnostics(data, NOW)
    # The site total follows the sources; the measured 940 W is the check that fails.
    assert result['derived']['house_total'] == 520 and result['derived']['house_total_measured'] == 940
    assert next(row for row in result['sources'] if row['key'] == 'house_total')['value'] == 940
    assert result['balance']['residual_w'] == -420 and result['balance']['balanced'] is False
    assert result['complete'] is True and result['deviation_since'] == NOW.isoformat()
    later = NOW + timedelta(seconds=10)
    data['live'].update(time=later.isoformat(), heat=None)
    apply_balance(data['live'], balance.update({**data['live'], 'house_total': 940}, later))
    assert source_diagnostics(data, later)['estimates'] == [{'key': 'heat', 'reason': 'consumer_hold'}]


def test_shared_balance_rule_matches_accounting_tolerance():
    assert energy_balance(0, 100, 0, 0, None) is None
    assert energy_balance(1000, -200, 0, 0, 500)['balanced'] is True
    assert energy_balance(1000, 0, 0, 0, 650)['balanced'] is False
    assert energy_balance(0, 10000, 0, 0, 9100)['tolerance_w'] == 910


def test_vehicle_soc_row_shows_the_sensor_reading_even_when_the_shared_live_data_has_none():
    # Issue #33: in a fleet the shared live data carries no SoC; the row showed "—"
    # although the sensor delivered 76 %. An estimate never replaces the reading.
    data = snapshot(car_soc=None)
    data['source_configuration']['sources']['car_soc'] = {
        'source': {'type': 'sensor', 'name': 'sensor.car_soc'}, 'available': True, 'reason': None,
        'max_age_s': 43200, 'sample': NOW.isoformat(), 'value': 76.0}
    rows = {row['key']: row for row in source_diagnostics(data, NOW)['sources']}
    assert rows['car_soc']['value'] == 76.
    data['live']['car_soc'] = 80.6
    data['source_configuration']['sources']['car_soc'].update(available=False, value=None)
    rows = {row['key']: row for row in source_diagnostics(data, NOW)['sources']}
    assert rows['car_soc']['value'] is None

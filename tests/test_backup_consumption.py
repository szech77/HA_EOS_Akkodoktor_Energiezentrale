"""Fresh AC output is the island load; separate consumers stay independent."""
from dataclasses import replace
from datetime import timedelta
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from custom_components.eos_energiezentrale.energy.contracts import BatteryReading, Measurement, PowerSupplyReading
from custom_components.eos_energiezentrale.energy.measurement_sources import resolve_sources
from custom_components.eos_energiezentrale.energy.status import view_state
from test_energy import NOW
from test_measurement_sources import provider
from test_requirements import state


def resolve(mode='backup', watts=3500, stamp=NOW, options=None, states=None):
    sample = BatteryReading(50, 0, 500, measurements={'inverter_ac':Measurement(watts, stamp)},
                            power_supply=PowerSupplyReading(mode, NOW))
    options = {'wallbox_type':'none', 'house_entity':'sensor.house', **(options or {})}
    rows = {'sensor.house':state(9000), **(states or {})}
    return resolve_sources(options, rows, ((provider(('inverter_ac',)), sample),), NOW)


def test_backup_ac_overrides_grid_based_house_sensor_without_mutating_it():
    options, rows, report = resolve(stamp=NOW-timedelta(seconds=7))
    assert options['house_entity'] == '@backup:house_total'
    assert rows['@backup:house_total']['state'] == 3500
    assert rows['@backup:house_total']['last_reported'] == (NOW-timedelta(seconds=7)).isoformat()
    assert rows['sensor.house']['state'] == '9000'
    assert report['sources']['house_total']['source']['type'] == 'backup'
    assert 'house_total' not in report['unavailable']


@pytest.mark.parametrize('mode', ['grid', 'unknown', 'unsupported'])
def test_other_modes_keep_the_normal_house_source(mode):
    options, rows, _ = resolve(mode)
    assert options['house_entity'] == 'sensor.house'
    assert '@backup:house_total' not in rows


@pytest.mark.parametrize('watts, stamp', [(None, NOW), (-10, NOW), (float('nan'), NOW),
    (3500, None), (3500, NOW-timedelta(seconds=120)), (3500, NOW+timedelta(seconds=1))])
def test_missing_invalid_or_old_ac_output_is_not_a_zero_house_load(watts, stamp):
    _, rows, report = resolve(watts=watts, stamp=stamp)
    assert rows['@backup:house_total']['state'] is None
    result = view_state({'power_supply':{'state':'backup','sample':NOW.isoformat()},
                         'source_configuration':report}, NOW)
    assert any('house_total' in item.get('measurements', []) for item in result['notices'])


@pytest.mark.parametrize('active, expected', [('on', '@backup:house_total'), ('off', 'sensor.house')])
def test_configured_backup_source_overrides_native_mode_for_consumption(active, expected):
    options, _, _ = resolve('grid', options={'backup_mode_entity':'binary_sensor.backup'},
                           states={'binary_sensor.backup':state(active)})
    assert options['house_entity'] == expected


def test_controller_subtracts_measured_ev_and_heat_from_island_ac_and_restores_normal_source():
    import test_requirements as requirements
    case = requirements.ControllerRequirements()
    case.setUp()
    try:
        case.battery.measurement_keys = ('inverter_ac',)
        case.battery.info = SimpleNamespace(name='Test inverter')
        case.battery.read.return_value = BatteryReading(50,0,0,
            measurements={'inverter_ac':Measurement(6000, NOW)}, power_supply=PowerSupplyReading('backup', NOW))
        case.box.read.return_value = requirements.wallbox(watts=2000, status='charging', enabled=True)
        case.app.tick(NOW, 0)
        live = case.app.snapshot(NOW)['live']
        assert (live['house_total'], live['car'], live['heat'], live['house']) == (6000, 2000, 1000, 3000)
        assert case.app.history.read(NOW)[-1]['house'] == 3000
        case.battery.read.return_value = replace(case.battery.read.return_value,
                                                power_supply=PowerSupplyReading('grid', NOW))
        case.app.tick(NOW, 5)
        # Back on grid: the measured house sensor is the fallback/check, the AC balance the total.
        live = case.app.snapshot(NOW)['live']
        assert live['house_total_measured'] == 4000 and live['house_total'] == 7000
    finally:
        case.doCleanups()


def test_multiple_fronius_inverters_provide_combined_ac_when_grid_meter_is_down():
    from test_fronius_site import site
    from test_power_supply import api
    with site() as (driver, primary, _, _), patch(
        'custom_components.eos_energiezentrale.energy._fronius_backup.request', return_value=api(True)):
        primary.meters.clear()
        sample = driver.read({}, NOW)
        assert sample.measurements['inverter_ac'].value == 1700
        options, rows, _ = resolve_sources({'house_entity':'sensor.offline'}, {}, ((driver,sample),), NOW)
        assert rows[options['house_entity']]['state'] == 1700


def test_device_list_requires_ac_from_every_configured_inverter():
    from custom_components.eos_energiezentrale.energy.devices import DeviceSite
    from test_devices import primary
    from test_fronius_modbus import inverter
    from test_fronius_site import pv_only, ac
    from test_power_supply import api
    with inverter() as (_, main), inverter() as (_, roof), patch(
        'custom_components.eos_energiezentrale.energy._fronius_backup.request', return_value=api(True)):
        pv_only(roof)
        main.meters.clear()
        devices = DeviceSite(None, [primary(main), {'id':'roof','name':'Roof','kind':'inverter',
            'plugin':'fronius_modbus','parameters':{'host':'127.0.0.1','port':roof.server_address[1]}}])
        sample = devices.read({}, NOW)
        assert sample.measurements['inverter_ac'].value == 1700
        options, rows, _ = resolve_sources({'house_entity':''}, {}, ((devices,sample),), NOW)
        assert rows[options['house_entity']]['state'] == 1700
        ac(roof, float('nan'))
        sample = devices.read({}, NOW)
        assert sample.measurements['inverter_ac'].value is None
        options, rows, _ = resolve_sources({'house_entity':''}, {}, ((devices,sample),), NOW)
        assert rows[options['house_entity']]['state'] is None

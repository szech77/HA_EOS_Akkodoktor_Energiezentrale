"""Source precedence, freshness, UI diagnostics and actual controller use."""
from datetime import timedelta
from types import SimpleNamespace

import pytest

from custom_components.eos_energiezentrale.const import DEFAULTS
from custom_components.eos_energiezentrale.energy.contracts import Measurement, BatteryReading, PluginContractError
from custom_components.eos_energiezentrale.energy.measurement_sources import resolve_sources, checked_measurements
from custom_components.eos_energiezentrale.energy.plugin_registry import PluginFactory, describe, validate_class
from custom_components.eos_energiezentrale.energy.plugins.fronius import Fronius
from test_energy import NOW
import test_requirements as requirements
from test_requirements import state


def provider(keys=('grid',)):
    return SimpleNamespace(measurement_keys=keys,info=SimpleNamespace(name='Test plugin'))


def test_sensor_priority_including_failed_sensor_and_no_mutation():
    opts={**DEFAULTS,'grid_entity':'sensor.grid'}
    sample=BatteryReading(50,0,0,measurements={'grid':Measurement(-1000,NOW)})
    for rows,expected in (({'sensor.grid':state(1500)},1500),({},None)):
        effective,values,report=resolve_sources(opts,rows,((provider(),sample),),NOW)
        assert report['sources']['grid']['source']['type']=='sensor'
        assert values.get('@plugin:grid') is None
        assert values.get('sensor.grid',{}).get('state')==('1500' if expected else None)
        assert opts['grid_entity']=='sensor.grid'


def test_empty_sensor_uses_declared_plugin_with_timestamp_and_no_stored_changes():
    opts={**DEFAULTS,'grid_entity':''}
    sample=BatteryReading(50,0,0,measurements={'grid':Measurement(-1000,NOW)})
    effective,rows,report=resolve_sources(opts,{},((provider(),sample),),NOW)
    assert effective['grid_entity']=='@plugin:grid'
    assert rows['@plugin:grid']['state']==-1000
    assert rows['@plugin:grid']['last_reported']==NOW.isoformat()
    assert report['sources']['grid']=={'source':{'type':'plugin','name':'Test plugin'},'available':True}
    assert opts['grid_entity']==''


def test_missing_configuration_is_distinct_from_a_temporarily_unavailable_provider():
    opts={**DEFAULTS,'grid_entity':''}
    _,_,report=resolve_sources(opts,{},(),NOW)
    assert 'grid' in report['missing'] and 'grid' not in report['unavailable']
    _,_,report=resolve_sources(opts,{},((provider(),BatteryReading(50,0,0)),),NOW)
    assert 'grid' not in report['missing'] and 'grid' in report['unavailable']


def test_absent_sensor_keys_are_normalized_to_empty_configuration():
    effective,_,report=resolve_sources({'wallbox_type':'none'}, {}, (), NOW)
    assert effective['grid_entity']==effective['pv_entity']==''
    assert report['missing']==['grid','house_total','price','solar']


@pytest.mark.parametrize('sample',[NOW-timedelta(seconds=45),NOW+timedelta(seconds=1),None])
def test_stale_future_and_missing_timestamps_do_not_become_valid_grid_readings(sample):
    result=checked_measurements({'grid':Measurement(1000,sample)},('grid',),NOW)
    assert result['grid']==Measurement(None,None)


def test_api_validates_declared_keys_and_preserves_existing_plugin_api():
    class Source(Fronius):
        measurement_keys=Fronius.measurement_keys+('grid',)
        def _read(self,states,now):
            return BatteryReading(50,0,0,now,now,now,{'grid':Measurement(-1000,now)})
    plugin=PluginFactory(Source)(None,{})
    assert plugin.read({},NOW).measurements['grid'].value==-1000
    assert 'grid' in describe(plugin)['measurements']
    with pytest.raises(PluginContractError):
        checked_measurements({'price':Measurement(30,NOW)},('grid',),NOW)
    class Invalid(Source): measurement_keys=('invalid',)
    with pytest.raises(PluginContractError): validate_class(Invalid)


def test_generic_values_and_normalized_percent_scales():
    keys=('solar','house_total','price','heat','heat_load','car_soc')
    opts={**DEFAULTS,**dict.fromkeys(('pv_entity','house_entity','price_entity','heat_entity','heat_load_entity','car_soc_entity'),'')}
    sample=BatteryReading(50,0,0,measurements={key:Measurement(50,NOW) for key in keys})
    effective,rows,report=resolve_sources(opts,{},((provider(keys),sample),),NOW)
    assert effective['car_soc_scale']==effective['heat_load_scale']=='percent'
    assert all(report['sources'][key]['source']['type']=='plugin' for key in keys)
    assert rows['@plugin:price']['attributes']['unit_of_measurement']=='ct/kWh'


def test_controller_uses_plugin_grid_for_live_data_and_reports_missing_source():
    fixture=requirements.ControllerRequirements();fixture.setUp()
    try:
        fixture.config.options['grid_entity']=''
        fixture.battery.measurement_keys=('grid',)
        fixture.battery.info=SimpleNamespace(name='Test battery')
        fixture.battery.read.return_value=BatteryReading(50,0,0,measurements={'grid':Measurement(-2345,NOW)})
        fixture.app.tick(NOW,0)
        assert fixture.app.live['grid']==-2345
        snapshot=fixture.app.snapshot(NOW)
        assert snapshot['source_configuration']['sources']['grid']['source']['type']=='plugin'
        fixture.battery.measurement_keys=()
        fixture.app.tick(NOW+timedelta(seconds=20),20)
        assert fixture.app.live['grid'] is None
        assert 'grid' in fixture.app.snapshot(NOW)['source_configuration']['missing']
    finally:
        fixture.doCleanups()


def test_virtual_fleet_reservations_are_not_overwritten_by_raw_plugin_values():
    opts={**DEFAULTS,'grid_entity':''}
    sample=BatteryReading(50,0,0,measurements={'grid':Measurement(-6000,NOW)})
    effective,rows,_=resolve_sources(opts,{},((provider(),sample),),NOW)
    rows[effective['grid_entity']]['state']=-3000  # First car reserves 3000 W.
    _,next_rows,_=resolve_sources(opts,rows,((provider(),sample),),NOW)
    assert next_rows[effective['grid_entity']]['state']==-3000

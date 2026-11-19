"""A battery-only installation must not depend on an EOS vehicle resource."""
from datetime import timedelta
from unittest.mock import Mock

import pytest

from custom_components.eos_energiezentrale.const import DEFAULTS
from custom_components.eos_energiezentrale.energy.controller import Controller
from custom_components.eos_energiezentrale.energy.contracts import BatteryReading
from custom_components.eos_energiezentrale.energy.settings import Configuration
from custom_components.eos_energiezentrale.validation import validate_options
from test_energy import NOW, instruction, temporary_project_directory
from test_requirements import OPTIONS, ControllerRequirements


@pytest.mark.parametrize('resource',['',None,'battery1','ev1'])
def test_no_vehicle_accepts_empty_missing_or_unused_legacy_resource(resource):
    options={**DEFAULTS,**OPTIONS,'wallbox_type':'none','car_soc_entity':''}
    if resource is None: options.pop('vehicle_resource')
    else: options['vehicle_resource']=resource
    validate_options(options)
    with temporary_project_directory() as directory:
        config=Configuration(options,Mock(),directory)
        assert config.wallbox.ids=={}
        assert config.options['vehicle_resource']==(resource or '')


@pytest.mark.parametrize('resource',['',None,'battery1','invalid/resource'])
def test_configured_vehicle_still_requires_its_own_valid_resource(resource):
    options={**DEFAULTS,**OPTIONS}
    if resource is None: options.pop('vehicle_resource')
    else: options['vehicle_resource']=resource
    with pytest.raises(ValueError): validate_options(options)
    with temporary_project_directory() as directory:
        with pytest.raises(ValueError): Configuration(options,Mock(),directory)


@pytest.mark.parametrize('resource',['','battery1'])
def test_battery_and_heat_continue_without_vehicle_plan_sync_or_soc_publication(resource):
    options={**DEFAULTS,**OPTIONS,'wallbox_type':'none','car_soc_entity':'','vehicle_resource':resource}
    with temporary_project_directory() as directory:
        ha=Mock();config=Configuration(options,ha,directory)
        config.battery=Mock();config.eos=Mock()
        config.eos.solution.return_value={}
        app=Controller(ha,config)
        app.set_armed(True);app.restore_pending=True
        # Even an old saved EV schedule cannot cause an EV request after removal.
        config.update({'schedule':'once','departure':(NOW+timedelta(hours=5)).isoformat()})
        for seconds in (0,30,360):
            now=NOW+timedelta(seconds=seconds)
            config.battery.read.return_value=BatteryReading(50,0,0,now,now,now)
            # Consistent sources: 4000 W PV cover the 4000 W site consumption.
            ha.states.return_value={**ControllerRequirements.states(when=now),'sensor.pv':ControllerRequirements.states(when=now)['sensor.house']}
            config.eos.plan.return_value={'generated_at':now.isoformat(),'instructions':[instruction(now)]}
            app.tick(now,seconds)
            snapshot=app.snapshot(now)
            assert app.eos_resources()=={'battery1'}
            assert snapshot['features']=={'car':False,'heat':True}
            assert not snapshot['control_waiting']
            assert snapshot['plan']['battery'] and snapshot['plan']['car']==[]
            assert snapshot['live']['heat']==1000 and snapshot['live']['house']==3000
            assert snapshot['vehicle_planning'] is None and not snapshot['errors']
            assert not app.sync_goal(now,seconds,NOW+timedelta(hours=5))
            assert not app.vehicle_plan_ready(now)
        assert config.battery.apply.call_count==3
        config.eos.set_vehicle_goal.assert_not_called()
        config.eos.set_vehicle_charging_limits.assert_not_called()
        ha.publish_soc.assert_not_called()

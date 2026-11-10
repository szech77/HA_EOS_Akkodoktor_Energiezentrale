"""Behavior at HA boundaries, using HA's real state machine and service registry."""
import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from threading import RLock
from types import MappingProxyType, SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.config_entries import ConfigEntry, ConfigEntries, ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import Unauthorized

from custom_components.eos_energiezentrale import async_setup_entry, async_unload_entry
from custom_components.eos_energiezentrale.adapter import HomeAssistantAdapter
from custom_components.eos_energiezentrale.config_flow import ConfigFlow, OptionsFlow, check
from custom_components.eos_energiezentrale.const import DEFAULTS, DOMAIN, GROUPS
from custom_components.eos_energiezentrale.coordinator import EnergyCoordinator
from custom_components.eos_energiezentrale.diagnostics import async_get_config_entry_diagnostics
from custom_components.eos_energiezentrale.frontend import websocket_request
from custom_components.eos_energiezentrale.sensor import EnergySensor
from custom_components.eos_energiezentrale.switch import EnergySwitch
from custom_components.eos_energiezentrale.energy.settings import daily_settings
from custom_components.eos_energiezentrale.energy.settings import Configuration
from custom_components.eos_energiezentrale.energy.controller import Controller
from custom_components.eos_energiezentrale.number import EnergyNumber
from custom_components.eos_energiezentrale.select import ScheduleSelect
from custom_components.eos_energiezentrale.text import EnergyText
from custom_components.eos_energiezentrale.binary_sensor import EnergyBinarySensor
from custom_components.eos_energiezentrale.validation import validate_options
from test_energy import temporary_project_directory


class HomeAssistantRequirements(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory_context = temporary_project_directory()
        self.directory = self.directory_context.__enter__()
        self.hass = HomeAssistant(str(self.directory))
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.entry = ConfigEntry(domain=DOMAIN, data=dict(DEFAULTS), options={}, version=1,
            minor_version=1, source="user", title="Energy", unique_id=DOMAIN,
            discovery_keys=MappingProxyType({}), subentries_data=[])
        await self.hass.config_entries.async_initialize()
        with patch.object(self.hass.config_entries, "async_setup", new_callable=AsyncMock):
            await self.hass.config_entries.async_add(self.entry)

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.directory_context.__exit__(None, None, None)

    def controller(self):
        app = Mock(lock=RLock(), armed=False, owned=False)
        app.config.daily = daily_settings({}, 20)
        app.config.options = dict(DEFAULTS)
        app.errors = {}
        app.snapshot.side_effect = lambda _: {"armed": app.armed, "live": {}, "errors": dict(app.errors),
                                             "settings": dict(app.config.daily)}
        self.entry.runtime_data = EnergyCoordinator(self.hass, self.entry, app)
        return self.entry.runtime_data, app

    async def test_slow_history_database_does_not_block_control_changes(self):
        from threading import Event
        coordinator, app = self.controller()
        started, finish = Event(), Event()
        def delayed_history(_config):
            started.set()
            if not finish.wait(5):
                raise TimeoutError("test did not release history request")
            return [{"solar": 123}]
        app.history.read.return_value = []
        with patch("custom_components.eos_energiezentrale.coordinator.influx_series", side_effect=delayed_history):
            history = asyncio.create_task(coordinator.async_history())
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                await asyncio.wait_for(coordinator.async_change(enabled=True), timeout=2)
                app.set_armed.assert_called_once_with(True)
            finally:
                finish.set()
            self.assertEqual((await history)["influx"], [{"solar": 123}])

    async def test_slow_eos_plan_does_not_block_control_or_local_measurements(self):
        from threading import Event
        started, finish = Event(), Event()
        adapter = Mock()
        adapter.states.return_value = {}
        config = Configuration({**DEFAULTS, "wallbox_type": "none"}, adapter, self.directory)
        config.eos = Mock()
        config.eos.solution.return_value = {}

        def delayed_plan():
            started.set()
            if not finish.wait(5):
                raise TimeoutError("test did not release EOS plan request")
            raise OSError("offline")

        config.eos.plan.side_effect = delayed_plan
        app = Controller(adapter, config)
        coordinator = EnergyCoordinator(self.hass, self.entry, app)
        try:
            result = await asyncio.wait_for(coordinator._async_update_data(), timeout=2)
            self.assertIn("time", result["live"])
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            await asyncio.wait_for(coordinator.async_change(enabled=True), timeout=2)
            self.assertTrue(app.armed)
            self.assertTrue(app.restore_pending)
            self.assertIsNone(app.order_for("battery1", datetime.now(timezone.utc)))
        finally:
            finish.set()
        await asyncio.wait_for(coordinator.eos_poll_tasks["plan"], timeout=3)
        self.assertIn("eos", app.errors)

    async def test_reporting_storage_error_never_disables_device_control(self):
        coordinator, app = self.controller()
        app.armed = True
        coordinator.accounting = Mock()
        coordinator.accounting.observe.side_effect = OSError("disk full")
        result = await coordinator._async_update_data()
        self.assertTrue(result["armed"])
        self.assertIn("accounting",result["errors"])
        app.release.assert_not_called()
        app.remember_control.assert_not_called()

    async def test_slow_accounting_refresh_does_not_block_control_or_apply_stale_settings(self):
        from threading import Event
        from zoneinfo import ZoneInfo
        from custom_components.eos_energiezentrale.energy.accounting import Accounting

        coordinator, app = self.controller()
        coordinator.accounting = Accounting(self.directory, ZoneInfo("Europe/Berlin"))
        started, finish = Event(), Event()

        def delayed_tariff(_now):
            started.set()
            if not finish.wait(5):
                raise TimeoutError("test did not release EOS accounting request")
            return {"constant_ct": 8.2}

        app.config.eos.feedin_accounting.side_effect = delayed_tariff
        app.config.eos.battery_accounting.return_value = {
            "capacity_wh": 11000, "charge_efficiency": .95, "discharge_efficiency": .95}
        try:
            await coordinator._async_update_data()
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            await asyncio.wait_for(coordinator.async_change(enabled=True), timeout=2)
            await asyncio.wait_for(coordinator.async_accounting({"settings": {"pv_price_source": "manual", "pv_price_ct": 12}}), timeout=2)
            self.assertEqual(coordinator.accounting.pv_price(), 12)
        finally:
            finish.set()
        await asyncio.wait_for(coordinator.accounting_refresh_task, timeout=3)
        self.assertIsNone(coordinator.accounting.pv_tariff)
        self.assertEqual(coordinator.accounting.pv_price(), 12)

    async def test_accounting_refresh_applies_valid_eos_results_after_control_tick(self):
        from zoneinfo import ZoneInfo
        from custom_components.eos_energiezentrale.energy.accounting import Accounting

        coordinator, app = self.controller()
        coordinator.accounting = Accounting(self.directory, ZoneInfo("Europe/Berlin"))
        app.config.eos.feedin_accounting.return_value = {"constant_ct": 8.2}
        app.config.eos.battery_accounting.return_value = {
            "capacity_wh": 11000, "charge_efficiency": .95, "discharge_efficiency": .95}
        await coordinator._async_update_data()
        await asyncio.wait_for(coordinator.accounting_refresh_task, timeout=3)
        self.assertEqual(coordinator.accounting.pv_price(), 8.2)
        self.assertEqual(coordinator.accounting.effective()["capacity_wh"], 11000)

    async def test_shutdown_does_not_wait_for_slow_accounting_request(self):
        from threading import Event
        from zoneinfo import ZoneInfo
        from custom_components.eos_energiezentrale.energy.accounting import Accounting

        coordinator, app = self.controller()
        coordinator.accounting = Accounting(self.directory, ZoneInfo("Europe/Berlin"))
        started, finish = Event(), Event()

        def delayed_tariff(_now):
            started.set()
            if not finish.wait(5):
                raise TimeoutError("test did not release EOS request")
            return {"constant_ct": 8.2}

        app.config.eos.feedin_accounting.side_effect = delayed_tariff
        try:
            await coordinator._async_update_data()
            self.assertTrue(await asyncio.to_thread(started.wait, 2))
            await asyncio.wait_for(coordinator.async_stop(), timeout=2)
            self.assertTrue(coordinator.closing)
            self.assertIsNone(coordinator.accounting.pv_tariff)
        finally:
            finish.set()

    async def test_cost_settings_are_persisted_and_reported_via_authenticated_api(self):
        from zoneinfo import ZoneInfo
        coordinator, app = self.controller()
        app.config.directory = self.directory
        app.config.zone = ZoneInfo("Europe/Berlin")
        app.config.influx.url = None
        app.controllers = []
        await coordinator.async_accounting({"settings":{"pv_price_ct":8,"efficiency_source":"manual"}})
        report = await coordinator.async_accounting({"period":"month","date":"2026-11-09"})
        self.assertEqual(report["settings"]["pv_price_ct"],8)
        self.assertEqual(report["date"],"2026-11-01")
        self.assertEqual(report["consumers"],{})
        with self.assertRaises(ValueError):
            await coordinator.async_accounting({"settings":{"charge_efficiency":0}})

    async def test_first_setup_routes_from_sensor_selection_to_plugin_selection(self):
        flow=ConfigFlow();flow.hass=self.hass
        flow.values={**DEFAULTS,'wallbox_type':'none','heat_entity':'','car_soc_entity':''}
        result=await flow.async_step_sensors({key:flow.values[key] for key in ('pv_entity','house_entity','grid_entity','heat_entity','price_entity','car_soc_entity','car_soc_scale')})
        self.assertEqual(result['step_id'],'hardware')
        self.assertEqual({str(key) for key in result['data_schema'].schema},{'battery_type','wallbox_type','vehicle_name'})
        params=await flow.async_step_hardware({'battery_type':'fronius','wallbox_type':'none','vehicle_name':'E-Auto'})
        self.assertEqual(params['step_id'],'hardware_parameters')
        following=await flow.async_step_hardware_parameters({'battery_parameters':{}})
        self.assertEqual(following['step_id'],'limits')

    async def test_plugin_selection_builds_battery_and_wallbox_fields_from_their_schemas(self):
        flow=OptionsFlow();flow.hass=self.hass;flow.handler=self.entry.entry_id;flow.context={"entry_id":self.entry.entry_id}
        selected=await flow.async_step_hardware({"battery_type":"generic","wallbox_type":"generic","vehicle_name":"E-Auto"})
        self.assertEqual(selected["step_id"],"hardware_parameters")
        schema={str(key):value for key,value in selected["data_schema"].schema.items()}
        battery_fields=schema['battery_parameters'].serialize()['selector']['object']['fields']
        wallbox_fields=schema['wallbox_parameters'].serialize()['selector']['object']['fields']
        self.assertIn('soc_scale',battery_fields)
        self.assertIn('phase_switching',wallbox_fields)
        self.assertIn('input_boolean',wallbox_fields['enable']['selector']['entity']['domain'])
        battery={"soc":"sensor.soc","charge_power":"sensor.charge","discharge_power":"sensor.discharge",
                 "mode":"input_select.battery","charge_limit":"input_number.charge","discharge_limit":"input_number.discharge"}
        from test_plugins import generic_wallbox
        wallbox,_=generic_wallbox()
        result=await flow.async_step_hardware_parameters({"battery_parameters":battery,"wallbox_parameters":wallbox})
        self.assertEqual(result['type'],'create_entry')
        self.assertEqual(result['data']['battery_type'],'generic')
        self.assertFalse(json.loads(result['data']['wallbox_parameters'])['phase_switching'])

    async def test_common_battery_form_does_not_edit_hidden_wallboxes_in_a_fleet(self):
        from test_fleet import definitions
        self.hass.config_entries.async_update_entry(self.entry,options={"vehicles":json.dumps(definitions())})
        flow=OptionsFlow();flow.hass=self.hass;flow.handler=self.entry.entry_id;flow.context={"entry_id":self.entry.entry_id}
        result=await flow.async_step_hardware()
        self.assertEqual({str(key) for key in result['data_schema'].schema},{'battery_type'})
        result=await flow.async_step_hardware({'battery_type':'fronius'})
        self.assertEqual({str(key) for key in result['data_schema'].schema},{'battery_parameters'})
        result=await flow.async_step_hardware_parameters({'battery_parameters':{}})
        self.assertEqual(json.loads(result['data']['vehicles']),definitions())

    async def test_wallbox_add_wizard_uses_selected_plugin_and_preserves_first_vehicle(self):
        flow=OptionsFlow();flow.hass=self.hass;flow.handler=self.entry.entry_id;flow.context={"entry_id":self.entry.entry_id}
        choice=await flow.async_step_vehicle_add()
        self.assertEqual(choice['step_id'],'vehicle_plugin')
        selected=await flow.async_step_vehicle_plugin({'wallbox_type':'generic'})
        self.assertEqual(selected['step_id'],'vehicle_parameters')
        from test_plugins import generic_wallbox
        params,_=generic_wallbox()
        result=await flow.async_step_vehicle_parameters({'id':'second','name':'Second EV','resource':'ev2','soc_entity':'sensor.ev2_soc',
            'soc_scale':'factor','capacity_wh':60000,'charging_efficiency':.9,'max_current_a':16,'wallbox_parameters':params})
        self.assertEqual(result['type'],'create_entry')
        stored=json.loads(result['data']['vehicles'])
        self.assertEqual(len(stored),2)
        self.assertEqual(stored[0]['wallbox_type'],'nrgkick')
        self.assertEqual(stored[1]['wallbox_type'],'generic')

    async def test_generic_helpers_use_only_the_matching_home_assistant_services(self):
        seen=[]
        async def record(call):seen.append((call.domain,call.service,dict(call.data)))
        for domain,service in (('input_number','set_value'),('input_boolean','turn_on'),('input_select','select_option')):
            self.hass.services.async_register(domain,service,record)
        adapter=HomeAssistantAdapter(self.hass)
        for entity,value in (('input_number.current',6.2),('input_boolean.charging',True),('input_select.mode','limits')):
            await self.hass.async_add_executor_job(adapter.set,entity,value)
        self.assertEqual([(domain,service) for domain,service,_ in seen],[('input_number','set_value'),('input_boolean','turn_on'),('input_select','select_option')])
        self.assertEqual(seen[0][2]['value'],6.2)
        with self.assertRaises(ValueError):await self.hass.async_add_executor_job(adapter.set,'script.unrestricted',True)

    async def test_driver_service_uses_native_registry_and_preserves_tenths(self):
        seen = []
        async def handle(call):
            seen.append(dict(call.data))
            self.hass.states.async_set("number.charger", call.data["value"])
        self.hass.services.async_register("number", "set_value", handle)
        adapter = HomeAssistantAdapter(self.hass)
        await self.hass.async_add_executor_job(adapter.set, "number.charger", 6.2)
        value = await self.hass.async_add_executor_job(adapter.state, "number.charger")
        self.assertEqual(seen, [{"entity_id": "number.charger", "value": 6.2}])
        self.assertEqual(value["state"], "6.2")
        self.assertIn("last_reported", value)

    async def test_driver_cannot_call_unrelated_services_or_nonfinite_current(self):
        adapter = HomeAssistantAdapter(self.hass)
        for entity, value in (("homeassistant.restart", True), ("sensor.read_only", 1),
                              ("number.current", float("nan")), ("number.current", True)):
            with self.subTest(entity=entity, value=value):
                with self.assertRaises(ValueError):
                    await self.hass.async_add_executor_job(adapter.set, entity, value)

    async def test_controller_failure_disarms_and_attempts_device_release(self):
        coordinator, app = self.controller()
        app.armed = app.owned = True
        app.tick.side_effect = OSError("connection lost")
        result = await coordinator._async_update_data()
        self.assertFalse(result["armed"])
        self.assertIn("runtime", result["errors"])
        app.release.assert_called_once()

    async def test_failure_survives_read_only_polls_with_actionable_confirmation_context(self):
        from custom_components.eos_energiezentrale.energy.drivers import DeviceConfirmationError
        ha=Mock()
        config=Configuration(dict(DEFAULTS),ha,self.directory)
        app=Controller(ha,config)
        app.set_armed(True)
        app.control_step="battery_control"
        app.tick=Mock(side_effect=DeviceConfirmationError("number.battery_limit"))
        coordinator=EnergyCoordinator(self.hass,self.entry,app)
        self.entry.runtime_data=coordinator
        with self.assertLogs("custom_components.eos_energiezentrale.coordinator",level="ERROR"):
            await coordinator._async_update_data()
        app.tick.side_effect=None
        result=await coordinator._async_update_data()
        self.assertFalse(result["armed"])
        self.assertEqual(result["errors"]["runtime"],"DeviceConfirmationError")
        coordinator.async_set_updated_data(result)
        diagnostic=await async_get_config_entry_diagnostics(self.hass,self.entry)
        self.assertEqual(diagnostic["last_failure"]["entity"],"number.battery_limit")
        self.assertEqual(diagnostic["last_failure"]["step"],"battery_control")
        app.set_armed(True)
        self.assertNotIn("runtime",app.errors)

    async def test_pending_mode_values_keep_control_enabled_and_resume_on_next_poll(self):
        from custom_components.eos_energiezentrale.energy.drivers import DeviceNotReady
        coordinator,app=self.controller()
        app.armed=app.owned=True
        app.tick.side_effect=DeviceNotReady("number.pv_limit")
        result=await coordinator._async_update_data()
        self.assertTrue(result["armed"])
        self.assertIn("device_pending",result["errors"])
        app.remember_control.assert_not_called()
        app.release.assert_not_called()
        app.tick.side_effect=None
        result=await coordinator._async_update_data()
        self.assertTrue(result["armed"])
        self.assertNotIn("device_pending",result["errors"])

    async def test_control_and_meter_poll_never_overlap_in_worker(self):
        coordinator, app = self.controller()
        entered = asyncio.Event()
        release = asyncio.Event()
        async def delayed(job, *args):
            if job == coordinator._tick:
                entered.set()
                await release.wait()
                return {"live": {}}
            return job(*args)
        with patch.object(self.hass, "async_add_executor_job", side_effect=delayed):
            polling = asyncio.create_task(coordinator._async_update_data())
            await entered.wait()
            changing = asyncio.create_task(coordinator.async_change(enabled=True))
            await asyncio.sleep(0)
            app.set_armed.assert_not_called()
            release.set()
            await asyncio.gather(polling, changing)
        app.set_armed.assert_called_once_with(True)

    async def test_invalid_daily_setting_does_not_persist_or_arm(self):
        coordinator, app = self.controller()
        for values in ({"target_soc": 101}, {"fast": "true"}, {"eos_url": "http://other"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                await coordinator.async_change(settings=values)
        app.config.update.assert_not_called()
        app.set_armed.assert_not_called()

    async def test_unload_releases_devices_before_removing_platforms(self):
        coordinator, app = self.controller()
        events = []
        app.set_armed.side_effect = lambda enabled, **kwargs: events.append(("control", enabled))
        async def unload(*_):
            events.append(("unload", True))
            return True
        with (patch.object(self.hass.config_entries, "async_unload_platforms", side_effect=unload),
              patch("custom_components.eos_energiezentrale.async_remove_panel")):
            self.assertTrue(await async_unload_entry(self.hass, self.entry))
        self.assertEqual(events, [("control", False), ("unload", True)])
        with self.assertRaises(ValueError):
            await coordinator.async_change(enabled=True)

    async def test_unconfirmed_release_keeps_entities_available_for_retry(self):
        coordinator, app = self.controller()
        app.set_armed.side_effect = OSError("device unavailable")
        with patch.object(self.hass.config_entries, "async_unload_platforms", new_callable=AsyncMock) as unload:
            self.assertFalse(await async_unload_entry(self.hass, self.entry))
            unload.assert_not_called()
        self.assertFalse(coordinator.closing)
        app.set_armed.side_effect = None
        await coordinator.async_change(enabled=False)

    async def test_native_sensor_converts_power_and_estimated_soc_consistently(self):
        coordinator, _ = self.controller()
        coordinator.async_set_updated_data({"live": {"car": 6443.378, "car_soc": 32.5,
                                                     "soc_source": "estimate"}})
        power = EnergySensor(coordinator, "car")
        self.assertEqual(power.native_unit_of_measurement, "kW")
        self.assertAlmostEqual(power.native_value, 6.443378)
        soc = EnergySensor(coordinator, "car_soc_factor")
        self.assertEqual(soc.native_value, .325)
        self.assertEqual(soc.extra_state_attributes, {"source": "estimate"})
        self.assertIsNone(EnergySensor(coordinator, "solar").native_value)

    async def test_mode_and_status_sensors_publish_text_through_ha_state_machine(self):
        coordinator, _ = self.controller()
        readings = {"battery_mode": "NON_EXPORT", "car_mode": "IDLE", "car_status": "connected"}
        coordinator.async_set_updated_data({"live": readings})
        for key, value in readings.items():
            with self.subTest(key=key):
                entity = EnergySensor(coordinator, key)
                entity.hass = self.hass
                entity.entity_id = "sensor.regression_" + key
                entity.platform_data = SimpleNamespace(platform_name=DOMAIN, domain="sensor",
                                                       default_language_platform_translations={})
                self.hass.states.async_set(entity.entity_id, entity.state)
                self.assertEqual(self.hass.states.get(entity.entity_id).state, value)

    async def test_language_failures_are_not_mislabeled_as_invalid_settings(self):
        self.controller()
        for failure,code in ((ValueError("broken JSON"),'language_invalid'),(FileNotFoundError("missing file"),'language_unavailable')):
            with self.subTest(code=code),patch('custom_components.eos_energiezentrale.frontend.load_language',side_effect=failure):
                connection=await self.invoke({'action':'language','language':'de'})
                self.assertEqual(connection.send_error.call_args.args[1],code)
                self.assertNotIn('missing file',connection.send_error.call_args.args[2])

    async def test_unexpected_ui_backend_failure_returns_an_error_instead_of_timing_out(self):
        coordinator,_=self.controller()
        coordinator.async_history=AsyncMock(side_effect=RuntimeError('private backend detail'))
        connection=await self.invoke({'action':'history'})
        self.assertEqual(connection.send_error.call_args.args[1],'internal_error')
        self.assertNotIn('private backend detail',connection.send_error.call_args.args[2])

    async def test_frontend_registration_uses_one_asset_version_for_panel_and_iframe(self):
        from custom_components.eos_energiezentrale.frontend import async_register_frontend
        self.hass.http=Mock(async_register_static_paths=AsyncMock())
        with patch('custom_components.eos_energiezentrale.frontend.asset_version',return_value='newbuild'),patch('custom_components.eos_energiezentrale.frontend.panel_custom.async_register_panel',new_callable=AsyncMock) as register,patch('custom_components.eos_energiezentrale.frontend.websocket_api.async_register_command'),patch('custom_components.eos_energiezentrale.frontend.frontend.add_extra_js_url') as add_icons:
            await async_register_frontend(self.hass)
        self.assertTrue(register.call_args.kwargs['module_url'].endswith('panel.js?v=newbuild'))
        self.assertEqual(register.call_args.kwargs['config']['asset_version'],'newbuild')
        self.assertEqual(register.call_args.kwargs['sidebar_icon'],'eos-energy:logo')
        add_icons.assert_called_once_with(self.hass,'/eos-energiezentrale-static/icons.js?v=newbuild')

    async def test_language_request_loads_translations_without_blocking_event_loop(self):
        self.controller()
        from custom_components.eos_energiezentrale.energy.localization import load_language
        def checked_load(*args, **kwargs):
            with self.assertRaises(RuntimeError):
                asyncio.get_running_loop()
            return load_language(*args, **kwargs)
        with patch("custom_components.eos_energiezentrale.frontend.load_language", side_effect=checked_load):
            connection = await self.invoke({"action": "language", "language": "de"})
        connection.send_error.assert_not_called()
        self.assertEqual(connection.send_result.call_args.args[1]["locale"], "de-DE")

    async def test_websocket_waits_for_delayed_language_response(self):
        from threading import Event
        from custom_components.eos_energiezentrale.energy.localization import load_language

        self.controller()
        started, finish = Event(), Event()

        def delayed_load(*args, **kwargs):
            started.set()
            if not finish.wait(5):
                raise TimeoutError("test did not release language request")
            return load_language(*args, **kwargs)

        with patch("custom_components.eos_energiezentrale.frontend.load_language", side_effect=delayed_load):
            request = asyncio.create_task(self.invoke({"action": "language", "language": "de"}))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 2))
                self.assertFalse(request.done())
            finally:
                finish.set()
            connection = await request
        connection.send_error.assert_not_called()
        self.assertEqual(connection.send_result.call_args.args[1]["locale"], "de-DE")

    async def test_first_setup_starts_without_control_permission(self):
        # Real config, SQLite cache and drivers, while external APIs remain offline.
        self.entry._async_set_state(self.hass, ConfigEntryState.SETUP_IN_PROGRESS, None)
        with (patch("custom_components.eos_energiezentrale.energy.clients.request", side_effect=OSError("offline")),
              patch.object(self.hass.config_entries, "async_forward_entry_setups", new_callable=AsyncMock),
              patch("custom_components.eos_energiezentrale.async_register_frontend", new_callable=AsyncMock)):
            self.assertTrue(await async_setup_entry(self.hass, self.entry))
            coordinator = self.entry.runtime_data
            await asyncio.gather(*coordinator.eos_poll_tasks.values())
            coordinator.async_set_updated_data(await coordinator._async_update_data())
        coordinator = self.entry.runtime_data
        self.assertFalse(coordinator.app.armed)
        self.assertFalse(coordinator.app.owned)
        self.assertIn("eos", coordinator.data["errors"])
        with patch.object(self.hass.config_entries, "async_unload_platforms", new_callable=AsyncMock, return_value=True), patch("custom_components.eos_energiezentrale.async_remove_panel"):
            self.assertTrue(await async_unload_entry(self.hass, self.entry))
        # Dispose scheduled callbacks in this direct lifecycle harness.
        await self.entry._async_process_on_unload(self.hass)

    async def test_new_installation_has_no_optional_consumers_and_accepts_empty_sources(self):
        from custom_components.eos_energiezentrale.config_flow import schema_for
        flow=ConfigFlow()
        self.assertEqual(flow.values["wallbox_type"],"none")
        self.assertEqual(flow.values["heat_entity"],"")
        validate_options(flow.values)
        config=Configuration(flow.values,Mock(),self.directory)
        self.assertEqual(config.wallbox.ids,{})
        fields=schema_for("sensors",flow.values)
        submitted={key:flow.values[key] for key in GROUPS["sensors"]
                   if key not in {"heat_entity","car_soc_entity","heat_load_entity"}}
        fields(submitted)

    async def test_config_wizard_preserves_selected_hardware_and_limits(self):
        flow = ConfigFlow()
        flow.hass = self.hass
        flow.context = {"source": "user"}
        with (patch("custom_components.eos_energiezentrale.config_flow.request", return_value={}),
              patch.object(flow, "_async_current_entries", return_value=[])):
            result = await flow.async_step_user({k: DEFAULTS[k] for k in GROUPS["connection"]})
        self.assertEqual(result["step_id"], "sensors")
        for group in ("sensors", "hardware", "limits", "history"):
            values = {k: DEFAULTS[k] for k in GROUPS[group]}
            if group == "limits":
                values["phase_wait_s"] = 90
            result = await getattr(flow, "async_step_" + group)(values)
        self.assertEqual(result["data"]["phase_wait_s"], 90)
        self.assertEqual(result["data"]["car_soc_scale"], "factor")

    async def test_invalid_urls_driver_parameters_and_ranges_are_rejected(self):
        for change in ({"eos_url": "http://user:secret@eos:8503"}, {"phase_wait_s": 0},
                       {"battery_min_soc": 100}, {"battery_parameters": '{"mode":"sensor.invalid"}'},
                       {"wallbox_type": "unknown"}, {"battery_resource": "ev1"}):
            with self.subTest(change=change):
                self.assertEqual(await check(self.hass, {**DEFAULTS, **change}), {"base": "invalid_config"})
        with patch("custom_components.eos_energiezentrale.config_flow.request", side_effect=OSError("offline")):
            self.assertEqual(await check(self.hass, DEFAULTS, True), {"base": "cannot_connect"})

    async def test_websocket_rejects_non_admin_before_accessing_controller(self):
        connection = Mock(user=SimpleNamespace(is_admin=False))
        with self.assertRaises(Unauthorized):
            websocket_request(self.hass, connection, {"id": 1, "action": "control", "values": {"enabled": True}})

    async def invoke(self, msg):
        answered = asyncio.Event()
        connection = Mock(user=SimpleNamespace(is_admin=True))
        connection.send_result.side_effect = lambda *_: answered.set()
        connection.send_error.side_effect = lambda *_: answered.set()
        websocket_request(self.hass, connection, {"id": 1, **msg})
        await asyncio.wait_for(answered.wait(), timeout=5)
        return connection

    async def test_websocket_control_rejects_ambiguous_payload(self):
        coordinator, app = self.controller()
        for values in ({"enabled": 1}, {"enabled": True, "entity": "switch.other"}):
            connection = await self.invoke({"action": "control", "values": values})
            connection.send_error.assert_called_once()
        app.set_armed.assert_not_called()

    async def test_websocket_history_keeps_local_data_on_influx_failure(self):
        coordinator, app = self.controller()
        app.history.read.return_value = [{"time": "2026-11-08T12:00:00+00:00", "solar": 1000}]
        with patch("custom_components.eos_energiezentrale.coordinator.influx_series", side_effect=OSError("offline")):
            connection = await self.invoke({"action": "history"})
        payload = connection.send_result.call_args.args[1]
        self.assertTrue(payload["influx_error"])
        self.assertEqual(payload["local"][0]["solar"], 1000)

    async def test_diagnostics_exclude_credentials_and_private_readings(self):
        coordinator, app = self.controller()
        app.config.options.update(influx_password="test-secret", eos_url="http://private-host:8503")
        coordinator.async_set_updated_data({"live": {"car_soc": 32}, "errors": {"eos": "OSError"}})
        diagnostics = json.dumps(await async_get_config_entry_diagnostics(self.hass, self.entry))
        for private in ("test-secret", "private-host", "car_soc"):
            self.assertNotIn(private, diagnostics)

    async def test_native_controls_preserve_independent_pv_target_and_restart_safety(self):
        app = Controller(Mock(), Configuration(dict(DEFAULTS), Mock(), self.directory))
        coordinator = EnergyCoordinator(self.hass, self.entry, app)
        coordinator.async_set_updated_data(app.snapshot(datetime.now(timezone.utc)))
        await EnergyNumber(coordinator, "target_soc").async_set_native_value(70)
        await EnergyNumber(coordinator, "pv_target_soc").async_set_native_value(85)
        await EnergySwitch(coordinator, "pv").async_turn_on()
        await EnergySwitch(coordinator, "fast").async_turn_on()
        self.assertEqual(EnergyNumber(coordinator, "target_soc").native_value, 70)
        self.assertEqual(EnergyNumber(coordinator, "pv_target_soc").native_value, 85)
        restored = Configuration(dict(DEFAULTS), Mock(), self.directory)
        self.assertTrue(restored.daily["pv"])
        self.assertFalse(restored.daily["fast"])
        self.assertFalse(app.armed)

    async def test_native_schedule_requires_valid_departure_and_keeps_previous_plan_on_error(self):
        app = Controller(Mock(), Configuration(dict(DEFAULTS), Mock(), self.directory))
        coordinator = EnergyCoordinator(self.hass, self.entry, app)
        coordinator.async_set_updated_data(app.snapshot(datetime.now(timezone.utc)))
        schedule = ScheduleSelect(coordinator, "schedule")
        with self.assertRaises(ValueError):
            await schedule.async_select_option("once")
        self.assertEqual(schedule.current_option, "off")
        departure = EnergyText(coordinator, "departure")
        await departure.async_set_value("2026-11-10T09:45:00+01:00")
        await schedule.async_select_option("once")
        with self.assertRaises(ValueError):
            await departure.async_set_value("not-a-date")
        self.assertEqual(departure.native_value, "2026-11-10T09:45:00+01:00")
        self.assertEqual(schedule.current_option, "once")

    async def test_pending_release_visible_immediately_after_failed_native_switch_off(self):
        ha = Mock()
        app = Controller(ha, Configuration(dict(DEFAULTS), ha, self.directory))
        app.armed = app.owned = True
        ha.states.side_effect = OSError("offline")
        coordinator = EnergyCoordinator(self.hass, self.entry, app)
        coordinator.async_set_updated_data(app.snapshot(datetime.now(timezone.utc)))
        switch = EnergySwitch(coordinator, "control")
        from homeassistant.exceptions import HomeAssistantError
        with self.assertRaises(HomeAssistantError):
            await switch.async_turn_off()
        self.assertFalse(switch.is_on)
        self.assertTrue(EnergyBinarySensor(coordinator, "release_pending").is_on)
        self.assertTrue(EnergyBinarySensor(coordinator, "problem").is_on)

    async def test_vehicle_manager_adds_second_charger_without_losing_existing_vehicle(self):
        from test_fleet import definitions
        flow=OptionsFlow()
        flow.hass=self.hass
        flow.handler=self.entry.entry_id
        flow.context={"entry_id":self.entry.entry_id}
        row=definitions()[1]
        fields={key:value for key,value in row.items() if key!="wallbox_parameters"}
        fields.pop("wallbox_type",None)
        fields.update(capacity_wh=77000,charging_efficiency=.9,max_current_a=16,soc_scale="factor")
        fields.update({"wallbox_"+key:value for key,value in row["wallbox_parameters"].items()})
        result=await flow.async_step_vehicle_add(fields)
        self.assertEqual(result["type"],"create_entry")
        stored=json.loads(result["data"]["vehicles"])
        self.assertEqual(len(stored),2)
        self.assertEqual(stored[0]["resource"],"ev1")
        self.assertEqual(stored[1]["id"],"second")
        self.assertEqual(result["data"]["battery_type"],DEFAULTS["battery_type"])

    async def test_removing_last_vehicle_does_not_restore_legacy_charger(self):
        flow=OptionsFlow()
        flow.hass=self.hass
        flow.handler=self.entry.entry_id
        flow.context={"entry_id":self.entry.entry_id}
        result=await flow.async_step_vehicle_remove({"vehicle_id":"vehicle1"})
        self.assertEqual(json.loads(result["data"]["vehicles"]),[])
        self.assertEqual(result["data"]["wallbox_type"],"none")

    async def test_individual_vehicle_sensors_use_distinct_values_and_stable_identity(self):
        from custom_components.eos_energiezentrale.sensor import VehicleSensor
        coordinator,_=self.controller()
        coordinator.async_set_updated_data({"vehicles":[
            {"id":"one","live":{"car":1000,"car_soc":40}},
            {"id":"two","live":{"car":2000,"car_soc":60}}]})
        one=VehicleSensor(coordinator,"one","Auto 1","car")
        two=VehicleSensor(coordinator,"two","Auto 2","car")
        self.assertEqual((one.native_value,two.native_value),(1,2))
        self.assertNotEqual(one.unique_id,two.unique_id)
        renamed=VehicleSensor(coordinator,"one","Neuer Name","car")
        self.assertEqual(one.unique_id,renamed.unique_id)
        self.assertEqual(VehicleSensor(coordinator,"two","Auto 2","car_soc_factor").native_value,.6)

    async def test_options_edit_keeps_other_hardware_and_sensor_settings(self):
        flow = OptionsFlow()
        flow.hass = self.hass
        flow.handler = self.entry.entry_id
        flow.context = {"entry_id": self.entry.entry_id}
        result = await flow.async_step_limits({"phase_wait_s": 90})
        self.assertEqual(result["data"]["phase_wait_s"], 90)
        self.assertEqual(result["data"]["grid_entity"], DEFAULTS["grid_entity"])
        result = await flow.async_step_limits({"battery_min_soc": 101})
        self.assertEqual(result["type"], "form")
        self.assertEqual(result["errors"], {"base": "invalid_config"})


    async def test_identical_meter_reports_refresh_freshness_without_faking_missing_reports(self):
        from datetime import timedelta
        from custom_components.eos_energiezentrale.energy.clients import reading
        now = datetime.now(timezone.utc)
        earlier = now - timedelta(minutes=10)
        attrs = {"unit_of_measurement": "W"}
        self.hass.states.async_set("sensor.idle_heat", "0", attrs, timestamp=earlier.timestamp())
        adapter = HomeAssistantAdapter(self.hass)
        # Other HA consumers may already have serialized the original state.
        self.hass.states.get("sensor.idle_heat").as_dict()
        self.hass.states.async_set("sensor.idle_heat", "0", attrs, timestamp=now.timestamp())
        rows = await self.hass.async_add_executor_job(adapter.states)
        single = await self.hass.async_add_executor_job(adapter.state, "sensor.idle_heat")
        self.assertEqual(reading(rows, "sensor.idle_heat", now, "power", 120), 0)
        self.assertEqual(single["last_reported"], now.isoformat())
        self.assertEqual(single["last_updated"], earlier.isoformat())
        # Polling the registry must never manufacture fresh data for an offline meter.
        later = now + timedelta(minutes=3)
        rows = await self.hass.async_add_executor_job(adapter.states)
        self.assertIsNone(reading(rows, "sensor.idle_heat", later, "power", 120))

    async def test_read_only_flow_shows_470w_battery_supply_with_idle_car_and_heat(self):
        from datetime import timedelta
        from custom_components.eos_energiezentrale.energy.drivers import Fronius, NRGkick
        now = datetime.now(timezone.utc)
        earlier = now - timedelta(minutes=10)
        battery, box = Fronius.defaults, NRGkick.defaults
        samples = {
            DEFAULTS["pv_entity"]: (0, "W"), DEFAULTS["house_entity"]: (470, "W"),
            DEFAULTS["grid_entity"]: (0, "W"), DEFAULTS["heat_entity"]: (0, "W"),
            DEFAULTS["price_entity"]: (.44, "EUR/kWh"), DEFAULTS["car_soc_entity"]: (.33, None),
            battery["soc"]: (55.4, "%"), battery["charge_power"]: (0, "W"),
            battery["discharge_power"]: (470, "W"), box["power"]: (0, "W"),
            box["status"]: ("connected", None), box["enable"]: ("off", None),
            box["phases"]: (3, None), box["current"]: (6, "A"),
        }
        def report(stamp):
            for entity, (value, unit) in samples.items():
                attrs = {"unit_of_measurement": unit} if unit else {}
                if entity == box["current"]:
                    attrs.update(step=.1, max=16)
                self.hass.states.async_set(entity, str(value), attrs, timestamp=stamp.timestamp())
        report(earlier)
        adapter = HomeAssistantAdapter(self.hass)
        await self.hass.async_add_executor_job(adapter.states)
        report(now)
        def collect():
            config = Configuration(dict(DEFAULTS), adapter, self.directory)
            config.eos = Mock()
            config.eos.plan.return_value = {}
            config.eos.solution.return_value = {}
            app = Controller(adapter, config)
            app.tick(now, 0)
            return app.snapshot(now)
        result = await self.hass.async_add_executor_job(collect)
        self.assertFalse(result["armed"])
        live = result["live"]
        self.assertEqual((live["battery_charge"], live["battery_discharge"], live["battery"]), (0, 470, -470))
        self.assertEqual((live["car"], live["heat"], live["house"]), (0, 0, 470))


    async def test_native_battery_limits_send_immediately_even_in_read_only_mode(self):
        ha = Mock()
        config = Configuration(dict(DEFAULTS),ha,self.directory)
        config.eos = Mock()
        app = Controller(ha,config)
        coordinator = EnergyCoordinator(self.hass,self.entry,app)
        coordinator.async_set_updated_data(app.snapshot(datetime.now(timezone.utc)))
        await EnergyNumber(coordinator,"battery_min_soc").async_set_native_value(30)
        config.eos.set_battery_limits.assert_called_once_with("battery1",30,100)
        await EnergyNumber(coordinator,"battery_max_soc").async_set_native_value(90)
        config.eos.set_battery_limits.assert_called_with("battery1",30,90)
        self.assertFalse(app.armed)
        self.assertTrue(EnergyBinarySensor(coordinator,"battery_limits_confirmed").is_on)
        self.assertEqual(EnergyNumber(coordinator,"battery_min_soc").native_value,30)

    async def test_failed_eos_sync_keeps_local_bounds_and_exposes_pending_state(self):
        ha = Mock()
        config = Configuration(dict(DEFAULTS),ha,self.directory)
        config.eos = Mock()
        config.eos.set_battery_limits.side_effect = OSError("EOS offline")
        app = Controller(ha,config)
        coordinator = EnergyCoordinator(self.hass,self.entry,app)
        coordinator.async_set_updated_data(app.snapshot(datetime.now(timezone.utc)))
        await coordinator.async_change(settings={"battery_min_soc":30,"battery_max_soc":90})
        self.assertEqual(coordinator.data["settings"]["battery_min_soc"],30)
        self.assertFalse(EnergyBinarySensor(coordinator,"battery_limits_confirmed").is_on)
        self.assertTrue(EnergyBinarySensor(coordinator,"problem").is_on)
        self.assertTrue(Configuration(dict(DEFAULTS),ha,self.directory).battery_limits_managed)

    async def test_failed_local_save_does_not_write_eos_or_claim_changed_limits(self):
        ha = Mock()
        config = Configuration(dict(DEFAULTS),ha,self.directory)
        config.eos = Mock()
        app = Controller(ha,config)
        coordinator = EnergyCoordinator(self.hass,self.entry,app)
        coordinator.async_set_updated_data(app.snapshot(datetime.now(timezone.utc)))
        with patch("custom_components.eos_energiezentrale.energy.settings.save", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                await coordinator.async_change(settings={"battery_min_soc":30})
        config.eos.set_battery_limits.assert_not_called()
        self.assertEqual(config.daily["battery_min_soc"],20)
        self.assertFalse(config.battery_limits_managed)


    async def test_graceful_stop_remembers_enabled_setting_for_next_start(self):
        ha = Mock()
        config = Configuration(dict(DEFAULTS),ha,self.directory)
        app = Controller(ha,config)
        coordinator = EnergyCoordinator(self.hass,self.entry,app)
        await coordinator.async_change(enabled=True)
        await coordinator.async_stop()
        self.assertFalse(app.armed)
        restored = Controller(ha,Configuration(dict(DEFAULTS),ha,self.directory))
        self.assertTrue(restored.armed)
        self.assertTrue(restored.restore_pending)

    async def test_runtime_fault_disables_persistently_instead_of_rearming_after_restart(self):
        ha = Mock()
        config = Configuration(dict(DEFAULTS),ha,self.directory)
        app = Controller(ha,config)
        app.set_armed(True)
        app.owned = True
        app.tick = Mock(side_effect=OSError("unconfirmed command"))
        app.release = Mock()
        coordinator = EnergyCoordinator(self.hass,self.entry,app)
        result = await coordinator._async_update_data()
        self.assertFalse(result["armed"])
        app.release.assert_called_once()
        self.assertFalse(Controller(ha,Configuration(dict(DEFAULTS),ha,self.directory)).armed)

    async def test_restart_waits_for_real_inputs_then_resumes_without_manual_enable(self):
        from datetime import timedelta
        from custom_components.eos_energiezentrale.energy.drivers import Fronius,NRGkick
        from test_energy import instruction
        now = datetime.now(timezone.utc)
        adapter = HomeAssistantAdapter(self.hass)
        config = Configuration(dict(DEFAULTS),adapter,self.directory)
        config.set_control_enabled(True)
        config.eos = Mock()
        config.eos.plan.return_value = {"generated_at":now.isoformat(),"instructions":[instruction(now,"NON_EXPORT")]}
        config.eos.solution.return_value = {}
        app = Controller(adapter,config)
        with (patch.object(config.battery,'apply') as apply,
              patch.object(config.battery,'release') as release,
              patch.object(config.wallbox,'pause') as pause):
            await self.hass.async_add_executor_job(app.tick,now,0)
            self.assertTrue(app.snapshot(now)["control_waiting"])
            self.assertTrue(app.armed)
            apply.assert_not_called()
            release.assert_not_called()
            pause.assert_not_called()
            battery,box = Fronius.defaults,NRGkick.defaults
            samples = {DEFAULTS["pv_entity"]:(0,"W"),DEFAULTS["grid_entity"]:(0,"W"),
                       battery["soc"]:(55.4,"%"),battery["charge_power"]:(0,"W"),
                       battery["discharge_power"]:(470,"W"),battery["mode"]:("Auto",None),
                       box["power"]:(0,"W"),box["status"]:("connected",None),
                       box["enable"]:("off",None),box["phases"]:(3,None),box["current"]:(6,"A")}
            for entity,(value,unit) in samples.items():
                attrs = {"unit_of_measurement":unit} if unit else {}
                if entity == box["current"]:
                    attrs.update(step=.1,max=16)
                self.hass.states.async_set(entity,str(value),attrs,timestamp=now.timestamp())
            await self.hass.async_add_executor_job(app.tick,now+timedelta(seconds=5),5)
            self.assertFalse(app.snapshot(now+timedelta(seconds=5))["control_waiting"])
            self.assertTrue(app.armed)
            apply.assert_called_once()


    async def test_eos_startup_errors_keep_saved_permission_and_resume_after_recovery(self):
        from datetime import timedelta
        from urllib.error import HTTPError
        from custom_components.eos_energiezentrale.energy.drivers import Fronius, NRGkick
        from test_energy import instruction
        now = datetime.now(timezone.utc)
        adapter = HomeAssistantAdapter(self.hass)
        config = Configuration(dict(DEFAULTS),adapter,self.directory)
        config.eos = Mock()
        config.eos.solution.side_effect = TimeoutError("optimization not ready")
        app = Controller(adapter,config)
        app.set_armed(True)
        coordinator = EnergyCoordinator(self.hass,self.entry,app)
        battery,box = Fronius.defaults,NRGkick.defaults
        samples = {DEFAULTS["pv_entity"]:(0,"W"),DEFAULTS["grid_entity"]:(0,"W"),
                   battery["soc"]:(55.4,"%"),battery["charge_power"]:(0,"W"),
                   battery["discharge_power"]:(0,"W"),battery["mode"]:("Auto",None),
                   box["power"]:(0,"W"),box["status"]:("connected",None),
                   box["enable"]:("off",None),box["phases"]:(3,None),box["current"]:(6,"A")}
        for entity,(value,unit) in samples.items():
            attrs = {"unit_of_measurement":unit} if unit else {}
            if entity == box["current"]:
                attrs.update(step=.1,max=16)
            self.hass.states.async_set(entity,str(value),attrs,timestamp=now.timestamp())
        with (patch.object(config.battery,'apply') as apply,
              patch.object(config.battery,'release') as release,
              patch.object(config.wallbox,'pause') as pause):
            for response in (TimeoutError("offline"), HTTPError("http://eos",503,"not ready",{},None),
                             ValueError("invalid JSON"), None, {"detail":"still planning"}):
                coordinator.eos_poll_started = {"plan": -1000, "solution": -1000}
                config.eos.plan.side_effect = response if isinstance(response,Exception) else None
                config.eos.plan.return_value = response
                await coordinator._async_update_data()
                await asyncio.gather(*coordinator.eos_poll_tasks.values())
                result = await coordinator._async_update_data()
                self.assertTrue(result["armed"])
                self.assertTrue(result["control_waiting"])
                self.assertIn("eos",result["errors"])
                self.assertNotIn("runtime",result["errors"])
                self.assertTrue(Configuration(dict(DEFAULTS),adapter,self.directory).control_enabled)
            apply.assert_not_called()
            release.assert_not_called()
            pause.assert_not_called()
            config.eos.plan.side_effect = None
            config.eos.plan.return_value = {"generated_at":now.isoformat(),"instructions":[instruction(now-timedelta(seconds=1),"NON_EXPORT"),{**instruction(now-timedelta(seconds=1),"IDLE"),"resource_id":"ev1"}]}
            config.eos.solution.side_effect = None
            config.eos.solution.return_value = {}
            coordinator.eos_poll_started = {"plan": -1000, "solution": -1000}
            await coordinator._async_update_data()
            await asyncio.gather(*coordinator.eos_poll_tasks.values())
            result = await coordinator._async_update_data()
            self.assertTrue(result["armed"])
            self.assertFalse(result["control_waiting"])
            self.assertNotIn("eos",result["errors"])
            apply.assert_called_once()

    async def test_shutdown_service_error_does_not_erase_saved_control_permission(self):
        from threading import Event
        ha = Mock()
        config = Configuration(dict(DEFAULTS),ha,self.directory)
        app = Controller(ha,config)
        app.set_armed(True)
        entered,finish = Event(),Event()
        def tick(*_):
            entered.set()
            if not finish.wait(5):
                raise TimeoutError("test worker did not finish")
            raise OSError("service disappeared during HA shutdown")
        app.tick = Mock(side_effect=tick)
        app.release = Mock()
        app.owned = True
        coordinator = EnergyCoordinator(self.hass,self.entry,app)
        polling = asyncio.create_task(coordinator._async_update_data())
        self.assertTrue(await self.hass.async_add_executor_job(entered.wait,5))
        stopping = asyncio.create_task(coordinator.async_stop())
        await asyncio.sleep(0)
        finish.set()
        await asyncio.gather(polling,stopping)
        self.assertFalse(app.armed)
        self.assertTrue(Controller(ha,Configuration(dict(DEFAULTS),ha,self.directory)).armed)


    async def test_vehicle_name_can_be_changed_without_changing_eos_or_source_identity(self):
        flow = OptionsFlow()
        flow.hass = self.hass
        flow.handler = self.entry.entry_id
        flow.context = {"entry_id":self.entry.entry_id}
        result = await flow.async_step_hardware({"vehicle_name":"Familienauto"})
        self.assertEqual(result["data"]["vehicle_name"],"Familienauto")
        config = Configuration(result["data"],Mock(),self.directory)
        app = Controller(Mock(),config)
        self.assertEqual(app.snapshot(datetime.now(timezone.utc))["vehicle_name"],"Familienauto")
        self.assertEqual(config.options["vehicle_resource"],"ev1")
        self.assertEqual(config.options["car_soc_entity"],DEFAULTS["car_soc_entity"])

    async def test_vehicle_name_validation_and_existing_entry_default(self):
        for name in ("", "   ", "x"*61, "car\nname", 123):
            with self.subTest(name=name):
                self.assertEqual(await check(self.hass,{**DEFAULTS,"vehicle_name":name}),{"base":"invalid_config"})
        old_options = dict(DEFAULTS)
        old_options.pop("vehicle_name")
        self.assertEqual(await check(self.hass,old_options),{})
        config = Configuration(old_options,Mock(),self.directory)
        self.assertEqual(Controller(Mock(),config).snapshot(datetime.now(timezone.utc))["vehicle_name"],"E-Auto")

    async def test_native_vehicle_sensor_names_use_configured_name_with_stable_identity(self):
        coordinator,app = self.controller()
        before = EnergySensor(coordinator,"car")
        self.assertEqual(before.translation_placeholders["vehicle"],"E-Auto")
        app.config.options["vehicle_name"] = "Familienauto"
        renamed = EnergySensor(coordinator,"car")
        self.assertEqual(renamed.translation_placeholders["vehicle"],"Familienauto")
        self.assertEqual(before.unique_id,renamed.unique_id)


class CredentialRetentionRequirements(unittest.TestCase):
    def test_only_superseded_password_is_removed_and_other_data_is_preserved(self):
        from custom_components.eos_energiezentrale import remove_superseded_password
        hass=Mock()
        entry=SimpleNamespace(data={'influx_password':'old','eos_url':'http://eos'},
                              options={'influx_password':'new'})
        remove_superseded_password(hass,entry)
        hass.config_entries.async_update_entry.assert_called_once_with(entry,data={'eos_url':'http://eos'})

    def test_original_password_is_not_removed_if_options_do_not_override_it(self):
        from custom_components.eos_energiezentrale import remove_superseded_password
        hass=Mock();entry=SimpleNamespace(data={'influx_password':'only'},options={})
        remove_superseded_password(hass,entry)
        hass.config_entries.async_update_entry.assert_not_called()

    def test_password_is_not_rendered_in_config_form_default(self):
        import probatio
        from homeassistant.helpers.config_validation import custom_serializer
        from custom_components.eos_energiezentrale.config_flow import schema_for
        fields=probatio.to_field_list(schema_for('history',{**DEFAULTS,'influx_password':'do-not-echo'}),
                                      custom_serializer=custom_serializer)
        self.assertNotIn('do-not-echo',json.dumps(fields))
        password=next(field for field in fields if field['name']=='influx_password')
        self.assertFalse(password['required'])


class ExternalSecretRequirements(unittest.TestCase):
    def test_external_secret_is_resolved_without_persisting_its_value(self):
        from custom_components.eos_energiezentrale.energy.settings import influx_credential
        options={**DEFAULTS,'influx_password':'','influx_password_env':'EOS_INFLUX_SECRET'}
        self.assertEqual(influx_credential(options,{'EOS_INFLUX_SECRET':'private-value'}),'private-value')
        self.assertNotIn('private-value',json.dumps(options))

    def test_missing_external_secret_and_invalid_name_fail_closed_without_disclosing_it(self):
        from custom_components.eos_energiezentrale.energy.settings import influx_credential
        for name in ('MISSING_SECRET','INVALID SECRET'):
            with self.subTest(name=name),self.assertRaises(ValueError) as error:
                influx_credential({**DEFAULTS,'influx_password_env':name},{})
            self.assertNotIn('private-value',str(error.exception))

    def test_legacy_password_remains_usable_without_external_secret(self):
        from custom_components.eos_energiezentrale.energy.settings import influx_credential
        self.assertEqual(influx_credential({**DEFAULTS,'influx_password':'legacy'},{}),'legacy')

    def test_config_does_not_accept_two_password_sources(self):
        from custom_components.eos_energiezentrale.validation import validate_options
        with self.assertRaises(ValueError):
            validate_options({**DEFAULTS,'influx_password':'legacy','influx_password_env':'EOS_INFLUX_SECRET'})

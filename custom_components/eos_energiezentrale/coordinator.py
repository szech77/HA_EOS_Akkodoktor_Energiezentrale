"""Serialize all controller work outside Home Assistant's event loop."""
import asyncio
from copy import copy, deepcopy
from datetime import datetime, timezone
from functools import partial
import logging
import sqlite3
from time import monotonic

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .energy.history import influx_series
from .energy.accounting import Accounting
from .energy.accounting_history import reconstruct, merge_reconstruction
from .energy.clients import ENTITY
from .energy.controller import Controller
from .energy.domain import instant, next_departure
from .energy.drivers import DeviceNotReady
from .energy.settings import changed_settings, settings_payload
from .energy.source_diagnostics import source_diagnostics
from .energy.status import IssueLog, view_state, failure_details
from .energy.report_values import current_day_values, report_values
from .energy.charge_view import charge_plan
from .energy.pv_view import pv_effects, pv_hours, pv_now, weather_days
from .energy.power_profile import battery_origin, day_bounds, power_profile
from .energy.pv_report import pv_forecast
from .energy.presentation import measured_pv_energy, mode_timeline, node_problems, plan_events
from .weather_forecast import WeatherForecast

_LOGGER = logging.getLogger(__name__)


class EnergyCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, app):
        super().__init__(hass, _LOGGER, name="EOS Energiezentrale", config_entry=entry)
        self.entry, self.app = entry, app
        self.work_lock = asyncio.Lock()
        self.influx_lock = asyncio.Lock()
        self.closing = False
        self.influx_at = -1000
        self.influx_rows = []
        self.influx_error = False
        self.accounting = None
        self.accounting_cache = {}
        self.accounting_refresh_task = None
        self.accounting_revision = 0
        self.day_historical = None
        self.history_for_view = {'local':[], 'vehicles':{}}
        self.eos_poll_tasks = {}
        self.eos_poll_started = {"plan": float("-inf"), "solution": float("-inf")}
        self.battery_sync_task = None
        self.battery_sync_revision = 0
        self.battery_sync_last = float("-inf")
        self.battery_sync_last_revision = -1
        self.goal_sync_tasks = {}
        self.goal_sync_last = {}
        self.vehicle_sync_tasks = {}
        self.vehicle_sync_last = {}
        self.weather_forecast = WeatherForecast(hass)
        self.issue_log = IssueLog(_LOGGER)
        self.control_status = None
        self.eos_run_status = None
        if isinstance(app, Controller):
            app.external_eos_polling = True
            app.external_battery_sync = True
            app.external_goal_sync = True
            app.external_vehicle_sync = True
            for _, child, _ in getattr(app, "controllers", ()):
                child.external_battery_sync = True
                child.external_goal_sync = True
                child.external_vehicle_sync = True

    def _tick(self):
        with self.app.lock:
            clock = monotonic()
            controller = isinstance(self.app, Controller)
            if controller and not self.closing:
                self.app.resume_after_connection(clock)
            paused = False
            try:
                self.app.tick(datetime.now(timezone.utc), clock)
                self.app.errors.pop("device_pending", None)
                if self.app.armed:
                    self.app.errors.pop("runtime", None)
                if controller and self.app.connection_restored():
                    self.app.errors.pop("control_resume", None)
            except DeviceNotReady as error:
                self.app.errors["device_pending"] = error.entity
            except Exception as error:
                self.app.errors.pop("device_pending", None)
                # An unreachable device pauses control; it resumes on its own (Issue #33).
                paused = controller and not self.closing and self.app.pause_for_connection(error, clock)
                self.app.errors.pop("runtime" if paused else "control_resume", None)
                self._sync_failure(self.app, "control_resume" if paused else "runtime", error)
                entity = getattr(error, "entity", None)
                self.app.last_failure = {
                    "type": type(error).__name__,
                    "step": getattr(self.app, "control_step", "unknown"),
                    "at": datetime.now(timezone.utc).isoformat(),
                    "entity": entity if isinstance(entity, str) and ENTITY.fullmatch(entity) else None}
                self.app.armed = False
                self.app.restore_pending = False
                if not self.closing and not paused:
                    try:
                        self.app.remember_control(False)
                    except Exception:
                        pass  # Persistence failure is exposed by the controller.
                if self.app.owned:
                    try:
                        self.app.release(self.app.ha.states(), datetime.now(timezone.utc))
                    except Exception:
                        self.app.errors["release"] = "Device release unconfirmed"
            now = datetime.now(timezone.utc)
            result = self.app.snapshot(now)
            try:
                ledger = self._accounting()
                ledger.observe(result["live"], result.get("vehicles", []))
                consumers = ['house'] + (['heat'] if result.get('features', {}).get('heat') else []) + (['car'] if result.get('features', {}).get('car') else [])
                result["accounting"] = current_day_values(ledger.report({"period":"day"}, now), self.day_historical, consumers)
                local = self.app.history.read(now)
                self.history_for_view = {'local':local, 'vehicles':self.app.vehicle_histories(now)
                    if callable(getattr(type(self.app), 'vehicle_histories', None)) else {}}
                result['pv_today_kwh'] = measured_pv_energy(local, self.influx_rows, now, result['zone'])
                result['pv_price_ct'] = ledger.pv_price(now.isoformat())
                self.app.errors.pop("accounting", None)
            except (OSError, sqlite3.Error, ValueError, TypeError, KeyError) as error:
                # Reporting failures must never stop an otherwise safe charge.
                self.app.errors["accounting"] = type(error).__name__
                result['accounting'] = None
                result['pv_today_kwh'] = None
                result['pv_price_ct'] = None
                if isinstance(self.app, Controller):
                    self.app.record_failure("accounting", error)
            result["errors"] = self.app.visible_errors(now) if isinstance(self.app, Controller) else dict(self.app.errors)
            if isinstance(self.app, Controller):
                result['error_details'] = dict(self.app.error_details)
            return self._present(result)

    def _present(self, data):
        now = datetime.now(timezone.utc)
        retained = {key:self.data[key] for key in ('accounting', 'pv_today_kwh', 'pv_price_ct') if self.data and key in self.data}
        result = view_state({**retained, **data}, now)
        measured = result.get('pv_today_kwh')
        result['pv_forecast_totals'] = [{**row, 'total_kwh':row['kwh'] + measured if index == 0
            and row.get('kwh') is not None and measured is not None else row.get('kwh'),
            'includes_measured':index == 0 and row.get('kwh') is not None and measured is not None}
            for index, row in enumerate(result.get('pv_daily_forecast', []))]
        # The panel draws "now" at the snapshot time; split history and plan at the same instant.
        stamp = instant((result.get('live') or {}).get('time'))
        split = stamp if stamp is not None and stamp <= now else now
        result['mode_timeline'] = mode_timeline(result, self.history_for_view['local'], split)
        for vehicle in result.get('vehicles', []):
            vehicle['mode_timeline'] = mode_timeline(vehicle, self.history_for_view['vehicles'].get(vehicle['id'], []), split)
        result['source_diagnostics'] = source_diagnostics(result, now)
        # A persistently deviating measured site total hints at a missing source or a wrong meter.
        since = instant(result['source_diagnostics'].get('deviation_since'))
        self.issue_log.update('consumption', [{'id': 'consumption/house_total', 'code': 'house_total_deviation',
            'severity': 'info'}] if since and (now - since).total_seconds() >= 900 else [])
        self.issue_log.update('state', result['notices'])
        since = self.issue_log.active_since('state')
        result['notices'] = [{**notice, 'since':since.get(notice['id'])} for notice in result['notices']]
        result['resolved_notices'] = self.issue_log.recently_resolved('state', now)
        result['node_problems'] = node_problems(result['notices'], result.get('vehicles') or ())
        result['plan_events'] = plan_events(result, now)
        if result.get('features', {}).get('car'):
            result['charge_plan'] = charge_plan(result, now, result.get('pv_price_ct'))
        for vehicle in result.get('vehicles', []):
            vehicle['charge_plan'] = charge_plan({'armed':result.get('armed'), **vehicle}, now, result.get('pv_price_ct'))
        result['pv_now'] = pv_now(result, now)
        result['pv_effects'] = pv_effects(result, now)
        self.issue_log.update('indicators', [{'id':'battery_minimum', 'code':'battery_minimum', 'severity':'info'}]
                              if result['battery_low'] else [])
        if result['control_status'] != self.control_status:
            _LOGGER.info('EOS control status: %s', result['control_status'])
            self.control_status = result['control_status']
        run_status = result.get('eos_run', {}).get('state', 'unknown')
        if run_status != self.eos_run_status:
            _LOGGER.info('EOS calculation status: %s', run_status)
            self.eos_run_status = run_status
        return result

    def async_set_updated_data(self, data):
        super().async_set_updated_data(self._present(data))

    async def _async_publish_snapshot(self):
        snapshot = await self.hass.async_add_executor_job(self.app.snapshot, datetime.now(timezone.utc))
        self.async_set_updated_data({**(self.data or {}), **snapshot})

    def report_failure(self, area, error, code):
        self.report_notice(area, code, failure_details(error))

    def report_notice(self, area, code, details=None):
        self.issue_log.update(area, [{'id':area, 'code':code, 'scope':area,
            'severity':'warning', 'details':details or {}}])

    def report_success(self, area):
        self.issue_log.update(area, [])

    async def _async_update_data(self):
        async with self.work_lock:
            if self.closing:
                return self.data
            self._schedule_eos_polling()
            try:
                result = await self.hass.async_add_executor_job(self._tick)
            except (OSError, ValueError) as error:
                raise UpdateFailed("Local controller unavailable") from error
            self._schedule_accounting_refresh()
            self._schedule_battery_sync()
            self._schedule_goal_sync()
            self._schedule_vehicle_sync()
            return result

    def _vehicle_controllers(self):
        if not isinstance(self.app, Controller):
            return ()
        return tuple(child for _, child, _ in self.app.controllers) if hasattr(self.app, "controllers") else (self.app,)

    @staticmethod
    def _desired_goal(app, now):
        if app.vehicle_connected is False:
            return None
        if app.vehicle_profile is not None and not app.vehicle_profile[-1]:
            return None
        departure = next_departure(app.config.daily, now, app.config.zone)
        return (app.goal_target(now), departure) if departure else None

    @staticmethod
    def _sync_failure(app, area, error):
        app.errors[area] = type(error).__name__
        if isinstance(app, Controller):
            app.error_details[area] = failure_details(error)

    def _schedule_vehicle_sync(self):
        if self.closing:
            return
        for app in self._vehicle_controllers():
            desired = app.vehicle_profile
            if desired is None or app.config.options.get('wallbox_type')=='none':
                continue
            resource = app.config.options['vehicle_resource']
            task = self.vehicle_sync_tasks.get(resource)
            if task and not task.done():
                continue
            previous = self.vehicle_sync_last.get(resource)
            interval = 60 if desired == app.vehicle_profile_confirmed else 30
            if previous and previous[0] == desired and monotonic() - previous[1] < interval:
                continue
            self.vehicle_sync_last[resource] = (desired, monotonic())
            self.vehicle_sync_tasks[resource] = self.hass.async_create_background_task(
                self._async_sync_vehicle(app, resource, desired), 'EOS vehicle limits sync')

    async def _async_sync_vehicle(self, app, resource, desired):
        error = None
        try:
            await self.hass.async_add_executor_job(app.config.eos.set_vehicle_charging_limits, resource, *desired)
        except Exception as caught:
            error = caught
        async with self.work_lock:
            if self.closing:
                return
            if desired == app.vehicle_profile:
                if error is None:
                    changed = app.vehicle_profile_confirmed != desired
                    app.vehicle_profile_confirmed = desired
                    if changed:
                        app.vehicle_profile_at = datetime.now(timezone.utc)
                    app.errors.pop('vehicle_limits', None)
                else:
                    app.vehicle_profile_confirmed = None
                    self._sync_failure(app, 'vehicle_limits', error)
            self.vehicle_sync_tasks.pop(resource, None)
            await self._async_publish_snapshot()
            if desired != app.vehicle_profile:
                self._schedule_vehicle_sync()

    def _schedule_goal_sync(self):
        if not isinstance(self.app, Controller) or 'vehicle' not in self.app.control_domains():
            return
        for app in self._vehicle_controllers():
            if (not app.goal_sync_ready or app.restore_pending
                    or app.config.options.get("wallbox_type") == "none"):
                continue
            resource = app.config.options["vehicle_resource"]
            task = self.goal_sync_tasks.get(resource)
            if task and not task.done():
                continue
            desired = self._desired_goal(app, datetime.now(timezone.utc))
            if desired == app.goal and app.goal_at is not None:
                continue
            previous = self.goal_sync_last.get(resource)
            if (previous and previous[:2] == (desired, app.goal_sync_revision)
                    and monotonic() - previous[2] < 30):
                continue
            revision = app.goal_sync_revision
            self.goal_sync_last[resource] = (desired, revision, monotonic())
            self.goal_sync_tasks[resource] = self.hass.async_create_background_task(
                self._async_sync_goal(app, resource, desired, revision), "EOS vehicle goal sync")

    async def _async_sync_goal(self, app, resource, desired, revision):
        target, deadline = desired or (0, None)
        error = None
        try:
            await self.hass.async_add_executor_job(app.config.eos.set_vehicle_goal, resource, target, deadline)
        except Exception as caught:
            error = caught
        async with self.work_lock:
            if self.closing:
                return
            current = self._desired_goal(app, datetime.now(timezone.utc))
            if revision == app.goal_sync_revision and desired == current:
                if error is None:
                    app.goal, app.goal_at = desired, datetime.now(timezone.utc)
                    app.errors.pop("goal", None)
                else:
                    app.goal_at = None
                    self._sync_failure(app, "goal", error)
            self.goal_sync_tasks.pop(resource, None)
            await self._async_publish_snapshot()
            if revision != app.goal_sync_revision or desired != current:
                self._schedule_goal_sync()

    def _schedule_battery_sync(self):
        app = self.app
        if (not isinstance(app, Controller) or not app.battery_sync_managed()
                or (self.battery_sync_task and not self.battery_sync_task.done())):
            return
        desired = app.battery_limits_request()
        interval = 60 if app.battery_limits_confirmed == desired else 30
        if (self.battery_sync_last_revision == self.battery_sync_revision
                and monotonic() - self.battery_sync_last < interval):
            return
        self.battery_sync_last = monotonic()
        self.battery_sync_last_revision = self.battery_sync_revision
        self.battery_sync_task = self.hass.async_create_background_task(
            self._async_sync_battery(desired, self.battery_sync_revision), "EOS battery limits sync")

    async def _async_sync_battery(self, desired, revision):
        error = None
        try:
            await self.hass.async_add_executor_job(
                self.app.config.eos.set_battery_limits,
                self.app.config.options["battery_resource"], *desired)
        except Exception as caught:
            error = caught
        async with self.work_lock:
            if self.closing:
                return
            current = self.app.battery_limits_request()
            if revision == self.battery_sync_revision and desired == current:
                if error is None:
                    self.app.battery_limits_confirmed = desired
                    self.app.battery_limits_confirmed_at = datetime.now(timezone.utc)
                    self.app.errors.pop("battery_limits", None)
                else:
                    self.app.battery_limits_confirmed = None
                    self.app.battery_limits_confirmed_at = None
                    self._sync_failure(self.app, "battery_limits", error)
                await self._async_publish_snapshot()
            self.battery_sync_task = None
            if revision != self.battery_sync_revision or desired != current:
                self._schedule_battery_sync()

    def _schedule_eos_polling(self):
        if not isinstance(self.app, Controller):
            return
        now = monotonic()
        for kind, interval in (("plan", 15), ("solution", 60)):
            task = self.eos_poll_tasks.get(kind)
            if (task and not task.done()) or now - self.eos_poll_started[kind] < interval:
                continue
            self.eos_poll_started[kind] = now
            self.eos_poll_tasks[kind] = self.hass.async_create_background_task(
                self._async_poll_eos(kind), "EOS " + kind + " polling")

    async def _async_poll_eos(self, kind):
        if kind == 'plan':
            try:
                health = await self.hass.async_add_executor_job(self.app.config.eos.health)
            except Exception:
                health = None
            async with self.work_lock:
                if self.closing:
                    return
                await self.hass.async_add_executor_job(self.app.apply_eos_health, health, datetime.now(timezone.utc))
                if self.data is not None:
                    await self._async_publish_snapshot()
        started = datetime.now(timezone.utc)
        try:
            result = await self.hass.async_add_executor_job(getattr(self.app.config.eos, kind))
            error = None
        except Exception as caught:
            result, error = None, caught
        async with self.work_lock:
            if self.closing:
                return
            def apply():
                with self.app.lock:
                    now = started if error is not None else datetime.now(timezone.utc)
                    if kind == "plan":
                        self.app.apply_eos_plan(result, now, error)
                    else:
                        self.app.apply_eos_forecast(result, now, error)
            await self.hass.async_add_executor_job(apply)
            await self._async_publish_snapshot()

    def _schedule_accounting_refresh(self):
        """Refresh accounting data without holding the device-control lock."""
        ledger = self.accounting
        if not isinstance(ledger, Accounting) or (self.accounting_refresh_task and not self.accounting_refresh_task.done()):
            return
        detached = copy(ledger)
        detached.settings = deepcopy(ledger.settings)
        settings = deepcopy(ledger.settings)
        self.accounting_refresh_task = self.hass.async_create_background_task(
            self._async_refresh_accounting(ledger, detached, settings, self.accounting_revision), "EOS accounting refresh")

    async def _async_refresh_accounting(self, ledger, detached, settings, revision):
        try:
            await self.hass.async_add_executor_job(
                detached.refresh_eos, self.app.config.eos,
                self.app.config.options["battery_resource"], datetime.now(timezone.utc))
        except Exception as error:
            self.report_failure('accounting_refresh', error, 'accounting')
            return
        async with self.work_lock:
            if (self.closing or self.accounting is not ledger or ledger.settings != settings
                    or self.accounting_revision != revision):
                return
            for key in ("last_eos_attempt", "eos_battery", "eos_error", "eos_failure_details",
                        "last_pv_attempt", "pv_tariff", "pv_error", "pv_failure_details"):
                setattr(ledger, key, getattr(detached, key))
            self.report_success('accounting_refresh')
            for key in ('eos_error', 'pv_error'):
                if getattr(ledger, key):
                    self.report_notice('accounting/' + key, key, getattr(ledger, key.replace('_error', '_failure_details')))
                else:
                    self.report_success('accounting/' + key)

    async def async_change(self, *, enabled=None, settings=None, control=None):
        area = 'api/control' if enabled is not None or control is not None else 'api/settings'
        async with self.work_lock:
            if self.closing:
                raise ValueError("Integration is stopping")
            def change(settings=settings):
                with self.app.lock:
                    now = datetime.now(timezone.utc)
                    if settings is not None:
                        settings = settings_payload(settings, self.app.config.zone)
                    previous_goals = [(vehicle, self._desired_goal(vehicle, now))
                                      for vehicle in self._vehicle_controllers()]
                    previous_limits = ((self.app.battery_sync_managed(), self.app.battery_limits_request())
                                       if isinstance(self.app, Controller) else None)
                    manage_limits = bool(settings and settings.keys() & {"battery_min_soc", "battery_max_soc"})
                    if enabled is not None:
                        self.app.set_armed(enabled)
                    if control is not None:
                        self.app.set_control(**control)
                    if settings is not None and "vehicle_id" in settings:
                        identity=settings["vehicle_id"]
                        if not hasattr(self.app,"change_vehicle_settings"):
                            raise ValueError("No vehicle fleet configured")
                        self.app.change_vehicle_settings(identity,{key:value for key,value in settings.items() if key!="vehicle_id"})
                        settings=None
                    if settings is not None:
                        values = changed_settings(self.app.config.daily, settings,
                                                  self.app.config.options["regulation_interval_s"])
                        self.app.config.update(values, manage_battery_limits=manage_limits)
                        if hasattr(self.app,"persist_primary_settings"):
                            self.app.persist_primary_settings()
                    # The panel submits battery bounds with every vehicle edit.
                    # Preserve an existing confirmation (and any in-flight sync)
                    # when only the departure or target changed. The first explicit
                    # save still opts into managed limits, even for default bounds.
                    if manage_limits and (previous_limits is None or previous_limits !=
                            (self.app.battery_sync_managed(), self.app.battery_limits_request())):
                        self.battery_sync_revision += 1
                        self.app.battery_limits_confirmed = None
                        self.app.battery_limits_confirmed_at = None
                        self.app.sync_battery_limits(now, monotonic(), force=True)
                    if hasattr(self.app, 'share_general_settings'):
                        self.app.share_general_settings()
                    for vehicle, previous in previous_goals:
                        if previous != self._desired_goal(vehicle, now):
                            vehicle.goal_sync_revision += 1
                            vehicle.goal_at = None
                    return self.app.snapshot(datetime.now(timezone.utc))
            try:
                result = await self.hass.async_add_executor_job(change)
            except Exception as error:
                self.report_failure(area, error, 'invalid_settings' if isinstance(error, ValueError) else 'change_unconfirmed')
                # A failed release already disarms the core; expose its pending
                # state immediately instead of showing an obsolete enabled switch.
                result = await self.hass.async_add_executor_job(self.app.snapshot, datetime.now(timezone.utc))
                self.async_set_updated_data(result)
                raise
            self._schedule_battery_sync()
            self._schedule_goal_sync()
            self.report_success(area)
            self.async_set_updated_data(result)

    def _accounting(self):
        if self.accounting is None:
            self.accounting = Accounting(self.app.config.directory, self.app.config.zone)
        if isinstance(self.app,Controller):
            self.accounting.capacity_override=self.app.battery_group_capacity()
        return self.accounting

    async def async_accounting(self, values):
        async with self.work_lock:
            if self.closing:
                raise ValueError("Integration is stopping")
            def read():
                ledger = self._accounting()
                if "settings" in values:
                    if values.keys() != {"settings"}:
                        raise ValueError("Unexpected settings fields")
                    ledger.configure(values["settings"])
                    self.accounting_revision += 1
                    return {"ok":True}
                report = ledger.report(values, datetime.now(timezone.utc))
                if report.get('period') == 'day':
                    # The power profile of the day from the local minute history (about two days).
                    zone = self.app.config.options['timezone']
                    start, end = day_bounds(report['date'], zone)
                    report['power_profile'] = power_profile(self.app.history.read_range(start, end), report['date'], zone,
                                                            origin=battery_origin(report))
                if report.get('period') in {'day', 'month', 'year'}:
                    # The PV report's forecast for the rest of the period, from the current EOS forecast.
                    report['pv_forecast'] = pv_forecast((self.data or {}).get('forecast'), report,
                                                        datetime.now(timezone.utc), self.app.config.options['timezone'])
                return report
            result = await self.hass.async_add_executor_job(read)
        if "settings" in values:
            self.accounting_cache.clear()
            return result
        # Network history is read outside the control lock. A slow database must
        # never delay a scheduled charge or fresh local safety measurements.
        key = (result["period"],result["date"],result["started"],repr(result["settings"]),repr(result["effective"]),repr(result.get("pv_tariff")))
        cached = self.accounting_cache.get(key)
        if cached is not None and monotonic()-cached[0] < 600:
            return self._accounting_result(merge_reconstruction(result,deepcopy(cached[1])))
        vehicles = [(identity,app.config) for identity,app,_ in getattr(self.app,"controllers",[])]
        try:
            historical = await self.hass.async_add_executor_job(
                reconstruct,self.app.config,deepcopy(result),datetime.now(timezone.utc),vehicles)
        except (OSError, ValueError, KeyError, TypeError) as error:
            result["historical_error"] = True
            self.report_failure('accounting_history', error, 'history_unavailable')
            return self._accounting_result(result)
        self.report_success('accounting_history')
        if len(self.accounting_cache) >= 32:
            self.accounting_cache.pop(next(iter(self.accounting_cache)))
        self.accounting_cache[key] = (monotonic(),historical)
        return self._accounting_result(merge_reconstruction(result,deepcopy(historical)))

    def _accounting_result(self, result):
        if result['period'] == 'day' and result['date'] == datetime.now(self.app.config.zone).date().isoformat():
            self.day_historical = deepcopy(result)
        options = self.app.config.options
        consumers = ['house'] + (['heat'] if options.get('heat_entity') else []) + (['car'] if options.get('wallbox_type') != 'none' else [])
        return report_values(result, consumers)

    async def async_weather_forecast(self, values):
        if values or self.closing:
            raise ValueError('Invalid weather forecast request')
        result = await self.weather_forecast.async_read(self.app.config.options)
        data, now = self.data or {}, datetime.now(timezone.utc)
        # Pure in-memory presentation of already loaded data; no I/O in the event loop.
        result['hours'] = pv_hours(data.get('forecast'), result['rows'], now, data.get('zone') or self.app.config.options['timezone'],
                                   (data.get('live') or {}).get('weather'))
        result['days'] = weather_days(result['rows'], data.get('pv_forecast_totals'), data.get('pv_today_kwh'), now,
                                      data.get('zone') or self.app.config.options['timezone'])
        if result['status'] != 'available':
            self.report_notice('weather_forecast', result['status'], result.get('error_details'))
        else:
            self.report_success('weather_forecast')
        return result

    async def async_history(self):
        # An unresponsive history database must not block control operations.
        # Separate serialization prevents duplicate concurrent Influx requests.
        async with self.influx_lock:
            if self.closing:
                raise ValueError("Integration is stopping")
            if monotonic() - self.influx_at >= 300:
                self.influx_at = monotonic()
                try:
                    rows = await self.hass.async_add_executor_job(influx_series, self.app.config)
                except Exception as error:
                    self.influx_error = True
                    self.report_failure('influx_history', error, 'history_unavailable')
                else:
                    self.influx_rows = rows
                    self.influx_error = False
                    self.report_success('influx_history')
            async with self.work_lock:
                if self.closing:
                    raise ValueError("Integration is stopping")
                def read():
                    now = datetime.now(timezone.utc)
                    result = {"local": self.app.history.read(now),
                              "influx": self.influx_rows, "influx_error": self.influx_error,
                              "status":'local_history' if not self.app.config.influx.url else
                                  'fetch_failed' if self.influx_error else 'history_available' if self.influx_rows else 'no_samples'}
                    if callable(getattr(type(self.app), "vehicle_histories", None)):
                        result["vehicles"] = self.app.vehicle_histories(now)
                    return result
                return await self.hass.async_add_executor_job(read)

    async def async_stop(self):
        # Mark shutdown before waiting for an in-flight tick, so a service
        # disappearing during HA shutdown does not clear the saved user intent.
        self.closing = True
        if self.battery_sync_task and not self.battery_sync_task.done():
            self.battery_sync_task.cancel()
        for task in self.goal_sync_tasks.values():
            if not task.done():
                task.cancel()
        for task in self.vehicle_sync_tasks.values():
            if not task.done():
                task.cancel()
        for task in self.eos_poll_tasks.values():
            if not task.done():
                task.cancel()
        if self.accounting_refresh_task and not self.accounting_refresh_task.done():
            self.accounting_refresh_task.cancel()
        async with self.work_lock:
            await self.hass.async_add_executor_job(partial(self.app.set_armed, False, persist=False))

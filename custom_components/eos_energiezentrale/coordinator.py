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
from .energy.drivers import DeviceNotReady
from .energy.settings import daily_settings

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
        self.eos_poll_tasks = {}
        self.eos_poll_started = {"plan": float("-inf"), "solution": float("-inf")}
        if isinstance(app, Controller):
            app.external_eos_polling = True

    def _tick(self):
        with self.app.lock:
            try:
                self.app.tick(datetime.now(timezone.utc), monotonic())
                self.app.errors.pop("device_pending", None)
                if self.app.armed:
                    self.app.errors.pop("runtime", None)
            except DeviceNotReady as error:
                self.app.errors["device_pending"] = error.entity
            except Exception as error:
                self.app.errors.pop("device_pending", None)
                self.app.errors["runtime"] = type(error).__name__
                entity = getattr(error, "entity", None)
                self.app.last_failure = {
                    "type": type(error).__name__,
                    "step": getattr(self.app, "control_step", "unknown"),
                    "at": datetime.now(timezone.utc).isoformat(),
                    "entity": entity if isinstance(entity, str) and ENTITY.fullmatch(entity) else None}
                _LOGGER.exception("Energy control failed during %s", self.app.last_failure["step"])
                self.app.armed = False
                self.app.restore_pending = False
                if not self.closing:
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
                result["accounting"] = ledger.report({"period":"day"}, now)
                self.app.errors.pop("accounting", None)
            except (OSError, sqlite3.Error, ValueError, TypeError, KeyError) as error:
                # Reporting failures must never stop an otherwise safe charge.
                self.app.errors["accounting"] = type(error).__name__
                _LOGGER.warning("Energy accounting unavailable: %s", type(error).__name__)
            result["errors"] = dict(self.app.errors)
            return result

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
            return result

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
        except Exception:
            _LOGGER.exception("EOS accounting refresh failed")
            return
        async with self.work_lock:
            if (self.closing or self.accounting is not ledger or ledger.settings != settings
                    or self.accounting_revision != revision):
                return
            for key in ("last_eos_attempt", "eos_battery", "eos_error",
                        "last_pv_attempt", "pv_tariff", "pv_error"):
                setattr(ledger, key, getattr(detached, key))

    async def async_change(self, *, enabled=None, settings=None):
        async with self.work_lock:
            if self.closing:
                raise ValueError("Integration is stopping")
            def change(settings=settings):
                with self.app.lock:
                    if enabled is not None:
                        self.app.set_armed(enabled)
                    if settings is not None and "vehicle_id" in settings:
                        identity=settings["vehicle_id"]
                        if not hasattr(self.app,"change_vehicle_settings"):
                            raise ValueError("No vehicle fleet configured")
                        self.app.change_vehicle_settings(identity,{key:value for key,value in settings.items() if key!="vehicle_id"})
                        settings=None
                    if settings is not None:
                        values = daily_settings({**self.app.config.daily, **settings},
                                                self.app.config.options["regulation_interval_s"])
                        manage_limits = bool(settings.keys() & {"battery_min_soc", "battery_max_soc"})
                        self.app.config.update(values, manage_battery_limits=manage_limits)
                        if hasattr(self.app,"persist_primary_settings"):
                            self.app.persist_primary_settings()
                        if manage_limits:
                            self.app.sync_battery_limits(datetime.now(timezone.utc), monotonic(), force=True)
                    return self.app.snapshot(datetime.now(timezone.utc))
            try:
                result = await self.hass.async_add_executor_job(change)
            except Exception:
                # A failed release already disarms the core; expose its pending
                # state immediately instead of showing an obsolete enabled switch.
                result = await self.hass.async_add_executor_job(self.app.snapshot, datetime.now(timezone.utc))
                self.async_set_updated_data(result)
                raise
            self.async_set_updated_data(result)

    def _accounting(self):
        if self.accounting is None:
            self.accounting = Accounting(self.app.config.directory, self.app.config.zone)
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
                return ledger.report(values, datetime.now(timezone.utc))
            result = await self.hass.async_add_executor_job(read)
        if "settings" in values:
            self.accounting_cache.clear()
            return result
        # Network history is read outside the control lock. A slow database must
        # never delay a scheduled charge or fresh local safety measurements.
        key = (result["period"],result["date"],result["started"],repr(result["settings"]),repr(result["effective"]),repr(result.get("pv_tariff")))
        cached = self.accounting_cache.get(key)
        if cached is not None and monotonic()-cached[0] < 600:
            return merge_reconstruction(result,deepcopy(cached[1]))
        vehicles = [(identity,app.config) for identity,app,_ in getattr(self.app,"controllers",[])]
        try:
            historical = await self.hass.async_add_executor_job(
                reconstruct,self.app.config,deepcopy(result),datetime.now(timezone.utc),vehicles)
        except (OSError, ValueError, KeyError, TypeError):
            result["historical_error"] = True
            return result
        if len(self.accounting_cache) >= 32:
            self.accounting_cache.pop(next(iter(self.accounting_cache)))
        self.accounting_cache[key] = (monotonic(),historical)
        return merge_reconstruction(result,deepcopy(historical))

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
                except Exception:
                    self.influx_error = True
                else:
                    self.influx_rows = rows
                    self.influx_error = False
            async with self.work_lock:
                if self.closing:
                    raise ValueError("Integration is stopping")
                def read():
                    now = datetime.now(timezone.utc)
                    result = {"local": self.app.history.read(now),
                              "influx": self.influx_rows, "influx_error": self.influx_error}
                    if callable(getattr(type(self.app), "vehicle_histories", None)):
                        result["vehicles"] = self.app.vehicle_histories(now)
                    return result
                return await self.hass.async_add_executor_job(read)

    async def async_stop(self):
        # Mark shutdown before waiting for an in-flight tick, so a service
        # disappearing during HA shutdown does not clear the saved user intent.
        self.closing = True
        for task in self.eos_poll_tasks.values():
            if not task.done():
                task.cancel()
        if self.accounting_refresh_task and not self.accounting_refresh_task.done():
            self.accounting_refresh_task.cancel()
        async with self.work_lock:
            await self.hass.async_add_executor_job(partial(self.app.set_armed, False, persist=False))

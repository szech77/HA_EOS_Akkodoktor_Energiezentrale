"""Serialize all controller work outside Home Assistant's event loop."""
import asyncio
from datetime import datetime, timezone
from functools import partial
import logging
from time import monotonic

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .energy.history import influx_series
from .energy.clients import ENTITY
from .energy.drivers import DeviceNotReady
from .energy.settings import daily_settings

_LOGGER = logging.getLogger(__name__)


class EnergyCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, entry, app):
        super().__init__(hass, _LOGGER, name="EOS Energiezentrale", config_entry=entry)
        self.entry, self.app = entry, app
        self.work_lock = asyncio.Lock()
        self.closing = False
        self.influx_at = -1000
        self.influx_rows = []
        self.influx_error = False

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
            return self.app.snapshot(datetime.now(timezone.utc))

    async def _async_update_data(self):
        async with self.work_lock:
            if self.closing:
                return self.data
            try:
                return await self.hass.async_add_executor_job(self._tick)
            except (OSError, ValueError) as error:
                raise UpdateFailed("Local controller unavailable") from error

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

    async def async_history(self):
        async with self.work_lock:
            if self.closing:
                raise ValueError("Integration is stopping")
            def read():
                if monotonic() - self.influx_at >= 300:
                    self.influx_at = monotonic()
                    try:
                        self.influx_rows = influx_series(self.app.config)
                        self.influx_error = False
                    except Exception:
                        self.influx_error = True
                now=datetime.now(timezone.utc)
                result={"local": self.app.history.read(now),
                        "influx": self.influx_rows, "influx_error": self.influx_error}
                if callable(getattr(type(self.app),"vehicle_histories",None)):
                    result["vehicles"]=self.app.vehicle_histories(now)
                return result
            return await self.hass.async_add_executor_job(read)

    async def async_stop(self):
        # Mark shutdown before waiting for an in-flight tick, so a service
        # disappearing during HA shutdown does not clear the saved user intent.
        self.closing = True
        async with self.work_lock:
            await self.hass.async_add_executor_job(partial(self.app.set_armed, False, persist=False))

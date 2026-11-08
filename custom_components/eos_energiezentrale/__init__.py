"""EOS Energiezentrale custom integration."""
from pathlib import Path

from homeassistant.const import EVENT_HOMEASSISTANT_STOP, Platform
from homeassistant.core import callback
from homeassistant.exceptions import ConfigEntryError, ConfigEntryNotReady
from homeassistant.helpers.event import async_track_utc_time_change
from homeassistant.helpers import config_validation as cv

from .adapter import HomeAssistantAdapter
from .const import DEFAULTS, DOMAIN
from .coordinator import EnergyCoordinator
from .energy.controller import Controller
from .energy.settings import Configuration
from .frontend import async_register_frontend, async_remove_panel
from .validation import validate_options

PLATFORMS = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH,
             Platform.NUMBER, Platform.SELECT, Platform.TEXT]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup_entry(hass, entry):
    options = {**DEFAULTS, **entry.data, **entry.options, "timezone": hass.config.time_zone}
    adapter = HomeAssistantAdapter(hass)
    directory = Path(hass.config.path(".storage", DOMAIN, entry.entry_id))

    def create():
        validate_options(options)
        directory.mkdir(parents=True, exist_ok=True)
        return Controller(adapter, Configuration(options, adapter, directory))

    try:
        app = await hass.async_add_executor_job(create)
    except (ValueError, TypeError, KeyError) as error:
        raise ConfigEntryError("Invalid energy controller configuration") from error
    except OSError as error:
        raise ConfigEntryNotReady("Cannot initialize energy controller") from error
    coordinator = EnergyCoordinator(hass, entry, app)
    entry.runtime_data = coordinator
    await coordinator.async_config_entry_first_refresh()
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        await async_register_frontend(hass)
    except Exception:
        await coordinator.async_stop()
        await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        raise

    @callback
    def refresh(_now):
        if not coordinator.closing:
            entry.async_create_background_task(hass, coordinator.async_request_refresh(), "EOS refresh")

    entry.async_on_unload(async_track_utc_time_change(hass, refresh, second=list(range(0, 60, 5))))

    async def shutdown(_event):
        await coordinator.async_stop()

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, shutdown))
    entry.async_on_unload(entry.add_update_listener(async_reload_entry))
    return True


async def async_reload_entry(hass, entry):
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass, entry):
    coordinator = entry.runtime_data
    try:
        await coordinator.async_stop()
    except Exception:
        # Retain the integration and its off switch so an unconfirmed release can be retried.
        coordinator.closing = False
        return False
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        async_remove_panel(hass)
    else:
        coordinator.closing = False
    return unloaded

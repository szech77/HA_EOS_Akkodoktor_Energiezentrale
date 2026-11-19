"""Authenticated HA WebSocket API and same-origin panel resources."""
from functools import partial
from hashlib import sha256
from pathlib import Path
import sqlite3

import probatio as vol
from homeassistant.components import frontend, panel_custom, websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.exceptions import HomeAssistantError

from .const import DOMAIN
from .energy.failures import BackendError
from .energy.localization import load_language

STATIC_URL = "/eos-energiezentrale-static"
PANEL_URL = "eos-energiezentrale"


def asset_version(directory=None):
    directory = directory or Path(__file__).parent / "energy" / "web"
    digest = sha256()
    for path in sorted(directory.iterdir()):
        if path.is_file() and path.suffix in {".js",".html",".css",".svg"}:
            digest.update(path.name.encode())
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


async def async_register_frontend(hass):
    data = hass.data.setdefault(DOMAIN, {})
    if not data.get("registered"):
        await hass.http.async_register_static_paths([
            StaticPathConfig(STATIC_URL, str(Path(__file__).parent / "energy" / "web"), False)])
        websocket_api.async_register_command(hass, websocket_request)
        data["registered"] = True
    version = await hass.async_add_executor_job(asset_version)
    icons_url = STATIC_URL + "/icons.js?v=" + version
    if data.get("icons_url") != icons_url:
        if previous := data.get("icons_url"):
            frontend.remove_extra_js_url(hass, previous)
        # Load globally: the sidebar is visible before the custom panel is opened.
        frontend.add_extra_js_url(hass, icons_url)
        data["icons_url"] = icons_url
    await panel_custom.async_register_panel(
        hass, frontend_url_path=PANEL_URL, webcomponent_name="eos-energy-panel",
        sidebar_title="EOS Energiezentrale", sidebar_icon="eos-energy:logo",
        module_url=STATIC_URL + "/panel.js?v=" + version, require_admin=True,
        config={"asset_version":version},
    )


def async_remove_panel(hass):
    frontend.async_remove_panel(hass, PANEL_URL)
    if icons_url := hass.data.get(DOMAIN, {}).pop("icons_url", None):
        frontend.remove_extra_js_url(hass, icons_url)


@websocket_api.websocket_command({
    vol.Required("type"): DOMAIN + "/request",
    vol.Required("action"): vol.In(["snapshot", "history", "language", "settings", "control", "accounting", "weather_forecast", "client_event"]),
    vol.Optional("values", default={}): dict,
    vol.Optional("language"): str,
})
@websocket_api.require_admin
@websocket_api.async_response
async def websocket_request(hass, connection, msg):
    action, values = msg["action"], msg.get("values", {})
    if action == 'client_event':
        # Discard pending reports from cached older panels, including on restart.
        # ACK once so the old browser stops retrying; do not inspect or log data.
        connection.send_result(msg['id'], {'ok':True})
        return
    entries = hass.config_entries.async_entries(DOMAIN)
    coordinator = entries[0].runtime_data if entries else None
    if coordinator is None or coordinator.closing:
        # A panel reconnecting during HA startup is not a backend incident.
        connection.send_error(msg["id"], "not_ready", "Integration is not loaded")
        return
    try:
        if action == "snapshot":
            result = coordinator.data
        elif action == "accounting":
            result = await coordinator.async_accounting(values)
        elif action == "history":
            result = await coordinator.async_history()
        elif action == "weather_forecast":
            result = await coordinator.async_weather_forecast(values)
        elif action == "language":
            result = await hass.async_add_executor_job(partial(
                load_language, coordinator.app.config.options["language"],
                ha_language=msg.get("language") or hass.config.language))
        else:
            if action == "control":
                if values.keys() == {"enabled"} and type(values["enabled"]) is bool:
                    await coordinator.async_change(enabled=values["enabled"])
                elif (values and values.keys() <= {"battery", "vehicle"}
                        and all(type(value) is bool for value in values.values())):
                    await coordinator.async_change(control=dict(values))
                else:
                    raise ValueError("Explicit boolean required")
            else:
                await coordinator.async_change(settings=values)
            result = {"ok": True}
        coordinator.report_success('api/' + action)
        connection.send_result(msg["id"], result)
    except ValueError as error:
        code = {"language":"language_invalid","history":"history_invalid","accounting":"invalid_report"}.get(action,"invalid_settings")
        coordinator.report_failure('api/' + action, error, code)
        if isinstance(error, BackendError):
            # Reason and field names come from fixed allow-lists, never from submitted values.
            connection.send_error(msg["id"], code, "Request rejected: " + action, translation_key=code,
                translation_domain=DOMAIN, translation_placeholders={"reason":error.reason, "fields":",".join(error.fields)})
            return
        connection.send_error(msg["id"], code, "Request rejected: " + action)
    except (OSError, sqlite3.Error, HomeAssistantError, TimeoutError) as error:
        code = {"language":"language_unavailable","history":"history_unavailable","accounting":"report_unavailable"}.get(action,"change_unconfirmed")
        coordinator.report_failure('api/' + action, error, code)
        connection.send_error(msg["id"], code, "Request could not be completed: " + action)
    except Exception as error:
        coordinator.report_failure('api/' + action, error, 'internal_error')
        connection.send_error(msg["id"], "internal_error", "Unexpected error during " + action)

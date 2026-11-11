"""NRGkick Gen2 local JSON API, without HA measurement or control entities.

Protocol: https://nrgkick.com/wp-content/uploads/local_api_docu_simulate-1.html
"""
import base64
from http.client import HTTPException
from datetime import datetime, timezone
from math import floor
import json
import os
import re
from time import monotonic
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, ProxyHandler, build_opener

from ..clients import NoRedirect, base_url
from ..contracts import WallboxDriver, WallboxReading, WallboxFeatures, PluginInfo, PluginField
from ..sanitiser import bounded


class NRGkickAPIError(OSError):
    """Safe error text: no credentials, URLs or private response bodies."""


def flag(value):
    if type(value) is bool or type(value) is int and value in (0, 1):
        return bool(value)
    raise NRGkickAPIError("Invalid NRGkick boolean response")


class NRGkickLocal(WallboxDriver):
    info = PluginInfo("nrgkick_local", "NRGkick Gen2 local JSON API", "wallbox")
    configuration = (
        PluginField("url", "Local API URL", "text", default="http://nrgkick.local"),
        PluginField("phase_switching", "Phase switching enabled in NRGkick app", "boolean", default=False),
        PluginField("username", "Basic Auth username (optional)", "text", required=False, default=""),
        PluginField("password_env", "Basic Auth password environment variable (optional)", "text", required=False, default=""),
    )

    def __init__(self, ha, params):
        from ..plugin_parameters import parameters
        values = parameters(self.configuration, params)
        self.url = base_url(values["url"])
        self.username, self.password_env = values["username"] or "", values["password_env"] or ""
        if (bool(self.username) != bool(self.password_env) or ":" in self.username
                or any(ord(c) < 32 for c in self.username)
                or self.password_env and not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", self.password_env)):
            raise ValueError("Configure both NRGkick username and password environment variable")
        parsed = urlsplit(self.url)
        if parsed.port == 0:
            raise ValueError("Invalid NRGkick API port")
        self.device_key = f"nrgkick:{parsed.scheme}://{parsed.hostname.lower()}:{parsed.port or (443 if parsed.scheme == 'https' else 80)}"
        self.ids = dict.fromkeys(("power", "status", "enable", "current", "phases"), "")
        self.phase_switching = values["phase_switching"]
        self.features = WallboxFeatures(phase_switching=self.phase_switching, optional_connection=True)
        self.opener = build_opener(ProxyHandler({}), NoRedirect())
        self.zero_after = self.zero_sample = self.phase_requested = None

    def _request(self, path):
        headers = {"Accept": "application/json", "Cache-Control": "no-cache"}
        if self.password_env:
            secret = os.environ.get(self.password_env)
            if not secret:
                raise NRGkickAPIError("NRGkick API credential is unavailable")
            token = base64.b64encode(f"{self.username}:{secret}".encode()).decode("ascii")
            headers["Authorization"] = "Basic " + token
        try:
            with self.opener.open(Request(self.url + path, headers=headers), timeout=3) as response:
                raw = response.read(262145)
            if len(raw) > 262144:
                raise ValueError("Response too large")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError("Expected JSON object")
            return result
        except (OSError, HTTPException, ValueError, TypeError):
            raise NRGkickAPIError("NRGkick local API request failed") from None

    def _control(self):
        control = self._request("/control")
        if (bounded(control.get("current_set"), 6, 32) is None
                or type(control.get("phase_count")) is not int or control["phase_count"] not in (1, 2, 3)):
            raise NRGkickAPIError("Incomplete NRGkick control response")
        flag(control.get("charge_pause"))
        return control

    def _set(self, **values):
        self._request("/control?" + urlencode(values))
        actual = self._control()
        for key, desired in values.items():
            if key == "charge_pause":
                confirmed = flag(actual.get(key)) == bool(desired)
            else:
                value = bounded(actual.get(key), 0, 32)
                confirmed = value is not None and abs(value - float(desired)) < .001
            if not confirmed:
                raise NRGkickAPIError("NRGkick did not confirm requested setting")
        return actual

    def _read(self, states, now):
        try:
            return self._sample(now)
        except NRGkickAPIError:
            # Telemetry failure must still allow an independent confirmed pause
            # through /control, including during explicit disarm/unload.
            return WallboxReading(None, "unavailable", False, None, None, None, None, None)

    def _sample(self, now):
        info = self._request("/info?raw&general&connector&grid")
        control = self._control()
        values = self._request("/values?raw&powerflow&general")
        try:
            rated = bounded(info["general"].get("rated_current"), 6, 32)
            attachment = info["connector"]
            limit = bounded(attachment.get("max_current"), 6, 32)
            phases = attachment.get("phase_count")
            grid = info["grid"].get("phases")
            self.features = WallboxFeatures(phase_switching=bool(self.phase_switching and phases == 3 and grid == 7), optional_connection=True)
            maximum = floor(min(rated, limit) * 10 + 1e-9) / 10 if rated is not None and limit is not None else None
            general, power = values["general"], values["powerflow"]
            status = general.get("status")
            if isinstance(status, str): status = status.upper()
            status = {0:"unknown",1:"disconnected",2:"connected",3:"charging",6:"error",7:"wakeup",
                      "UNKNOWN":"unknown","STANDBY":"disconnected","CONNECTED":"connected",
                      "CHARGING":"charging","ERROR":"error","WAKEUP":"wakeup"}.get(status,"unknown")
            flag(general.get("charge_permitted"))
            if general.get("error_code") not in (0, "NO_ERROR") or general.get("rcd_trigger") not in (0, "NO_FAULT"):
                status = "error"
            selected = control["phase_count"]
            if type(phases) is not int or phases not in (1, 3) or type(grid) is not int or grid not in (1, 7):
                selected = None
            elif selected in (1, 3):
                selected = min(selected, phases, 3 if grid == 7 else 1)
            else:
                selected = None
            relay = general.get("relay_state")
            if status == "charging":
                active = (relay & 14).bit_count() if type(relay) is int and 0 <= relay <= 15 else None
                selected = active if active in (1, 3) else None
            watts = bounded(power.get("total_active_power"), 0, 25000)
            maximum_phases = (min(phases,3 if grid == 7 else 1) if type(phases) is int and phases in (1,3)
                              and type(grid) is int and grid in (1,7) else None)
            if maximum_phases is not None and not self.features.phase_switching:
                maximum_phases = min(maximum_phases,control['phase_count'])
            return WallboxReading(watts, status, not flag(control["charge_pause"]), selected,
                                  float(control["current_set"]), .1, maximum, now if watts is not None else None,
                                  max_phases=maximum_phases, nominal_voltage=bounded(info['grid'].get('voltage'),100,260))
        except (KeyError, TypeError, AttributeError):
            raise NRGkickAPIError("Incomplete NRGkick measurement response") from None

    def _pause(self, state):
        # Always send and confirm pause, even if the previous poll was unavailable.
        self.zero_after = self.zero_sample = self.phase_requested = None
        self._set(charge_pause=1)

    def _phase(self, phases, state):
        if self.phase_requested is not None:
            target, requested_at = self.phase_requested
            if (state.phases == target and not state.enabled and state.sample is not None
                    and state.watts is not None and state.watts <= 30 and state.status == "connected"):
                self.phase_requested = self.zero_after = self.zero_sample = None
                return target == phases
            if monotonic() - requested_at >= 45:
                raise NRGkickAPIError("NRGkick phase setting was not confirmed")
            return False
        if state.phases == phases:
            return True
        if state.enabled or self.zero_after is None:
            self._set(charge_pause=1)
            self.zero_after, self.zero_sample = state.sample, None
            return False
        if (state.watts is None or state.watts > 30 or state.status != "connected"
                or state.sample is None or self.zero_after is None or state.sample <= self.zero_after):
            self.zero_sample = None
            return False
        if self.zero_sample is None:
            self.zero_sample = state.sample
            return False
        if (state.sample - self.zero_sample).total_seconds() < 3:
            return False
        self._set(phase_count=phases)
        self.phase_requested = (phases, monotonic())
        return False

    def _charge(self, amps, state):
        if self.phase_requested is not None:
            raise NRGkickAPIError("NRGkick phase switch is still pending")
        fresh = self._read({}, datetime.now(timezone.utc))
        if (fresh.maximum is None or amps > fresh.maximum or fresh.phases not in (1, 3)
                or fresh.phases != state.phases
                or fresh.nominal_voltage is None or fresh.nominal_voltage != state.nominal_voltage
                or fresh.watts is None or fresh.status not in ("connected", "charging", "wakeup")):
            raise NRGkickAPIError("NRGkick is not ready for requested charging current")
        self._set(current_set=f"{amps:.1f}")
        if not fresh.enabled:
            self._set(charge_pause=0)


PLUGINS = (NRGkickLocal,)

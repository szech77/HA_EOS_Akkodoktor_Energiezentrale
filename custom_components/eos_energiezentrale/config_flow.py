"""Guided setup and separate commissioning options."""
import probatio as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import DEFAULTS, DOMAIN, GROUPS
from .energy.clients import request
from .validation import validate_options


def schema_for(group, values):
    fields = {}
    for key in GROUPS[group]:
        default = values[key]
        if key.endswith("_entity"):
            field = selector.EntitySelector(selector.EntitySelectorConfig(domain="sensor"))
        elif isinstance(default, bool):
            field = selector.BooleanSelector()
        elif key in {"language", "car_soc_scale", "battery_type", "wallbox_type"}:
            choices = {"language": ["auto", "en", "de"], "car_soc_scale": ["factor", "percent"],
                       "battery_type": ["fronius"], "wallbox_type": ["nrgkick"]}[key]
            field = selector.SelectSelector(selector.SelectSelectorConfig(options=choices))
        elif isinstance(default, (int, float)):
            field = vol.Coerce(type(default))
        else:
            field = selector.TextSelector(selector.TextSelectorConfig(
                type=selector.TextSelectorType.PASSWORD if key == "influx_password"
                else selector.TextSelectorType.TEXT, multiline=key.endswith("_parameters")))
        marker = vol.Optional if key in {"influx_url", "influx_user", "influx_password"} else vol.Required
        fields[marker(key, default=default)] = field
    return vol.Schema(fields)


async def check(hass, values, connection=False):
    try:
        validate_options(values)
        if connection:
            await hass.async_add_executor_job(request, values["eos_url"].rstrip("/") + "/v1/config")
    except (ValueError, TypeError, KeyError):
        return {"base": "invalid_config"}
    except OSError:
        return {"base": "cannot_connect"}
    return {}


class ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self):
        self.values = dict(DEFAULTS)

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return await self._step("connection", user_input)

    async def _step(self, group, user_input):
        errors = {}
        if user_input is not None:
            values = {**self.values, **user_input}
            errors = await check(self.hass, values, group == "connection")
            if not errors:
                self.values = values
                groups = list(GROUPS)
                position = groups.index(group) + 1
                if position == len(groups):
                    return self.async_create_entry(title="EOS Energiezentrale", data=self.values)
                return await self._step(groups[position], None)
        return self.async_show_form(step_id="user" if group == "connection" else group,
                                    data_schema=schema_for(group, {**self.values, **(user_input or {})}),
                                    errors=errors)

    async def async_step_sensors(self, user_input=None):
        return await self._step("sensors", user_input)

    async def async_step_hardware(self, user_input=None):
        return await self._step("hardware", user_input)

    async def async_step_limits(self, user_input=None):
        return await self._step("limits", user_input)

    async def async_step_history(self, user_input=None):
        return await self._step("history", user_input)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return OptionsFlow()


class OptionsFlow(config_entries.OptionsFlow):
    async def async_step_init(self, user_input=None):
        return self.async_show_menu(step_id="init", menu_options=list(GROUPS))

    async def _step(self, group, user_input):
        values = {**DEFAULTS, **self.config_entry.data, **self.config_entry.options, **(user_input or {})}
        errors = {}
        if user_input is not None:
            errors = await check(self.hass, values, group == "connection")
            if not errors:
                return self.async_create_entry(title="", data=values)
        return self.async_show_form(step_id=group, data_schema=schema_for(group, values), errors=errors)

    async def async_step_connection(self, user_input=None):
        return await self._step("connection", user_input)

    async def async_step_sensors(self, user_input=None):
        return await self._step("sensors", user_input)

    async def async_step_hardware(self, user_input=None):
        return await self._step("hardware", user_input)

    async def async_step_limits(self, user_input=None):
        return await self._step("limits", user_input)

    async def async_step_history(self, user_input=None):
        return await self._step("history", user_input)

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
                       "battery_type": ["fronius"], "wallbox_type": ["none", "nrgkick"]}[key]
            field = selector.SelectSelector(selector.SelectSelectorConfig(options=choices))
        elif isinstance(default, (int, float)):
            field = vol.Coerce(type(default))
        else:
            field = selector.TextSelector(selector.TextSelectorConfig(
                type=selector.TextSelectorType.PASSWORD if key == "influx_password"
                else selector.TextSelectorType.TEXT, multiline=key.endswith("_parameters") or key == "vehicles"))
        optional_source = key in {"heat_entity", "car_soc_entity"}
        marker = vol.Optional if optional_source or key in {"influx_url", "influx_user", "influx_password"} else vol.Required
        fields[marker(key, **({} if optional_source and not default else {"default":default}))] = field
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
        self.values = {**DEFAULTS, "wallbox_type":"none", "heat_entity":"", "car_soc_entity":""}

    async def async_step_user(self, user_input=None):
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        return await self._step("connection", user_input)

    async def _step(self, group, user_input):
        errors = {}
        if user_input is not None:
            if group == "sensors":
                user_input = {"heat_entity":"", "car_soc_entity":"", **user_input}
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
        return self.async_show_menu(step_id="init", menu_options=[*GROUPS,"vehicles"])

    async def _step(self, group, user_input):
        if group == "sensors" and user_input is not None:
            user_input = {"heat_entity":"", "car_soc_entity":"", **user_input}
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


    def _vehicle_values(self):
        return {**DEFAULTS,**self.config_entry.data,**self.config_entry.options}

    def _vehicle_rows(self):
        import json
        values=self._vehicle_values()
        rows=json.loads(values.get("vehicles","[]"))
        if not rows and values["wallbox_type"]!="none":
            rows=[{"id":"vehicle1","name":values["vehicle_name"],"resource":values["vehicle_resource"],
                   "soc_entity":values["car_soc_entity"],"soc_scale":values["car_soc_scale"],
                   "capacity_wh":values["capacity_wh"],"charging_efficiency":values["charging_efficiency"],
                   "max_current_a":values["max_current_a"],"wallbox_type":values["wallbox_type"],
                   "wallbox_parameters":json.loads(values["wallbox_parameters"])}]
        return rows

    async def async_step_vehicles(self,user_input=None):
        return self.async_show_menu(step_id="vehicles",menu_options=["vehicle_add","vehicle_edit","vehicle_remove"])

    async def _choose_vehicle(self,step_id,user_input):
        rows=self._vehicle_rows()
        if not rows:
            return self.async_abort(reason="no_vehicles")
        if user_input is None:
            return self.async_show_form(step_id=step_id,data_schema=vol.Schema({
                vol.Required("vehicle_id"):selector.SelectSelector(selector.SelectSelectorConfig(
                    options=[{"value":row["id"],"label":row.get("name",row["id"])} for row in rows]))}))
        identity=user_input.get("vehicle_id")
        if not any(row["id"]==identity for row in rows):
            return self.async_abort(reason="no_vehicles")
        return identity

    async def async_step_vehicle_remove(self,user_input=None):
        import json
        selected=await self._choose_vehicle("vehicle_remove",user_input)
        if not isinstance(selected,str):
            return selected
        rows=[row for row in self._vehicle_rows() if row["id"]!=selected]
        values={**self._vehicle_values(),"vehicles":json.dumps(rows)}
        if not rows:
            values["wallbox_type"]="none"
        return self.async_create_entry(title="",data=values)

    async def async_step_vehicle_add(self,user_input=None):
        return await self._vehicle_form("vehicle_add",None,user_input)

    async def async_step_vehicle_edit(self,user_input=None):
        if user_input is None or "vehicle_id" in user_input:
            selected=await self._choose_vehicle("vehicle_edit",user_input)
            if not isinstance(selected,str):
                return selected
            self._editing_vehicle=selected
            return await self._vehicle_form("vehicle_edit",selected,None)
        return await self._vehicle_form("vehicle_edit",self._editing_vehicle,user_input)

    async def _vehicle_form(self,step_id,identity,user_input):
        import json
        from .energy.drivers import NRGkick
        rows=self._vehicle_rows()
        old=next((row for row in rows if row["id"]==identity),{})
        index=len(rows)+1
        defaults={"id":identity or f"vehicle{index}","name":old.get("name","E-Auto"),
                  "resource":old.get("resource",f"ev{index}"),"soc_entity":old.get("soc_entity",""),
                  "soc_scale":old.get("soc_scale","factor"),"capacity_wh":old.get("capacity_wh",77000),
                  "charging_efficiency":old.get("charging_efficiency",.9),"max_current_a":old.get("max_current_a",16)}
        ids={**NRGkick.defaults,**old.get("wallbox_parameters",{})}
        defaults.update({"wallbox_"+key:value for key,value in ids.items()})
        errors={}
        if user_input is not None:
            row={key:user_input.get(key,"") for key in ("id","name","resource","soc_entity","soc_scale","capacity_wh","charging_efficiency","max_current_a")}
            if identity is not None and row["id"]!=identity:
                errors={"base":"invalid_config"}
            row.update(wallbox_type="nrgkick",wallbox_parameters={key:user_input["wallbox_"+key] for key in NRGkick.defaults})
            updated=[row if item["id"]==identity else item for item in rows]
            if identity is None:
                updated.append(row)
            values={**self._vehicle_values(),"vehicles":json.dumps(updated)}
            errors=errors or await check(self.hass,values)
            if not errors:
                return self.async_create_entry(title="",data=values)
            defaults.update(user_input)
        fields={}
        for key,value in defaults.items():
            if key=="soc_entity" or key.startswith("wallbox_"):
                domain="switch" if key=="wallbox_enable" else "number" if key in {"wallbox_current","wallbox_phases"} else "sensor"
                field=selector.EntitySelector(selector.EntitySelectorConfig(domain=domain))
            elif key=="soc_scale":
                field=selector.SelectSelector(selector.SelectSelectorConfig(options=["factor","percent"]))
            elif key in {"capacity_wh","max_current_a"}:
                field=vol.Coerce(int)
            elif key=="charging_efficiency":
                field=vol.Coerce(float)
            else:
                field=str
            marker=vol.Optional if key=="soc_entity" else vol.Required
            fields[marker(key,**({} if key=="soc_entity" and not value else {"default":value}))]=field
        return self.async_show_form(step_id=step_id,data_schema=vol.Schema(fields),errors=errors)

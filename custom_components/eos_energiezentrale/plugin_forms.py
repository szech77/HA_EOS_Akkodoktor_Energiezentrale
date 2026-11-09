"""HA forms generated exclusively from installed plugin configuration descriptors."""
import json
import probatio as vol
from homeassistant.helpers import selector

from .const import DEFAULTS
from .energy.drivers import BATTERY_DRIVERS, WALLBOX_DRIVERS
from .energy.plugin_parameters import parameters


def plugin_choices(registry,include_none=True):
    return [{"value":key,"label":factory.info.name} for key,factory in registry.items() if include_none or key!="none"]


def plugin_object(factory,supplied=None):
    supplied = supplied or {}
    if isinstance(supplied,str): supplied = json.loads(supplied)
    fields = {}
    defaults = {}
    for field in factory.configuration:
        value = supplied.get(field.key,field.default)
        if field.kind=="entity":
            control = selector.EntitySelector(selector.EntitySelectorConfig(domain=list(field.domains)))
        elif field.kind=="boolean": control = selector.BooleanSelector()
        elif field.kind=="choice": control = selector.SelectSelector(selector.SelectSelectorConfig(options=list(field.choices)))
        elif field.kind=="number": control = selector.NumberSelector(selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX))
        else:
            control = selector.TextSelector(selector.TextSelectorConfig(multiline=field.kind=="json"))
            if field.kind=="json" and isinstance(value,dict): value = json.dumps(value,ensure_ascii=False)
        descriptor = {"label":field.label,"required":field.required,"selector":control}
        if value is not None and value!="":
            descriptor["default"] = value
            defaults[field.key] = value
        fields[field.key] = descriptor
    return selector.ObjectSelector(selector.ObjectSelectorConfig(fields=fields)), defaults


def configured(factory,values):
    checked = parameters(factory.configuration,values)
    factory(None,checked)  # Constructor and entity-map validation, no device access.
    return checked


class PluginFormMixin:
    def _fleet_configured(self):
        return not hasattr(self,"values") and bool(json.loads(self._vehicle_values().get("vehicles","[]")))

    async def _hardware_selection(self,user_input=None):
        base = self.values if hasattr(self,"values") else self._vehicle_values()
        if user_input is not None:
            # Existing options/service clients can still submit direct edits.
            if "battery_type" not in user_input:
                return await self._step("hardware",user_input)
            selected = {**base,**user_input}
            if selected["battery_type"] not in BATTERY_DRIVERS or selected["wallbox_type"] not in WALLBOX_DRIVERS:
                return self.async_abort(reason="invalid_plugin")
            for kind in ("battery","wallbox"):
                if selected[kind+"_type"]!=base[kind+"_type"]: selected[kind+"_parameters"]="{}"
            self._hardware_values = selected
            return await self.async_step_hardware_parameters()
        fields = {vol.Required("battery_type",default=base["battery_type"]):selector.SelectSelector(selector.SelectSelectorConfig(options=plugin_choices(BATTERY_DRIVERS)))}
        if not self._fleet_configured():
            fields[vol.Required("wallbox_type",default=base["wallbox_type"])] = selector.SelectSelector(selector.SelectSelectorConfig(options=plugin_choices(WALLBOX_DRIVERS)))
            fields[vol.Required("vehicle_name",default=base["vehicle_name"])] = str
        return self.async_show_form(step_id="hardware",data_schema=vol.Schema(fields))

    async def async_step_hardware_parameters(self,user_input=None):
        values = self._hardware_values
        errors = {}
        if user_input is not None:
            try:
                payload = {key:values[key] for key in ("battery_type","wallbox_type","vehicle_name")}
                for kind,registry in (("battery",BATTERY_DRIVERS),("wallbox",WALLBOX_DRIVERS)):
                    if kind=="wallbox" and self._fleet_configured():
                        payload[kind+"_parameters"] = values[kind+"_parameters"]
                        continue
                    payload[kind+"_parameters"] = json.dumps(configured(registry[values[kind+"_type"]],user_input.get(kind+"_parameters",{})))
                return await self._step("hardware",payload)
            except (ValueError,KeyError,TypeError): errors={"base":"invalid_config"}
        fields = {}
        for kind,registry in (("battery",BATTERY_DRIVERS),("wallbox",WALLBOX_DRIVERS)):
            if kind=="wallbox" and self._fleet_configured(): continue
            if not registry[values[kind+"_type"]].configuration: continue
            control,defaults = plugin_object(registry[values[kind+"_type"]],values[kind+"_parameters"])
            fields[vol.Required(kind+"_parameters",default=defaults)] = control
        return self.async_show_form(step_id="hardware_parameters",data_schema=vol.Schema(fields),errors=errors)

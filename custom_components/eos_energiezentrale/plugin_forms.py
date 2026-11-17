"""HA forms generated exclusively from installed plugin configuration descriptors."""
import json
import probatio as vol
from homeassistant.helpers import selector

from .const import DEFAULTS
from .energy.drivers import BATTERY_DRIVERS, WALLBOX_DRIVERS
from .energy.plugin_parameters import parameters
from .flow_translations import _translations, flow_language
from .configuration_logging import configuration_failure, configuration_success
from .energy.failures import PluginParameterError


def plugin_configuration_error(plugin, error):
    """Expose translated, fixed parameter errors without raw exception content."""
    if plugin=='victron_modbus' and isinstance(error,PluginParameterError):
        keys={field.key for field in BATTERY_DRIVERS['victron_modbus'].configuration}
        return {'base':'victron_'+error.parameter if error.parameter in keys else 'victron_parameters'}
    return {'base':'invalid_config'}


def plugin_choices(registry,include_none=True):
    return [{"value":key,"label":factory.info.name} for key,factory in registry.items() if include_none or key!="none"]


def plugin_object(factory,supplied=None,labels=None,choice_labels=None):
    supplied = supplied or {}
    if isinstance(supplied,str): supplied = json.loads(supplied)
    fields = {}
    defaults = {}
    labels=labels or {};choice_labels=choice_labels or {}
    translation_key = f'plugin_{factory.info.kind}_{factory.info.identifier}'
    for field in factory.configuration:
        value = supplied.get(field.key,field.default)
        if field.kind=="entity":
            control = selector.EntitySelector(selector.EntitySelectorConfig(domain=list(field.domains)))
        elif field.kind=="boolean": control = selector.BooleanSelector()
        elif field.kind=="choice":
            translated=choice_labels.get(field.key,{})
            options=([{'value':option,'label':translated.get(option) or option} for option in field.choices]
                     if translated else list(field.choices))
            control = selector.SelectSelector(selector.SelectSelectorConfig(
                options=options,translation_key=f'{translation_key}_{field.key}'))
        elif field.kind=="number":
            # HA defaults to step=1, which rejects fractional plugin parameters in the browser.
            # Hardware-specific ranges and integer constraints remain backend validations.
            control = selector.NumberSelector(selector.NumberSelectorConfig(mode=selector.NumberSelectorMode.BOX,step='any'))
        else:
            control = selector.TextSelector(selector.TextSelectorConfig(multiline=field.kind=="json",
                type=selector.TextSelectorType.PASSWORD if field.kind=='password' else selector.TextSelectorType.TEXT))
            if field.kind=="json" and isinstance(value,dict): value = json.dumps(value,ensure_ascii=False)
        descriptor = {"label":labels.get(field.key) or field.label,"required":field.required,"selector":control}
        if value is not None and value!="" and field.kind!='password':
            descriptor["default"] = value
            defaults[field.key] = value
        fields[field.key] = descriptor
    return selector.ObjectSelector(selector.ObjectSelectorConfig(fields=fields,translation_key=translation_key)), defaults


def _plugin_labels(language,translation_key,choices):
    english=_translations('en').get('selector',{})
    translated=_translations(language).get('selector',{})
    labels={}
    for resource in (english,translated):
        labels.update({key:value['name'] for key,value in resource.get(translation_key,{}).get('fields',{}).items()
                       if value.get('name')})
    options={}
    for key in choices:
        selector_key=f'{translation_key}_{key}'
        options[key]={}
        for resource in (english,translated):
            options[key].update({value:label for value,label in resource.get(selector_key,{}).get('options',{}).items() if label})
    return labels,options


async def async_plugin_object(flow,factory,supplied=None):
    """Send translated labels even when an inner HA dialog lacks localizeValue."""
    key=f'plugin_{factory.info.kind}_{factory.info.identifier}'
    choices=tuple(field.key for field in factory.configuration if field.kind=='choice')
    labels,options=await flow.hass.async_add_executor_job(_plugin_labels,flow_language(flow),key,choices)
    return plugin_object(factory,supplied,labels,options)


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
            # Compatibility for existing clients submitting the single-device form.
            # A legacy edit must never silently discard a configured device list.
            if json.loads(base.get('devices','null')):
                return self.async_abort(reason='use_device_manager')
            selected['devices']='null'
            if selected["battery_type"] not in BATTERY_DRIVERS or selected["wallbox_type"] not in WALLBOX_DRIVERS:
                configuration_failure(self, 'hardware_selection', ValueError('Invalid plugin selection'))
                return self.async_abort(reason="invalid_plugin")
            configuration_success(self, 'hardware_selection')
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
            selected_plugin = None
            try:
                payload = {key:values[key] for key in ("battery_type","wallbox_type","vehicle_name","devices")}
                for kind,registry in (("battery",BATTERY_DRIVERS),("wallbox",WALLBOX_DRIVERS)):
                    if kind=="wallbox" and self._fleet_configured():
                        payload[kind+"_parameters"] = values[kind+"_parameters"]
                        continue
                    selected_plugin = registry[values[kind+"_type"]].info.identifier
                    payload[kind+"_parameters"] = json.dumps(configured(registry[values[kind+"_type"]],user_input.get(kind+"_parameters",{})))
                configuration_success(self, 'hardware_parameters')
                return await self._step("hardware",payload)
            except (ValueError,KeyError,TypeError) as error:
                configuration_failure(self, 'hardware_parameters', error, selected_plugin)
                errors=plugin_configuration_error(selected_plugin,error)
        fields = {}
        for kind,registry in (("battery",BATTERY_DRIVERS),("wallbox",WALLBOX_DRIVERS)):
            if kind=="wallbox" and self._fleet_configured(): continue
            if not registry[values[kind+"_type"]].configuration: continue
            control,defaults = await async_plugin_object(self,registry[values[kind+"_type"]],values[kind+"_parameters"])
            fields[vol.Required(kind+"_parameters",default=defaults)] = control
        return self.async_show_form(step_id="hardware_parameters",data_schema=vol.Schema(fields),errors=errors)

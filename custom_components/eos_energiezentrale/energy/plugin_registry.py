"""Discover only trusted local plugin modules; reject incompatible implementations."""
from collections.abc import Mapping
from dataclasses import asdict, fields
from importlib import import_module
import inspect
import logging
import pkgutil
import re
from types import MappingProxyType

from .contracts import (API_VERSION, BatteryDriver, WallboxDriver, BatteryFeatures,
                        WallboxFeatures, PluginInfo, PluginField, PluginContractError)
from .clients import ENTITY
from .plugin_parameters import parameters
from .device_io import ScopedHardwareAdapter

_LOGGER = logging.getLogger(__name__)
IDENTIFIER = re.compile(r"[a-z][a-z0-9_]{0,47}\Z")
METHODS = {"battery": {"_read":("self","states","now"),"_apply":("self","command","states"),"_release":("self","states")},
           "wallbox": {"_read":("self","states","now"),"_pause":("self","state"),"_phase":("self","phases","state"),"_charge":("self","amps","state")}}


def validate_class(plugin):
    if not inspect.isclass(plugin) or inspect.isabstract(plugin):
        raise PluginContractError("Plugin must be a concrete class")
    info = getattr(plugin,"info",None)
    if (not isinstance(info,PluginInfo) or not isinstance(info.identifier,str) or not IDENTIFIER.fullmatch(info.identifier)
            or type(info.api_version) is not int or info.api_version != API_VERSION
            or not isinstance(info.kind,str) or info.kind not in METHODS or not isinstance(info.name,str)
            or not 1 <= len(info.name.strip()) <= 80 or any(ord(c)<32 or ord(c)==127 for c in info.name)):
        raise PluginContractError("Invalid plugin metadata/version")
    base = BatteryDriver if info.kind=="battery" else WallboxDriver
    if not issubclass(plugin,base):
        raise PluginContractError("Plugin must implement the correct ABC")
    for public in (("read","apply","release") if info.kind=="battery" else ("read","pause","phase","charge")):
        if getattr(plugin,public) is not getattr(base,public):
            raise PluginContractError("Plugins cannot bypass the sanitiser: "+public)
    for method,names in {"__init__":("self","ha","params"),**METHODS[info.kind]}.items():
        function = getattr(plugin,method)
        parameters = list(inspect.signature(function).parameters.values())
        if (inspect.iscoroutinefunction(function) or tuple(p.name for p in parameters)!=names
                or any(p.kind!=inspect.Parameter.POSITIONAL_OR_KEYWORD or p.default is not inspect.Parameter.empty for p in parameters)):
            raise PluginContractError("Invalid plugin signature: "+method)
    configuration = getattr(plugin,"configuration",None)
    if not isinstance(configuration,tuple) or any(not isinstance(field,PluginField) for field in configuration):
        raise PluginContractError("Missing typed configuration schema")
    seen = set()
    for field in configuration:
        if (not isinstance(field.key,str) or not IDENTIFIER.fullmatch(field.key) or field.key in seen
                or not isinstance(field.label,str) or not field.label.strip()
                or type(field.required) is not bool or field.kind not in {"entity","boolean","number","choice","json","text"}
                or not isinstance(field.domains,tuple) or not isinstance(field.choices,tuple)
                or (field.kind=="entity" and (not field.domains or any(domain not in {"sensor","binary_sensor","number","switch","select","input_number","input_boolean","input_select"} for domain in field.domains)))
                or (field.kind=="choice" and (not field.choices or any(not isinstance(choice,str) for choice in field.choices)))):
            raise PluginContractError("Invalid configuration field")
        seen.add(field.key)
    return plugin


def validate_instance(plugin):
    info = plugin.info
    expected = BatteryFeatures if info.kind=="battery" else WallboxFeatures
    if not isinstance(getattr(plugin,"features",None),expected) or any(type(getattr(plugin.features,field.name)) is not bool for field in fields(expected)):
        raise PluginContractError("Invalid plugin features")
    ids = getattr(plugin,"ids",None)
    required = {"soc","charge_power","discharge_power","mode"} if info.kind=="battery" else {"power","status","enable","current","phases"}
    if not isinstance(ids,Mapping) or not required.issubset(ids):
        if info.identifier=="none" and ids=={}:
            return plugin
        raise PluginContractError("Missing entity mapping")
    for key,value in ids.items():
        if not isinstance(key,str) or not isinstance(value,str) or (value and not ENTITY.fullmatch(value)):
            raise PluginContractError("Invalid entity mapping")
    plugin.ids = MappingProxyType(dict(ids))
    return plugin


class PluginFactory:
    def __init__(self,plugin):
        self.plugin_class = validate_class(plugin)
        self.info = plugin.info
        self.configuration = plugin.configuration

    def __call__(self, ha, params):
        scoped_adapter = ScopedHardwareAdapter(ha)
        plugin = validate_instance(self.plugin_class(scoped_adapter, parameters(self.configuration, params)))
        scoped_adapter.bind(plugin.ids.values())
        return plugin


def load_plugins(package_name=__package__+".plugins"):
    package = import_module(package_name)
    registries = {"battery":{},"wallbox":{}}
    errors = {}
    for module in sorted(pkgutil.iter_modules(package.__path__),key=lambda item:item.name):
        if module.name.startswith('_') or module.ispkg:
            continue
        try:
            exported = getattr(import_module(package_name+"."+module.name),"PLUGINS",None)
            if not isinstance(exported,tuple) or not exported:
                raise PluginContractError("Plugin module must export PLUGINS tuple")
            pending = []
            for plugin in exported:
                factory = PluginFactory(plugin)
                key = (factory.info.kind,factory.info.identifier)
                if factory.info.identifier in registries[factory.info.kind] or key in [item[0] for item in pending]:
                    raise PluginContractError("Duplicate plugin identifier")
                pending.append((key,factory))
            for (kind,identity),factory in pending:
                registries[kind][identity] = factory
        except Exception as error:
            # One broken optional plugin must not hide healthy installed devices.
            errors[module.name] = type(error).__name__
            _LOGGER.error("Rejected hardware plugin %s: %s",module.name,error)
    return MappingProxyType(registries["battery"]),MappingProxyType(registries["wallbox"]),MappingProxyType(errors)


def describe(plugin):
    if not isinstance(plugin,(BatteryDriver,WallboxDriver)):
        plugin = getattr(plugin,"driver",None)
    if not isinstance(plugin,(BatteryDriver,WallboxDriver)):
        return None
    return {**asdict(plugin.info),"features":asdict(plugin.features)}

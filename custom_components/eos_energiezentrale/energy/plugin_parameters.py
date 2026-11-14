"""Validate plugin-declared parameters without evaluating configuration as code."""
from copy import deepcopy
import json

from .clients import ENTITY
from .domain import number
from .failures import PluginParameterError


def parameters(schema,supplied):
    if not isinstance(supplied,dict) or supplied.keys()-{field.key for field in schema}:
        raise PluginParameterError("Unknown plugin parameter")
    result = {}
    for field in schema:
        value = supplied.get(field.key,deepcopy(field.default))
        if value in (None,"") and not field.required:
            result[field.key] = value
            continue
        if field.kind=="entity":
            if not isinstance(value,str) or not ENTITY.fullmatch(value) or value.split('.')[0] not in field.domains:
                raise PluginParameterError("Invalid entity: "+field.key, field.key)
        elif field.kind=="boolean":
            if type(value) is not bool: raise PluginParameterError("Invalid boolean: "+field.key, field.key)
        elif field.kind=="number":
            if number(value) is None: raise PluginParameterError("Invalid number: "+field.key, field.key)
            value = float(value)
        elif field.kind=="choice":
            if value not in field.choices: raise PluginParameterError("Invalid choice: "+field.key, field.key)
        elif field.kind=="json":
            try:
                value = json.loads(value) if isinstance(value,str) else deepcopy(value)
            except (ValueError, TypeError) as error:
                raise PluginParameterError("Invalid JSON object: "+field.key, field.key) from error
            if not isinstance(value,dict): raise PluginParameterError("Expected JSON object: "+field.key, field.key)
        elif not isinstance(value,str) or not 1<=len(value)<=200:
            raise PluginParameterError("Invalid text: "+field.key, field.key)
        result[field.key] = value
    return result

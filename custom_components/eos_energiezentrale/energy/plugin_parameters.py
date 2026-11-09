"""Validate plugin-declared parameters without evaluating configuration as code."""
from copy import deepcopy
import json

from .clients import ENTITY
from .domain import number


def parameters(schema,supplied):
    if not isinstance(supplied,dict) or supplied.keys()-{field.key for field in schema}:
        raise ValueError("Unknown plugin parameter")
    result = {}
    for field in schema:
        value = supplied.get(field.key,deepcopy(field.default))
        if value in (None,"") and not field.required:
            result[field.key] = value
            continue
        if field.kind=="entity":
            if not isinstance(value,str) or not ENTITY.fullmatch(value) or value.split('.')[0] not in field.domains:
                raise ValueError("Invalid entity: "+field.key)
        elif field.kind=="boolean":
            if type(value) is not bool: raise ValueError("Invalid boolean: "+field.key)
        elif field.kind=="number":
            if number(value) is None: raise ValueError("Invalid number: "+field.key)
            value = float(value)
        elif field.kind=="choice":
            if value not in field.choices: raise ValueError("Invalid choice: "+field.key)
        elif field.kind=="json":
            value = json.loads(value) if isinstance(value,str) else deepcopy(value)
            if not isinstance(value,dict): raise ValueError("Expected JSON object: "+field.key)
        elif not isinstance(value,str) or not 1<=len(value)<=200:
            raise ValueError("Invalid text: "+field.key)
        result[field.key] = value
    return result

"""Restricted HA entity commands and confirmation shared by plugins."""
from time import monotonic, sleep
from .clients import ENTITY

def entities(defaults, supplied):
    if not isinstance(supplied, dict) or supplied.keys() - defaults.keys():
        raise ValueError("Unbekannte Treiberparameter")
    result = {**defaults, **supplied}
    for name, value in result.items():
        if not value and name == "grid_discharge":
            continue
        domain = defaults[name].split(".")[0] if defaults[name] else "number"
        if not isinstance(value, str) or not ENTITY.fullmatch(value) or not value.startswith(domain + "."):
            raise ValueError(f"Ungültige Entität für {name}")
    return result


class DeviceNotReady(RuntimeError):
    """A mode-dependent control entity is still waiting for its next report."""
    def __init__(self, entity):
        super().__init__(f"Waiting for control entity: {entity}")
        self.entity = entity


class DeviceConfirmationError(ValueError):
    """A local control entity did not confirm the requested state."""
    def __init__(self, entity):
        super().__init__(f"Device state not confirmed: {entity}")
        self.entity = entity


def confirmed_state(ha, entity, matches, timeout=5):
    deadline = monotonic() + timeout
    while True:
        row = ha.state(entity)
        if matches(row):
            return row
        if monotonic() >= deadline:
            raise DeviceConfirmationError(entity)
        sleep(0.4)



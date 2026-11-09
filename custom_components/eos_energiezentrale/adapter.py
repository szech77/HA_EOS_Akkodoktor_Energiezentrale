"""Synchronous driver interface to HA's event loop, only used in an executor."""
from asyncio import run_coroutine_threadsafe
from datetime import datetime, timezone

from .energy.clients import ENTITY
from .energy.domain import number


class StateSnapshot(dict):
    """State batch with the time at which the HA loop finished reading it."""
    captured_at = None


class HomeAssistantAdapter:
    def __init__(self, hass):
        self.hass = hass

    def _wait(self, coroutine):
        pending = run_coroutine_threadsafe(coroutine, self.hass.loop)
        try:
            return pending.result(timeout=15)
        except BaseException:
            pending.cancel()
            raise

    @staticmethod
    def _snapshot(state):
        # HA mutates last_reported for identical reports, but State.as_dict()
        # may still contain the time cached by an earlier consumer. Read the
        # public properties directly so idle power remains fresh when reported.
        return {"entity_id": state.entity_id, "state": state.state,
                "attributes": dict(state.attributes),
                "last_changed": state.last_changed.isoformat(),
                "last_updated": state.last_updated.isoformat(),
                "last_reported": state.last_reported.isoformat()}

    async def _states(self, entity=None):
        if entity is not None:
            state = self.hass.states.get(entity)
            return self._snapshot(state) if state else {}
        result=StateSnapshot({state.entity_id:self._snapshot(state) for state in self.hass.states.async_all()})
        result.captured_at=datetime.now(timezone.utc)
        return result

    def states(self):
        return self._wait(self._states())

    def state(self, entity):
        return self._wait(self._states(entity))

    def set(self, entity, value):
        if not isinstance(entity, str) or not ENTITY.fullmatch(entity):
            raise ValueError("Invalid control entity")
        domain = entity.split(".", 1)[0]
        if domain == "switch" and type(value) is bool:
            service, extra = ("turn_on" if value else "turn_off"), {}
        elif domain == "select" and isinstance(value, str):
            service, extra = "select_option", {"option": value}
        elif domain == "number" and type(value) is not bool and number(value) is not None:
            service, extra = "set_value", {"value": value}
        else:
            raise ValueError("Unsupported driver command")
        self._wait(self.hass.services.async_call(domain, service,
                   {"entity_id": entity, **extra}, blocking=True))

    def publish_soc(self, value, measured):
        # The coordinator-backed sensor owns its state and entity registry identity.
        pass

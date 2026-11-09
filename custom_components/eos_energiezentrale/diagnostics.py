"""Diagnostics without credentials, network locations or household history."""


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    data = coordinator.data or {}
    return {"version": entry.version, "armed": bool(data.get("armed")),
            "control_waiting": bool(data.get("control_waiting")),
            "release_pending": bool(data.get("release_pending")),
            "eos_cache": data.get("eos_cache", {}),
            "errors": data.get("errors", {}), "last_failure": data.get("last_failure"), "plan_available": bool(data.get("plan_end")),
            "battery_type": coordinator.app.config.options["battery_type"],
            "wallbox_type": coordinator.app.config.options["wallbox_type"]}

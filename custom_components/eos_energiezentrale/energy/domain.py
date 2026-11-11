"""Device-independent decisions. Positive grid power means import."""
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from math import floor, isfinite


def number(value):
    try:
        result = float(value)
        return result if isfinite(result) and not isinstance(value, bool) else None
    except (TypeError, ValueError, OverflowError):
        return None


def instant(value):
    try:
        result = datetime.fromisoformat(value)
        return result if result.utcoffset() is not None else None
    except (ValueError, TypeError):
        return None


def house_only(total, car, heat):
    if any(value is None or value < 0 for value in (total, car, heat)):
        return None
    return max(0, total - car - heat)


@dataclass(frozen=True)
class Instruction:
    when: datetime
    mode: str
    factor: float


def plan_series(plan, resource):
    if not isinstance(plan, dict) or not isinstance(plan.get("instructions"), list):
        return []
    result = []
    for item in plan["instructions"]:
        if not isinstance(item, dict):
            continue
        identifier = item.get("id")
        fallback = identifier.rsplit("@", 1)[0] if isinstance(identifier, str) else None
        if (item.get("resource_id") or fallback) != resource:
            continue
        when = instant(item.get("execution_time"))
        factor = number(item.get("operation_mode_factor"))
        mode = item.get("operation_mode_id")
        if (when and factor is not None and 0 <= factor <= 1 and isinstance(mode, str)
                and item.get("type") in {"FRBCInstruction", "DDBCInstruction"}):
            result.append(Instruction(when, mode.strip().upper(), factor))
    return sorted(result, key=lambda item: item.when)


def current_instruction(plan, resource, now):
    if not isinstance(plan, dict):
        return None
    generated = instant(plan.get("generated_at"))
    if not generated or not timedelta(0) <= now - generated < timedelta(hours=1):
        return None
    for key, is_valid in (("valid_from", lambda t: t <= now), ("valid_until", lambda t: now < t)):
        if plan.get(key) is not None:
            bound = instant(plan[key])
            if bound is None or not is_valid(bound):
                return None
    raw = plan.get("instructions")
    if not isinstance(raw, list):
        return None
    due_times = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        identifier = item.get("id")
        fallback = identifier.rsplit("@", 1)[0] if isinstance(identifier, str) else None
        if (item.get("resource_id") or fallback) == resource:
            when = instant(item.get("execution_time"))
            if when is None:
                return None
            if when <= now:
                due_times.append(when)
    newest = max(due_times, default=None)
    if newest is None or due_times.count(newest) != 1:
        return None
    return next((item for item in plan_series(plan, resource) if item.when == newest), None)


@dataclass(frozen=True)
class BatteryCommand:
    mode: str
    charge_w: float = 0
    discharge_w: float = 0
    min_soc: float | None = None
    max_soc: float | None = None
    net_demand_w: float | None = None
    required_discharge_w: float = 0


def battery_command(order, soc, settings, pv_car, grid, discharge, charge):
    if order is None or soc is None or not 0 <= soc <= 100:
        return None
    mode = order.mode
    low = soc <= settings["battery_min_soc"]
    high = soc >= settings["battery_max_soc"]
    charging = settings["battery_charge_w"] if not high else 0
    discharging = settings["battery_discharge_w"] if not low else 0
    if mode in {"IDLE", "NON_EXPORT"}:
        pv_limit = charging if mode == "NON_EXPORT" else 0
        if pv_car and not low:
            return BatteryCommand("limits", pv_limit, discharging)
        return BatteryCommand("block_discharge" if mode == "NON_EXPORT" else "limits", pv_limit)
    if mode == "SELF_CONSUMPTION":
        return BatteryCommand("limits", charging, discharging)
    if mode == "PEAK_SHAVING":
        if any(value is None for value in (grid, discharge, charge)):
            return None
        return BatteryCommand("limits", charging,
                              min(discharging, max(0, grid + discharge - charge - settings["grid_limit_w"])))
    if mode in {"FORCED_CHARGE", "GRID_SUPPORT_IMPORT"}:
        return (BatteryCommand("grid_charge", charging * order.factor)
                if charging * order.factor > 0 else BatteryCommand("limits"))
    if mode in {"FORCED_DISCHARGE", "GRID_SUPPORT_EXPORT"}:
        if not settings["allow_battery_export"]:
            return BatteryCommand("limits")
        return (BatteryCommand("grid_discharge", discharge_w=discharging * order.factor)
                if discharging * order.factor > 0 else BatteryCommand("limits"))
    return None


def current_for_power(power, phases, step, maximum, nearest=False, hard_limit=None, voltage=230):
    if phases not in (1, 3) or not 0 < step <= 1:
        return None
    watts_per_amp = voltage * phases
    budget = power + (watts_per_amp * step / 2 if nearest else 0)
    if hard_limit is not None:
        budget = min(budget, hard_limit)
    amps = min(maximum, budget / watts_per_amp)
    result = round(6 + floor((amps - 6) / step + 1e-9) * step, 6)
    return result if result >= 6 else None


def pv_budget(pv, grid, car, discharge, reserve, phases=None, setpoint=None, voltage=230):
    if phases in (1, 3) and setpoint is not None:
        return max(0, voltage * phases * setpoint - grid - discharge - reserve)
    return max(0, min(pv, car - grid - discharge) - reserve)


def estimate_soc(previous, measured, new_report, charging, previous_w, watts, seconds,
                 capacity_wh, efficiency, plugged=True):
    if measured is not None and (new_report or previous is None or not plugged):
        return measured
    if previous is None or not plugged or (measured is None and not charging):
        return None
    if charging and previous_w > 0 and watts > 0 and 0 < seconds <= 20:
        return min(100, previous + previous_w * seconds * efficiency * 100 / (3600 * capacity_wh))
    return previous


def next_departure(settings, now, zone):
    if settings["schedule"] == "once":
        value = instant(settings["departure"])
        return value if value and value > now else None
    if settings["schedule"] != "weekly":
        return None
    hour, minute = map(int, settings["departure_time"].split(":"))
    local = now.astimezone(zone)
    for offset in range(8):
        day = local.date() + timedelta(days=offset)
        if day.weekday() in settings["weekdays"]:
            candidate = datetime(day.year, day.month, day.day, hour, minute, tzinfo=zone)
            normalized = candidate.astimezone(timezone.utc).astimezone(zone)
            if normalized.astimezone(timezone.utc) > now.astimezone(timezone.utc):
                return normalized
    return None

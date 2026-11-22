"""Structured failure reasons; never expose user values or raw responses."""
import errno

REASONS = frozenset({'unknown_fields', 'invalid_type', 'out_of_range', 'battery_bounds',
    'invalid_schedule', 'invalid_departure', 'invalid_departure_time', 'invalid_weekdays',
    'profile_invalid', 'profile_nonpositive_power', 'settings_unconfirmed',
    'effective_limits_unavailable', 'effective_limits_differ', 'goal_unconfirmed', 'resource_missing',
    'credential_unavailable', 'device_api_error', 'invalid_charge_plan', 'invalid_holiday_region'})
# Fixed causes of a failed Modbus request (_modbus_tcp.ModbusError.reason).
TRANSPORT_REASONS = frozenset({'rejected', 'not_acknowledged', 'readback_mismatch', 'invalid_response', 'connection_closed'})
FIELDS = frozenset({'target_soc', 'pv_target_soc', 'reserve_w', 'regulation_interval_s',
    'battery_min_soc', 'battery_max_soc', 'battery_pv_min_soc', 'battery_pv_wait_s', 'battery_pv_surplus_w',
    'pv', 'fast', 'battery_pv_support', 'battery_pv_start', 'phase_auto', 'schedule', 'departure',
    'departure_time', 'weekdays', 'capacity_wh', 'nominal_capacity_wh', 'max_charge_power_w',
    'max_discharge_power_w', 'min_charge_power_w', 'min_soc_percentage', 'max_soc_percentage',
    'min_soc_deadline_datetime', 'min_soc_max_duration_h', 'charge_rates', 'profile_adjustment', 'password_env',
    'charge_plans', 'holiday_state', 'holiday_locality', 'holiday_catholic',
    'pv_price_ct', 'pv_price_source', 'efficiency_source', 'charge_efficiency', 'discharge_efficiency',
    'initial_price_ct', 'base_price_eur_month'})


class BackendError(ValueError):
    def __init__(self, message, *, reason, fields=()):
        super().__init__(message)
        self.reason = reason if reason in REASONS else 'invalid_type'
        self.fields = sorted(set(fields) & FIELDS)


class PluginParameterError(BackendError):
    def __init__(self, message, parameter=None):
        super().__init__(message, reason='invalid_type')
        self.parameter = parameter


class HardwareAPIError(OSError):
    def __init__(self, message, *, reason='device_api_error', fields=()):
        super().__init__(message)
        self.reason = reason if reason in REASONS else 'device_api_error'
        self.fields = sorted(set(fields) & FIELDS)


# Network errors of an unreachable device or service (connect, route, reset).
_NETWORK_ERRNOS = frozenset(getattr(errno, name) for name in (
    'ENETUNREACH', 'EHOSTUNREACH', 'ENETDOWN', 'EHOSTDOWN', 'ECONNREFUSED', 'ECONNRESET', 'ECONNABORTED', 'ETIMEDOUT')
    if hasattr(errno, name))


# Modbus exceptions of a gateway (e.g. Victron GX) whose target device is unreachable:
# 10 gateway path unavailable, 11 gateway target device failed to respond.
GATEWAY_UNREACHABLE = frozenset({10, 11})


def connection_lost(error):
    """True when a device or service could not be reached: timeout, refused or dropped
    connection, or a Modbus gateway that cannot reach its target device.

    A device that answered with a refusal or a wrong confirmation (other Modbus
    exceptions, readback mismatch, invalid response) is not a connection loss, even if
    an earlier timeout is part of the exception context.
    """
    for _ in range(6):
        if not isinstance(error, BaseException):
            return False
        reason = getattr(error, 'reason', None)
        if reason == 'connection_closed':
            return True
        if reason == 'rejected' and getattr(error, 'exception_code', None) in GATEWAY_UNREACHABLE:
            return True
        if isinstance(reason, str) and reason in TRANSPORT_REASONS:
            return False
        if isinstance(error, (TimeoutError, ConnectionError)):
            return True
        if isinstance(error, OSError) and error.errno in _NETWORK_ERRNOS:
            return True
        error = reason if isinstance(reason, BaseException) else (error.__cause__ or error.__context__)
    return False

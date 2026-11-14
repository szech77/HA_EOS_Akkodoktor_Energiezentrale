"""Structured failure reasons; never expose user values or raw responses."""
REASONS = frozenset({'unknown_fields', 'invalid_type', 'out_of_range', 'battery_bounds',
    'invalid_schedule', 'invalid_departure', 'invalid_departure_time', 'invalid_weekdays',
    'profile_invalid', 'profile_nonpositive_power', 'settings_unconfirmed',
    'effective_limits_unavailable', 'effective_limits_differ', 'goal_unconfirmed', 'resource_missing'})
FIELDS = frozenset({'target_soc', 'pv_target_soc', 'reserve_w', 'regulation_interval_s',
    'battery_min_soc', 'battery_max_soc', 'battery_pv_min_soc', 'battery_pv_wait_s', 'battery_pv_surplus_w',
    'pv', 'fast', 'battery_pv_support', 'battery_pv_start', 'phase_auto', 'schedule', 'departure',
    'departure_time', 'weekdays', 'capacity_wh', 'nominal_capacity_wh', 'max_charge_power_w',
    'max_discharge_power_w', 'min_charge_power_w', 'min_soc_percentage', 'max_soc_percentage',
    'min_soc_deadline_datetime', 'min_soc_max_duration_h', 'charge_rates', 'profile_adjustment'})


class BackendError(ValueError):
    def __init__(self, message, *, reason, fields=()):
        super().__init__(message)
        self.reason = reason if reason in REASONS else 'invalid_type'
        self.fields = sorted(set(fields) & FIELDS)

"""Plugin read incidents, including partial/empty returns, without private data."""
from datetime import datetime
from .contracts import BatteryReading, WallboxReading, PluginInfo
from .status import IssueLog, failure_details


def partial_read_failure(plugin, error, stage):
    failures = getattr(plugin, '_partial_read_failures', None)
    if failures is not None:
        failures.append({**failure_details(error), 'stage':stage})


def report_plugin_read(plugin, missing=(), *, error=None, controls=(), problems=(), stage=None, scope=None, group='read', status=None, include_partial=True):
    info = getattr(plugin, 'info', None)
    if not isinstance(info, PluginInfo) or info.identifier in {'none','devices'}:
        return
    log = getattr(plugin, '_telemetry_log', None)
    if log is None:
        plugin._telemetry_log = log = IssueLog()
    details = failure_details(error) if error is not None else {}
    partial = getattr(plugin, '_partial_read_failures', ()) if include_partial else ()
    if not details and partial:
        details = dict(partial[0])
    if stage:
        details['stage'] = stage
    context = getattr(plugin, 'read_diagnostics', None)
    if isinstance(context, dict) and isinstance(context.get('failure'), dict):
        details.update({key:context['failure'][key] for key in ('stage','unit','address','count','exception_code')
                        if key in context['failure']})
    code = ('plugin_read_failed' if error is not None or partial else
            'plugin_device_error' if status == 'error' else
            'plugin_unavailable' if status in {'unknown','unavailable'} else
            'plugin_measurements_incomplete' if missing or controls else None)
    log.update(group, [{'id':group, 'code':code, 'plugin':info.identifier,
        'scope':scope or getattr(plugin, 'diagnostic_scope', 'plugin/' + info.kind),
        'measurements':sorted(missing), 'missing_controls':sorted(controls), 'source_problems':list(problems), 'details':details}]
        if code else [])
    plugin.telemetry_status = log.diagnostics()['active']


def checked_plugin_read(plugin, now, collect):
    plugin._partial_read_failures = []
    try:
        result, raw = collect()
    except Exception as error:
        report_plugin_read(plugin, error=error)
        raise
    # Containers report each physical child separately, including the legacy pool.
    if getattr(plugin, 'site', None) is not None:
        return result
    expected = set(getattr(plugin, 'measurement_keys', ()))
    core, controls, status = {}, [], None
    if isinstance(result, BatteryReading):
        core = {'battery_soc':result.soc, 'battery_charge':result.charge, 'battery_discharge':result.discharge}
    elif isinstance(result, WallboxReading):
        core, status = {'car':result.watts}, result.status
        if result.plugged:
            controls = [key for key in ('phases','amps','step','maximum') if getattr(result,key) is None]
            if getattr(plugin.features, 'optional_connection', False):
                controls += [key for key in ('max_phases','nominal_voltage') if getattr(result,key) is None]
    missing = {key for key in expected if (core[key] if key in core else
               getattr(result.measurements.get(key), 'value', None)) is None}
    problems = []
    for key in sorted(missing):
        if key in core:
            attribute = {'battery_soc':'soc','battery_charge':'charge','battery_discharge':'discharge','car':'watts'}[key]
            value = getattr(raw, attribute)
            stamp = getattr(raw, 'sample' if key == 'car' else attribute+'_sample')
            age = getattr(plugin, 'soc_max_age', 120) if key == 'battery_soc' else 120
            age = age if type(age) in (int,float) and 1 <= age <= 360 else 120
        else:
            item = raw.measurements.get(key)
            value, stamp = getattr(item, 'value', None), getattr(item, 'sample', None)
            from .measurement_sources import SOURCES
            age = SOURCES[key][3] if key in SOURCES else 120
        reason = ('not_reported' if value is None else
            'sample_missing' if not isinstance(stamp, datetime) or stamp.utcoffset() is None else
            'future_sample' if stamp > now else 'stale' if (now-stamp).total_seconds() >= age else 'invalid_value')
        problems.append({'measurement':key,'reason':reason,'max_age_s':age})
    report_plugin_read(plugin, missing, controls=controls, problems=problems, status=status)
    return result

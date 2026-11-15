"""Backend-owned notices and control status, shared by the UI and HA logs."""
from collections import deque
from datetime import datetime, timezone
import json
import logging
import re
from pathlib import Path
from threading import RLock
from traceback import walk_tb
from urllib.error import HTTPError, URLError

from .domain import instant, number
from .measurement_sources import MEASUREMENT_KEYS
from .failures import BackendError, PluginParameterError, HardwareAPIError, REASONS, FIELDS

ERROR_MESSAGES = {key: 'notice.' + key for key in (
    'eos', 'accounting', 'device_pending', 'goal', 'runtime', 'forecast', 'release',
    'battery_limits', 'vehicle_limits', 'wallbox', 'wallbox_stop', 'control_persistence', 'connection')}
CRITICAL = {'runtime', 'release', 'wallbox_stop', 'control_persistence'}
CONTROL_STATUSES = ('waiting', 'read_only', 'cached_eos', 'syncing_vehicle', 'planning_vehicle', 'active')
BATTERY_LIMIT_STATUSES = ('failed', 'confirmed', 'pending', 'unmanaged')
CONNECTION_STATUSES = ('fetch_failed', 'plan_available', 'no_plan', 'local_history', 'history_available', 'no_samples', 'connecting')


def failure_details(error):
    """Never retain raw exceptions, URLs, response bodies or configuration."""
    result = {'exception': type(error).__name__}
    if isinstance(error, HTTPError):
        result['http_status'] = error.code
    if isinstance(error, URLError) and isinstance(error.reason, Exception):
        result['cause'] = type(error.reason).__name__
    nested = error.__cause__ or error.__context__
    for _ in range(4):
        if not isinstance(nested, Exception):
            break
        result['cause'] = type(nested).__name__
        if isinstance(nested, HTTPError):
            result['http_status'] = nested.code
        if isinstance(nested, URLError) and isinstance(nested.reason, Exception):
            result['cause'] = type(nested.reason).__name__
        nested = nested.__cause__ or nested.__context__
    if isinstance(error, (BackendError, HardwareAPIError)):
        result.update(reason=error.reason, fields=error.fields)
    if isinstance(error, PluginParameterError) and isinstance(error.parameter, str):
        result['parameter'] = safe_kind(error.parameter)
    if isinstance(getattr(error, 'plugin_identifier', None), str):
        result['plugin'] = safe_kind(error.plugin_identifier)
    if error.__traceback__ is not None:
        result['trace'] = [{'module':Path(frame.f_code.co_filename).stem, 'function':frame.f_code.co_name, 'line':line}
                           for frame, line in list(walk_tb(error.__traceback__))[-8:]]
    return result


def safe_kind(value):
    return value if isinstance(value, str) and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]{0,63}', value) else 'unavailable'


def view_state(data, now):
    """No device I/O: turn backend facts into an explicit presentation contract."""
    result = dict(data)
    notices = []
    vehicles = data.get('vehicles') or [data]
    scopes = [(data, 'system', None)] + [(vehicle, f'vehicle/{index}', vehicle.get('name'))
        for index, vehicle in enumerate(vehicles[1:], 2)]
    for source, scope, name in scopes:
        for area, value in source.get('errors', {}).items():
            if scope != 'system' and area not in {'goal', 'vehicle_limits', 'wallbox', 'wallbox_stop'}:
                continue
            code = 'eos_cached' if area == 'eos' and source.get('eos_cache') else area
            message = 'notice.eos_cached' if code == 'eos_cached' else ERROR_MESSAGES.get(area, 'notice.unknown')
            details = {'exception': safe_kind(value)}
            details.update(source.get('error_details', {}).get(area, {}))
            notices.append({'id': f'{scope}/{area}', 'code': code, 'message': message,
                'severity': 'error' if area in CRITICAL else 'warning', 'scope': scope,
                'vehicle_name': name, 'details': details})
        report = source.get('source_configuration') or {}
        for kind in ('missing', 'unavailable'):
            measurements = [key for key in report.get(kind, []) if key in MEASUREMENT_KEYS
                            and (scope == 'system' or key == 'car_soc')]
            if measurements:
                notices.append({'id': f'{scope}/sources_{kind}', 'code': f'sources_{kind}',
                    'message': f'notice.sources_{kind}', 'severity': 'warning', 'scope': scope,
                    'vehicle_name': name, 'measurements': sorted(measurements), 'details': {}})
                notices[-1]['source_problems'] = [{'measurement':key,
                    'reason':report.get('sources', {}).get(key, {}).get('reason', kind),
                    'max_age_s':report.get('sources', {}).get(key, {}).get('max_age_s')}
                    for key in sorted(measurements)]
    result['notices'] = notices
    pending = {vehicle.get('vehicle_planning') for vehicle in vehicles}
    result['control_status'] = ('waiting' if data.get('control_waiting') else
        'read_only' if not data.get('armed') else 'cached_eos' if data.get('eos_cache') else
        'syncing_vehicle' if pending & {'goal_pending', 'limits_pending'} else
        'planning_vehicle' if 'plan_pending' in pending else 'active')
    result['eos_status'] = ('fetch_failed' if data.get('errors', {}).get('eos') else
        'plan_available' if any(data.get('plan', {}).values()) else 'no_plan')
    limits = data.get('battery_limits') or {}
    result['battery_limits_status'] = ('failed' if 'battery_limits' in data.get('errors', {}) else
        'confirmed' if limits.get('confirmed') else 'pending' if limits.get('managed') else 'unmanaged')
    soc = number(data.get('live', {}).get('battery_soc'))
    minimum = number(data.get('settings', {}).get('battery_min_soc'))
    result['battery_low'] = soc is not None and minimum is not None and soc <= minimum
    result['next_mode'], result['upcoming_plan'] = {}, {}
    for key, rows in data.get('plan', {}).items():
        future = [row for row in rows if (stamp := instant(row.get('time'))) is not None and stamp > now]
        result['upcoming_plan'][key] = future[:5]
        result['next_mode'][key] = next((row for row in future
            if row.get('mode') != data.get('live', {}).get(key + '_mode')), None)
    if data.get('vehicles'):
        result['vehicles'] = [view_state(vehicle, now) for vehicle in vehicles]
    return result


class IssueLog:
    """Log transitions without poll spam; keep a bounded, privacy-safe history."""
    def __init__(self, logger=None):
        self.logger = logger or logging.getLogger('custom_components.eos_energiezentrale')
        self.groups = {}
        self.events = deque(maxlen=50)
        self.lock = RLock()

    def update(self, group, notices):
        with self.lock:
            self._update(group, notices)

    def _update(self, group, notices):
        current = {}
        for item in notices:
            details = item.get('details', {})
            safe = {'code': safe_kind(item['code']), 'scope': item.get('scope', 'system'),
                'severity': item.get('severity', 'warning'),
                'details': {key: safe_kind(details[key]) for key in ('exception', 'cause') if key in details}}
            status = details.get('http_status')
            if type(status) is int and 100 <= status <= 599:
                safe['details']['http_status'] = status
            if details.get('reason') in REASONS:
                safe['details']['reason'] = details['reason']
                safe['details']['fields'] = sorted(key for key in details.get('fields', []) if key in FIELDS)
            if details.get('trace'):
                safe['details']['trace'] = [{'module':safe_kind(frame.get('module')),
                    'function':safe_kind(frame.get('function')), 'line':frame['line']}
                    for frame in details['trace'][-8:] if type(frame.get('line')) is int and 0 < frame['line'] < 1000000]
            if details.get('stage'):
                safe['details']['stage'] = safe_kind(details['stage'])
            if details.get('parameter'):
                safe['details']['parameter'] = safe_kind(details['parameter'])
            for key in ('unit','address','count','exception_code'):
                value = details.get(key)
                if type(value) is int and 0 <= value <= 65535:
                    safe['details'][key] = value
            if item.get('plugin'):
                safe['plugin'] = safe_kind(item['plugin'])
            if item.get('missing_controls'):
                safe['missing_controls'] = sorted(key for key in item['missing_controls'] if key in
                    {'phases','amps','step','maximum','max_phases','nominal_voltage'})
            if item.get('control_problems'):
                safe['control_problems'] = [{'parameter':row['parameter'],'reason':safe_kind(row.get('reason'))}
                    for row in item['control_problems'] if row.get('parameter') in
                    {'status','plugged','enable','current','phases','phase_feedback','step','maximum'}]
            if item.get('measurements'):
                safe['measurements'] = sorted(key for key in item['measurements'] if key in MEASUREMENT_KEYS)
            if item.get('source_problems'):
                safe['source_problems'] = [{'measurement':row['measurement'], 'reason':safe_kind(row.get('reason')),
                    'max_age_s':row['max_age_s'] if type(row.get('max_age_s')) is int else None}
                    for row in item['source_problems'] if row.get('measurement') in MEASUREMENT_KEYS]
            current[item['id']] = safe
        previous = self.groups.get(group, {})
        for key, item in current.items():
            def signature(value):
                if value is None:
                    return None
                details = value['details']
                return {**value, 'details':{**details, 'trace':details.get('trace', [])[-1:]}}
            if signature(previous.get(key)) != signature(item):
                self._event('active' if key not in previous else 'changed', item)
        for key, item in previous.items():
            if key not in current:
                self._event('resolved', item)
        self.groups[group] = current

    def _event(self, state, item):
        event = {'state': state, **item, 'at': datetime.now(timezone.utc).isoformat()}
        self.events.append(event)
        level = logging.INFO if state == 'resolved' or item['severity'] == 'info' else logging.ERROR if item['severity'] == 'error' else logging.WARNING
        self.logger.log(level, 'EOS issue %s: %s', state, json.dumps(item, sort_keys=True))

    def diagnostics(self):
        with self.lock:
            return {'active': [item for group in self.groups.values() for item in group.values()],
                    'history': list(self.events)}

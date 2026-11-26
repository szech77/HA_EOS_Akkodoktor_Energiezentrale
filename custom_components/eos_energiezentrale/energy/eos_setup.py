"""Reviewed EOS commissioning through its configuration API, without device commands.

API reference: Akkudoktor-EOS/EOS openapi.json, SettingsEOS and /v1/config/file.
Only a server-built patch is accepted. Configuration, secrets and GPS coordinates
never enter diagnostics; previews expire and are checked again before writing.
"""
from copy import deepcopy
from hashlib import sha256
import json
import re
import secrets
from time import monotonic
from urllib.error import HTTPError
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from .clients import request
from .domain import number
from .failures import BackendError
from ._eos_battery import confirmed, limits_patch

TTL = 600
NAME = re.compile(r'[A-Za-z0-9_.-]{1,64}\Z')
PROVIDERS = {
    'pvforecast': ('PVForecastAkkudoktor', 'PVForecastForecastSolar'),
    'weather': ('WeatherClearOutside', 'WeatherBrightSky'),
    'elecprice': ('ElecPriceEnergyCharts', 'ElecPriceAkkudoktor', 'ElecPriceSMARD', 'ElecPriceFixed'),
    'load': ('LoadAkkudoktor',),
}
PLANE_FIELDS = ('name', 'peakpower', 'surface_tilt', 'surface_azimuth', 'inverter_paco', 'loss')
MAX_PRICE_ZONES = 12
DAY_S = 86400
ZONE_START = re.compile(r'([01][0-9]|2[0-3]):[0-5][0-9]\Z')
# EOS returns times as HH:MM:SS.ffffff and durations in words ("5 hours 30 minutes").
CLOCK = re.compile(r'([0-9]{1,2}):([0-9]{2})(?::([0-9]{2})(?:\.[0-9]+)?)?\Z')
ISO_DURATION = re.compile(r'P(?:([0-9]+)D)?(?:T(?:([0-9]+)H)?(?:([0-9]+)M)?(?:([0-9]+)S)?)?\Z')
DURATION_UNITS = {'week': 604800, 'day': DAY_S, 'hour': 3600, 'minute': 60, 'second': 1}
WINDOW_FILTERS = ('date', 'month', 'day_of_week', 'locale', 'end_time')


def rejected(reason, *fields):
    raise BackendError('EOS setup request rejected', reason=reason, fields=fields)


def numeric(value, low, high, field, *, integer=False):
    parsed = number(value) if type(value) in (int, float) else None
    if parsed is None or not low <= parsed <= high or integer and parsed != int(parsed):
        rejected('out_of_range', field)
    return int(parsed) if integer else parsed


def identifier(value):
    if not isinstance(value, str) or not NAME.fullmatch(value):
        rejected('invalid_type', 'resource')
    return value


def window(value):
    return {'windows': [{'start_time': '00:00:00', 'duration': 'P1D', 'value': value}]}


def time_of_day(value):
    """Seconds after midnight of an EOS window start, or None."""
    match = CLOCK.fullmatch(value) if isinstance(value, str) else None
    if not match:
        return None
    hour, minute, second = int(match[1]), int(match[2]), int(match[3] or 0)
    return hour * 3600 + minute * 60 + second if hour < 24 and minute < 60 and second < 60 else None


def duration_seconds(value):
    """Seconds of an ISO 8601 or EOS word duration, or None."""
    if not isinstance(value, str):
        return None
    match = ISO_DURATION.fullmatch(value)
    if match and value not in ('P', 'PT') and not value.endswith('T'):
        days, hours, minutes, seconds = (int(part or 0) for part in match.groups())
        return days * DAY_S + hours * 3600 + minutes * 60 + seconds
    words = value.split()
    if not words or len(words) % 2:
        return None
    total = 0
    for amount, unit in zip(words[::2], words[1::2]):
        unit = unit.removesuffix('s')
        if not amount.isdigit() or unit not in DURATION_UNITS:
            return None
        total += int(amount) * DURATION_UNITS[unit]
    return total


def clock(seconds):
    return '24:00' if seconds == DAY_S else f'{seconds // 3600 % 24:02d}:{seconds // 60 % 60:02d}'


def iso_duration(seconds):
    hours, minutes = divmod(seconds // 60, 60)
    return 'PT' + (f'{hours}H' if hours else '') + (f'{minutes}M' if minutes else '')


def price_zones(value):
    """Daily price zones of a fixed EOS tariff that repeats every day, or None.

    Each zone applies from its start until the next one; the last continues past midnight.
    """
    if type(value) in (int, float):
        return [{'start': '00:00', 'price_ct': value * 100}]
    rows = value.get('windows') if isinstance(value, dict) else None
    if not isinstance(rows, list) or not rows or len(rows) > MAX_PRICE_ZONES + 1:
        return None
    spans = []
    for row in rows:
        if not isinstance(row, dict) or any(row.get(key) is not None for key in WINDOW_FILTERS):
            return None
        start, length, price = time_of_day(row.get('start_time')), duration_seconds(row.get('duration')), number(row.get('value'))
        if start is None or not length or price is None or start % 60 or length % 60:
            return None
        spans.append((start, start + length, price))
    spans.sort()
    if spans[0][0] or spans[-1][1] != DAY_S or any(left[1] != right[0] for left, right in zip(spans, spans[1:])):
        return None
    zones = []
    for start, _, price in spans:
        if not zones or zones[-1][1] != price:
            zones.append((start, price))
    if len(zones) > 1 and zones[0][1] == zones[-1][1]:
        zones.pop(0)  # The window before the first start belongs to the zone running past midnight.
    if len(zones) > MAX_PRICE_ZONES:
        return None
    return [{'start': clock(start), 'price_ct': round(price * 100, 6)} for start, price in zones]


def price_windows(zones):
    """EOS time windows for daily price zones; windows never cross midnight."""
    if not isinstance(zones, list) or not 1 <= len(zones) <= MAX_PRICE_ZONES:
        rejected('out_of_range', 'price_zones')
    parsed = []
    for zone in zones:
        if (not isinstance(zone, dict) or zone.keys() != {'start', 'price_ct'}
                or not isinstance(zone['start'], str) or not ZONE_START.fullmatch(zone['start'])):
            rejected('invalid_type', 'price_zones')
        hour, minute = zone['start'].split(':')
        parsed.append((int(hour) * 3600 + int(minute) * 60, numeric(zone['price_ct'], 0, 1000, 'price_zones') / 100))
    parsed.sort()
    if len({start for start, _ in parsed}) != len(parsed):
        rejected('out_of_range', 'price_zones')
    if len(parsed) == 1:
        return window(parsed[0][1])
    spans = [(0, parsed[0][0], parsed[-1][1])] if parsed[0][0] else []
    spans += [(start, end, price) for (start, price), (end, _) in zip(parsed, parsed[1:] + [(DAY_S, None)])]
    return {'windows': [{'start_time': f'{start // 3600:02d}:{start // 60 % 60:02d}:00',
                         'duration': iso_duration(end - start), 'value': price} for start, end, price in spans]}


def window_rows(rows):
    """Comparable start, end and value of time windows for the review."""
    result = []
    for row in rows if isinstance(rows, list) else []:
        row = row if isinstance(row, dict) else {}
        start, length = time_of_day(row.get('start_time')), duration_seconds(row.get('duration'))
        if (start is None or length is None or start + length > DAY_S
                or any(row.get(key) is not None for key in WINDOW_FILTERS)):
            result.append({key: row.get(key) for key in ('start_time', 'duration', 'value')})
        else:
            result.append({'start': clock(start), 'end': clock(start + length), 'value': row.get('value')})
    return result


def constant(value):
    if type(value) in (int, float):
        return value
    rows = value.get('windows', []) if isinstance(value, dict) else []
    if len(rows) == 1 and isinstance(rows[0], dict):
        row = rows[0]
        if (time_of_day(row.get('start_time')) == 0 and duration_seconds(row.get('duration')) == DAY_S
                and not any(row.get(key) is not None for key in WINDOW_FILTERS)):
            return number(row.get('value'))
    return None


def resolve(schema, api):
    if '$ref' in schema:
        return api.get('components', {}).get('schemas', {}).get(schema['$ref'].rsplit('/', 1)[-1], {})
    return next((resolve(row, api) for row in schema.get('anyOf', []) if row.get('type') != 'null'), schema)


def checked_schema(patch, schema, api):
    """Do not send unsupported fields or read-only outputs to another EOS version."""
    schema = resolve(schema, api)
    if isinstance(patch, dict):
        properties = schema.get('properties', {})
        for key, value in patch.items():
            child = properties.get(key, schema.get('additionalProperties'))
            if not isinstance(child, dict) or child.get('readOnly'):
                rejected('setup_unsupported')
            checked_schema(value, child, api)
    elif isinstance(patch, list):
        for value in patch:
            checked_schema(value, schema.get('items', {}), api)


def projection(current, patch):
    if isinstance(patch, dict):
        source = current if isinstance(current, dict) else {}
        return {key: projection(source.get(key), value) for key, value in patch.items()}
    return current


def digest(value):
    return sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def contains(actual, expected):
    """EOS adds defaults to time windows and PV planes; verify every submitted value."""
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return False
        return all(contains(actual.get(key), value) for key, value in expected.items())
    if isinstance(expected, list):
        return isinstance(actual, list) and len(actual) == len(expected) and all(contains(a, b) for a, b in zip(actual, expected))
    if isinstance(expected, str) and CLOCK.fullmatch(expected):
        return time_of_day(expected) is not None and time_of_day(actual) == time_of_day(expected)
    if isinstance(expected, str) and expected.startswith('P') and duration_seconds(expected) is not None:
        return duration_seconds(actual) == duration_seconds(expected)
    return actual == expected


class EOSSetup:
    def __init__(self, eos):
        self.eos = eos
        self.pending = None

    def get(self, path):
        return request(self.eos.url + path)

    def schema(self):
        api = self.get('/openapi.json')
        try:
            schema = api['paths']['/v1/config']['put']['requestBody']['content']['application/json']['schema']
            api['paths']['/v1/config/file']['put']
            if not resolve(schema, api).get('properties'):
                raise KeyError('properties')
        except (KeyError, TypeError):
            rejected('setup_unsupported')
        return api, schema

    def configuration(self):
        current = self.get('/v1/config')
        sections = ('general', 'devices', 'pvforecast', 'weather', 'elecprice', 'elecfee', 'feedintariff',
                    'load', 'optimization', 'prediction', 'ems', 'adapter')
        if not isinstance(current, dict) or any(not isinstance(current.get(key), dict) for key in sections):
            rejected('setup_unsupported')
        return current

    def profiles(self, kind):
        try:
            rows = self.get('/v1/profile/' + kind)
        except HTTPError as error:
            if error.code == 404:
                return []
            raise
        if not isinstance(rows, list):
            rejected('setup_unsupported')
        return sorted({row['name'] for row in rows if isinstance(row, dict)
                       and isinstance(row.get('name'), str) and NAME.fullmatch(row['name'])})

    def load(self, hardware, location):
        with self.eos._configuration_lock:
            self.pending = None
            current = self.configuration()
            api, schema = self.schema()
            checked_schema({'general': {'latitude': 0, 'longitude': 0, 'timezone_override': 'UTC'},
                            'devices': {}, 'ems': {'mode': 'OPTIMIZATION'}}, schema, api)
            devices = current.get('devices', {})
            rows = []
            for supplied in hardware:
                kind, resource = supplied['kind'], supplied['resource']
                device = (devices.get(kind) or {}).get(resource, {}) or {}
                adjustment = device.get('profile_adjustment') or {}
                row = {**supplied,
                       'capacity_wh': supplied.get('capacity_wh') or device.get('effective_nominal_capacity_wh') or device.get('capacity_wh') or 10000,
                       'charge_w': supplied['charge_w'] if supplied.get('charge_w') is not None else device.get('effective_max_charge_power_w') or device.get('max_charge_power_w') or 5000,
                       'profile': device.get('battery_profile', 'generic-lfp'),
                       'min_soc': supplied.get('min_soc', device.get('min_soc_percentage', 20)),
                       'max_soc': supplied.get('max_soc', device.get('max_soc_percentage', 100)),
                       'locked': [key for key in ('capacity_wh', 'charge_w', 'discharge_w')
                                  if number(supplied.get(key)) is not None and supplied[key] >= 0]}
                if kind == 'batteries':
                    row['discharge_w'] = supplied['discharge_w'] if supplied.get('discharge_w') is not None else adjustment.get('max_discharge_power_w') or device.get('max_discharge_power_w') or 5000
                rows.append(row)
            general = current.get('general', {})
            pv = current.get('pvforecast', {})
            planes = [{**{key: row.get(key) for key in PLANE_FIELDS}, 'source': digest(row)} for row in pv.get('planes') or []]
            tariff = current.get('elecprice', {})
            zones = price_zones(tariff.get('elecpricefixed', {}).get('elecprice_marketprice_amt_kwh'))
            feedin = current.get('feedintariff', {})
            feedprice = constant(feedin.get('feedintarifffixed', {}).get('feed_in_tariff_amt_kwh'))
            fees = current.get('elecfee', {}).get('elecfeefixed', {})
            fee, percent = constant(fees.get('consumption_amt_kwh')), constant(fees.get('consumption_percent_amt'))
            inverters = devices.get('inverters') or {}
            battery = next((row for row in rows if row['kind'] == 'batteries'), None)
            inverter_id = next((key for key, row in inverters.items() if row.get('battery_id') == (battery or {}).get('resource')), None)
            if inverter_id is None:
                inverter_id = next('inverter' + str(i) for i in range(1, 101) if 'inverter' + str(i) not in inverters)
            inverter = inverters.get(inverter_id, {})
            options = {kind: [name for name in names if name in current.get(kind, {}).get('providers', names)]
                       for kind, names in PROVIDERS.items()}
            # A fixed tariff the wizard can show again opens with its zones. Only when
            # applying it unchanged rewrites nothing: gross prices without extra fees.
            fixed_tariff = (tariff.get('provider') == 'ElecPriceFixed' and zones is not None
                            and 'ElecPriceFixed' in options['elecprice']
                            and current.get('elecfee', {}).get('provider') == 'ElecFeeFixed' and fee == 0 and percent == 0)
            draft = {
                'latitude': general.get('latitude') if general.get('latitude') is not None else location.get('latitude'),
                'longitude': general.get('longitude') if general.get('longitude') is not None else location.get('longitude'),
                'timezone': location['timezone'],
                'pv_provider': 'keep',
                'planes': planes,
                'weather_provider': 'keep' if current.get('weather', {}).get('provider') else (options['weather'][:1] or ['keep'])[0],
                'price_provider': ('ElecPriceFixed' if fixed_tariff else 'keep' if tariff.get('provider')
                                   else (options['elecprice'][:1] or ['keep'])[0]),
                'price_zones': zones or [{'start': '00:00', 'price_ct': 30}],
                'fee_ct': fee * 100 if fee is not None else 0,
                'vat_percent': percent if percent is not None else 19,
                'bidding_zone': tariff.get('energycharts', {}).get('bidding_zone') or 'DE-LU',
                'feedin_provider': 'keep' if feedin.get('provider') else 'FeedInTariffFixed',
                'feedin_ct': feedprice * 100 if feedprice is not None else 8.2,
                'load_provider': 'keep' if current.get('load', {}).get('provider') else 'LoadAkkudoktor',
                'annual_kwh': current.get('load', {}).get('loadakkudoktor', {}).get('loadakkudoktor_year_energy_kwh') or 5000,
                'devices': rows,
                'inverter_id': inverter_id,
                'inverter_profile': inverter.get('inverter_profile', 'generic-hybrid'),
                'inverter_power_w': inverter.get('effective_nominal_power_w') or 10000,
                'horizon_hours': current.get('optimization', {}).get('genetic', {}).get('horizon_hours') or 24,
                'prediction_hours': max(72, current.get('prediction', {}).get('hours') or 0),
                'interval_seconds': current.get('ems', {}).get('interval') or 300,
            }
            return {'draft': draft, 'providers': options,
                    'profiles': {'battery': self.profiles('battery'), 'inverter': self.profiles('inverter')},
                    'current_providers': {key: current.get(key, {}).get('provider') for key in (*PROVIDERS, 'feedintariff')},
                    'ha_location': location}

    def build(self, draft, current, hardware):
        fields = {'latitude', 'longitude', 'timezone', 'pv_provider', 'planes', 'weather_provider', 'price_provider',
                  'price_zones', 'fee_ct', 'vat_percent', 'bidding_zone', 'feedin_provider', 'feedin_ct',
                  'load_provider', 'annual_kwh', 'devices', 'inverter_id', 'inverter_profile', 'inverter_power_w',
                  'horizon_hours', 'prediction_hours', 'interval_seconds'}
        if not isinstance(draft, dict) or draft.keys() != fields:
            rejected('unknown_fields')
        d = draft
        try:
            if not isinstance(d['timezone'], str):
                raise ValueError('timezone')
            ZoneInfo(d['timezone'])
        except (ValueError, ZoneInfoNotFoundError):
            rejected('invalid_type', 'timezone')
        patch = {'general': {'latitude': numeric(d['latitude'], -90, 90, 'latitude'),
                             'longitude': numeric(d['longitude'], -180, 180, 'longitude'), 'timezone_override': d['timezone']},
                 'ems': {'mode': 'OPTIMIZATION', 'interval': numeric(d['interval_seconds'], 60, 3600, 'interval_seconds')},
                 'optimization': {'algorithm': 'GENETIC', 'genetic': {
                     'horizon_hours': numeric(d['horizon_hours'], 1, 48, 'horizon_hours', integer=True)}},
                 'prediction': {'hours': numeric(d['prediction_hours'], 24, 168, 'prediction_hours', integer=True)},
                 'adapter': {'provider': []}}
        tail = current.get('optimization', {}).get('genetic', {}).get('tail_horizon_hours') or 0
        if patch['prediction']['hours'] < patch['optimization']['genetic']['horizon_hours'] + tail:
            rejected('out_of_range', 'prediction_hours')
        for field, kind in (('pv_provider', 'pvforecast'), ('weather_provider', 'weather'),
                            ('price_provider', 'elecprice'), ('load_provider', 'load')):
            value = d[field]
            if value == 'keep':
                if not current.get(kind, {}).get('provider') and not (kind == 'pvforecast' and not d['planes']):
                    rejected('invalid_type', field)
                continue
            if value not in PROVIDERS[kind] or value not in current.get(kind, {}).get('providers', PROVIDERS[kind]):
                rejected('invalid_type', field)
            patch[kind] = {'provider': value}
        if not isinstance(d['planes'], list) or not len(d['planes']) <= 20:
            rejected('out_of_range', 'planes')
        old_planes = current.get('pvforecast', {}).get('planes') or []
        originals = {digest(plane): plane for plane in old_planes}
        used = set()
        planes = []
        for plane in d['planes']:
            if not isinstance(plane, dict) or plane.keys() != set(PLANE_FIELDS) | {'source'}:
                rejected('unknown_fields', 'planes')
            source = plane['source']
            if not isinstance(source, str) or source and (source not in originals or source in used):
                rejected('setup_conflict', 'planes')
            if source:
                used.add(source)
            name = plane['name']
            if not isinstance(name, str) or not 1 <= len(name.strip()) <= 60 or any(ord(c) < 32 for c in name):
                rejected('invalid_type', 'planes')
            planes.append({**originals.get(source, {}), 'name': name,
                **{key: numeric(plane[key], low, high, 'planes', integer=key == 'inverter_paco')
                   for key, low, high in (('peakpower', .01, 1000), ('surface_tilt', 0, 90),
                                         ('surface_azimuth', 0, 360), ('inverter_paco', 1, 1000000), ('loss', 0, 100))}})
        if [{key: row.get(key) for key in PLANE_FIELDS} for row in d['planes']] != [{key: row.get(key) for key in PLANE_FIELDS} for row in old_planes]:
            patch.setdefault('pvforecast', {}).update(planes=planes, max_planes=len(planes))
        pv_provider = patch.get('pvforecast', {}).get('provider', current.get('pvforecast', {}).get('provider'))
        if pv_provider in PROVIDERS['pvforecast'] and not d['planes']:
            rejected('out_of_range', 'planes')
        if 'elecprice' in patch:
            if d['price_provider'] == 'ElecPriceFixed':
                patch['elecprice']['elecpricefixed'] = {'elecprice_marketprice_amt_kwh': price_windows(d['price_zones'])}
                fee, vat = 0, 0  # The entered fixed price is already gross.
            else:
                fee, vat = numeric(d['fee_ct'], 0, 1000, 'fee_ct') / 100, numeric(d['vat_percent'], 0, 100, 'vat_percent')
                if d['price_provider'] == 'ElecPriceEnergyCharts':
                    if d['bidding_zone'] not in ('DE-LU', 'AT', 'CH', 'FR', 'NL', 'BE', 'DK1', 'DK2', 'PL', 'CZ'):
                        rejected('invalid_type', 'bidding_zone')
                    patch['elecprice']['energycharts'] = {'bidding_zone': d['bidding_zone']}
            patch['elecfee'] = {'provider': 'ElecFeeFixed', 'elecfeefixed': {
                'consumption_amt_kwh': window(fee), 'consumption_percent_amt': window(vat)}}
        if d['feedin_provider'] == 'FeedInTariffFixed':
            patch['feedintariff'] = {'provider': 'FeedInTariffFixed', 'feedintarifffixed': {
                'feed_in_tariff_amt_kwh': window(numeric(d['feedin_ct'], 0, 1000, 'feedin_ct') / 100)}}
        elif d['feedin_provider'] != 'keep' or not current.get('feedintariff', {}).get('provider'):
            rejected('invalid_type', 'feedin_ct')
        if 'load' in patch:
            patch['load']['loadakkudoktor'] = {'loadakkudoktor_year_energy_kwh': numeric(d['annual_kwh'], 1, 1000000, 'annual_kwh')}
        if not isinstance(d['devices'], list) or len(d['devices']) != len(hardware):
            rejected('invalid_type', 'resource')
        for row, supplied in zip(d['devices'], hardware):
            allowed = {'kind', 'resource', 'name', 'capacity_wh', 'charge_w', 'profile', 'min_soc', 'max_soc', 'discharge_w', 'locked'}
            if (not isinstance(row, dict) or row.keys() - allowed
                    or not {'capacity_wh', 'charge_w', 'profile'} <= row.keys() or row.get('kind') != supplied['kind']
                    or row.get('resource') != supplied['resource']):
                rejected('invalid_type', 'resource')
            kind, resource = supplied['kind'], identifier(supplied['resource'])
            existing = (current.get('devices', {}).get(kind) or {}).get(resource, {})
            desired = {'capacity_wh': numeric(row['capacity_wh'], 100, 1000000, 'capacity_wh', integer=True),
                       'max_charge_power_w': numeric(row['charge_w'], 1, 1000000, 'max_charge_power_w')}
            for field in ('capacity_wh', 'charge_w', 'discharge_w'):
                if number(supplied.get(field)) is not None and supplied[field] >= 0 and row.get(field) != supplied[field]:
                    rejected('out_of_range', {'charge_w': 'max_charge_power_w', 'discharge_w': 'max_discharge_power_w'}.get(field, field))
            if kind == 'batteries':
                if 'discharge_w' not in row:
                    rejected('invalid_type', 'max_discharge_power_w')
                desired['max_discharge_power_w'] = numeric(row['discharge_w'], 1, 1000000, 'max_discharge_power_w')
                # These are the bounds used by the local controller; do not create conflicting settings.
                if row.get('min_soc') != supplied['min_soc'] or row.get('max_soc') != supplied['max_soc']:
                    rejected('battery_bounds', 'battery_min_soc', 'battery_max_soc')
                desired.update(min_soc_percentage=supplied['min_soc'], max_soc_percentage=supplied['max_soc'])
            # The wizard targets the profile API; older incompatible servers fail the schema check before writing.
            base = {**existing, 'battery_profile': identifier(row['profile'])}
            desired = {'device_id': resource, 'battery_profile': base['battery_profile'], **limits_patch(base, desired)}
            if not existing and kind == 'electric_vehicles':
                desired['charge_rates'] = [0.]
            patch.setdefault('devices', {}).setdefault(kind, {})[resource] = desired
        if any(row['kind'] == 'batteries' for row in hardware) or d['planes']:
            resource = identifier(d['inverter_id'])
            battery = next((row['resource'] for row in hardware if row['kind'] == 'batteries'), None)
            existing = (current.get('devices', {}).get('inverters') or {}).get(resource, {})
            if existing and existing.get('battery_id') != battery:
                rejected('invalid_type', 'resource')
            patch.setdefault('devices', {})['inverters'] = {resource: {
                'device_id': resource, 'inverter_profile': identifier(d['inverter_profile']),
                'battery_id': battery, 'profile_adjustment': {
                    'nominal_power_w': numeric(d['inverter_power_w'], 1, 1000000, 'inverter_power_w')}}}
        return patch

    def preview(self, draft, hardware):
        with self.eos._configuration_lock:
            current = self.configuration()
            api, schema = self.schema()
            patch = self.build(draft, current, hardware)
            checked_schema(patch, schema, api)
            for kind, profile_kind in (('batteries', 'battery'), ('electric_vehicles', 'battery'), ('inverters', 'inverter')):
                rows = patch.get('devices', {}).get(kind, {})
                if rows:
                    available = self.profiles(profile_kind)
                    for row in rows.values():
                        if row[profile_kind + '_profile'] not in available:
                            rejected('invalid_type', 'resource')
            changes = []

            def collect(value, old, path=''):
                for key, desired in value.items():
                    before = old.get(key) if isinstance(old, dict) else None
                    name = path + '/' + key if path else key
                    if isinstance(desired, dict):
                        collect(desired, before, name)
                    elif key == 'windows' and contains(before, desired):
                        continue
                    elif before != desired:
                        if key == 'planes':
                            before = [{field: plane.get(field) for field in PLANE_FIELDS} for plane in before or []]
                            desired = [{field: plane.get(field) for field in PLANE_FIELDS} for plane in desired]
                        elif key == 'windows':
                            before, desired = window_rows(before), window_rows(desired)
                        changes.append({'path': name, 'before': before, 'after': desired})

            collect(patch, current)
            token = secrets.token_urlsafe(32)
            self.pending = {'token': token, 'at': monotonic(), 'patch': patch,
                            'basis': digest(projection(current, patch)), 'hardware': digest(hardware)}
            return {'token': token, 'changes': changes, 'expires_seconds': TTL}

    def apply(self, token, hardware, before_write=lambda: None):
        with self.eos._configuration_lock:
            pending = self.pending
            if (not isinstance(token, str) or not pending or not secrets.compare_digest(token, pending['token'])
                    or monotonic() - pending['at'] > TTL or digest(hardware) != pending['hardware']):
                rejected('setup_preview_expired')
            current = self.configuration()
            patch = pending['patch']
            if digest(projection(current, patch)) != pending['basis']:
                self.pending = None
                rejected('setup_conflict')
            # Consume before the first write. A timed-out write is never blindly repeated.
            self.pending = None
            before_write()
            request(self.eos.url + '/v1/config', method='PUT', payload=patch)
            returned = self.get('/v1/config')
            if not contains(returned, patch):
                rejected('settings_unconfirmed')
            for kind in ('batteries', 'electric_vehicles'):
                for resource, desired in patch.get('devices', {}).get(kind, {}).items():
                    confirmed(returned.get('devices', {}).get(kind, {}).get(resource), desired)
            for resource, desired in patch.get('devices', {}).get('inverters', {}).items():
                if number(returned.get('devices', {}).get('inverters', {}).get(resource, {}).get('effective_nominal_power_w')) != desired['profile_adjustment']['nominal_power_w']:
                    rejected('settings_unconfirmed', 'inverter_power_w')
            try:
                saved = request(self.eos.url + '/v1/config/file', method='PUT')
            except Exception as error:
                raise BackendError('EOS configuration persistence was not confirmed', reason='setup_save_failed') from error
            if not contains(saved, patch):
                rejected('setup_save_failed')
            return {'ok': True, 'state': 'configured'}

"""Explicit, fresh backup-power facts; never infer islanding from missing watts."""
from datetime import datetime
from .contracts import PowerSupplyReading, PluginContractError
from .domain import instant

MAX_AGE = 120


def checked_supply(value, now):
    if value is None:
        return None
    if not isinstance(value, PowerSupplyReading):
        raise PluginContractError('Power supply must be PowerSupplyReading')
    sample = value.sample if isinstance(value.sample, datetime) and value.sample.utcoffset() is not None else None
    if (value.mode not in ('grid', 'backup') or sample is None
            or not 0 <= (now-sample).total_seconds() < MAX_AGE):
        return PowerSupplyReading('unknown', None)
    return value


def supply_view(value, now):
    value = checked_supply(value, now)
    mode = value.mode if value is not None else 'unsupported'
    return {'state':mode, 'grid_active':False if mode == 'backup' else True if mode == 'grid' else None,
            'sample':value.sample.isoformat() if value and value.sample else None}


def requires_pause(value, now, options, states):
    """Pause control for backup and for a supported status that is not grid.

    Device-reported status is timestamped, so a stale or missing value is no
    evidence of grid operation. A configured HA entity keeps an unchanged state
    without new reports; its explicit grid state therefore does not pause
    running control, while unavailable or unexpected states do. Recovery from
    a pause still needs a fresh grid report (see Controller.pause_for_backup).
    """
    mode = supply_view(value, now)['state']
    if mode != 'unknown':
        return mode == 'backup'
    entity = options.get('backup_mode_entity', '')
    if not entity:
        return True
    state = states.get(entity, {}).get('state')
    inactive = options.get('backup_inactive_state', 'off')
    return not (isinstance(state, str) and state.casefold() == inactive.casefold())


def entity_supply(row, now, active='on', inactive='off'):
    state = row.get('state')
    mode = ('backup' if state.casefold() == active.casefold() else
            'grid' if state.casefold() == inactive.casefold() else 'unknown') if isinstance(state, str) else 'unknown'
    return checked_supply(PowerSupplyReading(mode, instant(row.get('last_reported') or row.get('last_updated'))), now)


def configured_supply(options, states, now):
    entity = options.get('backup_mode_entity', '')
    return entity_supply(states.get(entity, {}), now, options.get('backup_active_state', 'on'),
                         options.get('backup_inactive_state', 'off')) if entity else None


def validate_supply_options(options):
    if type(options.get('allow_backup_ev_charging', False)) is not bool:
        raise ValueError('Backup EV charging permission must be boolean')
    from .clients import ENTITY
    entity = options.get('backup_mode_entity', '')
    if not isinstance(entity, str) or (entity and
            (not ENTITY.fullmatch(entity) or entity.split('.')[0] not in ('binary_sensor', 'sensor'))):
        raise ValueError('Invalid backup mode entity')
    values = [options.get(key, default) for key, default in
              (('backup_active_state', 'on'), ('backup_inactive_state', 'off'))]
    if (any(not isinstance(value, str) or not 1 <= len(value) <= 80
            or value != value.strip() or any(ord(char) < 32 for char in value)
            or value.casefold() in ('unknown', 'unavailable') for value in values)
            or values[0].casefold() == values[1].casefold()):
        raise ValueError('Backup mode needs distinct, explicit active and inactive states')


def fronius_entity_supply(states, identities, now):
    """Use registry associations, including renamed entities; never guess names."""
    sources = getattr(states, 'fronius_backup_modes', None) or {}
    candidates = {sources[entity] for entity in identities if entity in sources}
    if len(candidates) == 1:
        return entity_supply(states.get(candidates.pop(), {}), now)
    return PowerSupplyReading('unknown', None) if candidates else None


def aggregate_supply(readings):
    """Use the common-grid device, otherwise require storage-wide agreement."""
    readings = list(readings)
    primary = [getattr(value, 'power_supply', None) for selected, value in readings if selected]
    if len(primary) == 1 and primary[0] is not None:
        return primary[0]
    values = [getattr(value, 'power_supply', None) for _, value in readings]
    if not any(value is not None for value in values):
        return None
    if (any(value is None or value.sample is None for value in values)
            or len({value.mode for value in values}) != 1):
        return PowerSupplyReading('unknown', None)
    return PowerSupplyReading(values[0].mode, min(value.sample for value in values))

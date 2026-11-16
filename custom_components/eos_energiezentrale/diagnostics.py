"""Diagnostics without credentials, network locations or household history."""


from .energy.drivers import PLUGIN_ERRORS
from .energy.status import IssueLog
from .const import DOMAIN


def device_diagnostics(data):
    """Allow only device capabilities and read failures, without user labels/data."""
    group=data.get('battery_group') or {}
    result=[]
    for index,device in enumerate(group.get('devices',[]),1):
        details=device.get('read_diagnostics') or {}
        failure=details.get('failure')
        result.append({'device':index,'plugin':device.get('plugin',{}).get('identifier'),
            **({'telemetry_status':device['telemetry_status']} if 'telemetry_status' in device else {}),
            'available':device.get('available'),'read_error':device.get('read_error'),
            'configuration':{key:details[key] for key in ('phases','control_enabled','legacy_control_enabled','grid_meter_enabled',
                'read_consumption','dc_pv_enabled','ac_pv_input_enabled','ac_pv_output_enabled') if key in details},
            **({'firmware':{key:details['firmware'][key] for key in (
                'version','source','detected','configured','register_status','raw_words') if key in details['firmware']}}
                if isinstance(details.get('firmware'),dict) else {}),
            'failure':{key:failure[key] for key in ('type','stage','unit','address','count','exception_code')
                if key in failure} if isinstance(failure,dict) else None})
    return result


async def async_get_config_entry_diagnostics(hass, entry):
    coordinator = entry.runtime_data
    data = coordinator.data or {}
    configuration_issues = hass.data.get(DOMAIN, {}).get('configuration_issues')
    return {"plugin_errors":dict(PLUGIN_ERRORS),"plugins":data.get("plugins",{}),"devices":device_diagnostics(data),
            "version": entry.version, "armed": bool(data.get("armed")),
            "control_waiting": bool(data.get("control_waiting")),
            "release_pending": bool(data.get("release_pending")),
            "issues": coordinator.issue_log.diagnostics() if isinstance(getattr(coordinator, 'issue_log', None), IssueLog) else {},
            "configuration_issues": configuration_issues.diagnostics() if isinstance(configuration_issues, IssueLog) else {},
            "plugin_read_issues": data.get('plugin_read_issues', {}),
            "eos_cache": data.get("eos_cache", {}),
            "errors": data.get("errors", {}), "last_failure": data.get("last_failure"), "plan_available": bool(data.get("plan_end")),
            "battery_type": coordinator.app.config.options["battery_type"],
            "wallbox_type": coordinator.app.config.options["wallbox_type"]}

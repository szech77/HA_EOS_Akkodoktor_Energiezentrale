"""Backend configuration failures, including native HA/plugin forms."""
import logging

from .const import DOMAIN
from .energy.status import IssueLog, failure_details

_LOGGER = logging.getLogger(__name__)


def configuration_log(owner):
    hass = getattr(owner, 'hass', owner)
    return hass.data.setdefault(DOMAIN, {}).setdefault('configuration_issues', IssueLog(_LOGGER))


def configuration_failure(owner, stage, error, plugin=None):
    details = failure_details(error)
    plugin = details.pop('plugin', None) or plugin
    code = 'configuration_connection_failed' if isinstance(error, OSError) else 'configuration_invalid'
    configuration_log(owner).update(stage, [{'id':stage, 'code':code, 'scope':'configuration/' + stage,
        'plugin':plugin, 'details':details}])


def configuration_success(owner, stage):
    configuration_log(owner).update(stage, [])

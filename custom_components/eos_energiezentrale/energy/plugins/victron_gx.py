"""Official Home Assistant Victron GX entities using the shared Venus ESS adapter.

Both integrations expose the same victron-mqtt sensor/number/select contracts.
Keep budgets, freshness checks and confirmed release identical for both sources.
No dependency on HA's private integration modules or another MQTT connection.
"""
from ..contracts import PluginInfo
from .victron_ha import VictronHA


class VictronGX(VictronHA):
    info=PluginInfo('victron_gx','Victron GX (Home Assistant official)','battery')


PLUGINS=(VictronGX,)

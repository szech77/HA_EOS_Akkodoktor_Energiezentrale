"""NRGkick HA entity implementation with acknowledged, stopped phase switching."""
from ..entity_wallbox import EntityWallbox
from ..contracts import WallboxFeatures, PluginInfo, PluginField
from ..device_io import entities

class NRGkick(EntityWallbox):
    info = PluginInfo("nrgkick","NRGkick","wallbox")
    features = WallboxFeatures(phase_switching=True)
    defaults = {"power": "sensor.nrgkick_id_4_gesamt_wirkleistung",
                "status": "sensor.nrgkick_id_4_status",
                "enable": "switch.nrgkick_id_4_laden_aktiviert",
                "current": "number.nrgkick_id_4_ladestromstarke",
                "phases": "number.nrgkick_id_4_phasenanzahl"}

    configuration = tuple(PluginField(key,key.replace("_"," ").title(),default=value,
                          required=key!="grid_discharge",domains=(value.split(".")[0] if value else "number",))
                          for key,value in defaults.items())

    def __init__(self, ha, params):
        self.ha = ha
        self.ids = entities(self.defaults, params)
        self.zero_sample = None
        self.zero_after = None
        self.phase_requested = None


PLUGINS = (NRGkick,)

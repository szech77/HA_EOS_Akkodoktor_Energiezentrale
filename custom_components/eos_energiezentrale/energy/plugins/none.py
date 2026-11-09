from ..contracts import WallboxDriver, WallboxFeatures, WallboxReading, PluginInfo

class NoWallbox(WallboxDriver):
    info = PluginInfo("none","No vehicle","wallbox")
    features = WallboxFeatures(phase_switching=False)
    """Explicitly absent vehicle: no device reads or commands."""
    configuration = ()
    ids = {}
    def __init__(self, ha, params):
        if not isinstance(params, dict):
            raise ValueError("Wallbox parameters must be an object")
    def _read(self, states, now):
        return WallboxReading(0, "disconnected", False, 1, 6, .1, 16, now)
    def _pause(self, state):
        pass
    def _charge(self, amps, state):
        raise ValueError("No wallbox configured")
    def _phase(self, phases, state):
        raise ValueError("No wallbox configured")



PLUGINS = (NoWallbox,)

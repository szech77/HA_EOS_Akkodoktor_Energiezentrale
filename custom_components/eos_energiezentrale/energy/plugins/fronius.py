"""Fronius Home Assistant mode and power-limit entity implementation."""
from math import floor
from time import monotonic
from ..contracts import BatteryDriver, BatteryFeatures, BatteryReading, PluginInfo, PluginField
from ..clients import report_time
from ..domain import number
from ..device_io import entities, confirmed_state, DeviceConfirmationError, DeviceNotReady
from ..plugin_diagnostics import entity_reading, plugin_operation
from ..power_supply import fronius_entity_supply

class Fronius(BatteryDriver):
    info = PluginInfo("fronius","Fronius GEN24 / BYD","battery")
    prefix = "number.byd_battery_box_premium_hv_"
    defaults = {"mode": "select.byd_battery_box_premium_hv_storage_control_mode",
                "soc": "sensor.byd_battery_box_premium_hv_ladezustand",
                "charge_power": "sensor.fronius_symo_gen24_storage_charging_power",
                "discharge_power": "sensor.fronius_symo_gen24_storage_discharging_power",
                "pv_limit": prefix + "pv_charge_limit", "discharge_limit": prefix + "discharge_limit",
                "grid_charge": prefix + "grid_charge_power", "grid_discharge": ""}
    configuration = tuple(PluginField(key,key.replace("_"," ").title(),default=value,
                          required=key!="grid_discharge",domains=(value.split(".")[0] if value else "number",))
                          for key,value in defaults.items())

    modes = {"limits": "PV Charge and Discharge Limit", "block_discharge": "Block Discharging",
             "grid_charge": "Charge from Grid", "grid_discharge": "Discharge to Grid"}

    def __init__(self, ha, params):
        self.ha = ha
        self.ids = entities(self.defaults, params)
        self.pending_limits = {}
        self.features = BatteryFeatures(grid_discharge=bool(self.ids["grid_discharge"]))

    def _read(self, states, now):
        self._source_problems={}
        return BatteryReading(entity_reading(self,states,now,'soc','soc',120,('battery_soc',)),
                              entity_reading(self,states,now,'charge_power','power',120,('battery_charge',)),
                              entity_reading(self,states,now,'discharge_power','power',120,('battery_discharge',)),
                              report_time(states, self.ids["soc"]),
                              report_time(states, self.ids["charge_power"]),
                              report_time(states, self.ids["discharge_power"]),
                              power_supply=fronius_entity_supply(states, self.ids.values(), now))

    @plugin_operation('release')
    def _release(self, states):
        self._operation_context={'stage':'write_confirmation','parameter':'mode'}
        self.pending_limits.clear()
        if states.get(self.ids["mode"], {}).get("state") != "Auto":
            self.ha.set(self.ids["mode"], "Auto")
            confirmed_state(self.ha, self.ids["mode"], lambda row: row.get("state") == "Auto")

    @plugin_operation('apply')
    def _apply(self, command, states):
        self._operation_context={'stage':'mode_selection','parameter':'mode'}
        mode_id = self.ids["mode"]
        mode = self.modes[command.mode]
        limits = {"limits": (("pv_limit", command.charge_w), ("discharge_limit", command.discharge_w)),
                  "block_discharge": (("pv_limit", command.charge_w),),
                  "grid_charge": (("grid_charge", command.charge_w),),
                  "grid_discharge": (("grid_discharge", command.discharge_w),)}[command.mode]
        if any(not self.ids[key] for key, _ in limits):
            self._operation_context={'stage':'control_configuration','parameter':next(key for key,_ in limits if not self.ids[key])}
            raise ValueError("Fronius-Leistungsentität fehlt")
        if states.get(mode_id, {}).get("state") != mode:
            self._operation_context={'stage':'write_confirmation','parameter':'mode'}
            self.ha.set(mode_id, mode)
            confirmed_state(self.ha, mode_id, lambda row: row.get("state") == mode)
        for key, watts in limits:
            self._operation_context={'stage':'control_state','parameter':key}
            entity = self.ids[key]
            row = self.ha.state(entity)
            if number(row.get("state")) is None:
                now = monotonic()
                since = self.pending_limits.setdefault(entity, now)
                if now - since >= 45:
                    raise DeviceConfirmationError(entity)
                raise DeviceNotReady(entity)
            self.pending_limits.pop(entity, None)
            attrs = row.get("attributes", {})
            self._operation_context={'stage':'control_bounds','parameter':key}
            maximum, step = number(attrs.get("max")), number(attrs.get("step"))
            if maximum is None or not step or attrs.get("unit_of_measurement") != "W":
                raise ValueError("Fronius-Limit nicht verfügbar")
            target = floor(min(maximum, max(0, watts)) / step) * step
            actual = number(row.get("state"))
            if actual is None or abs(actual - target) >= step / 2:
                self._operation_context={'stage':'write_confirmation','parameter':key}
                self.ha.set(entity, target)
                confirmed_state(self.ha, entity, lambda sample:
                                (value := number(sample.get("state"))) is not None and abs(value - target) < step / 2)



PLUGINS = (Fronius,)

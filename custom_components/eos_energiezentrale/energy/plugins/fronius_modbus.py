"""Direct GEN24 SunSpec model 124 control and model 124/160 telemetry.

Register offsets follow https://github.com/sunspec/models/blob/master/json/model_124.json
and https://manuals.fronius.com/html/4204102649/en-US.html .
"""
import ipaddress
from math import floor
import re

from .._modbus_tcp import ModbusTCP, ModbusError
from ..contracts import BatteryDriver, BatteryFeatures, BatteryReading, PluginField, PluginInfo
from ..plugin_parameters import parameters


def signed(value):
    return value - 65536 if value >= 32768 else value


class FroniusModbus(BatteryDriver):
    info = PluginInfo("fronius_modbus", "Fronius GEN24 direct Modbus TCP", "battery")
    configuration = (
        PluginField("host", "Modbus host / IP", "text"),
        PluginField("port", "Modbus TCP port", "number", default=502),
        PluginField("unit_id", "Modbus unit ID", "number", default=1),
        PluginField("grid_discharge_supported", "Allow forced grid export", "boolean", default=False),
    )

    def __init__(self, ha, params):
        values = parameters(self.configuration, params)
        host = values["host"]
        try:
            ipaddress.ip_address(host)
        except ValueError:
            if (len(host) > 253 or not all(re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?", label)
                                          for label in host.split("."))):
                raise ValueError("Modbus host must be an IP address or hostname") from None
        for key, maximum in (("port", 65535), ("unit_id", 247)):
            if values[key] != int(values[key]) or not 1 <= values[key] <= maximum:
                raise ValueError("Invalid Modbus " + key)
        self.ids = {key: "" for key in ("soc", "charge_power", "discharge_power", "mode")}
        self.features = BatteryFeatures(grid_discharge=values["grid_discharge_supported"])
        self.client = ModbusTCP(host, int(values["port"]), int(values["unit_id"]))
        self.model = None
        self.mppt = None
        self.original_grid = None

    def _read(self, states, now):
        storage = self._storage()
        soc = self._scaled(storage[6], storage[20], 100)
        charge, discharge = self._powers()
        # Timestamp a successful live poll, never a cached value. `now` is the
        # acquisition start, so it remains conservative while requests complete.
        return BatteryReading(soc, charge, discharge,
                              now if soc is not None else None,
                              now if charge is not None else None,
                              now if discharge is not None else None)

    @staticmethod
    def _scaled(raw, scale, maximum):
        factor = signed(scale)
        if raw == 65535 or not -4 <= factor <= 4:
            return None
        value = raw * 10 ** factor
        return value if 0 <= value <= maximum else None

    def _powers(self):
        if self.mppt is None:
            raise ModbusError("SunSpec MPPT model 160 missing")
        address, length = self.mppt
        header = self.client.read(address, 10)
        count = header[8]
        if (header[:2] != [160, length] or not 1 <= count <= 16
                or length != 8 + count * 20):
            self.model = self.mppt = None
            raise ModbusError("Invalid SunSpec MPPT model layout")
        powers = {}
        for index in range(count):
            module = self.client.read(address + 10 + index * 20, 20)
            identity = module[0]
            # Fronius: MPP1/2 are PV, MPP3 storage charging, MPP4 discharging.
            if identity in (3, 4):
                if identity in powers:
                    raise ModbusError("Duplicate SunSpec battery channel")
                powers[identity] = self._scaled(module[11], header[4], 1000000)
        return powers.get(3), powers.get(4)

    def _storage(self):
        # Fronius uses wire address 40000 for the SunSpec signature. Walk model
        # lengths rather than assuming an int/float-dependent absolute address.
        if self.model is None:
            if self.client.read(40000, 2) != [0x5375, 0x6E53]:
                raise ModbusError("SunSpec signature missing")
            address = 40002
            fronius = False
            for _ in range(128):
                identity, length = self.client.read(address, 2)
                if identity == 0xFFFF:
                    break
                if not 1 <= length <= 4096 or address + 2 + length > 65535:
                    raise ModbusError("Invalid SunSpec model length")
                if identity == 1 and length >= 65:
                    manufacturer = self.client.read(address + 2, 16)
                    name = b"".join(word.to_bytes(2, "big") for word in manufacturer).rstrip(b"\0 ")
                    fronius = name.lower() == b"fronius"
                if identity == 160:
                    self.mppt = (address, length)
                if identity == 124:
                    if not fronius or length != 24:
                        raise ModbusError("Unsupported SunSpec storage model length")
                    self.model = address
                if self.model is not None and self.mppt is not None:
                    break
                address += 2 + length
            if self.model is None:
                raise ModbusError("SunSpec storage model 124 missing")
        values = self.client.read(self.model, 26)
        if values[:2] != [124, 24]:
            self.model = self.mppt = None
            raise ModbusError("SunSpec storage model changed; control refused")
        return values[2:]

    def _write(self, offset, values):
        self.client.write(self.model + 2 + offset, values)

    def _apply(self, command, states):
        data = self._storage()
        power_scale, rate_scale = signed(data[16]), signed(data[23])
        if (data[0] in (0, 65535) or not -4 <= power_scale <= 4
                or not -2 <= rate_scale <= 0 or data[3] not in (0, 1, 2, 3)
                or data[15] not in (0, 1)):
            raise ModbusError("Invalid battery reference power, scaling or control state")
        maximum = data[0] * 10 ** power_scale
        if not 0 < maximum <= 1000000:
            raise ModbusError("Invalid battery reference power")

        def rate(watts):
            return floor(min(100, watts / maximum * 100) / 10 ** rate_scale + 1e-9)

        charge, discharge = rate(command.charge_w), rate(command.discharge_w)
        if command.mode == "block_discharge":
            discharge = 0
        elif command.mode == "grid_charge":
            discharge = -charge
        elif command.mode == "grid_discharge":
            charge = -discharge
        if self.original_grid is None:
            self.original_grid = data[15]
        # Refresh on every command, including unchanged setpoints. The inverter
        # must drop external power limits if HA stops renewing this 300s lease.
        self._write(13, [300])
        self._write(15, [int(command.mode == "grid_charge")])
        # Both signed rates in one FC16 prevent an invalid intermediate window.
        self._write(10, [discharge & 0xFFFF, charge & 0xFFFF])
        self._write(3, [3])

    def _release(self, states):
        data = self._storage()
        if data[3] != 0:
            self._write(3, [0])
        if self.original_grid is not None:
            self._write(15, [self.original_grid])
            self.original_grid = None


PLUGINS = (FroniusModbus,)

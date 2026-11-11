"""Direct GEN24 SunSpec model 124 control and model 124/160 telemetry.

Register offsets follow https://github.com/sunspec/models/blob/master/json/model_124.json
and https://manuals.fronius.com/html/4204102649/en-US.html .
"""
from math import floor, isfinite
import struct

from .._modbus_tcp import ModbusTCP, ModbusError, checked_host
from ..contracts import BatteryDriver, BatteryFeatures, BatteryReading, PluginField, PluginInfo, Measurement
from ..plugin_parameters import parameters


def signed(value):
    return value - 65536 if value >= 32768 else value


class FroniusModbus(BatteryDriver):
    measurement_keys = BatteryDriver.measurement_keys + ("solar", "grid", "house_total", "inverter_ac")
    info = PluginInfo("fronius_modbus", "Fronius GEN24 direct Modbus TCP", "battery")
    configuration = (
        PluginField("host", "Modbus host / IP", "text"),
        PluginField("port", "Modbus TCP port", "number", default=502),
        PluginField("unit_id", "Modbus unit ID", "number", default=1),
        PluginField("grid_meter_enabled", "Read grid connection meter", "boolean", default=True),
        PluginField("grid_meter_unit_id", "Grid meter unit ID", "number", default=200),
        PluginField("grid_meter_host", "Grid meter gateway host (empty: primary inverter)", "text", required=False, default=""),
        PluginField("grid_meter_port", "Grid meter gateway port (0: primary inverter port)", "number", default=0),
        PluginField("grid_meter_invert", "Invert grid meter sign", "boolean", default=False),
        PluginField("grid_discharge_supported", "Allow forced grid export", "boolean", default=False),
        PluginField("battery_capacity_wh", "Primary battery capacity (Wh; required with multiple batteries)", "number", default=0),
        PluginField("additional_inverters", "Additional inverters (JSON object; see PLUGINS.md)", "json", default={}),
    )

    def __init__(self, ha, params):
        values = parameters(self.configuration, params)
        host = checked_host(values["host"])
        for key, maximum in (("port", 65535), ("unit_id", 247), ("grid_meter_unit_id", 247)):
            if values[key] != int(values[key]) or not 1 <= values[key] <= maximum:
                raise ValueError("Invalid Modbus " + key)
        self.ids = {key: "" for key in ("soc", "charge_power", "discharge_power", "mode")}
        self.features = BatteryFeatures(grid_discharge=values["grid_discharge_supported"])
        self.client = ModbusTCP(host, int(values["port"]), int(values["unit_id"]))
        grid_host=checked_host(values['grid_meter_host']) if values['grid_meter_host'] else host
        grid_port=values['grid_meter_port']
        if grid_port!=int(grid_port) or not 0<=grid_port<=65535:
            raise ValueError('Invalid grid meter port')
        self.grid_client = ModbusTCP(grid_host,int(grid_port or values['port']),int(values['grid_meter_unit_id']))
        self.grid_invert = values["grid_meter_invert"]
        self.grid_model = None
        if not values["grid_meter_enabled"]:
            self.measurement_keys = BatteryDriver.measurement_keys + ("solar", "inverter_ac")
        self.model = None
        self.mppt = None
        self.inverter_model = None
        self.original_grid = None
        self.discovered = False
        self.site = None
        from .._fronius_site import FroniusSite, capacity
        primary_capacity=capacity(values['battery_capacity_wh'],optional=True)
        if values['additional_inverters']:
            self.site=FroniusSite(self,values['additional_inverters'],primary_capacity,type(self))

    @property
    def device_key(self):
        from .._fronius_site import endpoint
        host,port,unit=endpoint(self)
        return f'modbus:{host}:{port}:{unit}'

    @property
    def requires_dispatch_context(self):
        return self.site is not None and len(self.site.batteries)>1

    def power_limits(self, states):
        data=self._storage()
        reference=self._scaled(data[0],data[16],1000000)
        if reference is None or reference<=0:
            raise ModbusError('Storage power reference missing')
        return reference,reference

    @property
    def site_summary(self):
        return self.site.summary if self.site else None

    def _read(self, states, now):
        if self.site:
            return self.site.read(states,now)
        return self._read_single(states,now)

    def _read_single(self, states, now, include_grid=True):
        storage = self._storage()
        soc = self._scaled(storage[6], storage[20], 100)
        powers = self._powers()
        charge, discharge = powers.get(3), powers.get(4)
        pv_channels = [powers[key] for key in (1, 2) if key in powers]
        solar = sum(pv_channels) if pv_channels and all(value is not None for value in pv_channels) else None
        extra = {"solar": Measurement(solar, now if solar is not None else None)}
        try:
            ac = self._ac_power()
        except (OSError, ValueError):
            self._invalidate()
            ac = None
        extra['inverter_ac'] = Measurement(ac, now if ac is not None else None)
        if include_grid and "grid" in self.measurement_keys:
            try:
                grid = self._grid_power()
            except (OSError, ValueError):
                # A missing gateway meter must not hide healthy battery data.
                self.grid_model = None
                grid = None
            extra["grid"] = Measurement(grid, now if grid is not None else None)
            # AC output already includes PV, storage discharge and grid charging.
            # Do not mix DC battery/PV channels into this AC balance.
            house = ac + grid if ac is not None and grid is not None else None
            if house is not None and not 0 <= house <= 1000000:
                house = None
            extra["house_total"] = Measurement(house, now if house is not None else None)
        # Timestamp a successful live poll, never a cached value. `now` is the
        # acquisition start, so it remains conservative while requests complete.
        return BatteryReading(soc, charge, discharge,
                              now if soc is not None else None,
                              now if charge is not None else None,
                              now if discharge is not None else None, extra)

    def _ac_power(self):
        if self.inverter_model is None:
            return None
        address, identity, length = self.inverter_model
        if self.client.read(address, 2) != [identity, length]:
            raise ModbusError("Inverter measurement model changed")
        if identity < 110:
            if length < 14: raise ModbusError("Incomplete integer inverter model")
            raw, scale = self.client.read(address + 14, 2)
            factor = signed(scale)
            value = signed(raw) * 10 ** factor if raw != 32768 and -4 <= factor <= 4 else None
        else:
            if length < 22: raise ModbusError("Incomplete float inverter model")
            raw = self.client.read(address + 22, 2)
            value = struct.unpack(">f", struct.pack(">HH", *raw))[0]
        return value if value is not None and isfinite(value) and abs(value) <= 1000000 else None

    def _generation(self):
        """Read-only PV inverter path: storage model 124 is not required."""
        try:
            if not self.discovered:
                self._discover()
            ac=self._ac_power()
            if self.mppt is not None:
                powers=self._powers()
                if any((powers.get(key) or 0)>0 for key in (3,4)):
                    raise ModbusError('Storage activity on an inverter configured without battery')
                values=[powers[key] for key in (1,2) if key in powers]
                solar=sum(values) if values and all(value is not None for value in values) else None
            else:
                solar=self._dc_power()
            return solar,ac
        except (OSError,ValueError):
            self._invalidate()
            raise

    def _dc_power(self):
        if self.inverter_model is None:
            return None
        address,identity,length=self.inverter_model
        # SunSpec inverter models: DCW at +31 (int16 + SF), +38 (float32).
        if identity<110:
            if length<31: return None
            raw,scale=self.client.read(address+31,2)
            value=signed(raw)*10**signed(scale) if raw!=32768 and -4<=signed(scale)<=4 else None
        else:
            if length<38: return None
            value=struct.unpack('>f',struct.pack('>HH',*self.client.read(address+38,2)))[0]
        return value if value is not None and isfinite(value) and 0<=value<=1000000 else None

    def _invalidate(self):
        self.model=self.mppt=self.inverter_model=None
        self.discovered=False

    def _discover(self):
        self._invalidate()
        if self.client.read(40000,2)!=[0x5375,0x6E53]:
            raise ModbusError('SunSpec signature missing')
        address=40002
        fronius=False
        ended=False
        for _ in range(128):
            identity,length=self.client.read(address,2)
            if identity==65535:
                ended=True
                break
            if not 1<=length<=4096 or address+2+length>65535:
                raise ModbusError('Invalid SunSpec model length')
            if identity==1 and length>=65:
                words=self.client.read(address+2,16)
                name=b''.join(word.to_bytes(2,'big') for word in words).rstrip(b'\0 ')
                fronius=name.lower()==b'fronius'
            if identity==160:
                if self.mppt is not None: raise ModbusError('Duplicate SunSpec MPPT model')
                self.mppt=(address,length)
            if identity in (101,102,103,111,112,113):
                if self.inverter_model is not None: raise ModbusError('Duplicate SunSpec inverter model')
                self.inverter_model=(address,identity,length)
            if identity==124:
                if self.model is not None or length!=24:
                    raise ModbusError('Unsupported SunSpec storage model')
                self.model=address
            address+=2+length
        if not ended or not fronius:
            self._invalidate()
            raise ModbusError('Incomplete or non-Fronius SunSpec device')
        self.discovered=True

    def _grid_power(self):
        if self.grid_model is None:
            if self.grid_client.read(40000, 2) != [0x5375, 0x6E53]:
                raise ModbusError("Grid meter SunSpec signature missing")
            address = 40002
            for _ in range(128):
                identity, length = self.grid_client.read(address, 2)
                if identity == 65535:
                    break
                if not 1 <= length <= 4096 or address + length + 2 > 65535:
                    raise ModbusError("Invalid grid meter model length")
                if identity in (201, 202, 203, 211, 212, 213):
                    self.grid_model = (address, identity, length)
                    break
                address += length + 2
            if self.grid_model is None:
                raise ModbusError("SunSpec grid meter model missing")
        address, identity, length = self.grid_model
        if self.grid_client.read(address, 2) != [identity, length]:
            raise ModbusError("Grid meter model changed")
        if identity < 210:
            if length < 21: raise ModbusError("Incomplete integer grid meter")
            values = self.grid_client.read(address + 18, 5)
            scale = signed(values[4])
            value = signed(values[0]) * 10 ** scale if values[0] != 32768 and -4 <= scale <= 4 else None
        else:
            if length < 28: raise ModbusError("Incomplete float grid meter")
            values = self.grid_client.read(address + 28, 2)
            value = struct.unpack(">f", struct.pack(">HH", *values))[0]
        if value is None or not isfinite(value) or abs(value) > 1000000:
            return None
        return -value if self.grid_invert else value

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
            self.model = self.mppt = self.inverter_model = None
            raise ModbusError("Invalid SunSpec MPPT model layout")
        powers = {}
        for index in range(count):
            module = self.client.read(address + 10 + index * 20, 20)
            identity = module[0]
            # Fronius: MPP1/2 are PV, MPP3 storage charging, MPP4 discharging.
            if identity in (1, 2, 3, 4):
                if identity in powers:
                    raise ModbusError("Duplicate SunSpec measurement channel")
                powers[identity] = self._scaled(module[11], header[4], 1000000)
        return powers

    def _storage(self):
        # Fronius uses wire address 40000 for the SunSpec signature. Walk model
        # lengths rather than assuming an int/float-dependent absolute address.
        if not self.discovered or self.model is None or ("house_total" in self.measurement_keys and self.inverter_model is None):
            self._discover()
        if self.model is None:
            raise ModbusError("SunSpec storage model 124 missing")
        values = self.client.read(self.model, 26)
        if values[:2] != [124, 24]:
            self._invalidate()
            raise ModbusError("SunSpec storage model changed; control refused")
        return values[2:]

    def _write(self, offset, values):
        self.client.write(self.model + 2 + offset, values)

    def _apply(self, command, states):
        if self.site:
            return self.site.apply(command,states)
        return self._apply_single(command,states)

    def _apply_single(self, command, states):
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
        if self.site:
            return self.site.release(states)
        return self._release_single(states)

    def _release_single(self, states):
        data = self._storage()
        if data[3] != 0:
            self._write(3, [0])
        if self.original_grid is not None:
            self._write(15, [self.original_grid])
            self.original_grid = None


PLUGINS = (FroniusModbus,)

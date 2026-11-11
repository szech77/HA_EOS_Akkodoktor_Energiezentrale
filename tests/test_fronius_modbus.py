"""Exercise the native plugin against a local Modbus TCP inverter emulator."""
from contextlib import contextmanager
from datetime import timedelta
import socket
import socketserver
import struct
from threading import Thread
from unittest.mock import Mock, patch

import pytest

from custom_components.eos_energiezentrale.energy._modbus_tcp import ModbusTCP, ModbusError
from custom_components.eos_energiezentrale.energy.contracts import UnsupportedFeature
from custom_components.eos_energiezentrale.energy.domain import BatteryCommand
from custom_components.eos_energiezentrale.energy.drivers import BATTERY_DRIVERS
from test_energy import NOW


def receive(connection, count):
    result = b""
    while len(result) < count:
        chunk = connection.recv(count - len(result))
        if not chunk:
            raise ConnectionError("Incomplete test request")
        result += chunk
    return result


class Inverter(socketserver.TCPServer):
    allow_reuse_address = True

    def __init__(self, model_address):
        super().__init__(("127.0.0.1", 0), Request)
        self.registers = {40000: 0x5375, 40001: 0x6E53,
                          40002: 1, 40003: 65,
                          40069: 160, 40070: 88,
                          40159: 113, 40160: model_address - 40161,
                          model_address: 124, model_address + 1: 24,
                          model_address + 26: 65535, model_address + 27: 0}
        self.mppt = 40069
        self.base = model_address + 2
        manufacturer = b"Fronius".ljust(32, b"\0")
        self.registers.update({40004 + index: value for index, value in enumerate(struct.unpack(">16H", manufacturer))})
        self.registers.update({self.base + index: 0 for index in range(24)})
        self.registers.update({self.base: 5000, self.base + 23: 65534,
                               self.base + 6: 5500, self.base + 20: 65534})
        self.registers.update({40071 + index: 0 for index in range(88)})
        self.registers[40077] = 4
        for index in range(4):
            start = 40079 + index * 20
            self.registers[start] = index + 1
            self.registers[start + 11] = (900, 1100, 1500, 0)[index]
        self.writes = []
        self.reject = False
        self.ignore_writes = False


class Request(socketserver.BaseRequestHandler):
    def handle(self):
        self.request.settimeout(1)
        transaction, protocol, length, unit = struct.unpack(">HHHB", receive(self.request, 7))
        request = receive(self.request, length - 1)
        function = request[0]
        address, count = struct.unpack(">HH", request[1:5])
        if self.server.reject:
            pdu = bytes([function | 128, 3])
        elif function == 3:
            words = [self.server.registers.get(address + offset, 0) for offset in range(count)]
            pdu = bytes([3, count * 2]) + struct.pack(">" + "H" * count, *words)
        else:
            assert function == 16 and request[5] == count * 2
            values = list(struct.unpack(">" + "H" * count, request[6:]))
            self.server.writes.append((address, values))
            if not self.server.ignore_writes:
                self.server.registers.update({address + index: value for index, value in enumerate(values)})
            pdu = bytes([16]) + request[1:5]
        response = struct.pack(">HHHB", transaction, protocol, len(pdu) + 1, unit) + pdu
        # Fragment responses to exercise TCP stream framing, not packet assumptions.
        self.request.sendall(response[:4])
        self.request.sendall(response[4:])


@contextmanager
def inverter(address=40342, export=False):
    with Inverter(address) as server:
        thread = Thread(target=server.serve_forever, kwargs={"poll_interval": .01}, daemon=True)
        thread.start()
        params = {"host": "127.0.0.1", "port": server.server_address[1],
                  "grid_discharge_supported": export}
        driver = BATTERY_DRIVERS["fronius_modbus"](None, params)
        try:
            yield driver, server
        finally:
            server.shutdown()
            thread.join(timeout=2)


@pytest.mark.parametrize("address", [40342, 40352])
@pytest.mark.parametrize("mode,charge,discharge,expected", [
    ("limits", 2500, 1000, [2000, 5000]),
    ("block_discharge", 2500, 1000, [0, 5000]),
    ("grid_charge", 2500, 0, [65536 - 5000, 5000]),
    ("grid_discharge", 0, 2500, [5000, 65536 - 5000]),
])
def test_power_windows_are_scaled_signed_atomic_and_confirmed(address, mode, charge, discharge, expected):
    with inverter(address, export=True) as (driver, server):
        driver.apply(BatteryCommand(mode, charge, discharge), {})
        assert (server.base + 10, expected) in server.writes
        assert server.registers[server.base + 3] == 3
        assert server.registers[server.base + 13] == 300
        assert server.registers[server.base + 15] == int(mode == "grid_charge")


def test_limits_clamp_and_round_down_and_renew_unchanged_commands():
    with inverter() as (driver, server):
        command = BatteryCommand("limits", 999999, 1234.56)
        driver.apply(command, {})
        driver.apply(command, {})
        assert server.writes.count((server.base + 13, [300])) == 2
        assert server.registers[server.base + 11] == 10000
        assert server.registers[server.base + 10] == 2469


def test_release_disables_limits_and_restores_original_grid_permission():
    with inverter() as (driver, server):
        driver.apply(BatteryCommand("grid_charge", 1000, 0), {})
        driver.release({})
        assert server.registers[server.base + 3] == 0
        assert server.registers[server.base + 15] == 0
        # Retrying release after a reconnect also disables leftover limits.
        server.registers[server.base + 3] = 3
        driver.original_grid = None
        driver.release({})
        assert server.registers[server.base + 3] == 0


def test_export_requires_explicit_capability_before_any_connection():
    with inverter() as (driver, server):
        with pytest.raises(UnsupportedFeature):
            driver.apply(BatteryCommand("grid_discharge", 0, 1000), {})
        assert not server.writes
        assert driver.model is None


@pytest.mark.parametrize("offset,value", [(0, 0), (0, 65535), (16, 32768), (23, 32768), (3, 4), (15, 65535)])
def test_invalid_device_data_prevents_all_writes(offset, value):
    with inverter() as (driver, server):
        server.registers[server.base + offset] = value
        with pytest.raises(ModbusError):
            driver.apply(BatteryCommand("limits", 1000, 1000), {})
        assert not server.writes


def test_missing_or_changed_model_never_writes_to_cached_addresses():
    with inverter() as (driver, server):
        server.registers[server.base - 2] = 65535
        with pytest.raises(ModbusError):
            driver.apply(BatteryCommand("limits", 1000, 1000), {})
        assert not server.writes

        # Rediscover a valid model, then refuse a changed cached layout.
        server.registers[server.base - 2] = 124
        driver.apply(BatteryCommand("limits", 1000, 1000), {})
        server.writes.clear()
        server.registers[server.base - 2] = 65535
        with pytest.raises(ModbusError):
            driver.apply(BatteryCommand("limits", 1000, 1000), {})
        assert not server.writes


def test_non_fronius_device_is_not_controlled():
    with inverter() as (driver, server):
        server.registers[40004] = 0
        with pytest.raises(ModbusError):
            driver.apply(BatteryCommand("limits", 1000, 1000), {})
        assert not server.writes


def test_rejected_and_unconfirmed_commands_are_failures():
    with inverter() as (driver, server):
        server.reject = True
        with pytest.raises(ModbusError):
            driver.apply(BatteryCommand("limits", 1000, 1000), {})
        server.reject = False
        server.ignore_writes = True
        with pytest.raises(ModbusError):
            driver.apply(BatteryCommand("limits", 1000, 1000), {})
        assert server.registers[server.base + 3] == 0


@pytest.mark.parametrize("address", [40342, 40352])
def test_telemetry_is_read_directly_without_ha_entities(address):
    with inverter(address) as (driver, server):
        measured = driver.read({}, NOW)
        assert (measured.soc, measured.charge, measured.discharge) == (55, 1500, 0)
        assert (measured.soc_sample, measured.charge_sample, measured.discharge_sample) == (NOW, NOW, NOW)
        assert all(not identity for identity in driver.ids.values())
        assert not server.writes


def test_telemetry_reads_new_values_on_each_poll():
    with inverter() as (driver, server):
        measured = driver.read({}, NOW)
        assert (measured.soc, measured.charge, measured.discharge) == (55, 1500, 0)
        server.registers[server.base + 6] = 5700
        server.registers[40130] = 0
        server.registers[40150] = 2500
        later = NOW + timedelta(seconds=120)
        measured = driver.read({}, later)
        assert (measured.soc, measured.charge, measured.discharge) == (57, 0, 2500)
        assert measured.discharge_sample == later
        server.reject = True
        with pytest.raises(ModbusError):
            driver.read({}, later + timedelta(seconds=20))


@pytest.mark.parametrize("offset,value", [(6, 65535), (20, 32768), (6, 10001)])
def test_invalid_soc_is_unknown_not_zero(offset, value):
    with inverter() as (driver, server):
        server.registers[server.base + offset] = value
        measured = driver.read({}, NOW)
        assert measured.soc is None and measured.soc_sample is None
        assert measured.charge == 1500


@pytest.mark.parametrize("register,value", [(40130, 65535), (40073, 32768), (40073, 5)])
def test_invalid_power_and_scale_are_unknown(register, value):
    with inverter() as (driver, server):
        server.registers[register] = value
        measured = driver.read({}, NOW)
        assert measured.charge is None and measured.charge_sample is None


def test_power_scaling_uses_unsigned_words_and_channel_ids():
    with inverter() as (driver, server):
        server.registers[40073] = 65535  # -1 power scale
        server.registers[40119] = 4     # Swap storage channels: classify by ID.
        server.registers[40139] = 3
        server.registers[40130] = 40000  # uint16, not signed int16
        server.registers[40150] = 15000
        measured = driver.read({}, NOW)
        assert (measured.charge, measured.discharge) == (1500, 4000)


def test_missing_battery_channel_never_uses_pv_power():
    with inverter() as (driver, server):
        server.registers[40119] = 5  # No channel 3.
        measured = driver.read({}, NOW)
        assert measured.charge is None
        assert measured.discharge == 0


@pytest.mark.parametrize("raw,expected", [(0, 0), (10000, 100)])
def test_soc_endpoints_and_idle_power_are_valid(raw, expected):
    with inverter() as (driver, server):
        server.registers[server.base + 6] = raw
        server.registers[40130] = 0
        measured = driver.read({}, NOW)
        assert (measured.soc, measured.charge, measured.discharge) == (expected, 0, 0)
        assert measured.soc_sample == NOW


def test_missing_mppt_still_allows_returning_storage_control_to_auto():
    with inverter() as (driver, server):
        server.registers[40069] = 999  # No model 160.
        server.registers[server.base + 3] = 3
        with pytest.raises(ModbusError):
            driver.read({}, NOW)
        assert not server.writes
        driver.release({})
        assert server.registers[server.base + 3] == 0


@pytest.mark.parametrize("register,value", [(40070, 89), (40077, 3), (40139, 3)])
def test_inconsistent_mppt_layout_is_rejected(register, value):
    with inverter() as (driver, server):
        server.registers[register] = value
        with pytest.raises(ModbusError):
            driver.read({}, NOW)
        assert not server.writes


@pytest.mark.parametrize("override", [{"port": 0}, {"port": 502.5}, {"unit_id": 0}, {"unit_id": 248},
                                      {"host": "http://inverter"}, {"host": "host/path"}, {"host": "a\nb"}])
def test_bad_connection_settings_fail_without_connecting(override):
    params = {"host": "inverter.local", **override}
    with patch("socket.create_connection") as connect, pytest.raises(ValueError):
        BATTERY_DRIVERS["fronius_modbus"](None, params)
    connect.assert_not_called()


@pytest.mark.parametrize("header,pdu", [
    ((2, 0, 5, 1), b"\x03\x02\x00\x01"),  # Wrong transaction.
    ((1, 1, 5, 1), b"\x03\x02\x00\x01"),  # Wrong protocol.
    ((1, 0, 5, 2), b"\x03\x02\x00\x01"),  # Wrong unit.
    ((1, 0, 65535, 1), b""),  # Unbounded length.
    ((1, 0, 5, 1), b"\x04\x02\x00\x01"),  # Wrong function.
    ((1, 0, 5, 1), b"\x03\x04\x00\x01"),  # Wrong byte count.
    ((1, 0, 3, 1), b"\x83\x03"),  # Device exception.
])
def test_invalid_transport_responses_fail_closed(header, pdu):
    connection = Mock()
    buffer = bytearray(struct.pack(">HHHB", *header) + pdu)

    def recv(count):
        data = bytes(buffer[:count])
        del buffer[:count]
        return data

    connection.recv.side_effect = recv
    connection.__enter__ = Mock(return_value=connection)
    connection.__exit__ = Mock(return_value=False)
    with patch("socket.create_connection", return_value=connection), pytest.raises(ModbusError):
        ModbusTCP("inverter.local", 502, 1).read(40000, 1)


def test_transport_timeout_propagates_without_retrying_writes():
    with patch("socket.create_connection", side_effect=socket.timeout), pytest.raises(TimeoutError):
        ModbusTCP("inverter.local", 502, 1).write(40345, [3])

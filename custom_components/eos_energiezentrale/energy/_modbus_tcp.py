"""Bounded synchronous Modbus TCP transport (FC03/FC16), used in the HA executor."""
import socket
import struct
import ipaddress
import re
from time import monotonic, sleep

# Some devices (e.g. Victron GX) acknowledge a write before the new value can be read back.
CONFIRM_TIMEOUT = 1.0
CONFIRM_INTERVAL = 0.1


class ModbusError(OSError):
    """Transport, protocol or device confirmation failed.

    ``reason`` is a fixed code for diagnostics: ``rejected`` (Modbus exception response),
    ``not_acknowledged``, ``readback_mismatch``, ``invalid_response`` or ``connection_closed``.
    """

    def __init__(self, message, *, exception_code=None, reason=None):
        super().__init__(message)
        self.exception_code = exception_code
        self.reason = reason


def checked_host(host):
    try:
        ipaddress.ip_address(host)
    except ValueError:
        if (len(host)>253 or not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?',label)
                                    for label in host.split('.'))):
            raise ValueError('Modbus host must be an IP address or hostname') from None
    return host


class ModbusTCP:
    def __init__(self, host, port, unit, timeout=3):
        self.host, self.port, self.unit, self.timeout = host, port, unit, timeout
        self.transaction = 0

    @staticmethod
    def _receive(connection, size, deadline):
        result = bytearray()
        while len(result) < size:
            remaining = deadline - monotonic()
            if remaining <= 0:
                raise TimeoutError("Modbus response deadline exceeded")
            connection.settimeout(remaining)
            chunk = connection.recv(size - len(result))
            if not chunk:
                raise ModbusError("Modbus connection closed before response completed", reason="connection_closed")
            result.extend(chunk)
        return bytes(result)

    def _request(self, function, payload):
        self.transaction = (self.transaction + 1) % 65536
        pdu = bytes([function]) + payload
        header = struct.pack(">HHHB", self.transaction, 0, len(pdu) + 1, self.unit)
        with socket.create_connection((self.host, self.port), timeout=self.timeout) as connection:
            deadline = monotonic() + self.timeout
            connection.sendall(header + pdu)
            transaction, protocol, size, unit = struct.unpack(">HHHB", self._receive(connection, 7, deadline))
            if (transaction != self.transaction or protocol != 0 or unit != self.unit
                    or not 2 <= size <= 254):
                raise ModbusError("Invalid Modbus response header", reason="invalid_response")
            response = self._receive(connection, size - 1, deadline)
        if response[0] == function | 0x80:
            raise ModbusError("Modbus device rejected request",
                              exception_code=response[1] if len(response) == 2 else None, reason="rejected")
        if response[0] != function:
            raise ModbusError("Unexpected Modbus response function", reason="invalid_response")
        return response[1:]

    def read(self, address, count):
        if not 1 <= count <= 125 or not 0 <= address <= 65536 - count:
            raise ValueError("Invalid Modbus read range")
        response = self._request(3, struct.pack(">HH", address, count))
        if len(response) != 1 + count * 2 or response[0] != count * 2:
            raise ModbusError("Invalid Modbus register response", reason="invalid_response")
        return list(struct.unpack(">" + "H" * count, response[1:]))

    def write(self, address, values):
        if not 1 <= len(values) <= 123 or not 0 <= address <= 65536 - len(values):
            raise ValueError("Invalid Modbus write range")
        data = struct.pack(">" + "H" * len(values), *values)
        expected = struct.pack(">HH", address, len(values))
        response = self._request(16, expected + bytes([len(data)]) + data)
        if response != expected:
            raise ModbusError("Modbus write was not acknowledged", reason="not_acknowledged")
        # Read back until the device reports the value, bounded in time; never accept a different value.
        deadline = monotonic() + CONFIRM_TIMEOUT
        while self.read(address, len(values)) != list(values):
            if monotonic() >= deadline:
                raise ModbusError("Modbus register did not confirm requested value", reason="readback_mismatch")
            sleep(CONFIRM_INTERVAL)

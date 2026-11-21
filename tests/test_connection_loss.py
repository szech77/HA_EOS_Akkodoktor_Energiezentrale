"""Which failures count as an unreachable device (control pauses) and which as a refusal."""
import errno
import socket
from urllib.error import URLError

from custom_components.eos_energiezentrale.energy._modbus_tcp import ModbusError
from custom_components.eos_energiezentrale.energy.failures import HardwareAPIError, connection_lost


def wrapped(outer, inner):
    try:
        try:
            raise inner
        except BaseException as error:
            raise outer from error
    except BaseException as error:
        return error


def test_timeouts_refused_and_dropped_connections_are_connection_losses():
    for error in (TimeoutError(), socket.timeout(), ConnectionRefusedError(), ConnectionResetError(),
                  OSError(errno.EHOSTUNREACH, 'unreachable'), ModbusError('closed', reason='connection_closed'),
                  URLError(TimeoutError()), wrapped(HardwareAPIError('go-e'), TimeoutError())):
        assert connection_lost(error), error


def test_answers_of_the_device_and_other_failures_are_not():
    for reason in ('rejected', 'not_acknowledged', 'readback_mismatch', 'invalid_response'):
        assert not connection_lost(wrapped(ModbusError('answer', reason=reason), TimeoutError()))
    for error in (ValueError('setpoint'), OSError('unconfirmed command'), KeyError('soc'), None):
        assert not connection_lost(error)

"""The GX Modbus service is shared: few requests over one kept connection, confirmed again after failures."""
from time import monotonic, sleep
from unittest.mock import patch

import pytest

from custom_components.eos_energiezentrale.energy._modbus_tcp import ModbusError, ModbusTCP
from custom_components.eos_energiezentrale.energy.plugins import victron_modbus
from test_energy import NOW
from test_fronius_modbus import inverter
from test_victron_modbus import command, gx, target


def addresses(server):
    return [address for _, _, address, _ in server.requests]


def test_one_connection_serves_all_requests_and_a_closed_idle_connection_is_opened_once_more():
    with inverter() as (_, server):
        client = ModbusTCP('127.0.0.1', server.server_address[1], 1)
        for _ in range(5):
            client.read(40000, 2)
        assert server.connections == 1 and client.opened == 1
        # The device closed the kept connection while idle: the request is sent again on a new one.
        server.drop_after_requests = 0
        assert client.read(40000, 2) == [0x5375, 0x6E53]
        assert server.connections == 2 and client.opened == 2
        client.close()


def timeouts(count):
    """Let the next ``count`` responses miss their deadline, then answer normally."""
    receive = ModbusTCP._receive
    remaining = [count]

    def delayed(connection, size, deadline):
        if remaining[0] > 0:
            remaining[0] -= 1
            raise TimeoutError('deadline')
        return receive(connection, size, deadline)
    return patch.object(ModbusTCP, '_receive', side_effect=delayed)


def wait_for(condition):
    deadline = monotonic() + 2
    while not condition() and monotonic() < deadline:
        sleep(0.01)
    return condition()


def test_a_read_that_misses_one_deadline_is_sent_once_more_on_a_new_connection():
    with inverter() as (_, server):
        client = ModbusTCP('127.0.0.1', server.server_address[1], 1)
        client.read(40000, 2)
        with timeouts(1):
            assert client.read(40000, 2) == [0x5375, 0x6E53]
        assert client.connected and client.opened == 2
        client.close()


def test_a_read_that_times_out_twice_fails_and_the_next_request_uses_a_new_connection():
    with inverter() as (_, server):
        client = ModbusTCP('127.0.0.1', server.server_address[1], 1)
        client.read(40000, 2)
        with timeouts(2), pytest.raises(TimeoutError):
            client.read(40000, 2)
        assert not client.connected
        with timeouts(2), pytest.raises(TimeoutError):
            client.read(40000, 2)
        assert client.read(40000, 2) == [0x5375, 0x6E53]
        client.close()


def test_a_write_that_times_out_is_not_sent_again():
    with inverter() as (_, server):
        client = ModbusTCP('127.0.0.1', server.server_address[1], 1)
        with timeouts(1), pytest.raises(TimeoutError):
            client.write(40000, [1])
        assert wait_for(lambda: [r[0] for r in server.requests] == [16])
        sleep(0.1)
        assert [request[0] for request in server.requests] == [16]
        assert not client.connected
        client.close()


def test_a_read_cycle_needs_three_requests_and_identity_is_confirmed_only_now_and_then():
    with gx() as (driver, server, _):
        assert driver.read({}, NOW).power_supply.mode == 'grid'
        first = addresses(server)
        assert first.count(800) == 1 and 834 in first
        # Consumption, grid and the active AC input arrive in one block; no separate 826 request.
        assert (3, 100, 817, 10) in server.requests and 826 not in first and 820 not in first
        server.requests.clear()
        sample = driver.read({}, NOW)
        assert addresses(server) == [840, 850, 817]
        assert {key: item.value for key, item in sample.measurements.items()} == {'solar': 2000, 'grid': 1000, 'house_total': 6000}
        assert server.connections == 1
        # After the refresh time identity and firmware are read again.
        with patch.object(victron_modbus.time, 'monotonic', return_value=victron_modbus.time.monotonic() + victron_modbus.IDENTITY_REFRESH_S):
            server.requests.clear()
            driver.read({}, NOW)
        assert addresses(server)[:2] == [800, 834]


def test_a_gx_that_misses_one_deadline_still_delivers_the_reading_and_identity_is_confirmed_again():
    with gx() as (driver, server, _):
        driver.read({}, NOW)
        server.requests.clear()
        with timeouts(1):
            sample = driver.read({}, NOW)
        assert driver.read_diagnostics['failure'] is None
        assert {key: item.value for key, item in sample.measurements.items()} == {'solar': 2000, 'grid': 1000, 'house_total': 6000}
        # The repeated read used a new connection: the GX identity is confirmed on it.
        assert server.connections == 2 and 800 in addresses(server)


def test_ess_state_is_confirmed_before_control_and_again_after_a_failure():
    with gx() as (driver, server, _):
        driver.apply(command('grid_charge', 2000, 0), {})
        assert addresses(server).count(2900) == 1 and addresses(server).count(5423) == 1
        driver.apply(command('grid_charge', 2000, 0), {})
        assert addresses(server).count(2900) == 1
        # A failed request (here an answer that is not understood) checks everything again.
        server.reject = True
        with pytest.raises(ModbusError):
            driver.apply(command(), {})
        server.reject = False
        server.requests.clear()
        driver.apply(command('grid_charge', 2000, 0), {})
        assert {800, 2900, 5423} <= set(addresses(server))
        assert target(server) == 3000


def test_a_disconnected_grid_input_in_the_control_snapshot_still_blocks_writes():
    with gx() as (driver, server, _):
        driver.apply(command('grid_charge', 2000, 0), {})
        writes = len(server.writes)
        server.registers[826] = 240
        with pytest.raises(ModbusError, match='grid input'):
            driver.apply(command(), {})
        assert len(server.writes) == writes
        assert driver.telemetry_status[0]['details']['stage'] == 'grid_connection'


def test_a_server_without_the_block_range_is_read_group_by_group():
    with gx() as (driver, server, _):
        original = driver.client.read

        def read(address, count):
            if (address, count) == (817, 10):
                raise ModbusError('illegal address', exception_code=2, reason='rejected')
            return original(address, count)

        with patch.object(driver.client, 'read', side_effect=read):
            sample = driver.read({}, NOW)
            assert {key: item.value for key, item in sample.measurements.items()} == {'solar': 2000, 'grid': 1000, 'house_total': 6000}
            assert sample.power_supply.mode == 'grid'
            server.requests.clear()
            driver.read({}, NOW)
        assert addresses(server) == [840, 850, 820, 817, 826]

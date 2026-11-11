"""EOS collection updates preserve other resources under concurrent requests."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event, Lock
from unittest.mock import patch

from custom_components.eos_energiezentrale.energy.clients import EOS


def test_two_clients_updating_vehicles_do_not_overwrite_each_other():
    configuration = {"devices": {"electric_vehicles": {
        "ev1": {"capacity_wh": 77000}, "ev2": {"capacity_wh": 40000}}}}
    first_read, release_first = Event(), Event()
    access = Lock()
    read_count = 0

    def fake_request(url, *, method="GET", payload=None, **_kwargs):
        nonlocal read_count
        if method == "PUT":
            with access:
                configuration["devices"]["electric_vehicles"] = deepcopy(payload)
            return {}
        with access:
            result = deepcopy(configuration)
            read_count += 1
            first = read_count == 1
        if first:
            first_read.set()
            if not release_first.wait(5):
                raise TimeoutError("test did not release first request")
        return result

    with patch("custom_components.eos_energiezentrale.energy.clients.request", side_effect=fake_request):
        client1, client2 = EOS("http://same-eos"), EOS("http://SAME-EOS:80/")
        with ThreadPoolExecutor(max_workers=2) as workers:
            first = workers.submit(client1.set_vehicle_goal, "ev1", 70, None)
            try:
                assert first_read.wait(2)
                second_started = Event()

                def update_second():
                    second_started.set()
                    client2.set_vehicle_goal("ev2", 80, None)

                second = workers.submit(update_second)
                assert second_started.wait(2)
                try:
                    second.result(timeout=0.25)
                except TimeoutError:
                    pass  # It may wait until the first update finishes.
            finally:
                release_first.set()
            first.result(timeout=5)
            second.result(timeout=5)

    vehicles = configuration["devices"]["electric_vehicles"]
    assert vehicles["ev1"]["min_soc_percentage"] == 70
    assert vehicles["ev2"]["min_soc_percentage"] == 80
    assert vehicles["ev1"]["capacity_wh"] == 77000
    assert vehicles["ev2"]["capacity_wh"] == 40000


def test_failed_update_does_not_prevent_subsequent_writes():
    client1, client2 = EOS("http://same-eos"), EOS("http://same-eos")
    with patch("custom_components.eos_energiezentrale.energy.clients.request", side_effect=OSError("offline")):
        try:
            client1.set_vehicle_goal("ev1", 70, None)
        except OSError:
            pass
        else:
            raise AssertionError("expected an unavailable EOS")
    with patch("custom_components.eos_energiezentrale.energy.clients.request", return_value={"devices": {"electric_vehicles": {
        "ev1": {"min_soc_percentage": 70, "max_soc_percentage": 70,
                "min_soc_deadline_datetime": None, "min_soc_max_duration_h": None}}}}):
        client2.set_vehicle_goal("ev1", 70, None)


def test_a_slow_eos_instance_does_not_block_another_instance():
    started, release = Event(), Event()
    configured = {"devices": {"electric_vehicles": {"ev1": {
        "min_soc_percentage": 70, "max_soc_percentage": 70,
        "min_soc_deadline_datetime": None, "min_soc_max_duration_h": None}}}}

    def request(url, **_kwargs):
        if "slow-eos" in url:
            started.set()
            if not release.wait(5):
                raise TimeoutError("test did not release slow EOS")
        return deepcopy(configured)

    with patch("custom_components.eos_energiezentrale.energy.clients.request", side_effect=request):
        with ThreadPoolExecutor(max_workers=2) as workers:
            slow = workers.submit(EOS("http://slow-eos").set_vehicle_goal, "ev1", 70, None)
            try:
                assert started.wait(2)
                fast = workers.submit(EOS("http://fast-eos").set_vehicle_goal, "ev1", 70, None)
                fast.result(timeout=2)
            finally:
                release.set()
            slow.result(timeout=5)

"""EOS collection updates preserve other resources under concurrent requests."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event, Lock
from unittest.mock import patch

from custom_components.eos_energiezentrale.energy.clients import EOS
import pytest


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


def test_socket_limits_and_absence_preserve_other_vehicles_and_positive_rating():
    configuration={'devices':{'electric_vehicles':{
        'ev1':{'capacity_wh':77000,'max_charge_power_w':11000,'min_soc_percentage':70,
               'min_soc_deadline_datetime':'2026-11-12T09:00:00+00:00'},
        'ev2':{'capacity_wh':40000,'max_charge_power_w':7000}}}}
    other=deepcopy(configuration['devices']['electric_vehicles']['ev2'])
    def request(_url,*,method='GET',payload=None):
        if method=='PUT':
            configuration['devices']['electric_vehicles']=deepcopy(payload)
        return deepcopy(configuration)
    with patch('custom_components.eos_energiezentrale.energy.clients.request',side_effect=request):
        eos=EOS('http://eos')
        eos.set_vehicle_charging_limits('ev1',2300,1380,(0.,.6,1.),True)
        ev=configuration['devices']['electric_vehicles']['ev1']
        assert ev['max_charge_power_w']==2300 and ev['charge_rates']==[0.,.6,1.]
        eos.set_vehicle_charging_limits('ev1',None,None,(0.,),False)
        ev=configuration['devices']['electric_vehicles']['ev1']
        assert ev['max_charge_power_w']==2300 and ev['charge_rates']==[0.]
        assert ev['min_soc_percentage']==ev['max_soc_percentage']==0
        assert ev['min_soc_deadline_datetime'] is None
        eos.set_vehicle_charging_limits('ev1',11040,4140,(0.,.375,1.),True)
        assert configuration['devices']['electric_vehicles']['ev1']['max_charge_power_w']==11040
        assert configuration['devices']['electric_vehicles']['ev2']==other


def test_unconfirmed_socket_limit_is_rejected():
    with patch('custom_components.eos_energiezentrale.energy.clients.request',return_value={
            'devices':{'electric_vehicles':{'ev1':{'max_charge_power_w':11000}}}}),pytest.raises(ValueError):
        EOS('http://eos').set_vehicle_charging_limits('ev1',2300,1380,(0.,1.),True)


@pytest.mark.parametrize('charge,discharge',[(8000,9000),(0,9000),(8000,0),(0,0)])
def test_combined_storage_capacity_and_power_sync_preserves_other_resources_and_settings(charge,discharge):
    config={'devices':{'batteries':{
        'pool':{'capacity_wh':10000,'charging_efficiency':.95,'other':'preserved'},
        'other':{'capacity_wh':5000}}}}
    def request(_url,*,method='GET',payload=None):
        if method=='PUT': config['devices']['batteries']=deepcopy(payload)
        return deepcopy(config)
    with patch('custom_components.eos_energiezentrale.energy.clients.request',side_effect=request):
        EOS('http://eos').set_battery_limits('pool',20,90,30000,charge,discharge)
    pool=config['devices']['batteries']['pool']
    assert pool['capacity_wh']==30000
    assert (pool['max_charge_power_w'],pool['max_discharge_power_w'])==(charge,discharge)
    assert (pool['min_soc_percentage'],pool['max_soc_percentage'])==(20,90)
    assert pool['charging_efficiency']==.95 and pool['other']=='preserved'
    assert config['devices']['batteries']['other']=={'capacity_wh':5000}


def test_unconfirmed_group_capacity_is_rejected():
    configured={'devices':{'batteries':{'pool':{'capacity_wh':10000}}}}
    with patch('custom_components.eos_energiezentrale.energy.clients.request',return_value=configured),pytest.raises(ValueError):
        EOS('http://eos').set_battery_limits('pool',20,90,30000,8000,9000)

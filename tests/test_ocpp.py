"""Real OCPP frames: authentication, setup, measurements and acknowledged limits."""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
import socket
import ssl
from types import SimpleNamespace
from unittest.mock import patch

import aiohttp
from ocpp.routing import on
from ocpp.v16 import ChargePoint, call, call_result
from ocpp.v16.enums import Action
import pytest

from custom_components.eos_energiezentrale.energy import _ocpp_server
from custom_components.eos_energiezentrale.energy._ocpp_server import Socket, WIRE_LOG, OCPPError, power_watts
from custom_components.eos_energiezentrale.energy.contracts import UnsupportedFeature
from custom_components.eos_energiezentrale.energy.drivers import WALLBOX_DRIVERS
from custom_components.eos_energiezentrale.energy.failures import PluginParameterError


PASSWORD = 'test-only-ocpp-password'
CONTROL = ('profile', 'start', 'stop')


class Charger(ChargePoint):
    def __init__(self, websocket, configuration=None):
        super().__init__('simulator', Socket(websocket), response_timeout=3, logger=WIRE_LOG)
        self.commands = []
        self.tasks = []
        self.transaction = None
        self.profile_status = self.start_status = 'Accepted'
        self.confirm_start = True
        self.configuration = configuration if configuration is not None else {
            'SupportedFeatureProfiles':'Core,SmartCharging,RemoteTrigger',
            'MeterValuesSampledData':'Power.Active.Import', 'MeterValueSampleInterval':'10'}

    def control(self):
        return [command for command in self.commands if command[0] in CONTROL]

    def limits(self):
        return [command[2]['charging_schedule']['charging_schedule_period'] for command in self.commands if command[0] == 'profile']

    @on(Action.get_configuration)
    async def get_configuration(self, key=None):
        self.commands.append(('get_configuration', key))
        return call_result.GetConfiguration(configuration_key=[
            {'key':name, 'readonly':False, 'value':value} for name, value in self.configuration.items()])

    @on(Action.change_configuration)
    async def change_configuration(self, key, value):
        self.commands.append(('change_configuration', key, value))
        return call_result.ChangeConfiguration(status='Accepted')

    @on(Action.trigger_message)
    async def trigger_message(self, requested_message, connector_id=None):
        self.commands.append(('trigger', requested_message))
        return call_result.TriggerMessage(status='Accepted')

    @on(Action.set_charging_profile)
    async def profile(self, connector_id, cs_charging_profiles):
        self.commands.append(('profile', connector_id, cs_charging_profiles))
        return call_result.SetChargingProfile(status=self.profile_status)

    @on(Action.remote_start_transaction)
    async def remote_start(self, id_tag, connector_id=None, **kwargs):
        self.commands.append(('start', connector_id))
        if self.start_status == 'Accepted' and self.confirm_start:
            self.tasks.append(asyncio.create_task(self.started(id_tag)))
        return call_result.RemoteStartTransaction(status=self.start_status)

    @on(Action.remote_stop_transaction)
    async def remote_stop(self, transaction_id):
        self.commands.append(('stop', transaction_id))
        return call_result.RemoteStopTransaction(status='Accepted')

    async def started(self, id_tag):
        result = await self.call(call.StartTransaction(connector_id=1, id_tag=id_tag,
            meter_start=0, timestamp=datetime.now(timezone.utc).isoformat()))
        assert result.id_tag_info['status'] == 'Accepted'
        self.transaction = result.transaction_id
        await self.status('Charging')

    async def status(self, value, connector=1, error='NoError'):
        await self.call(call.StatusNotification(connector_id=connector, error_code=error, status=value))

    async def meter(self, watts, *, stamp=None, connector=1, context=None, **kwargs):
        sample = {'measurand':'Power.Active.Import','value':str(watts),'unit':'W'}
        if context:
            sample['context'] = context
        block = {'timestamp':(stamp or datetime.now(timezone.utc)).isoformat(), 'sampledValue':[sample]}
        await self.call(call.MeterValues(connector_id=connector, meter_value=[block], **kwargs))


def unused_port():
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1',0))
        return reservation.getsockname()[1]


async def until(condition, timeout=3):
    for _ in range(int(timeout / .02)):
        if condition():
            return
        await asyncio.sleep(.02)
    raise AssertionError('condition not reached')


@asynccontextmanager
async def station(client_ssl=True, configuration=None, boot=True, **params):
    port = unused_port()
    with patch.dict('os.environ', {'EOS_OCPP_PASSWORD':PASSWORD}):
        box = WALLBOX_DRIVERS['ocpp'](None, {'port':port, **params})
        try:
            await asyncio.to_thread(box.read, {}, datetime.now(timezone.utc))
            async with aiohttp.ClientSession() as http:
                scheme='https' if params.get('tls_cert') else 'http'
                async with http.ws_connect(f'{scheme}://127.0.0.1:{port}/wallbox', ssl=client_ssl,
                        protocols=('ocpp1.6',), headers={'Authorization':aiohttp.encode_basic_auth('wallbox',PASSWORD)}) as ws:
                    cp = Charger(ws, configuration)
                    reader = asyncio.create_task(cp.start())
                    try:
                        if boot:
                            result = await cp.call(call.BootNotification(charge_point_vendor='Simulator',charge_point_model='Test'))
                            assert result.status == 'Accepted'
                            await until(lambda: box.server.setup_state != 'pending')
                        await cp.status('Preparing')
                        await cp.meter(0)
                        yield box, cp, http, port
                        if cp.tasks:
                            await asyncio.gather(*cp.tasks)
                    finally:
                        for task in cp.tasks:
                            if not task.done():
                                task.cancel()
                        reader.cancel()
                        await asyncio.gather(reader,*cp.tasks,return_exceptions=True)
        finally:
            await asyncio.to_thread(box.close)


def read(box):
    return box.read({},datetime.now(timezone.utc))


def test_charging_starts_a_waiting_vehicle_and_pausing_keeps_its_transaction_open():
    async def scenario():
        async with station() as (box, cp, _, _):
            state = await asyncio.to_thread(read,box)
            assert state.status == 'connected' and state.phases == 3
            assert state.watts == 0 and not state.enabled and state.amps == 0
            await asyncio.to_thread(box.charge, 10, state)
            await asyncio.gather(*cp.tasks)
            assert cp.transaction is not None
            assert [command[0] for command in cp.control()] == ['profile','start']
            profile = cp.control()[0][2]
            assert profile['charging_profile_purpose'] == 'TxDefaultProfile' and profile['stack_level'] == 1
            assert profile['charging_schedule']['charging_rate_unit'] == 'A'
            # The schedule starts a minute early, so a charger clock running behind still applies it.
            start = datetime.fromisoformat(profile['charging_schedule']['start_schedule'])
            assert 55 <= (datetime.now(timezone.utc) - start).total_seconds() <= 65
            assert cp.limits()[0] == [{'start_period':0,'limit':10.,'number_phases':3},
                                      {'start_period':240,'limit':0.,'number_phases':3}]
            await cp.meter(6900)
            state = await asyncio.to_thread(read,box)
            assert state.enabled and state.watts == 6900 and state.amps == 10 and state.status == 'charging'
            # Pause: 0 A, no RemoteStopTransaction; the vehicle keeps its session.
            await asyncio.to_thread(box.pause,state)
            assert cp.limits()[-1] == [{'start_period':0,'limit':0.,'number_phases':3}]
            assert 'stop' not in [command[0] for command in cp.commands]
            await cp.status('SuspendedEVSE')
            await cp.meter(0)
            state = await asyncio.to_thread(read,box)
            assert not state.enabled and state.amps == 0 and box.server.transaction == cp.transaction
            # Resume: only a new limit, no second start.
            await asyncio.to_thread(box.charge,8,state)
            assert [command[0] for command in cp.control()] == ['profile','start','profile','profile']
            assert cp.limits()[-1][0]['limit'] == 8.
            assert (await asyncio.to_thread(read,box)).enabled
            with pytest.raises(UnsupportedFeature):
                box.phase(1,state)
    asyncio.run(scenario())


def test_an_unchanged_limit_is_renewed_only_with_a_fresh_valid_reading():
    async def scenario():
        async with station() as (box, cp, _, _):
            await asyncio.to_thread(box.charge,10,await asyncio.to_thread(read,box))
            await asyncio.gather(*cp.tasks)
            await cp.meter(6900)
            state = await asyncio.to_thread(read,box)
            count = len(cp.limits())
            await asyncio.to_thread(box.hold,10,state)
            assert len(cp.limits()) == count
            box.profile_at -= 31
            await asyncio.to_thread(box.hold,10,state)
            assert len(cp.limits()) == count + 1 and cp.limits()[-1][0]['limit'] == 10.
            box.profile_at -= 31
            stale = SimpleNamespace(**{**state.__dict__, 'sample':datetime.now(timezone.utc)-timedelta(seconds=121)})
            await asyncio.to_thread(box._hold,10,stale)
            assert len(cp.limits()) == count + 1
    asyncio.run(scenario())


def test_rejected_profile_never_starts_a_transaction_and_logs_without_private_frames(caplog):
    async def scenario():
        async with station() as (box,cp,_,_):
            cp.profile_status='Rejected'
            with pytest.raises(OCPPError):
                await asyncio.to_thread(box.charge,10,await asyncio.to_thread(read,box))
            assert [entry[0] for entry in cp.control()]==['profile']
            assert cp.transaction is None
            assert any(row['code']=='plugin_operation_failed' for row in box.telemetry_status)
    asyncio.run(scenario())
    assert 'set_charging_profile' in caplog.text
    assert PASSWORD not in caplog.text and 'sampledValue' not in caplog.text


def test_accepting_remote_start_without_transaction_is_not_a_confirmed_start():
    async def scenario():
        async with station() as (box,cp,_,_):
            cp.confirm_start=False
            with pytest.raises(OCPPError,match='start was not confirmed'):
                await asyncio.to_thread(box.charge,10,await asyncio.to_thread(read,box))
            assert not box.server.start_pending
            assert cp.limits()[-1][0]['limit']==0
    asyncio.run(scenario())


def test_a_session_started_by_the_charger_itself_is_accepted_and_regulated():
    async def scenario():
        async with station() as (box,cp,_,_):
            result=await cp.call(call.Authorize(id_tag='own-card'))
            assert result.id_tag_info['status']=='Accepted'
            result=await cp.call(call.StartTransaction(connector_id=1,id_tag='own-card',meter_start=0,
                timestamp=datetime.now(timezone.utc).isoformat()))
            assert result.id_tag_info['status']=='Accepted'
            assert box.server.transaction==result.transaction_id
            await cp.status('Charging')
            await cp.meter(4000)
            await asyncio.to_thread(box.charge,7,await asyncio.to_thread(read,box))
            assert [command[0] for command in cp.control()]==['profile']
    asyncio.run(scenario())


def test_unplugging_and_a_reboot_forget_the_remembered_transaction():
    async def scenario():
        async with station() as (box,cp,_,_):
            await asyncio.to_thread(box.charge,10,await asyncio.to_thread(read,box))
            await asyncio.gather(*cp.tasks)
            assert box.server.transaction is not None
            # A reboot does not end the session yet; the first conclusive status decides.
            await cp.call(call.BootNotification(charge_point_vendor='Simulator',charge_point_model='Test'))
            assert box.server.transaction is not None
            await cp.status('Preparing')
            assert box.server.transaction is None
            state=await asyncio.to_thread(read,box)
            assert not state.enabled
            await asyncio.to_thread(box.charge,10,state)
            await asyncio.gather(*cp.tasks)
            assert [command[0] for command in cp.control()].count('start')==2
            # Unplugged without a StopTransaction: the session is over.
            await cp.status('Available')
            state=await asyncio.to_thread(read,box)
            assert box.server.transaction is None and state.status=='disconnected' and state.watts==0
    asyncio.run(scenario())


def test_a_reboot_into_a_running_session_keeps_it():
    async def scenario():
        async with station() as (box,cp,_,_):
            await asyncio.to_thread(box.charge,10,await asyncio.to_thread(read,box))
            await asyncio.gather(*cp.tasks)
            transaction=box.server.transaction
            await cp.call(call.BootNotification(charge_point_vendor='Simulator',charge_point_model='Test'))
            await cp.status('Charging')
            assert box.server.transaction==transaction and not box.server.rebooted
    asyncio.run(scenario())


def test_freshness_follows_receipt_time_not_the_charger_clock():
    async def scenario():
        async with station() as (box,cp,_,_):
            ahead=datetime.now(timezone.utc)+timedelta(hours=1)
            await cp.meter(2500, stamp=ahead)
            assert (await asyncio.to_thread(read,box)).watts==2500
            # Older than the last charger time, another connector or a boundary snapshot: ignored.
            await cp.meter(9999, stamp=ahead-timedelta(seconds=1))
            await cp.meter(9999, connector=2)
            await cp.meter(9999, stamp=ahead+timedelta(seconds=1), context='Transaction.End')
            state=await asyncio.to_thread(read,box)
            assert state.watts==2500
            assert 0 <= (datetime.now(timezone.utc)-state.sample).total_seconds() < 5
    asyncio.run(scenario())


def test_stale_power_during_a_session_is_invalid_but_an_idle_connector_draws_nothing():
    async def scenario():
        async with station() as (box,cp,_,_):
            with box.server.changed:
                box.server.watts_at-=121
            # Idle without transaction: a known zero, not missing data.
            assert (await asyncio.to_thread(read,box)).watts==0
            await asyncio.to_thread(box.charge,10,await asyncio.to_thread(read,box))
            await asyncio.gather(*cp.tasks)
            await cp.meter(6900)
            with box.server.changed:
                box.server.watts_at-=121
            state=await asyncio.to_thread(read,box)
            assert state.watts is None
            assert any(row['code']=='plugin_measurements_incomplete' for row in box.telemetry_status)
            await cp.status('Faulted',connector=0,error='OtherError')
            assert (await asyncio.to_thread(read,box)).status=='error'
    asyncio.run(scenario())


def test_setup_reads_capabilities_and_configures_missing_meter_values():
    configuration={'SupportedFeatureProfiles':'Core,SmartCharging','ChargeProfileMaxStackLevel':'3',
        'ChargingScheduleAllowedChargingRateUnit':'Power','MeterValuesSampledData':'Energy.Active.Import.Register',
        'MeterValueSampleInterval':'60'}
    async def scenario():
        async with station(configuration=configuration) as (box,cp,_,_):
            assert ('change_configuration','MeterValuesSampledData','Power.Active.Import,Current.Offered') in cp.commands
            assert ('change_configuration','MeterValueSampleInterval','10') in cp.commands
            # Without RemoteTrigger in the feature list, nothing is triggered.
            assert not [command for command in cp.commands if command[0]=='trigger']
            server=box.server
            assert (server.stack_level,server.rate_unit,server.remote_trigger,server.smart_charging)==(3,'W',False,True)
            await asyncio.to_thread(box.charge,10,await asyncio.to_thread(read,box))
            profile=cp.control()[0][2]
            assert profile['stack_level']==3 and profile['charging_schedule']['charging_rate_unit']=='W'
            assert cp.limits()[0][0]['limit']==6900.
            diagnostics=box.read_diagnostics
            assert diagnostics['setup']=='configured' and diagnostics['vendor']=='Simulator'
    asyncio.run(scenario())


def test_setup_leaves_existing_meter_values_and_can_be_disabled():
    async def scenario():
        async with station() as (_,cp,_,_):
            assert not [command for command in cp.commands if command[0]=='change_configuration']
            assert ('trigger','MeterValues') in cp.commands and ('trigger','StatusNotification') in cp.commands
        async with station(configuration={'MeterValuesSampledData':''},configure_meter_values=False) as (_,cp,_,_):
            assert not [command for command in cp.commands if command[0]=='change_configuration']
    asyncio.run(scenario())


def test_a_charger_without_boot_notification_is_configured_after_connecting():
    async def scenario():
        with patch.object(_ocpp_server,'BOOT_WAIT_S',.05):
            async with station(boot=False) as (box,cp,_,_):
                await until(lambda: box.server.setup_state!='pending')
                assert cp.commands[0][0]=='get_configuration'
    asyncio.run(scenario())


def test_missing_meter_values_are_requested():
    async def scenario():
        async with station() as (box,cp,_,_):
            count=cp.commands.count(('trigger','MeterValues'))
            with box.server.changed:
                box.server.watts_at-=31
                box.server.last_trigger-=31
            await until(lambda: cp.commands.count(('trigger','MeterValues'))>count, timeout=4)
    asyncio.run(scenario())


def test_wrong_credentials_identity_protocol_and_duplicate_connection_are_rejected(caplog):
    async def scenario():
        async with station() as (box,cp,http,port):
            cases=[('wallbox', 'wallbox', 'wrong', ('ocpp1.6',),401),
                   ('other', 'wallbox', PASSWORD, ('ocpp1.6',),401),
                   ('wallbox', 'wallbox', PASSWORD, ('ocpp2.0.1',),400),
                   ('wallbox', 'wallbox', PASSWORD, ('ocpp1.6',),409)]
            for identity,user,password,protocols,status in cases:
                with pytest.raises(aiohttp.WSServerHandshakeError) as failure:
                    await http.ws_connect(f'http://127.0.0.1:{port}/{identity}',protocols=protocols,
                                          headers={'Authorization':aiohttp.encode_basic_auth(user,password)})
                assert failure.value.status==status
                await asyncio.to_thread(read,box)
            assert box.server.session is not None
            assert cp.transaction is None
    asyncio.run(scenario())
    assert 'authentication_failed' in caplog.text and 'protocol_unsupported' in caplog.text
    assert PASSWORD not in caplog.text


def test_phase_power_is_summed_only_when_complete_and_not_double_counted():
    values=[{'measurand':'Power.Active.Import','phase':phase,'value':'1.1','unit':'kW'} for phase in ('L1','L2','L3')]
    assert power_watts(values,3)==3300
    assert power_watts(values[:2],3) is None
    assert power_watts(values+[{'measurand':'Power.Active.Import','value':'5000'}],3)==5000
    assert power_watts([{'value':'1000','measurand':'Energy.Active.Import.Register'}],3) is None
    assert power_watts([{'value':'nan','measurand':'Power.Active.Import'}],3) is None


@pytest.mark.parametrize('params',[
    {'port':0}, {'port':9000.5}, {'connector':0}, {'max_current':81},
    {'bind_address':'not-an-IP'}, {'charge_point_id':'bad/path'}, {'id_tag':'x'*21},
    {'password_env':'INVALID-VAR'}, {'tls_cert':'cert.pem'}, {'password':'short'},
    {'configure_meter_values':'yes'},
])
def test_invalid_configuration_does_not_open_listener(params):
    with pytest.raises(PluginParameterError):
        WALLBOX_DRIVERS['ocpp'](None,params)


def test_configuration_is_lazy_and_missing_password_is_visible_without_binding():
    with patch.dict('os.environ',{},clear=True):
        box=WALLBOX_DRIVERS['ocpp'](None,{})
        assert box.server is None
        with pytest.raises(OCPPError,match='password is unavailable'):
            read(box)
        assert box.server.thread is None
        box.close()


def test_listener_port_is_released_on_close_and_close_is_idempotent():
    async def scenario():
        port=None
        async with station() as (box,_,_,port):
            server=box.server
        assert not server.thread.is_alive() and box.server is None
        box.close()
        with socket.socket() as replacement:
            replacement.bind(('127.0.0.1',port))
    asyncio.run(scenario())


def test_direct_password_is_not_echoed_in_plugin_form_or_diagnostics(caplog):
    from custom_components.eos_energiezentrale.plugin_forms import plugin_object, configured
    values={'password':PASSWORD}
    with patch.dict('os.environ',{},clear=True):
        checked=configured(WALLBOX_DRIVERS['ocpp'],values)
        control,defaults=plugin_object(WALLBOX_DRIVERS['ocpp'],checked)
        descriptor=control.serialize()['selector']['object']['fields']['password']
        assert descriptor['selector']['text']['type']=='password'
        assert 'default' not in descriptor and 'password' not in defaults
        assert PASSWORD not in str(control.serialize())
    assert PASSWORD not in caplog.text


def test_occupied_port_and_unreadable_tls_files_are_reported_without_secrets(caplog):
    with socket.socket() as occupied, patch.dict('os.environ',{'EOS_OCPP_PASSWORD':PASSWORD}):
        occupied.bind(('127.0.0.1',0));occupied.listen()
        box=WALLBOX_DRIVERS['ocpp'](None,{'port':occupied.getsockname()[1]})
        try:
            with pytest.raises(OCPPError,match='could not start'):
                read(box)
        finally:
            box.close()
    box=WALLBOX_DRIVERS['ocpp'](None,{'password':PASSWORD,'tls_cert':'missing-test-cert','tls_key':'missing-test-key'})
    try:
        with pytest.raises(OCPPError,match='could not start'):
            read(box)
    finally:
        box.close()
    assert 'listener_start' in caplog.text
    assert PASSWORD not in caplog.text and 'missing-test-key' not in caplog.text


def test_invalid_protocol_is_logged_and_disconnection_invalidates_retained_measurements(caplog):
    async def scenario():
        async with station() as (box,cp,_,_):
            await cp._connection.send('not-json')
            await asyncio.sleep(.05)
            state=await asyncio.to_thread(read,box)
            assert state.watts is None and state.status=='unavailable'
            assert box.read_diagnostics['connection_status'] in ('protocol_error','connection_lost')
    asyncio.run(scenario())
    assert 'plugin_unavailable' in caplog.text


def test_a_fault_blocks_positive_limits_but_never_a_pause():
    async def scenario():
        async with station() as (box,cp,_,_):
            state=await asyncio.to_thread(read,box)
            await cp.status('Faulted',error='OtherError')
            with pytest.raises(OCPPError):
                await asyncio.to_thread(box.charge,10,state)
            assert not cp.control()
            await asyncio.to_thread(box.pause,state)
            assert cp.limits()==[[{'start_period':0,'limit':0.,'number_phases':3}]]
            with box.server.changed:
                box.server.last_seen-=181
            await asyncio.to_thread(box.pause,state)
            assert len(cp.limits())==2
    asyncio.run(scenario())


def test_a_running_session_is_recovered_from_meter_values_but_never_a_finished_one():
    async def scenario():
        async with station() as (box,cp,_,_):
            await cp.status('Charging')
            await cp.meter(6900)
            state=await asyncio.to_thread(read,box)
            assert not state.enabled and state.watts==6900
            # Without a known transaction the default profile still limits the running session.
            await asyncio.to_thread(box.charge,10,state)
            assert [command[0] for command in cp.control()]==['profile']
            await cp.meter(6900,transaction_id=123)
            assert box.server.transaction==123 and (await asyncio.to_thread(read,box)).enabled
            await cp.call(call.StopTransaction(transaction_id=123,meter_stop=100,
                timestamp=datetime.now(timezone.utc).isoformat()))
            await cp.meter(0,transaction_id=123)
            assert box.server.transaction is None
    asyncio.run(scenario())


def test_no_vehicle_session_does_not_repeat_an_unchanged_limit():
    async def scenario():
        async with station() as (box,cp,_,_):
            await cp.status('Finishing')
            state=await asyncio.to_thread(read,box)
            for _ in range(3):
                await asyncio.to_thread(box.charge,10,state)
            assert [command[0] for command in cp.control()]==['profile']
            assert box.idle_reason()=='vehicle_complete'
    asyncio.run(scenario())


@pytest.mark.parametrize('status,transaction,reason',[
    ('Preparing',None,'access_control'), ('Preparing',5,None), ('SuspendedEV',5,'vehicle_waiting'),
    ('SuspendedEVSE',5,'charger_logic'), ('Finishing',None,'vehicle_complete'), ('Faulted',5,'charger_error'),
    ('Charging',5,None),
])
def test_the_ocpp_status_explains_an_idle_release(status,transaction,reason):
    box=WALLBOX_DRIVERS['ocpp'](None,{'password':PASSWORD})
    box.ocpp_status,box.ocpp_transaction=status,transaction
    assert box.idle_reason()==reason


def test_controller_starts_charging_and_renews_an_unchanged_setpoint():
    from custom_components.eos_energiezentrale.const import DEFAULTS
    from custom_components.eos_energiezentrale.energy.controller import Controller
    from custom_components.eos_energiezentrale.energy.settings import daily_settings
    from test_energy import temporary_project_directory
    async def scenario():
        with temporary_project_directory() as directory:
            async with station() as (box,cp,_,_):
                config=SimpleNamespace(directory=directory,wallbox=box,
                    options={**DEFAULTS,'wallbox_type':'ocpp','grid_limit_w':20000},
                    daily=daily_settings({'pv':False,'phase_auto':False},20))
                controller=Controller(None,config)
                controller.vehicle_profile=(11040,4140,(0,1),True)
                live={'solar':0,'grid':0,'battery_charge':0,'battery_discharge':0}
                await asyncio.to_thread(controller.regulate_car,await asyncio.to_thread(read,box),live,
                    6900,False,datetime.now(timezone.utc),1,{})
                await asyncio.gather(*cp.tasks)
                assert cp.transaction is not None
                await cp.meter(6900)
                count=len(cp.limits())
                controller.last_write -= timedelta(seconds=21)
                box.profile_at -= 31
                await asyncio.to_thread(controller.regulate_car,await asyncio.to_thread(read,box),live,
                    6900,False,datetime.now(timezone.utc),22,{})
                assert len(cp.limits())==count+1
                assert controller.close_resources() is None and box.server is None
    asyncio.run(scenario())


def test_wss_uses_a_verified_server_certificate():
    import ipaddress
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ec
    from cryptography.x509.oid import NameOID
    from test_energy import temporary_project_directory
    with temporary_project_directory() as directory:
        key=ec.generate_private_key(ec.SECP256R1())
        subject=x509.Name([x509.NameAttribute(NameOID.COMMON_NAME,'localhost')])
        now=datetime.now(timezone.utc)
        cert=(x509.CertificateBuilder().subject_name(subject).issuer_name(subject).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now-timedelta(minutes=1))
            .not_valid_after(now+timedelta(days=1))
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address('127.0.0.1'))]),critical=False)
            .sign(key,hashes.SHA256()))
        cert_path,key_path=directory/'server.pem',directory/'key.pem'
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,serialization.NoEncryption()))
        context=ssl.create_default_context(cafile=str(cert_path))
        async def scenario():
            async with station(tls_cert=str(cert_path),tls_key=str(key_path),client_ssl=context) as (box,_,_,_):
                assert (await asyncio.to_thread(read,box)).status=='connected'
        asyncio.run(scenario())
        key_path.write_bytes(key.private_bytes(serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,serialization.BestAvailableEncryption(b'test-only-key-password')))
        box=WALLBOX_DRIVERS['ocpp'](None,{'password':PASSWORD,'port':unused_port(),
            'tls_cert':str(cert_path),'tls_key':str(key_path)})
        try:
            with pytest.raises(OCPPError,match='could not start'):
                read(box)
        finally:
            box.close()

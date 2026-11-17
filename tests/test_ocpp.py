"""Real OCPP frames: authentication, measurements and acknowledged controls."""
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

from custom_components.eos_energiezentrale.energy._ocpp_server import Socket, WIRE_LOG, OCPPError, power_watts
from custom_components.eos_energiezentrale.energy.contracts import UnsupportedFeature
from custom_components.eos_energiezentrale.energy.drivers import WALLBOX_DRIVERS
from custom_components.eos_energiezentrale.energy.failures import PluginParameterError


PASSWORD = 'test-only-ocpp-password'


class Charger(ChargePoint):
    def __init__(self, websocket):
        super().__init__('simulator', Socket(websocket), response_timeout=3, logger=WIRE_LOG)
        self.commands = []
        self.tasks = []
        self.transaction = None
        self.profile_status = self.start_status = self.stop_status = 'Accepted'
        self.confirm_start = self.confirm_stop = True

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

    async def started(self, id_tag):
        result = await self.call(call.StartTransaction(connector_id=1, id_tag=id_tag,
            meter_start=0, timestamp=datetime.now(timezone.utc).isoformat()))
        assert result.id_tag_info['status'] == 'Accepted'
        self.transaction = result.transaction_id
        await self.status('Charging')

    @on(Action.remote_stop_transaction)
    async def remote_stop(self, transaction_id):
        self.commands.append(('stop', transaction_id))
        if self.stop_status == 'Accepted' and self.confirm_stop:
            self.tasks.append(asyncio.create_task(self.stopped(transaction_id)))
        return call_result.RemoteStopTransaction(status=self.stop_status)

    async def stopped(self, transaction_id):
        await self.call(call.StopTransaction(transaction_id=transaction_id, meter_stop=100,
            timestamp=datetime.now(timezone.utc).isoformat()))
        self.transaction = None
        await self.status('Preparing')
        await self.meter(0)

    async def status(self, value, connector=1, error='NoError'):
        await self.call(call.StatusNotification(connector_id=connector, error_code=error, status=value))

    async def meter(self, watts, *, stamp=None, connector=1, **kwargs):
        await self.call(call.MeterValues(connector_id=connector, meter_value=[{
            'timestamp':(stamp or datetime.now(timezone.utc)).isoformat(),
            'sampledValue':[{'measurand':'Power.Active.Import','value':str(watts),'unit':'W'}]}], **kwargs))


def unused_port():
    with socket.socket() as reservation:
        reservation.bind(('127.0.0.1',0))
        return reservation.getsockname()[1]


@asynccontextmanager
async def station(client_ssl=True, **params):
    port = unused_port()
    with patch.dict('os.environ', {'EOS_OCPP_PASSWORD':PASSWORD}):
        box = WALLBOX_DRIVERS['ocpp'](None, {'port':port, **params})
        try:
            await asyncio.to_thread(box.read, {}, datetime.now(timezone.utc))
            async with aiohttp.ClientSession() as http:
                scheme='https' if params.get('tls_cert') else 'http'
                async with http.ws_connect(f'{scheme}://127.0.0.1:{port}/wallbox', ssl=client_ssl,
                        protocols=('ocpp1.6',), headers={'Authorization':aiohttp.encode_basic_auth('wallbox',PASSWORD)}) as ws:
                    cp = Charger(ws)
                    reader = asyncio.create_task(cp.start())
                    try:
                        result = await cp.call(call.BootNotification(charge_point_vendor='Simulator',charge_point_model='Test'))
                        assert result.status == 'Accepted'
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


def test_direct_ocpp_reads_power_starts_limits_refreshes_and_stops_with_confirmations():
    async def scenario():
        async with station() as (box, cp, _, _):
            state = await asyncio.to_thread(read,box)
            assert state.status == 'connected' and state.phases == 3
            assert state.watts == 0 and not state.enabled and state.amps == 0
            await asyncio.to_thread(box.charge, 10, state)
            await asyncio.gather(*cp.tasks)
            assert cp.transaction is not None
            assert [command[0] for command in cp.commands] == ['profile','start','profile']
            profile = cp.commands[-1][2]
            assert profile['transaction_id'] == cp.transaction
            periods = profile['charging_schedule']['charging_schedule_period']
            assert periods == [{'start_period':0,'limit':10.},{'start_period':180,'limit':0.}]
            await cp.meter(6900)
            state = await asyncio.to_thread(read,box)
            assert state.enabled and state.watts == 6900 and state.amps == 10
            await asyncio.to_thread(box.charge,10,state)
            assert len(cp.commands)==3
            box.profile_at -= 31
            await asyncio.to_thread(box.charge,10,state)
            assert len(cp.commands)==4
            await asyncio.to_thread(box.pause,state)
            await asyncio.gather(*cp.tasks)
            state = await asyncio.to_thread(read,box)
            assert not state.enabled and cp.transaction is None
            assert cp.commands[-1][0]=='stop'
            with pytest.raises(UnsupportedFeature):
                box.phase(1,state)
    asyncio.run(scenario())


def test_rejected_profile_never_starts_a_transaction_and_logs_without_private_frames(caplog):
    async def scenario():
        async with station() as (box,cp,_,_):
            cp.profile_status='Rejected'
            with pytest.raises(OCPPError):
                await asyncio.to_thread(box.charge,10,await asyncio.to_thread(read,box))
            assert [entry[0] for entry in cp.commands]==['profile']
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
            assert box.server.start_until == 0
            assert cp.commands[-1][2]['charging_schedule']['charging_schedule_period'][0]['limit']==0
    asyncio.run(scenario())


def test_stop_without_stop_transaction_remains_unconfirmed_and_applies_zero_limit():
    async def scenario():
        async with station() as (box,cp,_,_):
            await asyncio.to_thread(box.charge,10,await asyncio.to_thread(read,box))
            cp.confirm_stop=False
            with pytest.raises(OCPPError,match='stop was not confirmed'):
                await asyncio.to_thread(box.pause,await asyncio.to_thread(read,box))
            assert box.server.transaction is not None
            assert cp.commands[-1][2]['charging_schedule']['charging_schedule_period'][0]['limit']==0
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


def test_old_future_foreign_connector_and_energy_only_samples_do_not_replace_valid_power():
    async def scenario():
        async with station() as (box,cp,_,_):
            await cp.meter(2500)
            sample=box.server.sample
            await cp.meter(9999, connector=2)
            await cp.meter(9999, stamp=datetime.now(timezone.utc)+timedelta(hours=1))
            await cp.meter(9999, stamp=sample-timedelta(seconds=1))
            assert (await asyncio.to_thread(read,box)).watts==2500
            with box.server.changed:
                box.server.sample=datetime.now(timezone.utc)-timedelta(seconds=121)
            state=await asyncio.to_thread(read,box)
            assert state.watts is None
            assert any(row['code']=='plugin_measurements_incomplete' for row in box.telemetry_status)
            await cp.status('Faulted',connector=0,error='OtherError')
            await cp.status('Charging')
            assert (await asyncio.to_thread(read,box)).status=='error'
    asyncio.run(scenario())


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


def test_unsolicited_start_and_wrong_tag_are_not_authorized():
    async def scenario():
        async with station() as (_,cp,_,_):
            result=await cp.call(call.Authorize(id_tag='other-card'))
            assert result.id_tag_info['status']=='Invalid'
            result=await cp.call(call.StartTransaction(connector_id=1,id_tag='EOS',meter_start=0,
                timestamp=datetime.now(timezone.utc).isoformat()))
            assert result.id_tag_info['status']=='Blocked'
    asyncio.run(scenario())


def test_controller_starts_without_current_offered_and_renews_an_unchanged_setpoint():
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
                count=len(cp.commands)
                controller.last_write -= timedelta(seconds=21)
                box.profile_at -= 31
                await asyncio.to_thread(controller.regulate_car,await asyncio.to_thread(read,box),live,
                    6900,False,datetime.now(timezone.utc),22,{})
                assert len(cp.commands)==count+1 and cp.commands[-1][0]=='profile'
                box.profile_at -= 31
                with box.server.changed:
                    box.server.sample=datetime.now(timezone.utc)-timedelta(seconds=121)
                await asyncio.to_thread(box.maintain,await asyncio.to_thread(read,box))
                assert len(cp.commands)==count+1
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


def test_new_fault_blocks_commands_but_stale_telemetry_does_not_prevent_a_stop():
    async def scenario():
        async with station() as (box,cp,_,_):
            state=await asyncio.to_thread(read,box)
            await cp.status('Faulted',error='OtherError')
            with pytest.raises(OCPPError):
                await asyncio.to_thread(box.charge,10,state)
            assert not cp.commands
            await cp.status('Preparing')
            await asyncio.to_thread(box.charge,10,await asyncio.to_thread(read,box))
            await asyncio.gather(*cp.tasks)
            state=await asyncio.to_thread(read,box)
            box.server.last_seen -= 181
            await asyncio.to_thread(box.pause,state)
            assert box.server.transaction is None
    asyncio.run(scenario())


def test_rejected_stop_stays_visible_and_sets_zero_profile():
    async def scenario():
        async with station() as (box,cp,_,_):
            await asyncio.to_thread(box.charge,10,await asyncio.to_thread(read,box))
            await asyncio.gather(*cp.tasks)
            cp.stop_status='Rejected'
            with pytest.raises(OCPPError):
                await asyncio.to_thread(box.pause,await asyncio.to_thread(read,box))
            assert box.server.transaction is not None
            assert cp.commands[-1][2]['charging_schedule']['charging_schedule_period'][0]['limit']==0
    asyncio.run(scenario())


def test_recovering_transactions_never_revives_a_finished_session_or_confirms_unknown_stop():
    async def scenario():
        async with station() as (box,cp,_,_):
            await cp.status('Charging')
            state=await asyncio.to_thread(read,box)
            assert state.enabled
            for command in (lambda:box.pause(state),lambda:box.charge(10,state)):
                with pytest.raises(OCPPError,match='identity is missing'):
                    await asyncio.to_thread(command)
            assert not cp.commands
            await cp.meter(6900,transaction_id=123)
            assert box.server.transaction==123
            await cp.call(call.StopTransaction(transaction_id=123,meter_stop=100,
                timestamp=datetime.now(timezone.utc).isoformat()))
            await cp.meter(0,transaction_id=123)
            assert box.server.transaction is None
    asyncio.run(scenario())

"""OCPP 1.6J transport on its own loop; no sockets or schema work in HA's loop."""
import asyncio
import base64
import hmac
import json
import logging
import secrets
import ssl
from collections import deque
from datetime import datetime, timezone
from threading import Condition, Event, Thread
from time import monotonic

from aiohttp import WSMsgType, web
from ocpp.routing import on
from ocpp.exceptions import OCPPError as ProtocolError
from ocpp.v16 import ChargePoint, call_result
from ocpp.v16.enums import Action

from .domain import instant, number
from .failures import HardwareAPIError


# Protocol frames may contain credentials, identifiers and private measurements.
# Use a private, disabled logger instead of ocpp's raw-frame logging.
WIRE_LOG = logging.Logger(__name__ + '.wire', level=logging.CRITICAL + 1)
WIRE_LOG.propagate = False


def utc_now():
    return datetime.now(timezone.utc)


class OCPPError(HardwareAPIError):
    """Fixed, safe failure text; never include frames or client identifiers."""


class Socket:
    def __init__(self, websocket):
        self.websocket = websocket

    async def send(self, text):
        await self.websocket.send_str(text)

    async def recv(self):
        message = await self.websocket.receive()
        if message.type != WSMsgType.TEXT:
            raise ConnectionError('OCPP connection closed')
        return message.data


class Session(ChargePoint):
    def __init__(self, server, websocket):
        super().__init__('configured-charge-point', Socket(websocket), response_timeout=8, logger=WIRE_LOG)
        self.server = server

    async def route_message(self, raw_msg):
        from ocpp.messages import unpack
        try:
            unpack(raw_msg)
            if self._response_queue.qsize() >= 16:
                raise ValueError('Too many unmatched responses')
        except Exception:
            self.server.connection_error = 'protocol_error'
            await self._connection.websocket.close(code=1002)
            return
        await super().route_message(raw_msg)

    async def _send(self, message):
        if json.loads(message)[0] == 4:
            self.server.connection_error = 'protocol_error'
        await super()._send(message)

    def seen(self):
        self.server.last_seen = monotonic()

    @on(Action.boot_notification)
    async def boot(self, charge_point_model, charge_point_vendor, **kwargs):
        with self.server.changed:
            self.seen()
            self.server.status = 'unknown'
            self.server.watts = self.server.sample = self.server.amps = None
            self.server.changed.notify_all()
        return call_result.BootNotification(current_time=utc_now().isoformat(), interval=60, status='Accepted')

    @on(Action.heartbeat)
    async def heartbeat(self):
        with self.server.changed:
            self.seen()
            # Available explicitly means no connected vehicle, not a stale zero meter.
            if self.server.status == 'Available' and self.server.transaction is None:
                self.server.watts, self.server.sample = 0., utc_now()
        return call_result.Heartbeat(current_time=utc_now().isoformat())

    @on(Action.authorize)
    async def authorize(self, id_tag):
        return call_result.Authorize(id_tag_info={'status':'Accepted' if self.server.authorized(id_tag) else 'Invalid'})

    @on(Action.status_notification)
    async def status_notification(self, connector_id, error_code, status, **kwargs):
        with self.server.changed:
            self.seen()
            if connector_id in (0, self.server.connector):
                if error_code != 'NoError' or status == 'Faulted':
                    self.server.status = 'Faulted'
                    if connector_id == 0:
                        self.server.station_fault = True
                elif connector_id == 0:
                    self.server.station_fault = False
                elif connector_id == self.server.connector:
                    self.server.status = status
                    if status == 'Available' and self.server.transaction is None:
                        self.server.watts, self.server.sample = 0., utc_now()
                self.server.changed.notify_all()
        return call_result.StatusNotification()

    @on(Action.start_transaction)
    async def start_transaction(self, connector_id, id_tag, meter_start, timestamp, **kwargs):
        server = self.server
        with server.changed:
            accepted = (connector_id == server.connector and server.authorized(id_tag)
                        and server.start_until >= monotonic() and server.transaction is None)
            transaction = secrets.randbelow(2**31 - 1) + 1
            if accepted:
                self.seen()
                server.transaction = transaction
                server.start_until = 0
                server.changed.notify_all()
        return call_result.StartTransaction(transaction_id=transaction,
            id_tag_info={'status':'Accepted' if accepted else 'Blocked'})

    @on(Action.stop_transaction)
    async def stop_transaction(self, transaction_id, meter_stop, timestamp, **kwargs):
        with self.server.changed:
            self.seen()
            if self.server.transaction == transaction_id:
                self.server.transaction = None
                self.server.amps = 0.
                self.server.changed.notify_all()
            self.server.finished_transactions.append(transaction_id)
        return call_result.StopTransaction()

    @on(Action.meter_values)
    async def meter_values(self, connector_id, meter_value, **kwargs):
        server = self.server
        with server.changed:
            self.seen()
            if connector_id == server.connector:
                for block in meter_value:
                    stamp = instant(block.get('timestamp'))
                    if stamp is None or stamp > utc_now() or (server.sample and stamp < server.sample):
                        continue
                    values = block.get('sampled_value', [])
                    watts = power_watts(values, server.phases)
                    if watts is not None:
                        server.watts, server.sample = watts, stamp
                    for value in values:
                        if (value.get('measurand') == 'Current.Offered' and not value.get('phase')
                                and value.get('unit', 'A') == 'A' and value.get('format', 'Raw') == 'Raw'):
                            amps = number(value.get('value'))
                            if amps is not None and 0 <= amps <= server.maximum:
                                server.amps = amps
                    transaction = kwargs.get('transaction_id')
                    if (server.transaction is None and type(transaction) is int and transaction > 0
                            and transaction not in server.finished_transactions
                            and server.status in ('Charging','SuspendedEV','SuspendedEVSE')
                            and 0 <= (utc_now()-stamp).total_seconds() < 120):
                        # Restore an ongoing session after a server restart/reconnect.
                        server.transaction = transaction
                server.changed.notify_all()
        return call_result.MeterValues()

    @on(Action.data_transfer)
    async def data_transfer(self, vendor_id, **kwargs):
        return call_result.DataTransfer(status='UnknownVendorId')


def power_watts(values, phases):
    """Prefer a total; sum only a complete, simultaneous set of phase readings."""
    totals, legs, duplicate = [], {}, False
    for item in values:
        if item.get('measurand') != 'Power.Active.Import' or item.get('format', 'Raw') != 'Raw':
            continue
        value, unit = number(item.get('value')), item.get('unit', 'W')
        if value is None or not 0 <= value <= 1000000 or unit not in ('W', 'kW'):
            continue
        value *= 1000 if unit == 'kW' else 1
        phase = item.get('phase')
        if not phase:
            totals.append(value)
        elif phase in ('L1','L2','L3','L1-N','L2-N','L3-N'):
            phase = phase[:2]
            if phase in legs:
                duplicate = True
            legs[phase] = value
    if len(totals) == 1:
        return totals[0]
    expected = {'L1'} if phases == 1 else {'L1','L2','L3'}
    return sum(legs.values()) if not totals and not duplicate and legs.keys() == expected else None


class Server:
    """One configured charge point/connector per listener, started only at runtime."""
    def __init__(self, settings):
        self.settings = settings
        self.connector = int(settings['connector'])
        self.phases = int(settings['phases'])
        self.maximum = settings['max_current']
        self.changed = Condition()
        self.ready = Event()
        self.thread = self.loop = self.stop = self.session = None
        self.error = self.connection_error = None
        self.status = 'unknown'
        self.watts = self.sample = self.amps = self.transaction = None
        self.start_until = self.last_seen = 0
        self.finished_transactions = deque(maxlen=128)
        self.password = None
        self.closed = False
        self.connecting = self.station_fault = False

    def authorized(self, tag):
        return hmac.compare_digest(tag.encode(), self.settings['id_tag'].encode())

    def start(self, password):
        if self.closed:
            raise OCPPError('OCPP listener is closed')
        if self.thread is None:
            self.password = password
            self.thread = Thread(target=self._run, name='EOS OCPP listener', daemon=True)
            self.thread.start()
        if not self.ready.wait(10) or self.error:
            raise OCPPError('OCPP listener could not start', reason='ocpp_listener_failed') from self.error

    def _run(self):
        try:
            asyncio.run(self._serve())
        except Exception as error:
            self.error = error
            self.ready.set()

    async def _serve(self):
        self.loop = asyncio.get_running_loop()
        self.stop = asyncio.Event()
        app = web.Application(client_max_size=65536)
        app.router.add_get('/{identity}', self._connect)
        runner = web.AppRunner(app, access_log=None, logger=WIRE_LOG)
        await runner.setup()
        try:
            context = None
            if self.settings['tls_cert']:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                # Never allow OpenSSL to prompt on HA's stdin for an encrypted key.
                context.load_cert_chain(self.settings['tls_cert'], self.settings['tls_key'], password=lambda:'')
            site = web.TCPSite(runner, self.settings['bind_address'], int(self.settings['port']), ssl_context=context)
            await site.start()
            self.ready.set()
            await self.stop.wait()
        finally:
            if self.session:
                await self.session._connection.websocket.close()
            await runner.cleanup()

    async def _connect(self, request):
        expected = base64.b64encode((self.settings['charge_point_id']+':'+self.password).encode()).decode()
        if (request.match_info['identity'] != self.settings['charge_point_id'] or
                not hmac.compare_digest(request.headers.get('Authorization', '').encode(), ('Basic '+expected).encode())):
            self.connection_error = 'authentication_failed'
            return web.Response(status=401, headers={'WWW-Authenticate':'Basic realm="OCPP"'})
        if 'ocpp1.6' not in request.headers.get('Sec-WebSocket-Protocol', '').replace(' ', '').split(','):
            self.connection_error = 'protocol_unsupported'
            return web.Response(status=400)
        if self.session is not None or self.connecting:
            self.connection_error = 'duplicate_connection'
            return web.Response(status=409)
        websocket = web.WebSocketResponse(protocols=('ocpp1.6',), heartbeat=30, max_msg_size=65536)
        self.connecting = True
        try:
            await websocket.prepare(request)
        except Exception:
            self.connecting = False
            raise
        session = Session(self, websocket)
        with self.changed:
            self.session = session
            self.connecting = False
            self.connection_error = None
            self.last_seen = monotonic()
            self.status = 'unknown'
            self.watts = self.sample = self.amps = None
        try:
            await session.start()
        except Exception:
            self.connection_error = 'connection_lost' if websocket.closed else 'protocol_error'
        finally:
            with self.changed:
                self.session = None
                self.status = 'unavailable'
                self.watts = self.sample = self.amps = None
                self.start_until = 0
                self.changed.notify_all()
            await websocket.close()
        return websocket

    def request(self, message):
        async def send():
            from ocpp.v16 import call
            session = self.session
            if session is None:
                raise OCPPError('OCPP charge point is not connected', reason='ocpp_not_connected')
            positive = isinstance(message, call.RemoteStartTransaction) or (
                isinstance(message, call.SetChargingProfile) and any(
                    period['limit'] > 0 for period in message.cs_charging_profiles['chargingSchedule']['chargingSchedulePeriod']))
            if positive and (monotonic() - self.last_seen > 180 or self.station_fault
                    or self.status not in ('Preparing','Charging','SuspendedEV','SuspendedEVSE','Finishing')
                    or self.sample is None or not 0 <= (utc_now()-self.sample).total_seconds() < 120):
                raise OCPPError('OCPP command requires healthy status and fresh measurements', reason='ocpp_unsafe_state')
            result = await session.call(message, suppress=False)
            if getattr(result, 'status', None) != 'Accepted':
                raise OCPPError('OCPP command was rejected', reason='ocpp_command_rejected')
            return result
        if self.loop is None or not self.loop.is_running():
            raise OCPPError('OCPP listener is unavailable')
        pending = asyncio.run_coroutine_threadsafe(send(), self.loop)
        try:
            return pending.result(timeout=10)
        except OCPPError:
            pending.cancel()
            raise
        except TimeoutError:
            pending.cancel()
            raise OCPPError('OCPP command timed out', reason='ocpp_command_timeout') from None
        except ProtocolError:
            pending.cancel()
            raise OCPPError('OCPP command was rejected', reason='ocpp_command_rejected') from None
        except Exception:
            pending.cancel()
            raise OCPPError('OCPP command was not confirmed') from None

    def close(self):
        self.closed = True
        if self.loop and self.loop.is_running() and self.stop:
            self.loop.call_soon_threadsafe(self.stop.set)
        if self.thread:
            self.thread.join(timeout=12)
            if self.thread.is_alive():
                raise OCPPError('OCPP listener did not stop')
        self.password = None

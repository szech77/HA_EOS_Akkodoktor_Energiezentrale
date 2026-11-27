"""OCPP 1.6J transport on its own loop; no sockets or schema work in HA's loop."""
import asyncio
import base64
from datetime import datetime, timedelta, timezone
import hmac
import json
import logging
import secrets
import ssl
from collections import deque
from threading import Condition, Event, Thread
from time import monotonic

from aiohttp import WSMsgType, web
from ocpp.routing import on
from ocpp.exceptions import OCPPError as ProtocolError
from ocpp.v16 import ChargePoint, call, call_result
from ocpp.v16.enums import Action

from .domain import instant, number
from .failures import HardwareAPIError


_LOGGER = logging.getLogger(__name__)
# Protocol frames may contain credentials, identifiers and private measurements.
# Use a private, disabled logger instead of ocpp's raw-frame logging.
WIRE_LOG = logging.Logger(__name__ + '.wire', level=logging.CRITICAL + 1)
WIRE_LOG.propagate = False

STALE_S = 120            # measurements older than this (local receipt) are invalid
SEEN_S = 180             # without any message for this long the charge point counts as offline
TRIGGER_S = 30           # request meter values when none arrived for this long
SAMPLE_INTERVAL_S = 10   # meter value interval written during automatic setup
BOOT_WAIT_S = 5          # wait for a spontaneous BootNotification before running setup
PROFILE_FALLBACK_S = 180 # an unrenewed charging profile drops to 0 A after this
CLOCK_SLACK_S = 60       # absolute profiles start this early; tolerates a charger clock running behind
MEASURANDS = 'Power.Active.Import,Current.Offered'
BOUNDARY_CONTEXTS = ('Transaction.Begin', 'Transaction.End')
ACTIVE = ('Charging', 'SuspendedEV', 'SuspendedEVSE')
CONFIGURATION_KEYS = ('ChargeProfileMaxStackLevel', 'ChargingScheduleAllowedChargingRateUnit',
    'SupportedFeatureProfiles', 'MeterValuesSampledData', 'MeterValueSampleInterval', 'NumberOfConnectors')


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


def listed(value, item):
    return item.lower() in {part.strip().strip("'").lower() for part in (value or '').split(',')}


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

    @on(Action.boot_notification)
    async def boot(self, charge_point_model, charge_point_vendor, **kwargs):
        server = self.server
        with server.changed:
            server.seen()
            # A transaction may not survive the reboot; the next conclusive status decides.
            server.rebooted = True
            server.status = 'unknown'
            server.watts = server.watts_at = server.offered = server.limit = None
            server.charger_info = {'vendor':str(charge_point_vendor)[:20], 'model':str(charge_point_model)[:20]}
            server.changed.notify_all()
        server.schedule_setup()
        return call_result.BootNotification(current_time=utc_now().isoformat(), interval=60, status='Accepted')

    @on(Action.heartbeat)
    async def heartbeat(self):
        with self.server.changed:
            self.server.seen()
        return call_result.Heartbeat(current_time=utc_now().isoformat())

    @on(Action.authorize)
    async def authorize(self, id_tag):
        # Access control stays with the charger; the authenticated charger may start any session.
        with self.server.changed:
            self.server.seen()
        return call_result.Authorize(id_tag_info={'status':'Accepted'})

    @on(Action.status_notification)
    async def status_notification(self, connector_id, error_code, status, **kwargs):
        server = self.server
        with server.changed:
            server.seen()
            if connector_id == 0:
                server.station_fault = error_code != 'NoError' or status == 'Faulted'
            elif connector_id == server.connector:
                server.status = 'Faulted' if error_code != 'NoError' else status
                if status == 'Available' and error_code == 'NoError':
                    # Unplugged: any remembered transaction is over.
                    server.forget_transaction()
                elif server.rebooted and status == 'Preparing':
                    server.forget_transaction()
                if server.rebooted and status in ('Available', 'Preparing') + ACTIVE:
                    server.rebooted = False
            server.changed.notify_all()
        return call_result.StatusNotification()

    @on(Action.start_transaction)
    async def start_transaction(self, connector_id, id_tag, meter_start, timestamp, **kwargs):
        server = self.server
        transaction = secrets.randbelow(2**31 - 1) + 1
        with server.changed:
            server.seen()
            if connector_id == server.connector:
                # Remote or local start (RFID, free charging); the charging profile decides the current.
                server.transaction = transaction
                server.rebooted = False
                server.changed.notify_all()
        return call_result.StartTransaction(transaction_id=transaction, id_tag_info={'status':'Accepted'})

    @on(Action.stop_transaction)
    async def stop_transaction(self, transaction_id, meter_stop, timestamp, **kwargs):
        server = self.server
        with server.changed:
            server.seen()
            if server.transaction == transaction_id:
                server.forget_transaction()
            server.finished_transactions.append(transaction_id)
            server.changed.notify_all()
        return call_result.StopTransaction()

    @on(Action.meter_values)
    async def meter_values(self, connector_id, meter_value, **kwargs):
        server = self.server
        with server.changed:
            server.seen()
            if connector_id == server.connector:
                server.meter_values(meter_value, kwargs.get('transaction_id'))
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
        # Freshness uses the local receipt time: charger clocks may be wrong or lag.
        self.watts = self.watts_at = self.watts_time = self.offered = self.limit = self.transaction = None
        self.last_seen = self.seen_at = None
        self.charger_stamp = None
        self.finished_transactions = deque(maxlen=128)
        self.password = None
        self.closed = False
        self.connecting = self.station_fault = self.rebooted = False
        self.start_pending = False
        self.stack_level = 1
        self.rate_unit = 'A'
        self.remote_trigger = True
        self.smart_charging = None
        self.charger_info = {}
        self.setup_state = 'pending'
        self.setup_task = None
        self.last_trigger = -1000.

    # --- state helpers; callers hold self.changed ---
    def seen(self):
        self.last_seen, self.seen_at = monotonic(), utc_now()

    def forget_transaction(self):
        self.transaction = None
        self.start_pending = False
        # Without a transaction nothing is drawn; a known zero is a valid measurement.
        self.watts, self.watts_at, self.watts_time = 0., monotonic(), utc_now()

    def online(self):
        return self.session is not None and self.last_seen is not None and monotonic() - self.last_seen <= SEEN_S

    def fresh(self):
        return self.watts_at is not None and 0 <= monotonic() - self.watts_at < STALE_S

    def power(self):
        """Fresh charging power; an idle connector without transaction draws nothing."""
        if not self.online():
            return None, None
        if self.fresh():
            return self.watts, self.watts_time
        if self.transaction is None and self.status in ('Available', 'Preparing', 'Finishing'):
            return 0., self.seen_at
        return None, None

    def meter_values(self, blocks, transaction):
        dated = []
        for block in blocks:
            stamp = instant(block.get('timestamp'))
            dated.append((stamp or utc_now(), block))
        for stamp, block in sorted(dated, key=lambda item: item[0]):
            # Order by the charger's own clock, but never judge freshness by it.
            if self.charger_stamp is not None and stamp < self.charger_stamp:
                continue
            self.charger_stamp = stamp
            values = [value for value in block.get('sampled_value', [])
                      if value.get('context') not in BOUNDARY_CONTEXTS]
            watts = power_watts(values, self.phases)
            if watts is not None:
                self.watts, self.watts_at, self.watts_time = watts, monotonic(), utc_now()
            for value in values:
                if (value.get('measurand') == 'Current.Offered' and not value.get('phase')
                        and value.get('unit', 'A') == 'A' and value.get('format', 'Raw') == 'Raw'):
                    amps = number(value.get('value'))
                    if amps is not None and 0 <= amps <= max(self.maximum, 80):
                        self.offered = amps
        if (self.transaction is None and type(transaction) is int and transaction > 0
                and transaction not in self.finished_transactions and self.status in ACTIVE):
            # Restore an ongoing session after a server restart/reconnect.
            self.transaction = transaction

    def healthy_for_charging(self):
        watts, _ = self.power()
        return (self.online() and not self.station_fault and watts is not None
                and self.status in ('Preparing', 'Finishing') + ACTIVE)

    # --- listener lifecycle ---
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
        watchdog = None
        try:
            context = None
            if self.settings['tls_cert']:
                context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
                context.minimum_version = ssl.TLSVersion.TLSv1_2
                # Never allow OpenSSL to prompt on HA's stdin for an encrypted key.
                context.load_cert_chain(self.settings['tls_cert'], self.settings['tls_key'], password=lambda:'')
            site = web.TCPSite(runner, self.settings['bind_address'], int(self.settings['port']), ssl_context=context)
            await site.start()
            watchdog = asyncio.create_task(self._watchdog())
            self.ready.set()
            await self.stop.wait()
        finally:
            for task in (watchdog, self.setup_task):
                if task is not None and not task.done():
                    task.cancel()
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
            self.seen()
            self.status = 'unknown'
            self.watts = self.watts_at = self.offered = self.limit = None
            self.charger_stamp = None
            self.setup_state = 'pending'
        # Without a spontaneous BootNotification, configure the reconnected charger anyway.
        self.schedule_setup(delay=BOOT_WAIT_S)
        try:
            await session.start()
        except Exception:
            self.connection_error = 'connection_lost' if websocket.closed else 'protocol_error'
        finally:
            if self.setup_task is not None and not self.setup_task.done():
                self.setup_task.cancel()
            with self.changed:
                self.session = None
                self.status = 'unavailable'
                self.watts = self.watts_at = self.offered = self.limit = None
                self.start_pending = False
                self.changed.notify_all()
            await websocket.close()
        return websocket

    # --- automatic setup and freshness, all on the listener loop ---
    def schedule_setup(self, delay=0):
        if self.setup_task is not None and not self.setup_task.done():
            if delay:
                return  # A running or scheduled setup already covers this connection.
            self.setup_task.cancel()
        self.setup_task = asyncio.get_running_loop().create_task(self._setup(delay))

    async def _call(self, message):
        session = self.session
        if session is None:
            raise ConnectionError('OCPP charge point is not connected')
        return await session.call(message, suppress=False)

    async def _setup(self, delay):
        if delay:
            await asyncio.sleep(delay)
        try:
            result = await self._call(call.GetConfiguration(key=list(CONFIGURATION_KEYS)))
            options = {item.get('key'): item.get('value') for item in result.configuration_key or ()
                       if isinstance(item, dict) and isinstance(item.get('key'), str)}
        except asyncio.CancelledError:
            raise
        except Exception:
            options = None
        configured = []
        if options is not None:
            level = number(options.get('ChargeProfileMaxStackLevel'))
            if level is not None and 0 <= level <= 1000 and level == int(level):
                self.stack_level = int(level)
            units = options.get('ChargingScheduleAllowedChargingRateUnit')
            if units and not (listed(units, 'Current') or listed(units, 'A')) and (listed(units, 'Power') or listed(units, 'W')):
                self.rate_unit = 'W'
            profiles = options.get('SupportedFeatureProfiles')
            if profiles and listed(profiles, 'Core'):
                self.remote_trigger = listed(profiles, 'RemoteTrigger')
                self.smart_charging = listed(profiles, 'SmartCharging')
            if self.settings['configure_meter_values']:
                configured = await self._configure(options)
        self.setup_state = 'configured' if options is not None else 'configuration_unavailable'
        if self.smart_charging is False:
            _LOGGER.warning('OCPP charge point does not report the SmartCharging profile; current limits may be ignored')
        _LOGGER.info('OCPP charge point setup: %s, stack level %s, rate unit %s, remote trigger %s, configured %s',
                     self.setup_state, self.stack_level, self.rate_unit, self.remote_trigger, ', '.join(configured) or 'nothing')
        await self._trigger('StatusNotification')
        await self._trigger('MeterValues')

    async def _configure(self, options):
        changed = []
        current = options.get('MeterValuesSampledData')
        if current is None or not listed(current, 'Power.Active.Import'):
            for value in (MEASURANDS, 'Power.Active.Import'):
                if await self._change('MeterValuesSampledData', value):
                    changed.append('MeterValuesSampledData')
                    break
        interval = number(options.get('MeterValueSampleInterval'))
        if interval is None or not 0 < interval <= TRIGGER_S:
            if await self._change('MeterValueSampleInterval', str(SAMPLE_INTERVAL_S)):
                changed.append('MeterValueSampleInterval')
        return changed

    async def _change(self, key, value):
        try:
            result = await self._call(call.ChangeConfiguration(key=key, value=value))
        except asyncio.CancelledError:
            raise
        except Exception:
            return False
        return result.status in ('Accepted', 'RebootRequired')

    async def _trigger(self, message):
        if not self.remote_trigger or self.session is None:
            return
        self.last_trigger = monotonic()
        try:
            await self._call(call.TriggerMessage(requested_message=message, connector_id=self.connector))
        except asyncio.CancelledError:
            raise
        except Exception:
            pass

    async def _watchdog(self):
        while True:
            await asyncio.sleep(2)
            with self.changed:
                due = (self.online() and self.remote_trigger and self.setup_state != 'pending'
                       and (self.watts_at is None or monotonic() - self.watts_at > TRIGGER_S)
                       and monotonic() - self.last_trigger > TRIGGER_S)
            if due:
                await self._trigger('MeterValues')

    # --- commands from the serialized backend ---
    def profile(self, amps):
        """A connector default profile; it falls back to 0 A unless renewed in time."""
        start = utc_now() - timedelta(seconds=CLOCK_SLACK_S)
        if self.rate_unit == 'W':
            limit = lambda value: float(round(value * self.phases * 230))
        else:
            limit = float
        periods = [{'startPeriod':0, 'limit':limit(amps), 'numberPhases':self.phases}]
        if amps > 0:
            periods.append({'startPeriod':CLOCK_SLACK_S + PROFILE_FALLBACK_S, 'limit':0., 'numberPhases':self.phases})
        return call.SetChargingProfile(connector_id=self.connector, cs_charging_profiles={
            'chargingProfileId':1, 'stackLevel':self.stack_level, 'chargingProfilePurpose':'TxDefaultProfile',
            'chargingProfileKind':'Absolute', 'chargingSchedule':{
                'startSchedule':start.isoformat(), 'chargingRateUnit':self.rate_unit,
                'chargingSchedulePeriod':periods}})

    def request(self, message):
        async def send():
            if self.session is None:
                raise OCPPError('OCPP charge point is not connected', reason='ocpp_not_connected')
            positive = isinstance(message, call.RemoteStartTransaction) or (
                isinstance(message, call.SetChargingProfile) and any(
                    period['limit'] > 0 for period in message.cs_charging_profiles['chargingSchedule']['chargingSchedulePeriod']))
            with self.changed:
                unsafe = positive and not self.healthy_for_charging()
            if unsafe:
                raise OCPPError('OCPP command requires healthy status and fresh measurements', reason='ocpp_unsafe_state')
            result = await self.session.call(message, suppress=False)
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

"""Direct OCPP 1.6J central system, independent of HA charger entities.

Charging is paused and resumed with a connector default charging profile (0 A or
the target current); a running transaction stays open, so vehicles keep their
charging session. A transaction is only started remotely while a connected
vehicle waits for authorization.
"""
import ipaddress
import os
import re
from time import monotonic

from ..contracts import WallboxDriver, WallboxFeatures, WallboxReading, PluginInfo, PluginField
from ..failures import PluginParameterError
from ..plugin_parameters import parameters
from ..plugin_diagnostics import plugin_operation, report_plugin_read

PROFILE_RENEW_S = 30  # renew a running limit long before its fallback to 0 A
START_CONFIRM_S = 8


class OCPPWallbox(WallboxDriver):
    info = PluginInfo('ocpp', 'OCPP 1.6J – direct connection', 'wallbox')
    features = WallboxFeatures(phase_switching=False, optional_connection=True)
    configuration = (
        PluginField('bind_address', 'Local HA IP address for the OCPP server', 'text', default='127.0.0.1'),
        PluginField('port', 'OCPP WebSocket port (one port per charge point)', 'number', default=9000),
        PluginField('charge_point_id', 'Charge point identity (URL and Basic Auth username)', 'text', default='wallbox'),
        PluginField('password', 'OCPP password (at least 16 characters; re-enter when editing)', 'password', required=False, default=''),
        PluginField('password_env', 'Alternative: environment variable with OCPP password', 'text', required=False, default='EOS_OCPP_PASSWORD'),
        PluginField('connector', 'Connector ID', 'number', default=1),
        PluginField('phases', 'Connected phases', 'choice', default='3', choices=('1','3')),
        PluginField('max_current', 'Maximum permitted current per phase (A)', 'number', default=16),
        PluginField('id_tag', 'Authorization tag for remote charging', 'text', default='EOS'),
        PluginField('configure_meter_values', 'Configure meter values in the charger automatically', 'boolean', default=True),
        PluginField('tls_cert', 'Optional TLS certificate file', 'text', required=False, default=''),
        PluginField('tls_key', 'Optional TLS private key file', 'text', required=False, default=''),
    )

    def __init__(self, ha, params):
        self.settings = values = parameters(self.configuration, params)
        try:
            address = ipaddress.ip_address(values['bind_address'])
            if address.version != 4:
                raise ValueError('IPv4 required')
        except ValueError:
            raise PluginParameterError('OCPP requires a local IPv4 bind address', 'bind_address') from None
        for field, minimum, maximum in (('port',1024,65535), ('connector',1,32), ('max_current',6,80)):
            if not minimum <= values[field] <= maximum or values[field] != int(values[field]):
                raise PluginParameterError('Invalid OCPP numeric setting', field)
        for field, pattern in (('charge_point_id',r'[A-Za-z0-9_-]{1,48}'),
                               ('password_env',r'[A-Za-z_][A-Za-z0-9_]*'), ('id_tag',r'[A-Za-z0-9_-]{1,20}')):
            if field == 'password_env' and not values[field]:
                continue
            if not re.fullmatch(pattern, values[field]):
                raise PluginParameterError('Invalid OCPP identifier', field)
        if bool(values['tls_cert']) != bool(values['tls_key']):
            raise PluginParameterError('Configure both OCPP TLS certificate and key', 'tls_cert')
        if values['password'] and not 16 <= len(values['password']) <= 200:
            raise PluginParameterError('OCPP password must contain 16 to 200 characters', 'password')
        if not values['password'] and not values['password_env']:
            raise PluginParameterError('Configure an OCPP password or environment variable', 'password')
        self.ids = dict.fromkeys(('power','status','enable','current','phases'), '')
        # A listener cannot be shared by independently controlled vehicle plugins.
        self.device_key = f"ocpp:{address}:{int(values['port'])}"
        self.server = None
        self.profile_at = -1000.

    def _ensure_server(self):
        # Constructors/configuration validation must not bind ports or load schemas.
        from .._ocpp_server import Server, OCPPError
        if self.server is None:
            self.server = Server(self.settings)
        password = self.settings['password'] or os.environ.get(self.settings['password_env'] or '', '')
        if not 16 <= len(password) <= 200:
            raise OCPPError('OCPP password is unavailable', reason='credential_unavailable', fields=('password_env',))
        if self.server.thread is None:
            self.read_diagnostics = {'protocol':'ocpp1.6', 'failure':{'stage':'listener_start'}}
        self.server.start(password)
        return self.server

    def _read(self, states, now):
        server = self._ensure_server()
        with server.changed:
            connected = server.online()
            status = {'Available':'disconnected', 'Preparing':'connected', 'Charging':'charging',
                'SuspendedEV':'connected', 'SuspendedEVSE':'connected', 'Finishing':'connected',
                'Reserved':'disconnected', 'Unavailable':'unavailable', 'Faulted':'error'}.get(server.status, 'unknown')
            if not connected:
                status = 'unavailable'
            elif server.station_fault:
                status = 'error'
            watts, sample = server.power()
            # The confirmed own limit; after a reconnect the charger's offered current.
            amps = server.limit if server.limit is not None else server.offered
            if amps is None and server.transaction is None:
                amps = 0.
            enabled = connected and server.transaction is not None and (amps or 0) > 0
            self.read_diagnostics = {'protocol':'ocpp1.6', 'server_running':server.thread.is_alive() and server.error is None,
                'connected':connected, 'connector':server.connector, 'setup':server.setup_state,
                'stack_level':server.stack_level, 'rate_unit':server.rate_unit, 'remote_trigger':server.remote_trigger,
                'smart_charging':server.smart_charging, **server.charger_info,
                'connection_status':server.connection_error or ('connected' if connected else 'waiting')}
            report_plugin_read(self, group='connection', status='unavailable' if server.connection_error else None,
                stage=server.connection_error, include_partial=False)
            if connected:
                # A rejected second client must not leave the healthy session in alarm.
                server.connection_error = None
            self.ocpp_status, self.ocpp_transaction = server.status, server.transaction
            return WallboxReading(watts, status, enabled, server.phases, amps, 1., server.maximum, sample,
                max_phases=server.phases, nominal_voltage=230.)

    def _limit(self, amps):
        self._operation_context = {'stage':'set_charging_profile'}
        self.server.request(self.server.profile(amps))
        with self.server.changed:
            self.server.limit = float(amps)
        self.profile_at = monotonic()

    @plugin_operation('charge')
    def _charge(self, amps, state):
        from ocpp.v16 import call
        from .._ocpp_server import OCPPError
        server = self._ensure_server()
        with server.changed:
            idle = (server.transaction is None and server.status != 'Preparing' and server.limit == amps
                    and monotonic() - self.profile_at < PROFILE_RENEW_S)
        if idle:
            return  # Without a vehicle session the unchanged default profile is already in place.
        self._limit(amps)
        with server.changed:
            transaction, waiting = server.transaction, server.status == 'Preparing'
            if transaction is None and waiting:
                server.start_pending = True
        if transaction is not None or not waiting:
            # A running transaction resumes with the new limit; a vehicle that has not yet
            # requested a session starts by itself once it does (the default profile applies).
            return
        try:
            self._operation_context = {'stage':'remote_start_transaction'}
            server.request(call.RemoteStartTransaction(connector_id=server.connector, id_tag=self.settings['id_tag']))
            with server.changed:
                if not server.changed.wait_for(lambda: server.transaction is not None or server.session is None,
                                               timeout=START_CONFIRM_S) or server.transaction is None:
                    raise OCPPError('OCPP transaction start was not confirmed', reason='ocpp_start_unconfirmed')
        except Exception as error:
            error._plugin_failure_context = dict(self._operation_context)
            # No late start may inherit a positive default profile.
            try:
                self._limit(0)
            except Exception:
                pass
            raise
        finally:
            with server.changed:
                server.start_pending = False

    @plugin_operation('pause')
    def _pause(self, state):
        # Pausing keeps the transaction open; only the offered current becomes 0 A.
        self._ensure_server()
        self._limit(0)

    def _phase(self, phases, state):
        return False  # Public contract rejects phase switching before reaching this.

    @plugin_operation('keepalive')
    def _hold(self, amps, state):
        # Only renew while the reading is valid; stale data must not extend a limit.
        from .._ocpp_server import utc_now
        if (not self.server or not state.enabled or state.watts is None or state.sample is None
                or not 0 <= (utc_now()-state.sample).total_seconds() < 120
                or state.status not in ('connected','charging')):
            return
        if monotonic() - self.profile_at >= PROFILE_RENEW_S:
            self._limit(min(amps, self.server.maximum))

    def idle_reason(self):
        """Why a released, connected vehicle takes no power, from the last OCPP status."""
        status, transaction = getattr(self, 'ocpp_status', None), getattr(self, 'ocpp_transaction', None)
        if status == 'Preparing' and transaction is None:
            return 'access_control'
        return {'SuspendedEV':'vehicle_waiting', 'SuspendedEVSE':'charger_logic',
                'Finishing':'vehicle_complete', 'Faulted':'charger_error'}.get(status)

    def close(self):
        if self.server:
            self.server.close()
            self.server = None


PLUGINS = (OCPPWallbox,)

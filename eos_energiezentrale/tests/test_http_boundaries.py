"""Exercise HTTP contracts with in-memory sockets and device error responses."""
import json
import unittest
from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import BaseHTTPRequestHandler
from io import BytesIO
from threading import Event
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from energy import clients, server
from energy.domain import BatteryCommand
from energy.drivers import Fronius
from test_energy import temporary_project_directory


class StalledBody(BytesIO):
    def read(self, size=-1):
        raise TimeoutError("Socket timed out while reading the response body")


class HttpSocket:
    def __init__(self, handler, application):
        self.handler, self.application = handler, application
        self.sent = BytesIO()

    def sendall(self, data):
        self.sent.write(data)

    def makefile(self, *args):
        reply = BytesIO()
        peer = SimpleNamespace(makefile=lambda *args: BytesIO(self.sent.getvalue()), sendall=reply.write)
        self.handler(peer, ("127.0.0.1", 12345), self.application)
        stream = StalledBody if getattr(self.application, "stall_body", False) else BytesIO
        return stream(reply.getvalue())

    def close(self):
        pass


@contextmanager
def transport(**hosts):
    def connect(connection):
        handler, attributes = hosts[connection.host]
        connection.sock = HttpSocket(handler, SimpleNamespace(**attributes))

    with (patch.object(HTTPConnection, "connect", connect),
          patch("urllib.request.proxy_bypass", return_value=True)):
        yield


class FixtureHandler(BaseHTTPRequestHandler):
    def respond(self):
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length) if length else b""
        self.server.requests.append((self.command, self.path, self.headers.get("Authorization"), body))
        status, headers, content = self.server.routes[self.path]
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.end_headers()
        self.wfile.write(content)

    do_GET = do_POST = respond

    def log_message(self, *args):
        pass


class TransportTests(unittest.TestCase):
    def test_redirect_never_sends_credentials_to_redirect_target(self):
        redirected = []
        routes = {"/v1/energy-management/plan": (302, {"Location": "http://capture/capture"}, b"")}
        with transport(eos=(FixtureHandler, {"routes": routes, "requests": []}),
                       capture=(FixtureHandler, {"routes": {"/capture": (200, {}, b"{}")}, "requests": redirected})):
            with self.assertRaises(HTTPError) as failure:
                clients.request("http://eos/v1/energy-management/plan",
                                headers={"Authorization": "Bearer test-credential"})
            self.assertEqual(failure.exception.code, 302)
            failure.exception.close()
        self.assertEqual(redirected, [])

    def test_eos_rejects_invalid_and_oversized_response_bodies(self):
        endpoint = "/v1/energy-management/plan"
        oversized = b'{"value":"' + b"x" * clients.MAX_RESPONSE + b'"}'
        for body in (b"this is not JSON", oversized):
            with self.subTest(size=len(body)):
                with transport(eos=(FixtureHandler, {"routes": {endpoint: (200, {}, body)}, "requests": []})):
                    with self.assertRaises(ValueError):
                        clients.EOS("http://eos").plan()

    def test_eos_times_out_when_response_body_stalls(self):
        endpoint = "/v1/energy-management/plan"
        routes = {endpoint: (200, {"Content-Length": "2"}, b"")}
        with transport(eos=(FixtureHandler, {"routes": routes, "requests": [], "stall_body": True})):
            with self.assertRaises(TimeoutError):
                clients.EOS("http://eos").plan()

    def test_home_assistant_service_contract_and_http_error(self):
        service = "/core/api/services/number/set_value"
        state = "/core/api/states/number.charger"
        states = "/core/api/states"
        routes = {service: (503, {}, b'{"error":"offline"}'),
                  state: (200, {}, b'{"entity_id":"number.charger","state":"6.2"}'),
                  states: (200, {}, b'[{"entity_id":"number.charger","state":"6.2"}]')}
        seen = []
        with transport(supervisor=(FixtureHandler, {"routes": routes, "requests": seen})):
            ha = clients.HomeAssistant("test-token")
            self.assertEqual(ha.states()["number.charger"]["state"], "6.2")
            self.assertEqual(ha.state("number.charger")["state"], "6.2")
            with self.assertRaises(HTTPError) as failure:
                ha.set("number.charger", 6.2)
            self.assertEqual(failure.exception.code, 503)
            failure.exception.close()
            with self.assertRaises(ValueError):
                ha.set("sensor.read_only", 1)
        self.assertEqual([(method, path) for method, path, _, _ in seen],
                         [("GET", states), ("GET", state), ("POST", service)])
        self.assertEqual(seen[-1][2], "Bearer test-token")
        self.assertEqual(json.loads(seen[-1][3]), {"entity_id": "number.charger", "value": 6.2})


class ServerBoundaryTests(unittest.TestCase):
    def test_ingress_serves_ui_and_enforces_write_contract_over_http(self):
        app = Mock(config=SimpleNamespace(options={"language": "auto"}))
        app.snapshot.return_value = {"armed": False, "live": {"solar": 1800}}
        with patch("energy.server.INGRESS_PEER", "127.0.0.1"):
            with transport(ingress=(server.Handler, {"controller": app})):
                base = "http://ingress"
                with urlopen(base + "/", timeout=2) as response:
                    self.assertIn(b"./app.js", response.read())
                    self.assertIn("frame-ancestors", response.headers["Content-Security-Policy"])
                with urlopen(base + "/api/snapshot", timeout=2) as response:
                    self.assertEqual(json.load(response)["live"]["solar"], 1800)
                data = b'{"enabled":true}'
                headers = {"Content-Type": "application/json"}
                with self.assertRaises(HTTPError) as failure:
                    urlopen(Request(base + "/api/control", data=data, headers=headers), timeout=2)
                self.assertEqual(failure.exception.code, 403)
                failure.exception.close()
                app.set_armed.assert_not_called()
                headers["X-Energy-Request"] = "1"
                with urlopen(Request(base + "/api/control", data=data, headers=headers), timeout=2) as response:
                    self.assertEqual(json.load(response), {"ok": True})
                app.set_armed.assert_called_once_with(True)

    def test_application_shutdown_releases_owned_devices(self):
        stopped = Event()
        app = Mock(owned=True, stop_event=stopped)
        worker_started = Event()
        app.run.side_effect = lambda: (worker_started.set(), stopped.wait(2))
        runtime = Mock()
        runtime.__enter__ = Mock(return_value=runtime)
        runtime.__exit__ = Mock(return_value=False)
        runtime.serve_forever.side_effect = lambda: self.assertTrue(worker_started.wait(2))
        with temporary_project_directory() as directory:
            (directory / "options.json").write_text("{}", encoding="utf-8")
            with (patch("energy.server.Path", return_value=directory),
                  patch("energy.server.HomeAssistant"),
                  patch("energy.server.Configuration"),
                  patch("energy.server.Controller", return_value=app),
                  patch("energy.server.ThreadingHTTPServer", return_value=runtime),
                  patch("energy.server.signal.signal")):
                server.main()
        self.assertTrue(stopped.is_set())
        app.set_armed.assert_called_once_with(False)


class DeviceBoundaryTests(unittest.TestCase):
    def test_fronius_return_to_auto_requires_device_acknowledgement(self):
        ha = Mock()
        driver = Fronius(ha, {})
        selector = driver.ids["mode"]
        active = {selector: {"state": "Block Discharging"}}
        ha.state.return_value = active[selector]
        with patch("energy.drivers.monotonic", side_effect=iter(range(0, 30, 6))):
            with self.assertRaises(ValueError):
                driver.release(active)
        self.assertIn((selector, "Auto"), [call.args for call in ha.set.call_args_list])

    def test_fronius_rejects_unconfirmed_discharge_limit(self):
        ha = Mock()
        driver = Fronius(ha, {})
        mode = {driver.ids["mode"]: {"state": "PV Charge and Discharge Limit"}}
        attrs = {"max": 10240, "step": 10, "unit_of_measurement": "W"}
        readings = {driver.ids["pv_limit"]: {"state": "0", "attributes": attrs},
                    driver.ids["discharge_limit"]: {"state": "4760", "attributes": attrs}}
        ha.state.side_effect = readings.__getitem__
        with patch("energy.drivers.monotonic", side_effect=iter(range(0, 30, 6))):
            with self.assertRaises(ValueError):
                driver.apply(BatteryCommand("limits", 0, 0), mode)
        self.assertIn((driver.ids["discharge_limit"], 0), [call.args for call in ha.set.call_args_list])

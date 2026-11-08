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

from custom_components.eos_energiezentrale.energy import clients
from custom_components.eos_energiezentrale.energy.domain import BatteryCommand
from custom_components.eos_energiezentrale.energy.drivers import Fronius
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

class DeviceBoundaryTests(unittest.TestCase):
    def test_fronius_return_to_auto_requires_device_acknowledgement(self):
        ha = Mock()
        driver = Fronius(ha, {})
        selector = driver.ids["mode"]
        active = {selector: {"state": "Block Discharging"}}
        ha.state.return_value = active[selector]
        with patch("custom_components.eos_energiezentrale.energy.drivers.monotonic", side_effect=iter(range(0, 30, 6))):
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
        with patch("custom_components.eos_energiezentrale.energy.drivers.monotonic", side_effect=iter(range(0, 30, 6))):
            with self.assertRaises(ValueError):
                driver.apply(BatteryCommand("limits", 0, 0), mode)
        self.assertIn((driver.ids["discharge_limit"], 0), [call.args for call in ha.set.call_args_list])

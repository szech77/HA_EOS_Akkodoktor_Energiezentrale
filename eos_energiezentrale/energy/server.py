"""Ingress-only HTTP surface. No generic proxy or device command endpoint."""
import json
import os
import signal
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from time import monotonic
from urllib.parse import parse_qs, urlsplit

from .clients import HomeAssistant
from .controller import Controller, LegacyControlActive
from .history import influx_series
from .localization import load_language
from .settings import Configuration

INGRESS_PEER = "172.30.32.2"
PUBLIC = Path(__file__).with_name("web")
STATIC = {"/": ("index.html", "text/html; charset=utf-8"),
          "/app.js": ("app.js", "text/javascript; charset=utf-8"),
          "/style.css": ("style.css", "text/css; charset=utf-8")}


class Handler(BaseHTTPRequestHandler):
    server_version = "EOS-Energiezentrale"
    sys_version = ""

    def reply(self, status, content, media="application/json; charset=utf-8"):
        if not isinstance(content, bytes):
            content = json.dumps(content, ensure_ascii=False, allow_nan=False).encode()
        self.send_response(status)
        self.send_header("Content-Type", media)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Content-Security-Policy",
                         "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                         "img-src 'self' data:; object-src 'none'; base-uri 'none'; "
                         "frame-ancestors 'self'; form-action 'self'")
        self.end_headers()
        self.wfile.write(content)

    def allowed(self):
        if self.client_address[0] != INGRESS_PEER:
            self.reply(403, {"error": "ingress_only"})
            return False
        return True

    def do_GET(self):
        if not self.allowed():
            return
        url = urlsplit(self.path)
        path = url.path
        app = self.server.controller
        now = datetime.now(timezone.utc)
        try:
            if path in STATIC:
                name, media = STATIC[path]
                self.reply(200, (PUBLIC / name).read_bytes(), media)
            elif path == "/api/snapshot":
                self.reply(200, app.snapshot(now))
            elif path == "/api/language":
                ha_language = parse_qs(url.query, max_num_fields=4).get("ha_language", [None])[0]
                self.reply(200, load_language(app.config.options.get("language", "auto"),
                                             ha_language=ha_language))
            elif path == "/api/history":
                if monotonic() - self.server.influx_at >= 300:
                    with self.server.influx_lock:
                        if monotonic() - self.server.influx_at >= 300:
                            self.server.influx_at = monotonic()
                            try:
                                self.server.influx_rows = influx_series(app.config)
                                self.server.influx_error = False
                            except Exception:
                                self.server.influx_error = True
                self.reply(200, {"local": app.history.read(now), "influx": self.server.influx_rows,
                                 "influx_error": self.server.influx_error})
            else:
                self.reply(404, {"error": "not_found"})
        except (OSError, ValueError):
            self.reply(503, {"error": "data_unavailable"})

    def do_POST(self):
        if not self.allowed():
            return
        if (self.headers.get("X-Energy-Request") != "1"
                or self.headers.get_content_type() != "application/json"
                or self.headers.get("Sec-Fetch-Site") == "cross-site"):
            self.reply(403, {"error": "browser_request"})
            return
        path = urlsplit(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 8192:
                raise ValueError("Ungültige Anfragelänge")
            values = json.loads(self.rfile.read(length))
            app = self.server.controller
            if path == "/api/settings":
                with app.lock:
                    app.config.update(values)
            elif path == "/api/control":
                if not isinstance(values, dict) or values.keys() != {"enabled"} or type(values["enabled"]) is not bool:
                    raise ValueError("Ungültige Steuerfreigabe")
                app.set_armed(values["enabled"])
            else:
                self.reply(404, {"error": "not_found"})
                return
            self.reply(200, {"ok": True})
        except json.JSONDecodeError:
            self.reply(400, {"error": "invalid_json"})
        except LegacyControlActive:
            self.reply(400, {"error": "legacy_control"})
        except ValueError:
            self.reply(400, {"error": "invalid_settings" if path == "/api/settings" else "control_rejected"})
        except (OSError, KeyError):
            self.reply(503, {"error": "change_unconfirmed"})

    def log_message(self, *args):
        # Ingress paths and request data can contain private information.
        pass


def main():
    from threading import Lock

    directory = Path("/data")
    options = json.loads((directory / "options.json").read_text(encoding="utf-8"))
    ha = HomeAssistant(os.environ.get("SUPERVISOR_TOKEN"))
    app = Controller(ha, Configuration(options, ha, directory))
    with ThreadingHTTPServer(("", 8099), Handler) as server:
        server.controller = app
        server.influx_at = -1000
        server.influx_rows = []
        server.influx_error = False
        server.influx_lock = Lock()
        thread = Thread(target=app.run, daemon=True)
        thread.start()
        signal.signal(signal.SIGTERM, lambda *_: Thread(target=server.shutdown, daemon=True).start())
        try:
            server.serve_forever()
        finally:
            app.stop_event.set()
            thread.join(timeout=10)
            if not thread.is_alive() and app.owned:
                try:
                    app.set_armed(False)
                except Exception:
                    print("Gerätefreigabe beim Stoppen konnte nicht bestätigt werden.")


if __name__ == "__main__":
    main()

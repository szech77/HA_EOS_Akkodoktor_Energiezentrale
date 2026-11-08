"""Bounded HTTP clients for Home Assistant, EOS and InfluxDB 1.x."""
import base64
import json
import re
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .domain import instant, number


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args):
        return None


OPENER = build_opener(NoRedirect())
MAX_RESPONSE = 8_000_000
ENTITY = re.compile(r"[a-z_]+\.[a-z0-9_]+\Z")


def base_url(value):
    if not isinstance(value, str) or any(c.isspace() for c in value):
        raise ValueError("Ungültige API-Adresse")
    url = urlsplit(value)
    if (url.scheme not in {"http", "https"} or not url.hostname or url.username is not None
            or url.query or url.fragment or url.path not in {"", "/"}):
        raise ValueError("API-Adresse muss aus Schema, Host und optional Port bestehen")
    _ = url.port
    return value.rstrip("/")


def request(url, *, method="GET", payload=None, headers=None):
    headers = {"Accept": "application/json", **(headers or {})}
    data = None
    if payload is not None:
        data = json.dumps(payload, allow_nan=False).encode()
        headers["Content-Type"] = "application/json"
    with OPENER.open(Request(url, data=data, headers=headers, method=method), timeout=5) as response:
        body = response.read(MAX_RESPONSE + 1)
    if len(body) > MAX_RESPONSE:
        raise ValueError("Antwort zu groß")
    return json.loads(body)


class HomeAssistant:
    def __init__(self, token):
        if not token:
            raise ValueError("Supervisor-Zugriff fehlt")
        self.headers = {"Authorization": "Bearer " + token}

    def states(self):
        rows = request("http://supervisor/core/api/states", headers=self.headers)
        return {item["entity_id"]: item for item in rows}

    def state(self, entity):
        return request("http://supervisor/core/api/states/" + quote(entity, safe=""), headers=self.headers)

    def set(self, entity, value):
        domain = entity.split(".", 1)[0]
        if not ENTITY.fullmatch(entity):
            raise ValueError("Ungültige Steuerentität")
        if domain == "switch" and isinstance(value, bool):
            service, extra = ("turn_on" if value else "turn_off"), {}
        elif domain == "select" and isinstance(value, str):
            service, extra = "select_option", {"option": value}
        elif domain == "number" and number(value) is not None:
            service, extra = "set_value", {"value": value}
        else:
            raise ValueError("Unzulässiger Steuerbefehl")
        request(f"http://supervisor/core/api/services/{domain}/{service}", method="POST",
                payload={"entity_id": entity, **extra}, headers=self.headers)

    def publish_soc(self, value, measured):
        request("http://supervisor/core/api/states/sensor.eos_energiezentrale_id4_soc", method="POST",
                payload={"state": round(value / 100, 7) if value is not None else "unavailable",
                         "attributes": {"friendly_name": "EOS Energiezentrale ID.4 SoC Faktor",
                                        "source": "vehicle" if measured else "estimate"}}, headers=self.headers)


def reading(states, entity, now, kind, max_age=None):
    row = states.get(entity, {})
    value = number(row.get("state"))
    unit = row.get("attributes", {}).get("unit_of_measurement")
    if value is None:
        return None
    if max_age is not None:
        stamp = instant(row.get("last_reported") or row.get("last_updated"))
        if stamp is None or not 0 <= (now - stamp).total_seconds() < max_age:
            return None
    scales = {"power": {"W": 1, "kW": 1000},
              "price": {"EUR/kWh": 100, "€/kWh": 100, "ct/kWh": 1, "c/kWh": 1}}
    if kind in scales:
        scale = scales[kind].get(unit)
        return value * scale if scale is not None else None
    return value


class EOS:
    def __init__(self, url):
        self.url = base_url(url)

    def plan(self):
        return request(self.url + "/v1/energy-management/plan")

    def solution(self):
        return request(self.url + "/v1/energy-management/optimization/solution/GENETIC")

    def set_vehicle_goal(self, resource, target, departure):
        configuration = request(self.url + "/v1/config")
        vehicles = configuration["devices"]["electric_vehicles"]
        if resource not in vehicles or not isinstance(vehicles[resource], dict):
            raise ValueError("Fahrzeug fehlt in EOS")
        current = vehicles[resource]
        desired = {"min_soc_percentage": target, "max_soc_percentage": target,
                   "min_soc_deadline_datetime": departure.isoformat() if departure else None}
        if all(current.get(key) == value for key, value in desired.items()):
            return
        updated = {**vehicles, resource: {**current, **desired}}
        request(self.url + "/v1/config/devices/electric_vehicles", method="PUT", payload=updated)
        confirmed = request(self.url + "/v1/config")["devices"]["electric_vehicles"][resource]
        if (confirmed.get("min_soc_percentage") != target or confirmed.get("max_soc_percentage") != target
                or instant(confirmed.get("min_soc_deadline_datetime")) != departure):
            raise ValueError("EOS hat das Ladeziel nicht bestätigt")


class Influx:
    def __init__(self, url, database, user, password):
        self.url = base_url(url) if url else None
        self.database = database
        encoded = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.headers = {"Authorization": "Basic " + encoded} if user else {}

    def history(self, entity, measurements, reducer="mean", field="value"):
        if not self.url or not ENTITY.fullmatch(entity):
            return []
        domain, entity_id = entity.split(".")
        if field not in {"value", "state"} or reducer not in {"mean", "last"}:
            raise ValueError("Ungültige Verlaufsabfrage")
        for measurement, scale in measurements:
            if measurement not in {"W", "kW", "%", "EUR/kWh", "€/kWh", "ct/kWh", "state"}:
                raise ValueError("Ungültiges Measurement")
            query = (f'SELECT {reducer}("{field}") FROM "{measurement}" WHERE "domain"=\'{domain}\' '
                     f'AND "entity_id"=\'{entity_id}\' AND time >= now() - 24h GROUP BY time(5m) fill(none)')
            result = request(self.url + "/query?" + urlencode({"db": self.database, "q": query}),
                             headers=self.headers)["results"][0]
            if "error" in result:
                raise ValueError("InfluxDB-Abfrage fehlgeschlagen")
            if result.get("series"):
                return [[ts, value if scale is None else value * scale]
                        for ts, value in result["series"][0]["values"]
                        if value is not None and (scale is None or number(value) is not None)]
        return []

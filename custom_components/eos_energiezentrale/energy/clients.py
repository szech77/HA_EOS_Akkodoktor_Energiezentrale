"""Bounded HTTP clients for Home Assistant, EOS and InfluxDB 1.x."""
import base64
import json
import re
from datetime import timedelta
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


def report_time(states, entity):
    """Return the reported observation timestamp, never the snapshot time."""
    state = states.get(entity, {})
    return instant(state.get("last_reported") or state.get("last_updated"))


class EOS:
    def __init__(self, url):
        self.url = base_url(url)

    def plan(self):
        return request(self.url + "/v1/energy-management/plan")

    def solution(self):
        return request(self.url + "/v1/energy-management/optimization/solution/GENETIC")

    def feedin_accounting(self, now):
        configuration = request(self.url + "/v1/config")
        tariff = configuration.get("feedintariff", {})
        if tariff.get("provider") == "FeedInTariffFixed":
            fixed = tariff.get("feedintarifffixed", {}).get("feed_in_tariff_amt_kwh")
            value = number(fixed) if not isinstance(fixed, dict) else None
            windows = fixed.get("windows", []) if isinstance(fixed, dict) else []
            if len(windows) == 1 and isinstance(windows[0], dict):
                window = windows[0]
                if (window.get("start_time") in {"00:00", "00:00:00", "00:00:00.000000"}
                        and window.get("duration") in {"1 day", "24 hours", "PT24H", "P1D"}
                        and all(window.get(key) is None for key in
                                ("end_time", "day_of_week", "date", "month", "locale"))):
                    value = number(window.get("value"))
            if value is not None and -10 <= value <= 10:
                return {"constant_ct": value*100}
        # EOS prediction values use currency/Wh; preserve sign and interval bounds.
        query = urlencode({"key":"feed_in_tariff_wh", "start_datetime":(now-timedelta(hours=1)).isoformat(),
                           "end_datetime":(now+timedelta(hours=24)).isoformat()})
        response = request(self.url + "/v1/prediction/series?" + query)
        data = response.get("data") if isinstance(response, dict) else None
        if not isinstance(data, dict):
            raise ValueError("Feed-in tariff is not ready")
        points = sorted((instant(stamp),number(value)) for stamp,value in data.items()
                        if instant(stamp) is not None and number(value) is not None)
        rows = []
        for index,(stamp,value) in enumerate(points):
            end = min(stamp+timedelta(hours=1),points[index+1][0]) if index+1<len(points) else stamp+timedelta(minutes=15)
            price = value*100000
            if -1000 <= price <= 1000 and end>stamp:
                rows.append({"time":stamp.isoformat(),"end":end.isoformat(),"price_ct":price})
        if not any(instant(row["time"])<=now<instant(row["end"]) for row in rows):
            raise ValueError("No current feed-in tariff")
        return {"series":rows}

    def battery_accounting(self, resource):
        configuration = request(self.url + "/v1/config")
        battery = configuration.get("devices", {}).get("batteries", {}).get(resource)
        if not isinstance(battery, dict):
            raise ValueError("Stationary battery configuration missing")
        keys = ("capacity_wh", "charging_efficiency", "discharging_efficiency")
        values = [number(battery.get(key)) for key in keys]
        if any(value is None for value in values):
            raise ValueError("Battery capacity/efficiencies missing")
        return dict(zip(("capacity_wh", "charge_efficiency", "discharge_efficiency"), values))

    def set_battery_limits(self, resource, minimum, maximum):
        if (type(minimum) is not int or type(maximum) is not int
                or not 0 <= minimum < maximum <= 100):
            raise ValueError("Invalid stationary battery SoC limits")
        configuration = request(self.url + "/v1/config")
        batteries = configuration.get("devices", {}).get("batteries")
        if (not isinstance(batteries, dict) or resource not in batteries
                or not isinstance(batteries[resource], dict)):
            raise ValueError("Configured stationary battery is missing in EOS")
        desired = {"min_soc_percentage": minimum, "max_soc_percentage": maximum}
        if all(batteries[resource].get(key) == value for key, value in desired.items()):
            return
        updated = {**batteries, resource: {**batteries[resource], **desired}}
        # Updating the collection avoids EOS versions rejecting a raw leaf dict.
        request(self.url + "/v1/config/devices/batteries", method="PUT", payload=updated)
        confirmed = request(self.url + "/v1/config").get("devices", {}).get("batteries", {}).get(resource)
        if not isinstance(confirmed, dict) or any(confirmed.get(key) != value for key, value in desired.items()):
            raise ValueError("EOS did not confirm stationary battery limits")

    def set_vehicle_goal(self, resource, target, departure):
        configuration = request(self.url + "/v1/config")
        vehicles = configuration["devices"]["electric_vehicles"]
        if resource not in vehicles or not isinstance(vehicles[resource], dict):
            raise ValueError("Fahrzeug fehlt in EOS")
        current = vehicles[resource]
        desired = {"min_soc_percentage": target, "max_soc_percentage": target,
                   "min_soc_deadline_datetime": departure.isoformat() if departure else None}
        if departure is None:
            desired["min_soc_max_duration_h"] = None
        if all(current.get(key) == value for key, value in desired.items()):
            return
        updated = {**vehicles, resource: {**current, **desired}}
        request(self.url + "/v1/config/devices/electric_vehicles", method="PUT", payload=updated)
        confirmed = request(self.url + "/v1/config")["devices"]["electric_vehicles"][resource]
        if (confirmed.get("min_soc_percentage") != target or confirmed.get("max_soc_percentage") != target
                or instant(confirmed.get("min_soc_deadline_datetime")) != departure
                or (departure is None and confirmed.get("min_soc_max_duration_h") is not None)):
            raise ValueError("EOS hat das Ladeziel nicht bestätigt")


class Influx:
    def __init__(self, url, database, user, password):
        self.url = base_url(url) if url else None
        self.database = database
        encoded = base64.b64encode(f"{user}:{password}".encode()).decode()
        self.headers = {"Authorization": "Basic " + encoded} if user else {}

    def history(self, entity, measurements, reducer="mean", field="value", *, start=None, end=None):
        if not self.url or not ENTITY.fullmatch(entity):
            return []
        domain, entity_id = entity.split(".")
        if field not in {"value", "state"} or reducer not in {"mean", "last"}:
            raise ValueError("Ungültige Verlaufsabfrage")
        bounds = "time >= now() - 24h"
        if start is not None or end is not None:
            first, last = instant(start), instant(end)
            if first is None or last is None or not 0 < (last-first).total_seconds() <= 367*86400:
                raise ValueError("Invalid historical time range")
            bounds = f"time >= '{first.isoformat()}' AND time < '{last.isoformat()}'"
        for measurement, scale in measurements:
            if measurement not in {"W", "kW", "%", "EUR/kWh", "€/kWh", "ct/kWh", "state"}:
                raise ValueError("Ungültiges Measurement")
            # InfluxQL identifiers are restricted by ENTITY and the allowlists above.
            query = (f'SELECT {reducer}("{field}") FROM "{measurement}" WHERE "domain"=\'{domain}\' '  # nosec B608
                     f'AND "entity_id"=\'{entity_id}\' AND {bounds} GROUP BY time(5m) fill(none)')
            result = request(self.url + "/query?" + urlencode({"db": self.database, "q": query}),
                             headers=self.headers)["results"][0]
            if "error" in result:
                raise ValueError("InfluxDB-Abfrage fehlgeschlagen")
            if result.get("series"):
                return [[ts, value if scale is None else value * scale]
                        for ts, value in result["series"][0]["values"]
                        if value is not None and (scale is None or number(value) is not None)]
        return []

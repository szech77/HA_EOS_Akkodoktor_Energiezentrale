"""Durable proportional energy allocation and weighted battery cost inventory.

Amounts are AC-side kWh/EUR. Attribution is an accounting model, not a physical
trace of electrons. Missing inputs never become free energy or zero consumption.
"""
import calendar
import json
import sqlite3
from contextlib import closing
from datetime import date, datetime, time, timedelta, timezone

from .domain import instant, number

DEFAULTS = {"pv_price_ct": 0.0, "pv_price_source": "eos", "efficiency_source": "eos",
            "charge_efficiency": .95, "discharge_efficiency": .95,
            "capacity_wh": 11000.0, "initial_price_ct": None}
SOURCES = ("pv", "battery", "grid", "unknown")


def checked_settings(values):
    if not isinstance(values, dict) or values.keys() - DEFAULTS.keys():
        raise ValueError("Unknown accounting setting")
    result = {**DEFAULTS, **values}
    if result["pv_price_source"] not in {"eos", "manual"}:
        raise ValueError("Invalid PV price source")
    if result["efficiency_source"] not in {"eos", "manual"}:
        raise ValueError("Invalid efficiency source")
    for key, low, high in (("pv_price_ct", -1000, 1000),
                           ("charge_efficiency", .1, 1), ("discharge_efficiency", .1, 1),
                           ("capacity_wh", 100, 1000000), ("initial_price_ct", -1000, 1000)):
        value = result[key]
        if key == "initial_price_ct" and value is None:
            continue
        if isinstance(value, bool) or number(value) is None or not low <= float(value) <= high:
            raise ValueError("Invalid accounting value: " + key)
        result[key] = float(value)
    return result


def empty():
    return {"kwh": 0., "cost_eur": 0., "cost_unknown_kwh": 0., "seconds": 0.,
            "sources": {key: {"kwh": 0., "cost_eur": 0., "cost_unknown_kwh": 0.} for key in SOURCES}}


def add(target, source):
    for key in ("kwh", "cost_eur", "cost_unknown_kwh", "seconds"):
        target[key] += source[key]
    for name in SOURCES:
        for key in ("kwh", "cost_eur", "cost_unknown_kwh"):
            target["sources"][name][key] += source["sources"][name][key]


class Accounting:
    def __init__(self, directory, zone):
        self.path = directory / "accounting.sqlite3"
        self.zone = zone
        self.previous = None
        self.last_eos_attempt = None
        self.eos_battery = None
        self.eos_error = None
        self.pv_tariff = None
        self.pv_error = None
        self.last_pv_attempt = None
        with closing(self.connect()) as db, db:
            db.execute("CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS energy (hour INTEGER, day TEXT, consumer TEXT, payload TEXT NOT NULL, PRIMARY KEY(hour,day,consumer))")
            db.execute("CREATE INDEX IF NOT EXISTS energy_day ON energy(day)")
            rows = dict(db.execute("SELECT key,value FROM meta"))
        raw = json.loads(rows.get("settings", "{}"))
        # Preserve earlier nonzero manual prices; migrate the former zero default to EOS.
        if "pv_price_source" not in raw and raw.get("pv_price_ct",0) != 0:
            raw["pv_price_source"] = "manual"
        self.settings = checked_settings(raw)
        self.stock = json.loads(rows.get("stock", "null"))
        self.started = rows.get("started")
        self.reconcile = self.stock is not None

    def connect(self):
        return sqlite3.connect(self.path)

    def configure(self, values):
        if not isinstance(values, dict):
            raise ValueError("Accounting settings must be an object")
        settings = checked_settings({**self.settings, **values})
        with closing(self.connect()) as db, db:
            db.execute("INSERT OR REPLACE INTO meta VALUES ('settings',?)", (json.dumps(settings),))
        self.settings = settings

    def refresh_eos(self, eos, resource, now):
        self.refresh_tariff(eos,now)
        if self.last_eos_attempt is not None and (now-self.last_eos_attempt).total_seconds() < (60 if self.eos_error else 3600):
            return
        self.last_eos_attempt = now
        try:
            values = eos.battery_accounting(resource)
            if not isinstance(values, dict) or values.keys() != {"capacity_wh", "charge_efficiency", "discharge_efficiency"}:
                raise ValueError("Incomplete EOS battery data")
            validated = checked_settings({**self.settings, **values})
            self.eos_battery = {key: validated[key] for key in
                                ("capacity_wh", "charge_efficiency", "discharge_efficiency")}
            self.eos_error = None
        except (ValueError, OSError, TimeoutError, KeyError, TypeError):
            self.eos_error = "unavailable"

    def refresh_tariff(self, eos, now):
        if self.settings["pv_price_source"] != "eos":
            return
        if self.last_pv_attempt is not None and (now-self.last_pv_attempt).total_seconds() < (60 if self.pv_error else 300):
            return
        self.last_pv_attempt = now
        try:
            tariff = eos.feedin_accounting(now)
            if not isinstance(tariff,dict) or tariff.keys() not in ({"constant_ct"},{"series"}):
                raise ValueError("Invalid tariff response")
            if "constant_ct" in tariff and (number(tariff["constant_ct"]) is None or not -1000<=tariff["constant_ct"]<=1000):
                raise ValueError("Invalid feed-in price")
            self.pv_tariff = tariff
            self.pv_error = None
        except (ValueError, OSError, TimeoutError, KeyError, TypeError):
            self.pv_error = "unavailable"

    def pv_price(self, when=None):
        if self.settings["pv_price_source"] == "manual":
            return self.settings["pv_price_ct"]
        tariff = getattr(self,"pv_tariff",None)
        if not isinstance(tariff,dict):
            return None
        if "constant_ct" in tariff:
            return number(tariff["constant_ct"])
        stamp = instant(when)
        for row in tariff.get("series",[]):
            start,end = instant(row.get("time")),instant(row.get("end"))
            if stamp is not None and start is not None and end is not None and start<=stamp<end:
                return number(row.get("price_ct"))
        return None

    def effective(self):
        if self.settings["efficiency_source"] == "eos":
            return self.eos_battery
        return self.settings

    def observe(self, live, vehicles=()):
        now = instant(live.get("time"))
        if now is None:
            return
        consumers = {"house": live.get("house"), "heat": live.get("heat"), "car": live.get("car")}
        for vehicle in vehicles:
            consumers["car/"+vehicle["id"]] = vehicle.get("live", {}).get("car")
        sample = {**live, "consumers": consumers}
        previous = self.previous
        if previous is not None and now <= previous[0]:
            return
        self.previous = (now, sample)
        if previous is None:
            return
        elapsed = (now-previous[0]).total_seconds()
        if elapsed > 120:
            if self.stock is not None:
                effective = self.effective()
                soc = number(sample.get("battery_soc"))
                if effective is not None and soc is not None:
                    self.stock["kwh"] = max(0,min(100,soc))*effective["capacity_wh"]/100000
                self.stock["unknown"] = self.stock["kwh"]
                self.stock["cost"] = 0.
            return  # No interpolation across outages or restarts.
        effective = self.effective()
        if effective is None and ((number(previous[1].get("battery_discharge")) or 0)>0 or (number(previous[1].get("battery_charge")) or 0)>0):
            self.reconcile = self.stock is not None
        if self.reconcile and effective is not None and number(previous[1].get("battery_soc")) is not None:
            energy = max(0,min(100,float(previous[1]["battery_soc"]))) * effective["capacity_wh"]/100000
            if energy > self.stock["kwh"]:
                self.stock["unknown"] += energy-self.stock["kwh"]
            elif self.stock["kwh"] > 0:
                ratio = energy/self.stock["kwh"]
                self.stock["cost"] *= ratio
                self.stock["unknown"] *= ratio
            self.stock["kwh"] = energy
            self.reconcile = False
        if self.stock is None and effective is not None and number(previous[1].get("battery_soc")) is not None:
            energy = max(0, min(100, float(previous[1]["battery_soc"]))) * effective["capacity_wh"] / 100000
            price = self.settings["initial_price_ct"]
            self.stock = {"kwh": energy, "cost": energy * (price or 0) / 100,
                          "unknown": energy if price is None else 0}
        # Split at UTC hours and local midnight, preserving DST days (23/25 hours).
        cursor = previous[0]
        with closing(self.connect()) as db, db:
            while cursor < now:
                hour = int(cursor.timestamp()) // 3600 * 3600
                next_hour = datetime.fromtimestamp(hour+3600, timezone.utc)
                next_date = cursor.astimezone(self.zone).date()+timedelta(days=1)
                midnight = datetime.combine(next_date, time(), self.zone).astimezone(timezone.utc)
                end = min(now, next_hour, midnight)
                values = self.allocate(previous[1], (end-cursor).total_seconds()/3600000, effective)
                day = cursor.astimezone(self.zone).date().isoformat()
                for consumer, amount in values.items():
                    old = db.execute("SELECT payload FROM energy WHERE hour=? AND day=? AND consumer=?", (hour, day, consumer)).fetchone()
                    total = json.loads(old[0]) if old else empty()
                    add(total, amount)
                    db.execute("INSERT OR REPLACE INTO energy VALUES (?,?,?,?)", (hour, day, consumer, json.dumps(total)))
                cursor = end
            if self.started is None:
                self.started = previous[0].isoformat()
            db.execute("INSERT OR REPLACE INTO meta VALUES ('stock',?)", (json.dumps(self.stock),))
            db.execute("INSERT OR REPLACE INTO meta VALUES ('started',?)", (self.started,))

    def allocate(self, row, hours_per_thousand, effective):
        def positive(key):
            value = number(row.get(key))
            return max(0, value) if value is not None else None
        pv, grid, discharge, charge = positive("solar"), number(row.get("grid")), positive("battery_discharge"), positive("battery_charge")
        outputs = {}
        sources_ok = all(value is not None for value in (pv, grid, discharge, charge))
        # At most 10%/300W balance residual is tolerated. Larger residuals are
        # visible as unknown rather than assigning async meter jumps to PV/grid.
        load = positive("house_total")
        supplied = pv + max(0, grid) + discharge if sources_ok else 0
        sinks = load + charge + max(0, -grid) if sources_ok and load is not None else None
        balanced = sinks is not None and abs(supplied-sinks) <= max(300, sinks*.1)
        ratios = {"pv": pv/supplied, "grid": max(0,grid)/supplied, "battery": discharge/supplied} if balanced and supplied > 0 else {}
        battery_rate, battery_unknown = 0., 1.
        if discharge is not None and discharge > 0 and effective is not None and self.stock is not None:
            needed = discharge*hours_per_thousand/effective["discharge_efficiency"]
            available = min(needed, self.stock["kwh"])
            fraction = available/self.stock["kwh"] if self.stock["kwh"] > 0 else 0
            cost = self.stock["cost"]*fraction
            unknown = self.stock["unknown"]*fraction + needed-available
            battery_rate = cost/(discharge*hours_per_thousand)
            battery_unknown = min(1., unknown/needed)
            for key in ("kwh", "cost", "unknown"):
                self.stock[key] *= 1-fraction
        elif discharge is None or charge is None:
            # Inventory composition is no longer trustworthy after missing storage telemetry.
            if self.stock is not None:
                self.stock["unknown"] = self.stock["kwh"]
                self.stock["cost"] = 0.
        price = number(row.get("price"))  # live price is ct/kWh
        pv_price = self.pv_price(row.get("time"))
        rates = {"pv": pv_price/100 if pv_price is not None else 0., "grid": price/100 if price is not None else 0., "battery": battery_rate}
        unknowns = {"pv": 1. if pv_price is None else 0., "grid": 1. if price is None else 0., "battery": battery_unknown}
        for name, watts in row["consumers"].items():
            if number(watts) is None:
                continue
            amount = empty()
            energy = max(0, float(watts))*hours_per_thousand
            amount["kwh"] = energy
            amount["seconds"] = hours_per_thousand*3600000
            for source in SOURCES:
                part = energy*(ratios.get(source,0) if ratios else (1 if source=="unknown" else 0))
                cost = part*rates.get(source,0)
                unknown = part*unknowns.get(source,1)
                amount["sources"][source] = {"kwh":part,"cost_eur":cost,"cost_unknown_kwh":unknown}
                amount["cost_eur"] += cost
                amount["cost_unknown_kwh"] += unknown
            outputs[name] = amount
        if charge is not None and charge > 0 and self.stock is not None and effective is not None:
            energy = charge*hours_per_thousand
            # A charging battery cannot be its own energy source.
            pv_ratio, grid_ratio = ratios.get("pv",0), ratios.get("grid",0)
            known_ratio = pv_ratio+grid_ratio
            self.stock["kwh"] += energy*effective["charge_efficiency"]
            self.stock["cost"] += energy*(pv_ratio*rates["pv"]+grid_ratio*rates["grid"])
            self.stock["unknown"] += energy*effective["charge_efficiency"]*min(1.,1-known_ratio+grid_ratio*unknowns["grid"]+pv_ratio*unknowns["pv"])
        return outputs

    def report(self, values, now):
        if not isinstance(values, dict) or values.keys()-{"period", "date"}:
            raise ValueError("Invalid report request")
        period = values.get("period", "month")
        if period not in {"day", "month", "year"}:
            raise ValueError("Invalid report period")
        try:
            selected = date.fromisoformat(values.get("date", now.astimezone(self.zone).date().isoformat()))
        except (ValueError, TypeError) as error:
            raise ValueError("Invalid report date") from error
        if not 2000 <= selected.year <= 2100:
            raise ValueError("Report date outside supported range")
        start = selected if period=="day" else selected.replace(day=1) if period=="month" else selected.replace(month=1,day=1)
        end = start+timedelta(days=1) if period=="day" else start+timedelta(days=calendar.monthrange(start.year,start.month)[1]) if period=="month" else start.replace(year=start.year+1)
        with closing(self.connect()) as db:
            rows = db.execute("SELECT hour,day,consumer,payload FROM energy WHERE day>=? AND day<? ORDER BY hour", (start.isoformat(),end.isoformat())).fetchall()
        consumers = {}
        for hour, day, consumer, payload in rows:
            entry = consumers.setdefault(consumer, {"total":empty(),"bins":{}})
            key = datetime.fromtimestamp(hour,timezone.utc).isoformat() if period=="day" else day if period=="month" else day[:7]
            amount = json.loads(payload)
            add(entry["total"],amount)
            add(entry["bins"].setdefault(key,empty()),amount)
        for entry in consumers.values():
            entry["bins"]=[{"time":key,**value} for key,value in entry["bins"].items()]
        hours = []
        if period == "day":
            cursor = datetime.combine(start,time(),self.zone).astimezone(timezone.utc)
            stop = datetime.combine(end,time(),self.zone).astimezone(timezone.utc)
            stamp = int(cursor.timestamp())//3600*3600
            while stamp < stop.timestamp():
                hours.append(datetime.fromtimestamp(stamp,timezone.utc).isoformat())
                stamp += 3600
        return {"period":period,"date":start.isoformat(),"end":end.isoformat(),"hours":hours,"consumers":consumers,
                "started":self.started,"settings":self.settings,"effective":self.effective(),
                "eos_error":self.eos_error,"pv_tariff":self.pv_tariff,"pv_price_ct":self.pv_price(now.isoformat()),"pv_error":self.pv_error,"stock":self.stock,"method":"proportional"}

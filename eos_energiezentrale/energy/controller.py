"""Single-writer coordinator. The UI can arm it only for the current process."""
from datetime import datetime, timedelta, timezone
from math import isclose
from threading import Event, RLock
from time import monotonic

from .clients import reading
from .domain import (battery_command, current_for_power, current_instruction, estimate_soc,
                     house_only, instant, next_departure, plan_series, pv_budget)
from .history import History, forecast_rows


LEGACY = ("input_boolean.eos_ev_aktiv", "input_boolean.eos_fronius_aktiv",
          "automation.eos_auto_laderegler", "automation.eos_fronius_plan_anwenden")


class LegacyControlActive(ValueError):
    pass


class Controller:
    def __init__(self, ha, config):
        self.ha, self.config = ha, config
        self.history = History(config.directory / "history.sqlite3")
        self.lock = RLock()
        self.stop_event = Event()
        self.armed = False
        self.owned = False
        self.live = {}
        self.plan = None
        self.forecast = []
        self.errors = {}
        self.goal = None
        self.goal_at = None
        self.soc = self.soc_report = self.soc_time = None
        self.soc_w = 0
        self.last_soc_publish = None
        self.last_write = None
        self.candidate = None
        self.phase_target = None
        self.pv_session = False
        self.last_minute = None
        self.last_plan_fetch = self.last_forecast_fetch = self.last_goal_attempt = -1000

    def set_armed(self, enabled):
        with self.lock:
            if enabled:
                states = self.ha.states()
                if any(states.get(key, {}).get("state") == "on" for key in LEGACY):
                    raise LegacyControlActive("Zuerst die bisherigen EOS-Regler deaktivieren")
                self.armed = True
                return
            self.armed = False
            if self.owned:
                try:
                    self.release(self.ha.states(), datetime.now(timezone.utc))
                except Exception:
                    self.errors["release"] = "Gerätefreigabe nicht bestätigt"
                    raise
                self.errors.pop("release", None)

    def release(self, states, now):
        try:
            self.config.wallbox.pause(self.config.wallbox.read(states, now))
        finally:
            self.config.battery.release(states)
        self.owned = False
        self.pv_session = False
        self.phase_target = None
        self.candidate = None

    def run(self):
        while not self.stop_event.is_set():
            started = monotonic()
            with self.lock:
                try:
                    self.tick(datetime.now(timezone.utc), started)
                    self.errors.pop("runtime", None)
                except Exception as error:
                    self.errors["runtime"] = type(error).__name__
                    if self.armed and self.owned:
                        try:
                            self.release(self.ha.states(), datetime.now(timezone.utc))
                        except Exception:
                            self.errors["release"] = "Gerätefreigabe nicht bestätigt"
                    self.armed = False
            self.stop_event.wait(max(0.1, 5 - (monotonic() - started)))

    def update_eos(self, now, clock):
        if clock - self.last_plan_fetch >= 15:
            self.last_plan_fetch = clock
            try:
                self.plan = self.config.eos.plan()
                self.errors.pop("eos", None)
            except Exception as error:
                self.errors["eos"] = type(error).__name__
        if clock - self.last_forecast_fetch >= 60:
            self.last_forecast_fetch = clock
            try:
                self.forecast = forecast_rows(self.config.eos.solution(), now)
                self.errors.pop("forecast", None)
            except Exception as error:
                self.forecast = []
                self.errors["forecast"] = type(error).__name__

    def update_soc(self, states, box, now):
        options = self.config.options
        entity = options["car_soc_entity"]
        raw = reading(states, entity, now, "soc")
        if raw is not None:
            raw *= 100 if options["car_soc_scale"] == "factor" else 1
            raw = raw if 0 <= raw <= 100 else None
        report = states.get(entity, {}).get("last_updated") if raw is not None else None
        watts = box.watts or 0
        elapsed = (now - self.soc_time).total_seconds() if self.soc_time else 0
        self.soc = estimate_soc(self.soc, raw, bool(report and report != self.soc_report),
                                box.charging, self.soc_w, watts, elapsed,
                                options["capacity_wh"], options["charging_efficiency"],
                                box.plugged or box.status in {"unknown", "unavailable"})
        self.soc_report = report or self.soc_report
        self.soc_time, self.soc_w = now, watts if box.charging else 0
        return raw is not None and isclose(raw, self.soc if self.soc is not None else -1, abs_tol=0.001)

    def sync_goal(self, now, clock, departure):
        daily = self.config.daily
        goal = (daily["target_soc"], departure) if departure else None
        if goal != self.goal and self.soc is not None and clock - self.last_goal_attempt >= 30:
            self.last_goal_attempt = clock
            try:
                target, deadline = goal or (int(self.soc or 0), None)
                self.config.eos.set_vehicle_goal(self.config.options["vehicle_resource"], target, deadline)
                self.goal, self.goal_at = goal, now
                self.errors.pop("goal", None)
            except Exception as error:
                self.errors["goal"] = type(error).__name__
        return goal is not None and goal == self.goal and self.goal_at is not None

    def tick(self, now, clock):
        self.update_eos(now, clock)
        states = self.ha.states()
        self.errors.pop("ha", None)
        opts, daily = self.config.options, self.config.daily
        battery = self.config.battery.read(states, now)
        box = self.config.wallbox.read(states, now)
        measured = self.update_soc(states, box, now)
        live = {key: reading(states, opts[source + "_entity"], now, kind, age)
                for key, source, kind, age in (("solar", "pv", "power", 45), ("grid", "grid", "power", 45),
                                               ("house_total", "house", "power", 120), ("heat", "heat", "power", 120),
                                               ("price", "price", "price", 3600))}
        live.update(time=now.isoformat(), car=box.watts, battery_soc=battery.soc, car_soc=self.soc,
                    soc_source="vehicle" if measured else "estimate" if self.soc is not None else None,
                    car_status=box.status, phases=box.phases, amps=box.amps,
                    battery_charge=battery.charge, battery_discharge=battery.discharge)
        live["house"] = house_only(live["house_total"], live["car"], live["heat"])
        live["battery"] = (battery.charge - battery.discharge
                           if battery.charge is not None and battery.discharge is not None else None)
        battery_order = current_instruction(self.plan, opts["battery_resource"], now)
        car_order = current_instruction(self.plan, opts["vehicle_resource"], now)
        live["battery_mode"] = battery_order.mode if battery_order else None
        live["car_mode"] = car_order.mode if car_order else None
        live["car_actual_mode"] = ("NON_EXPORT" if box.charging and self.pv_session
                                   else "CHARGING" if box.charging
                                   else "IDLE" if box.plugged
                                   else "DISCONNECTED" if box.status not in {"unknown", "unavailable", ""} else None)
        departure = next_departure(daily, now, self.config.zone)
        live["departure"] = departure.isoformat() if departure else None
        self.live = live
        minute = int(now.timestamp()) // 60
        if minute != self.last_minute:
            self.history.write(now, live)
            self.last_minute = minute
        if not self.armed:
            return
        if any(states.get(key, {}).get("state") == "on" for key in LEGACY):
            self.armed = False
            self.owned = False
            self.errors["ownership"] = "Alter EOS-Regler erkannt"
            self.pv_session = False
            return
        self.errors.pop("ownership", None)
        self.owned = True
        published = (round(self.soc, 4) if self.soc is not None else None, measured)
        if published != self.last_soc_publish:
            self.ha.publish_soc(self.soc, measured)
            self.last_soc_publish = published
        synchronized = self.sync_goal(now, clock, departure)
        generated = instant(self.plan.get("generated_at")) if isinstance(self.plan, dict) else None
        planned = 0
        maximum_power = min(11000, opts["max_current_a"] * 690)
        if daily["fast"] and self.soc is not None and self.soc < daily["target_soc"]:
            planned = maximum_power
        elif (synchronized and generated and (generated - self.goal_at).total_seconds() >= 120
              and car_order and car_order.mode in {"GRID_SUPPORT_IMPORT", "FORCED_CHARGE"}
              and self.soc is not None and self.soc < daily["target_soc"]):
            planned = maximum_power * car_order.factor
        pv = (self.soc is not None and not daily["fast"] and
              ((daily["pv"] and self.soc < daily["pv_target_soc"]) or
               (not daily["pv"] and synchronized and generated
                and (generated - self.goal_at).total_seconds() >= 120
                and car_order and car_order.mode == "NON_EXPORT" and self.soc < daily["target_soc"])))
        if not (pv and planned == 0):
            self.pv_session = False
        self.regulate_car(box, live, planned, pv, now, clock, states)
        command = battery_command(battery_order, battery.soc, opts,
                                  daily["battery_pv_support"] and box.charging and self.pv_session,
                                  live["grid"], battery.discharge, battery.charge)
        if command is None:
            self.config.battery.release(states)
        else:
            self.config.battery.apply(command, states)
        live["battery_control"] = command.mode if command else "auto"

    def regulate_car(self, box, live, planned, pv, now, clock, states):
        daily, opts, driver = self.config.daily, self.config.options, self.config.wallbox
        if (not box.plugged or box.phases is None or box.amps is None or not box.step or not box.maximum
                or box.watts is None or live["grid"] is None or live["battery_discharge"] is None
                or (pv and live["solar"] is None) or (not pv and planned <= 0)):
            driver.pause(box)
            self.pv_session = False
            self.candidate = self.phase_target = None
            return
        grid, discharge = live["grid"], max(0, live["battery_discharge"])
        hard = min(11000, max(0, box.watts + opts["grid_limit_w"] - grid - discharge - 100))
        solar_only = pv and planned == 0
        relative = solar_only and box.charging
        surplus = (pv_budget(max(0, live["solar"]), grid, box.watts if box.enabled else 0,
                             discharge, daily["reserve_w"], box.phases if relative else None,
                             box.amps if relative else None) if pv else 0)
        desired = min(hard, max(planned, surplus))
        nearest = pv and surplus > planned and box.charging and daily["reserve_w"] == 0 and box.step <= 0.1
        maximum = min(opts["max_current_a"], box.maximum)
        phase = box.phases
        if daily["phase_auto"]:
            if self.phase_target is not None:
                # Revalidate after opening the relay because export can have changed.
                phase = self.phase_target if desired >= 1380 * self.phase_target else box.phases
            elif not box.enabled:
                phase = 3 if desired >= 4290 else 1 if desired >= 1530 else box.phases
            elif phase == 3 and desired < 4140 and desired >= 1380:
                phase = 1
            elif phase == 1 and desired >= 4290 and (not solar_only or box.amps >= maximum - 0.05):
                phase = 3
        amps = current_for_power(desired, phase, box.step, maximum, nearest and phase == box.phases, hard)
        transition = (phase, amps is not None)
        if (not box.enabled and pv and planned == 0 and desired < (1380 * phase + 150)
                and self.phase_target is None):
            amps = None
            transition = (phase, False)
        if self.phase_target is None and (phase != box.phases or amps is None or (not box.enabled and solar_only)):
            if self.candidate is None or self.candidate[0] != transition:
                self.candidate = (transition, clock)
            if clock - self.candidate[1] < opts["phase_wait_s"] and pv and hard >= 1380 * box.phases:
                return
        else:
            self.candidate = None
        if amps is None:
            driver.pause(box)
            self.pv_session = False
            self.phase_target = None
            return
        if phase != box.phases or self.phase_target is not None:
            self.phase_target = phase
            self.pv_session = False
            if not driver.phase(phase, box):
                return
            self.phase_target = None
        if box.enabled and self.last_write is not None:
            meter = states.get(opts["grid_entity"], {})
            report = instant(meter.get("last_reported") or meter.get("last_updated"))
            if (now - self.last_write).total_seconds() < daily["regulation_interval_s"]:
                return
            if pv and (report is None or report <= self.last_write):
                return
        if not box.enabled or abs(box.amps - amps) >= 0.05:
            driver.charge(amps, box)
            self.last_write = now
        self.pv_session = solar_only
        live["car_control"] = "pv_only" if solar_only else "eos_pv" if pv else "grid_charge"

    def snapshot(self, now):
        with self.lock:
            plan = self.plan
            opts = self.config.options
            generated = instant(plan.get("generated_at")) if isinstance(plan, dict) else None
            current = bool(generated and 0 <= (now - generated).total_seconds() < 3600)
            plan_end = (instant(plan.get("valid_until")) or (instant(plan.get("valid_from")) or generated)
                        + timedelta(hours=24)) if current else None
            return {"live": dict(self.live), "settings": dict(self.config.daily),
                    "armed": self.armed, "release_pending": self.owned and not self.armed,
                    "errors": dict(self.errors), "zone": opts["timezone"],
                    "influx_configured": bool(self.config.influx.url),
                    "forecast": self.forecast if current else [], "plan_end": plan_end.isoformat() if plan_end else None,
                    "plan": {key: [{"time": item.when.isoformat(), "mode": item.mode, "factor": item.factor}
                                   for item in plan_series(plan, opts[resource])]
                             if current else [] for key, resource in (("battery", "battery_resource"),
                                                                        ("car", "vehicle_resource"))}}

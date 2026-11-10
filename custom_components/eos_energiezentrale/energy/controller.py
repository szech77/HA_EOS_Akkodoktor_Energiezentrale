"""Single-writer controller with persistent explicit control intent."""
from copy import deepcopy
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from math import isclose
from threading import Event, RLock
from time import monotonic

from .clients import reading
from .domain import (battery_command, current_for_power, current_instruction, estimate_soc,
                     house_only, instant, next_departure, plan_series, pv_budget)
from .history import History, forecast_rows
from .display import DisplayValues
from .presentation import daily_pv_forecast, heat_utilization, power_references, weather_display
from .plugin_registry import describe
from .alignment import ChargeTransitionDisplay, report_times


class Controller:
    def __init__(self, ha, config):
        self.ha, self.config = ha, config
        self.history = History(config.directory / "history.sqlite3")
        self.lock = RLock()
        self.stop_event = Event()
        self.armed = getattr(config, "control_enabled", False)
        self.restore_pending = self.armed
        self.owned = False
        self.live = {}
        self.display = {}
        self.flow_display = {}
        settings=getattr(config,"options",{})
        self.flow_alignment=ChargeTransitionDisplay(settings.get("display_hold_s",900),settings.get("display_transition_s",30))
        self.display_values = DisplayValues(getattr(config,"options",{}).get("display_hold_s",900))
        self.plan = None
        self.resource_plans = {}
        self.eos_failure_since = {}
        self.forecast = []
        self.errors = {}
        self.control_step = "startup"
        self.last_failure = None
        self.goal = None
        self.goal_at = None
        self.battery_limits_confirmed = None
        self.battery_limits_confirmed_at = None
        self.last_battery_limits_attempt = -1000
        self.soc = self.soc_report = self.soc_time = None
        self.soc_w = 0
        self.last_soc_publish = None
        self.last_write = None
        self.commanded_car_w = None
        self.candidate = None
        self.phase_target = None
        self.pv_session = False
        self.last_minute = None
        self.last_plan_fetch = self.last_forecast_fetch = self.last_goal_attempt = -1000
        self.external_eos_polling = False
        self.external_battery_sync = False

    def remember_control(self, enabled):
        store = getattr(self.config, "set_control_enabled", None)
        if store is None:
            return
        try:
            store(enabled)
        except Exception as error:
            self.errors["control_persistence"] = type(error).__name__
            raise
        self.errors.pop("control_persistence", None)

    def set_armed(self, enabled, *, persist=True):
        with self.lock:
            if type(enabled) is not bool:
                raise ValueError("Explicit boolean required for control setting")
            if enabled:
                if persist:
                    self.remember_control(True)
                self.restore_pending = True
                self.armed = True
                self.errors.pop("runtime", None)
                return
            self.armed = False
            self.commanded_car_w = None
            self.restore_pending = False
            persistence_error = None
            if persist:
                try:
                    self.remember_control(False)
                except Exception as error:
                    persistence_error = error
            if self.owned:
                try:
                    self.release(self.ha.states(), datetime.now(timezone.utc))
                except Exception:
                    self.errors["release"] = "Gerätefreigabe nicht bestätigt"
                    raise
                self.errors.pop("release", None)
            if persistence_error is not None:
                raise persistence_error

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
                    self.restore_pending = False
                    try:
                        self.remember_control(False)
                    except Exception:
                        pass  # Persistence failure is exposed in errors.
            self.stop_event.wait(max(0.1, 5 - (monotonic() - started)))

    def sync_battery_limits(self, now, clock, *, force=False):
        if self.external_battery_sync or not getattr(self.config, "battery_limits_managed", False):
            return
        desired = (self.config.daily["battery_min_soc"], self.config.daily["battery_max_soc"])
        interval = 60 if self.battery_limits_confirmed == desired else 30
        if not force and clock - self.last_battery_limits_attempt < interval:
            return
        self.last_battery_limits_attempt = clock
        try:
            self.config.eos.set_battery_limits(self.config.options["battery_resource"], *desired)
        except Exception as error:
            self.battery_limits_confirmed = None
            self.battery_limits_confirmed_at = None
            self.errors["battery_limits"] = type(error).__name__
        else:
            self.battery_limits_confirmed = desired
            self.battery_limits_confirmed_at = now
            self.errors.pop("battery_limits", None)

    def eos_resources(self):
        configured=getattr(self,"fleet_resources",None)
        if configured is not None:
            return configured
        options=self.config.options
        return {options["battery_resource"]} | ({options["vehicle_resource"]} if options.get("wallbox_type")!="none" else set())

    def plan_for(self,resource,now):
        failed=self.eos_failure_since.get(resource)
        if failed is not None and (now-failed).total_seconds()>=300:
            return None
        return self.resource_plans.get(resource,self.plan if failed is None else None)

    def order_for(self,resource,now):
        plan=self.plan_for(resource,now)
        order=current_instruction(plan,resource,now)
        if (order is None and plan is not None and resource in self.eos_failure_since
                and resource!=self.config.options["battery_resource"]):
            # Age can be relaxed during an outage; validity bounds and stops cannot.
            order=current_instruction({**plan,"generated_at":now.isoformat()},resource,now)
        return order

    def update_eos(self, now, clock):
        if clock - self.last_plan_fetch >= 15:
            self.last_plan_fetch = clock
            try:
                candidate = self.config.eos.plan()
            except Exception as error:
                self.apply_eos_plan(None, now, error)
            else:
                self.apply_eos_plan(candidate, now)
        if clock - self.last_forecast_fetch >= 60:
            self.last_forecast_fetch = clock
            try:
                solution = self.config.eos.solution()
            except Exception as error:
                self.apply_eos_forecast(None, now, error)
            else:
                self.apply_eos_forecast(solution, now)

    def apply_eos_plan(self, candidate, now, error=None):
        resources = self.eos_resources()
        try:
            if error is not None:
                raise error
            if (not isinstance(candidate, dict)
                    or instant(candidate.get("generated_at")) is None
                    or not isinstance(candidate.get("instructions"), list)):
                raise ValueError("EOS plan is not ready")
            candidate = deepcopy(candidate)
            accepted = False
            incomplete = False
            for resource in resources:
                previous = self.resource_plans.get(resource)
                newer = previous is None or instant(candidate["generated_at"]) >= instant(previous["generated_at"])
                if newer and current_instruction(candidate, resource, now) is not None:
                    self.resource_plans[resource] = candidate
                    self.eos_failure_since.pop(resource, None)
                    accepted = True
                else:
                    self.eos_failure_since.setdefault(resource, now)
                    incomplete = True
            if accepted:
                self.plan = candidate
            if incomplete:
                self.errors["eos"] = "PlanIncomplete"
            else:
                self.errors.pop("eos", None)
        except Exception as error:
            for resource in resources:
                self.eos_failure_since.setdefault(resource,now)
            self.errors["eos"] = type(error).__name__

    def apply_eos_forecast(self, solution, now, error=None):
        try:
            if error is not None:
                raise error
            self.forecast = forecast_rows(solution, now)
            self.errors.pop("forecast", None)
        except Exception as error:
            self.forecast = []
            self.errors["forecast"] = type(error).__name__

    def update_soc(self, states, box, now):
        if self.config.options.get("wallbox_type") == "none":
            return False
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
        if (goal != self.goal or self.goal_at is None) and clock - self.last_goal_attempt >= 30:
            self.last_goal_attempt = clock
            try:
                # No schedule means no optimizer-managed EV charging; local PV charging stays independent.
                target, deadline = goal or (0, None)
                self.config.eos.set_vehicle_goal(self.config.options["vehicle_resource"], target, deadline)
                self.goal, self.goal_at = goal, now
                self.errors.pop("goal", None)
            except Exception as error:
                self.errors["goal"] = type(error).__name__
        return goal is not None and goal == self.goal and self.goal_at is not None

    def tick(self, now, clock):
        self.control_step = "read_inputs"
        self.sync_battery_limits(now, clock)
        if not self.external_eos_polling:
            self.update_eos(now, clock)
        states = self.ha.states()
        captured=getattr(states,"captured_at",None)
        if captured is not None and isinstance(captured,datetime) and captured.utcoffset() is not None:
            now=max(now,captured)
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
        live["heat_load"] = heat_utilization(states,opts,now)
        live["weather"] = weather_display(states,opts,now)
        car_enabled = opts.get("wallbox_type") != "none"
        heat_enabled = bool(opts.get("heat_entity"))
        live["house"] = house_only(live["house_total"], live["car"] if car_enabled else 0,
                                   live["heat"] if heat_enabled else 0)
        live["battery"] = (battery.charge - battery.discharge
                           if battery.charge is not None and battery.discharge is not None else None)
        battery_ids=getattr(self.config.battery,"ids",{})
        wallbox_ids=getattr(self.config.wallbox,"ids",{})
        self.display=self.display_values.update(states,live,opts,
            battery_ids if isinstance(battery_ids,Mapping) else {},
            wallbox_ids if isinstance(wallbox_ids,Mapping) else {},now)
        times=report_times(states,opts,battery_ids if isinstance(battery_ids,Mapping) else {},
                           wallbox_ids if isinstance(wallbox_ids,Mapping) else {},now)
        self.flow_display=self.flow_alignment.update(live,times,now,car_enabled,heat_enabled,self.display,expected_car_w=self.commanded_car_w if self.armed else None,command_at=self.last_write)
        battery_order = self.order_for(opts["battery_resource"], now)
        car_order = self.order_for(opts["vehicle_resource"], now)
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
        if self.restore_pending:
            # HA integrations and EOS can become ready after this integration.
            # Keep the remembered switch on but issue no commands until ready.
            ready = (battery_order is not None and battery.soc is not None
                     and all(live[key] is not None for key in
                             ("solar", "grid", "battery_charge", "battery_discharge"))
                     and box.watts is not None and box.status not in {"", "unknown", "unavailable"}
                     and box.phases in (1, 3) and box.amps is not None and box.step and box.maximum)
            ids = getattr(self.config.battery, "ids", {})
            mode = ids.get("mode") if isinstance(ids, Mapping) else None
            if mode and states.get(mode, {}).get("state") in {None, "", "unknown", "unavailable"}:
                ready = False
            ids = getattr(self.config.wallbox, "ids", {})
            enable = ids.get("enable") if isinstance(ids, Mapping) else None
            if enable and states.get(enable, {}).get("state") not in {"on", "off"}:
                ready = False
            if not ready:
                return
            self.restore_pending = False
        self.owned = True
        published = (round(self.soc, 4) if self.soc is not None else None, measured)
        if published != self.last_soc_publish:
            self.ha.publish_soc(self.soc, measured)
            self.last_soc_publish = published
        synchronized = self.sync_goal(now, clock, departure) if car_enabled else False
        vehicle_plan=self.plan_for(opts["vehicle_resource"],now)
        generated = instant(vehicle_plan.get("generated_at")) if isinstance(vehicle_plan, dict) else None
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
        self.control_step = "wallbox_control"
        if car_enabled:
            self.regulate_car(box, live, planned, pv, now, clock, states)
        command = battery_command(battery_order, battery.soc,
                                  {**opts, "battery_min_soc": daily["battery_min_soc"],
                                   "battery_max_soc": daily["battery_max_soc"]},
                                  daily["battery_pv_support"] and box.charging and self.pv_session,
                                  live["grid"], battery.discharge, battery.charge)
        self.control_step = "battery_control"
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
            self.commanded_car_w = 0
            self.pv_session = False
            self.candidate = self.phase_target = None
            return
        grid, discharge = live["grid"], max(0, live["battery_discharge"])
        hard = min(11000, max(0, box.watts + opts["grid_limit_w"] - grid - discharge - 100))
        if self.last_write is not None and grid<=opts["grid_limit_w"]:
            meter=states.get(opts["grid_entity"],{})
            grid_report=instant(meter.get("last_reported") or meter.get("last_updated"))
            elapsed=(now-self.last_write).total_seconds()
            new_reports=(grid_report is not None and grid_report>self.last_write
                         and box.sample is not None and box.sample>self.last_write)
            # Only the closed-loop PV correction needs a post-command power sample.
            # EOS supplies an absolute target; unchanged wallbox readings must not
            # prevent a later scheduled increase or reduction from being applied.
            awaiting_feedback = pv and planned == 0 and not new_reports
            if elapsed<daily["regulation_interval_s"] or awaiting_feedback:
                if awaiting_feedback and elapsed>=opts.get("command_settle_s",60):
                    driver.pause(box)
                    self.commanded_car_w = 0
                    self.pv_session=False
                live["car_control"]="waiting_measurements"
                return

        solar_only = pv and planned == 0
        relative = solar_only and box.charging
        surplus = (pv_budget(max(0, live["solar"]), grid, box.watts if box.enabled else 0,
                             discharge, daily["reserve_w"], box.phases if relative else None,
                             box.amps if relative else None) if pv else 0)
        desired = min(hard, max(planned, surplus))
        nearest = pv and surplus > planned and box.charging and daily["reserve_w"] == 0 and box.step <= 0.1
        maximum = min(opts["max_current_a"], box.maximum)
        phase = box.phases
        if not getattr(getattr(driver,"features",None),"phase_switching",True):
            self.phase_target = None
        if daily["phase_auto"] and getattr(getattr(driver,"features",None),"phase_switching",True):
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
            self.commanded_car_w = 0
            self.pv_session = False
            self.phase_target = None
            return
        if phase != box.phases or self.phase_target is not None:
            self.phase_target = phase
            self.pv_session = False
            if not driver.phase(phase, box):
                return
            self.phase_target = None
        if not box.enabled or abs(box.amps - amps) >= 0.05:
            driver.charge(amps, box)
            self.commanded_car_w = amps*phase*230
            self.last_write = now
        self.pv_session = solar_only
        live["car_control"] = "pv_only" if solar_only else "eos_pv" if pv else "grid_charge"

    def snapshot(self, now):
        with self.lock:
            opts = self.config.options
            plan = self.plan_for(opts["battery_resource"],now)
            generated = instant(plan.get("generated_at")) if isinstance(plan, dict) else None
            current = bool(generated and self.order_for(opts["battery_resource"],now) is not None)
            plan_end = (instant(plan.get("valid_until")) or (instant(plan.get("valid_from")) or generated)
                        + timedelta(hours=24)) if current else None
            return {"power_reference":power_references(opts,self.live,getattr(self.config.wallbox,"features",None)),
                    "heat_load_configured":bool(opts.get("heat_load_entity")), "live": dict(self.live), "display": dict(self.display), "flow_display": dict(self.flow_display), "settings": dict(self.config.daily),
                    "battery_limits": {
                        "managed": getattr(self.config, "battery_limits_managed", False),
                        "confirmed": self.battery_limits_confirmed ==
                            (self.config.daily["battery_min_soc"], self.config.daily["battery_max_soc"]),
                        "confirmed_at": self.battery_limits_confirmed_at.isoformat()
                            if self.battery_limits_confirmed_at else None},
                    "control_waiting": self.armed and self.restore_pending,
                    "armed": self.armed, "release_pending": self.owned and not self.armed,
                    "eos_cache": {resource:{"remaining_s":max(0,300-(now-failed).total_seconds())} for resource,failed in self.eos_failure_since.items() if resource in self.resource_plans and (now-failed).total_seconds()<300 and self.order_for(resource,now) is not None},
                    "errors": dict(self.errors), "last_failure": self.last_failure, "zone": opts["timezone"],
                    "features": {"car": opts.get("wallbox_type") != "none", "heat": bool(opts.get("heat_entity"))},
                    "vehicle_name": opts.get("vehicle_name", "E-Auto").strip(),
                    "plugins": {"battery":describe(self.config.battery),"wallbox":describe(self.config.wallbox)},
                    "influx_configured": bool(self.config.influx.url),
                    "forecast": self.forecast if current else [], "pv_daily_forecast": daily_pv_forecast(self.forecast if current else [], now, opts["timezone"]), "plan_end": plan_end.isoformat() if plan_end else None,
                    "plan": {key: [{"time": item.when.isoformat(), "mode": item.mode, "factor": item.factor}
                                   for item in plan_series(self.plan_for(opts[resource],now), opts[resource])]
                             if self.order_for(opts[resource],now) is not None and (key != "car" or opts.get("wallbox_type") != "none") else [] for key, resource in (("battery", "battery_resource"),
                                                                        ("car", "vehicle_resource"))}}

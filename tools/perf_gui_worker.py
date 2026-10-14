"""Internal exploratory QA worker; importing this module never imports a GUI.

Run with python -B -m tools.perf_gui_worker and an existing isolated R_N run.
Timing schema 2 retains the startup build/update_idletasks endpoint, unverified.
Renders run in mainloop with a separate after_idle observation: duration_ns is
call only; layout_duration_ns is None and layout_wait_ns is return to completed
observation (loop wait, scheduling, getters/instrumentation, not exclusive layout
CPU). through_layout_ns includes that wait. Geometry/getters, validation and
scheduling are outside duration_ns. G-P/T-P render visibly after two stable
after(50) observations; H-F renders hidden/unverified, never comparable.
CTk geometry getter is logical; winfo dimensions are raw, not verified DPI.
ready.json precedes warmup; idle markers exclude diagnostics and teardown.
This tool neither starts a blocker nor establishes RNF01 or visual acceptance.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import math
import os
from pathlib import Path
import re
import sys
from time import perf_counter_ns
import traceback
from types import SimpleNamespace


@dataclass(frozen=True)
class Options:
    run_dir: Path
    rules: int
    profile: str
    warmup: float = 2.0
    idle: float = 5.0
    query: str = "none"

    def validate(self):
        if type(self.rules) is not int or self.rules not in (0, 100, 1000):
            raise ValueError("rules must be 0, 100 or 1000")
        if self.profile not in ("H-F", "G-P", "T-P"):
            raise ValueError("invalid profile")
        if self.query not in ("none", "single", "burst", "spaced") or (self.query != "none" and self.profile != "G-P"):
            raise ValueError("query sequences require G-P and a valid query mode")
        for name, minimum in (("warmup", 0), ("idle", 0)):
            value = getattr(self, name)
            if (isinstance(value, bool) or not isinstance(value, (int, float))
                    or not math.isfinite(value) or value < minimum
                    or (name == "idle" and value == 0)):
                raise ValueError(f"invalid finite duration: {name}")


def validate_run_dir(path, workspace):
    """Require run-<32 lowercase hex> below .qa, without linked paths."""
    workspace = Path(workspace).resolve()
    root = Path(path).absolute()
    qa = workspace / ".qa"
    if re.fullmatch(r"run-[0-9a-f]{32}", root.name) is None:
        raise ValueError("run directory must be run-<32 lowercase hex>")
    if not root.is_relative_to(qa) or root == qa:
        raise ValueError("run directory must be inside workspace .qa")
    for item in (root, *root.parents):
        if item == workspace:
            break
        if item.is_symlink() or item.is_junction():
            raise ValueError("linked run directory or ancestor")
    if not root.is_dir() or root.resolve() != root or not root.resolve().is_relative_to(qa.resolve()):
        raise ValueError("run directory is not an existing contained directory")
    fixture = root / "config.json"
    if fixture.is_symlink() or fixture.is_junction() or not fixture.is_file():
        raise ValueError("config.json must be an existing regular fixture")
    for name in ("ready.json", "report.json"):
        target = root / name
        if target.exists() or target.is_symlink() or target.is_junction():
            raise ValueError(f"refusing existing {name}")
    return root


class IdleController:
    """H-F reference: immutable idle presentation, no IO or worker."""
    def __init__(self, snapshot):
        self.value = snapshot

    def snapshot(self):
        return self.value

    def is_alive(self):
        return False

    def stop(self):
        pass


class ControllerGate:
    """Retain native stopped-controller costs in P profiles; forbid start."""
    def __init__(self, controller):
        self.controller = controller
        self.starts = 0

    def start(self):
        self.starts += 1
        raise RuntimeError("QA worker forbids motor start")

    def snapshot(self):
        return self.controller.snapshot()

    def is_alive(self):
        return self.controller.is_alive()

    def stop(self):
        return self.controller.stop()


class FakeTray:
    """H-F reference only, never used as fallback for G-P/T-P."""
    def start(self):
        raise RuntimeError("H-F must not start a tray")

    def stop(self):
        pass

    def is_alive(self):
        return False

    def wait(self, timeout=None):
        pass


def _native_dependencies():
    # Only the CLI calls this, after source freeze. Tests inject all interfaces.
    from tools.perf_artifacts import write_json, file_sha256
    import customtkinter as ctk
    import tkinter as tk
    from tkinter import filedialog, messagebox
    import psutil
    from importlib.metadata import version
    from core.config_session import ConfigSession
    from core.config_comparison import configs_equal
    from core.process_controller import ProcessController, RuntimeSnapshot
    from ui.config_gui import _build_app
    from ui.tray_commands import TrayMailbox
    from ui.windows_tray import WindowsTray

    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")

    def build(session, controller, tray, mailbox):
        return _build_app(ctk, tk, filedialog, messagebox, session,
                          controller=controller, tray=tray, mailbox=mailbox)

    return SimpleNamespace(
        session=ConfigSession, equal=configs_equal, build=build,
        controller=ProcessController, idle_snapshot=RuntimeSnapshot,
        mailbox=TrayMailbox, tray=WindowsTray, write_json=write_json,
        file_sha256=file_sha256,
        identity=lambda: {"pid": os.getpid(), "create_time": psutil.Process(os.getpid()).create_time()},
        versions=lambda: {"python": sys.version, "executable": sys.executable,
                          **{name: version(name) for name in
                             ("customtkinter", "psutil", "pystray", "Pillow")}},
    )


def _fixture_matches(config, rules):
    return (config.block_exes == tuple(f"qa-{i:04}.exe" for i in range(rules))
            and not config.windows and not config.block_folders
            and not config.safelist_exes and not config.block_cmdline and not config.extra)


class Worker:
    def __init__(self, options, dependencies, clock=perf_counter_ns):
        self.options, self.deps, self.clock = options, dependencies, clock
        self.app = self.session = self.controller = self.tray = self.mailbox = None
        self.errors, self.timings = [], {}
        self.idle_begin_ns = self.idle_end_ns = None
        self.before = self.after = self.geometry = None
        self.ready = False
        self.identity = {"pid": os.getpid(), "create_time": None}
        self.bgerror_installed = False
        self.bgerror_saved = None
        self.phase, self.callback_token = "startup", 0
        self.owned_callbacks = {}
        self.pending_timing = None
        self.render_anchor = None
        self.query_probe = None
        self.query_packets = []
        self.query_finished = False
        self.geometry_gate = dict(status="not_started", reason=None, observations=[],
                                  poll_ms=50, timeout_ns=10_000_000_000)

    def publish(self, name, value):
        if name != "report.json":
            self.require_clean()
        # Reject nonfinite values even if the injected writer is permissive.
        json.dumps(value, allow_nan=False)
        self.deps.write_json(self.options.run_dir / name, value)

    def require_clean(self):
        if self.errors:
            raise RuntimeError("QA worker aborted after previous error: " + self.errors[0])

    def fail(self, exc):
        if self.idle_begin_ns is not None and self.idle_end_ns is None:
            self.idle_end_ns = self.clock()
        self.errors.append(f"{type(exc).__name__}: {exc}")
        if self.query_probe is not None:
            self.query_probe.close()
        self.invalidate_pending(str(exc))
        if self.app is not None and not self.app.closed and not self.app.closing:
            try:
                self.app.close_editor()
            except Exception as close_error:
                self.errors.append(f"close after error: {type(close_error).__name__}: {close_error}")

    def invalidate_pending(self, reason):
        if self.pending_timing is not None:
            timing = self.timings[self.pending_timing]
            if timing["status"] != "invalid":
                failed = self.clock()
                timing.update(status="invalid", reason=reason, geometry_verified=False, comparable=False,
                              failed_ns=failed)
                if timing["start_ns"] is not None:
                    timing["partial_total_ns"] = failed - timing["start_ns"]
                if timing["return_ns"] is not None:
                    timing["partial_layout_wait_ns"] = failed - timing["return_ns"]
        if self.geometry_gate["status"] == "waiting":
            self.geometry_gate.update(status="invalid", reason=reason)

    def cancel_owned(self):
        self.callback_token += 1
        handles, self.owned_callbacks = self.owned_callbacks, {}
        if self.app is not None and not self.app.closed:
            for handle in handles:
                try:
                    self.app.after_cancel(handle)
                except Exception as exc:
                    self.errors.append(f"cancel QA callback: {type(exc).__name__}: {exc}")

    def transition(self, phase):
        self.cancel_owned()
        # Logical invalidation must happen even on failure. Closing still reaches
        # the app's original lifecycle; never recursively fail from cancel_owned.
        if phase != "closing":
            self.require_clean()
        self.phase = phase

    def schedule(self, operation, *, delay=0, idle=False, deadline_ns=None, timeout_reason=None):
        self.require_clean()
        phase, token = self.phase, self.callback_token
        handle = None

        def invoke():
            # Plain Python guards precede any getter/Tk and never erase a new owner.
            if (token != self.callback_token or phase != self.phase or handle not in self.owned_callbacks
                    or self.app is None
                    or self.app.closed or self.app.closing):
                return
            self.owned_callbacks.pop(handle, None)
            try:
                self.require_clean()
                operation()
            except Exception as exc:
                self.fail(exc)

        if deadline_ns is not None:
            remaining = deadline_ns - self.clock()
            if remaining <= 0:
                raise RuntimeError(timeout_reason)
            if not idle:
                delay = (remaining + 999_999) // 1_000_000  # positive ceil, no float conversion
        handle = self.app.after_idle(invoke) if idle else self.app.after(delay, invoke)
        self.owned_callbacks[handle] = phase
        self.require_clean()
        if deadline_ns is not None and self.clock() >= deadline_ns:
            raise RuntimeError(timeout_reason)
        return handle

    def watchdog(self, reason, *, deadline_ns=None):
        # Cooperative Tk deadline; cannot preempt a blocked synchronous operation.
        deadline = self.clock() + 10_000_000_000 if deadline_ns is None else deadline_ns
        def check():
            if self.clock() >= deadline:
                self.fail(RuntimeError(reason))
            else:
                self.watchdog(reason, deadline_ns=deadline)
        self.schedule(check, deadline_ns=deadline, timeout_reason=reason)

    def install_error_hooks(self):
        def callback_error(kind, exc, tb):
            if self.idle_begin_ns is not None and self.idle_end_ns is None:
                self.idle_end_ns = self.clock()
            self.fail(RuntimeError("Tk callback: " + "".join(traceback.format_exception(kind, exc, tb))))

        def bgerror(message):
            # End the measured phase before reading Tcl diagnostics.
            if self.idle_begin_ns is not None and self.idle_end_ns is None:
                self.idle_end_ns = self.clock()
            try:
                if self.app.closed or self.app.closing:
                    raise RuntimeError("window is closing or closed")
                detail = self.app.tk.call("set", "errorInfo")
            except Exception as exc:
                detail = f"errorInfo unavailable: {type(exc).__name__}: {exc}"
            self.fail(RuntimeError(f"Tk bgerror: {message}\n{detail}"))

        self.app.report_callback_exception = callback_error
        if self.app.tk.call("info", "commands", "bgerror"):
            self.bgerror_saved = f"::perf_worker_original_bgerror_{id(self)}"
            self.app.tk.call("rename", "bgerror", self.bgerror_saved)
        self.app.tk.createcommand("bgerror", bgerror)
        self.bgerror_installed = True
        original_close = self.app.close_editor

        def close():
            if self.query_probe is not None:
                self.query_probe.close()
            self.invalidate_pending("window closing before measurement completed")
            self.transition("closing")
            original_close()

        self.app.close_editor = close
        # The original WM callback was bound when the factory constructed the root.
        self.app.protocol("WM_DELETE_WINDOW", close)

    def restore_error_hooks(self):
        if self.bgerror_installed:
            self.app.tk.deletecommand("bgerror")
            self.bgerror_installed = False
        if self.bgerror_saved is not None:
            self.app.tk.call("rename", self.bgerror_saved, "bgerror")
            self.bgerror_saved = None

    def geometry_data(self, requested):
        observed = self.clock()
        getter = self.app.geometry()
        parsed = re.fullmatch(r"(\d+)x(\d+)(?:[+-]\d+[+-]\d+)?", getter)
        result = dict(requested_logical=requested, geometry=getter,
                    getter_units="ctk_logical",
                    logical_size=[int(parsed[1]), int(parsed[2])] if parsed else None,
                    client_width=self.app.winfo_width(), client_height=self.app.winfo_height(),
                    client_units="winfo_raw", state=self.app.state(), mapped=bool(self.app.winfo_ismapped()),
                    tk_scaling=float(self.app.tk.call("tk", "scaling")),
                    tk_version=self.app.tk.call("info", "patchlevel"),
                    windows_scale=None, monitor_dpi=None, layout_is_pixels=False,
                    observed_ns=observed)
        result["observation_end_ns"] = self.clock()
        return result

    def new_timing(self, name, phase, method):
        timing = dict(timing_schema_version=2, phase=phase, method=method,
                      status="partial", reason=None, geometry_verified=False, comparable=False,
                      start_ns=None, return_ns=None, layout_start_ns=None, layout_end_ns=None,
                      duration_ns=None, layout_duration_ns=None, layout_wait_ns=None,
                      instrumentation_duration_ns=None, through_layout_ns=None,
                      observation_deadline_ns=None,
                      geometry=None, geometry_before=None, geometry_after=None,
                      instrumentation="getters/validation/scheduling excluded from duration_ns; "
                                      "render layout_wait includes event-loop wait and observation instrumentation")
        self.timings[name] = timing
        self.pending_timing = name
        return timing

    def timed_build(self, operation):
        self.require_clean()
        timing = self.new_timing("build", "startup", "startup_observed")
        begin = self.clock()
        timing["start_ns"] = begin
        result = operation()
        returned = self.clock()
        timing.update(return_ns=returned, duration_ns=returned - begin)
        # Retain ownership even if build-layout fails.
        self.app = result
        self.install_error_hooks()
        layout_start = self.clock()
        self.app.update_idletasks()
        layout = self.clock()
        timing.update(layout_start_ns=layout_start, layout_end_ns=layout,
                      layout_duration_ns=layout - layout_start,
                      instrumentation_duration_ns=layout_start - returned,
                      through_layout_ns=layout - begin)
        if self.errors or self.app.closed or self.app.closing:
            raise RuntimeError("build ended with callback error or closed window")
        geometry = self.geometry_data("1000x740")
        timing.update(geometry=geometry, geometry_after=geometry)
        timing["status"] = "complete"
        self.pending_timing = None
        return result

    @staticmethod
    def geometry_signature(geometry):
        return (geometry["logical_size"], geometry["client_width"], geometry["client_height"],
                geometry["state"], geometry["mapped"])

    @staticmethod
    def mapped_geometry(geometry):
        return (geometry["logical_size"] == [880, 660] and geometry["state"] == "normal"
                and geometry["mapped"] and geometry["client_width"] > 0 and geometry["client_height"] > 0)

    def check_render_geometry(self, geometry):
        if self.options.profile == "H-F":
            valid = geometry["state"] == "withdrawn" and not geometry["mapped"]
        else:
            valid = self.mapped_geometry(geometry)
        if not valid or (self.render_anchor is not None and
                         self.geometry_signature(geometry) != self.geometry_signature(self.render_anchor)):
            raise RuntimeError("render geometry/state changed or unavailable")

    def prepare_renders(self):
        self.require_clean()
        if self.options.profile == "H-F":
            self.app.withdraw()
            self.geometry_gate.update(status="not_required", reason="hidden_unverified")
            self.queue_render("render_complete")
        else:
            self.transition("geometry_wait")
            self.geometry_gate.update(status="waiting", start_ns=self.clock())
            self.geometry_deadline_ns = self.clock() + 10_000_000_000
            self.previous_geometry = None
            self.watchdog("mapped geometry timeout")
            self.schedule(self.poll_geometry, delay=50)

    def poll_geometry(self):
        if self.clock() >= self.geometry_deadline_ns:
            raise RuntimeError("mapped geometry timeout")
        geometry = self.geometry_data("880x660")
        self.geometry_gate["observations"].append(geometry)
        if geometry["observation_end_ns"] >= self.geometry_deadline_ns:
            raise RuntimeError("mapped geometry timeout")
        if self.mapped_geometry(geometry):
            if (self.previous_geometry is not None and
                    self.geometry_signature(self.previous_geometry) == self.geometry_signature(geometry)
                    and geometry["observed_ns"] - self.previous_geometry["observed_ns"] >= 50_000_000):
                self.render_anchor = geometry
                self.geometry_gate.update(status="confirmed", confirmed_ns=self.clock())
                self.queue_render("render_complete")
                return
            self.previous_geometry = geometry
        else:
            self.previous_geometry = None
        self.schedule(self.poll_geometry, delay=50)

    def queue_render(self, name):
        self.transition(name + "_call")
        self.watchdog(name + " callback timeout")
        self.schedule(lambda: self.render_call(name), delay=50)

    def render_call(self, name):
        self.require_clean()
        hidden = self.options.profile == "H-F"
        timing = self.new_timing(name, "hidden" if hidden else "visible_before_tray",
                                 "hidden_unverified" if hidden else "mapped_stable_v1")
        before = self.geometry_data("880x660")
        timing["geometry_before"] = before
        self.check_render_geometry(before)
        if self.render_anchor is None:
            self.render_anchor = before
        self.require_clean()
        begin = self.clock()
        timing["start_ns"] = begin
        operation = self.app.render if name == "render_complete" else self.app.render_rules
        operation()
        returned = self.clock()
        timing.update(return_ns=returned, duration_ns=returned - begin)
        self.observation_deadline_ns = returned + 10_000_000_000
        timing["observation_deadline_ns"] = self.observation_deadline_ns
        if self.errors or self.app.closed or self.app.closing:
            raise RuntimeError("render call ended with callback error or closed window")
        # Revalidate at return as well: an idle continuation cannot rehabilitate it.
        at_return = self.geometry_data("880x660")
        timing["geometry_at_return"] = at_return
        self.check_render_geometry(at_return)
        reason = name + " after_idle observation timeout"
        if self.clock() >= self.observation_deadline_ns:
            raise RuntimeError(reason)
        self.transition(name + "_observation")
        timing["status"] = "awaiting_observation"
        self.watchdog(reason, deadline_ns=self.observation_deadline_ns)
        self.schedule(lambda: self.render_observed(name), idle=True,
                      deadline_ns=self.observation_deadline_ns, timeout_reason=reason)

    def render_observed(self, name):
        self.require_clean()
        timing = self.timings[name]
        # Timer order/cancellation cannot rehabilitate a late continuation.
        # This deadline starts at return, not call start: long calls are not
        # preempted or classified as starvation of their subsequent observation.
        if self.clock() >= self.observation_deadline_ns:
            raise RuntimeError(name + " after_idle observation timeout")
        after = self.geometry_data("880x660")
        timing.update(geometry_after=after, geometry=after,
                      layout_end_ns=after["observation_end_ns"],
                      layout_wait_ns=after["observation_end_ns"] - timing["return_ns"],
                      through_layout_ns=after["observation_end_ns"] - timing["start_ns"])
        if after["observation_end_ns"] >= self.observation_deadline_ns:
            raise RuntimeError(name + " after_idle observation timeout")
        self.check_render_geometry(after)
        timing.update(status="complete", geometry_verified=self.options.profile != "H-F",
                      comparable=self.options.profile != "H-F")
        self.pending_timing = None
        if name == "render_complete":
            self.queue_render("render_rules")
        else:
            self.start_profile()

    def start_profile(self):
        self.require_clean()
        self.transition("profile_wait")
        if self.options.profile == "H-F":
            self.schedule(self.profile_ready)
        else:
            self.tray_deadline_ns = self.clock() + 10_000_000_000
            if self.options.profile == "T-P":
                self.app.send_to_tray()
            else:
                self.tray.start()
            self.schedule(self.await_tray, delay=50)

    def check_profile_geometry(self, geometry):
        if self.options.profile == "H-F":
            valid = geometry["state"] == "withdrawn" and not geometry["mapped"]
        elif self.options.profile == "G-P":
            valid = self.mapped_geometry(geometry)
        else:
            valid = (geometry["state"] == "withdrawn" and not geometry["mapped"]
                     and geometry["logical_size"] == [880, 660])
        if self.options.profile != "H-F" and self.render_anchor is not None:
            valid = valid and all(geometry[key] == self.render_anchor[key] for key in
                                  ("logical_size", "client_width", "client_height"))
        if not valid:
            raise RuntimeError("profile geometry changed before ready/idle completion")

    def observe(self):
        app, session = self.app, self.session
        config = session.draft.config
        page = app.rule_page_result
        return {
            "fixture_sha256": self.deps.file_sha256(session.path),
            "dirty": session.dirty, "is_new": session.is_new,
            "can_undo": session.draft.can_undo, "can_redo": session.draft.can_redo,
            "fixture_matches": _fixture_matches(config, self.options.rules),
            "universe": len(app.rule_view_context[2]) if app.rule_view_context is not None else None,
            "rows": sum(field != "windows" for field, _ in app.review_rows),
            "page": page.page if page is not None else None,
            "page_count": page.page_count if page is not None else None,
            "query": app.rule_search.get(), "order": app.visual_rule_order,
            "selection_mode": app.rule_selection_mode,
            "selected": len(app.rule_selection_indices),
            "search_pending": app.rule_search_pending,
            "search_timer": app.rule_search_timer,
            "motor_starts": self.controller.starts,
            "motor_alive": self.controller.is_alive(),
            "motor_state": self.controller.snapshot().state,
            "tray_ready": app.tray_ready, "tray_alive": self.tray.is_alive(),
            "tray_hidden": app.tray_hidden, "window_state": app.state(),
        }

    def state_checks(self, state):
        rules = self.options.rules
        profile = self.options.profile
        return {
            "fixture": state["fixture_matches"],
            "clean_history": not any(state[k] for k in ("dirty", "is_new", "can_undo", "can_redo")),
            "universe": state["universe"] == rules,
            "projection": state["rows"] == min(25, rules) and state["page"] == 0
                          and state["page_count"] == max(1, (rules + 24) // 25),
            "view": state["query"] == "" and state["order"] == "registered"
                    and not state["selection_mode"] and state["selected"] == 0,
            "search": not state["search_pending"] and state["search_timer"] is None,
            "motor": state["motor_starts"] == 0 and not state["motor_alive"] and state["motor_state"] == "idle",
            "profile": ((not state["tray_alive"] and state["window_state"] == "withdrawn") if profile == "H-F"
                        else state["tray_ready"] and state["tray_alive"]
                        and state["tray_hidden"] == (profile == "T-P")
                        and state["window_state"] == ("withdrawn" if profile == "T-P" else "normal")),
        }

    def begin_idle(self):
        self.require_clean()
        # All diagnostics and IO precede the idle marker.
        self.before = self.observe()
        if not all(self.state_checks(self.before).values()):
            raise RuntimeError("invalid pre-idle invariants")
        self.before["geometry"] = self.geometry_data("880x660")
        self.check_profile_geometry(self.before["geometry"])
        self.transition("idle")
        self.schedule(self.end_idle, delay=math.ceil(self.options.idle * 1000))
        self.require_clean()
        self.idle_begin_ns = self.clock()

    def end_idle(self):
        self.idle_end_ns = self.clock()
        self.after = self.observe()
        self.after["geometry"] = self.geometry_data("880x660")
        self.check_profile_geometry(self.after["geometry"])
        self.app.close_editor()

    def profile_ready(self):
        self.require_clean()
        if self.options.query != "none" and not self.query_finished:
            self.begin_query_sequence(self.options.query)
            return
        state = self.observe()
        if not all(self.state_checks(state).values()):
            raise RuntimeError("invalid ready invariants")
        self.geometry = self.geometry_data("880x660")
        self.check_profile_geometry(self.geometry)
        self.transition("ready")
        self.publish("ready.json", dict(ok=True, profile=self.options.profile,
                     rules=self.options.rules, **self.identity, timings=self.timings,
                     timing_schema_version=2, geometry_gate=self.geometry_gate,
                     query_schema_version=1, query_mode=self.options.query,
                     geometry=self.geometry, ready_ns=self.clock()))
        self.ready = True
        self.transition("warmup")
        self.schedule(self.begin_idle, delay=math.ceil(self.options.warmup * 1000))

    def query_geometry_check(self):
        geometry = self.geometry_data("880x660")
        self.check_profile_geometry(geometry)
        return geometry

    def verify_query_data(self):
        state = self.observe()  # Outside every measured sequence/reset interval.
        checks = dict(bytes=state["fixture_sha256"] == self.initial_hash,
                      draft=self.session.draft is self.draft,
                      baseline=self.session.snapshot is self.baseline,
                      model=self.deps.equal(self.config, self.session.draft.config),
                      baseline_model=self.deps.equal(self.config, self.session.snapshot.config),
                      history_empty=not tuple(self.session.draft._undo) and not tuple(self.session.draft._redo),
                      clean=not any(state[key] for key in ("dirty", "is_new", "can_undo", "can_redo")),
                      zero_starts=self.controller.starts == 0 and not self.controller.is_alive())
        if not all(checks.values()):
            raise RuntimeError("query data invariants failed")
        return checks

    def begin_query_sequence(self, mode):
        from tools.perf_query_probe import QueryProbe
        self.transition("query_" + mode)
        self.verify_query_data()
        self.query_geometry_check()
        self.query_probe = QueryProbe(self.app, mode, self.options.rules, clock=self.clock,
                                     schedule=self.schedule, geometry_check=self.query_geometry_check,
                                     done=self.query_sequence_done)
        self.query_probe.start()

    def query_sequence_done(self, probe):
        from tools.perf_query import summarize_query
        packet = probe.packet()
        self.transition("query_audit")
        packet["summary"] = summarize_query(packet["writes"], packet["renders"], probe.mode, self.options.rules)
        self.query_packets.append(packet)
        if packet["summary"].get("ok") is not True:
            raise RuntimeError("query event summary is invalid")
        packet["data_checks"] = self.verify_query_data()
        if probe.mode != "reset":
            self.begin_query_sequence("reset")
        else:
            self.query_finished = True
            self.profile_ready()

    def await_tray(self):
        if self.app.closed or self.app.closing:
            raise RuntimeError("window closed before tray ready")
        if self.errors or self.app.tray_stopping:
            raise RuntimeError("real tray failed")
        if self.app.tray_ready and self.tray.is_alive():
            self.profile_ready()
        elif self.clock() >= self.tray_deadline_ns:
            raise RuntimeError("real tray ready timeout")
        else:
            self.schedule(self.await_tray, delay=50)

    def execute(self):
        try:
            identity = self.deps.identity()
            if (type(identity["pid"]) is not int or identity["pid"] <= 0
                    or isinstance(identity["create_time"], bool)
                    or not math.isfinite(identity["create_time"]) or identity["create_time"] <= 0):
                raise ValueError("invalid worker identity")
            self.identity = {"pid": identity["pid"], "create_time": identity["create_time"]}
            self.versions = self.deps.versions()
            self.session = self.deps.session(self.options.run_dir / "config.json")
            self.config = self.session.draft.config
            if not _fixture_matches(self.config, self.options.rules):
                raise ValueError("fixture is not the requested R_N")
            self.draft, self.baseline = self.session.draft, self.session.snapshot
            self.initial_hash = self.deps.file_sha256(self.session.path)
            native = (IdleController(self.deps.idle_snapshot()) if self.options.profile == "H-F"
                      else self.deps.controller(self.session.path))
            self.controller = ControllerGate(native)
            self.mailbox = self.deps.mailbox()
            self.tray = FakeTray() if self.options.profile == "H-F" else self.deps.tray(self.mailbox)
            self.timed_build(lambda: self.deps.build(self.session, self.controller, self.tray, self.mailbox))
            original_tray_error = self.app.tray_error

            def tray_error(detail):
                original_tray_error(detail)
                self.fail(RuntimeError(f"real tray: {detail}"))

            self.app.tray_error = tray_error
            self.app.geometry("880x660")
            self.app.tabs.set("Jogos / Apps")
            self.prepare_renders()
            self.app.mainloop()
        except Exception as exc:
            self.fail(exc)
        finally:
            if self.query_probe is not None:
                self.query_probe.close()
            self.cancel_owned()
            # Only outside mainloop may tray.wait block. Normal closure polls.
            for component in (self.controller, self.tray, self.mailbox):
                if component is not None:
                    try:
                        component.close() if component is self.mailbox else component.stop()
                    except Exception as exc:
                        self.errors.append(f"cleanup: {type(exc).__name__}: {exc}")
            if self.tray is not None:
                try:
                    self.tray.wait(timeout=5.0)
                except Exception as exc:
                    self.errors.append(f"tray wait: {type(exc).__name__}: {exc}")
            if self.app is not None:
                try:
                    self.app.finish_close()
                except Exception as exc:
                    self.errors.append(f"finish close: {type(exc).__name__}: {exc}")
                try:
                    self.restore_error_hooks()
                except Exception as exc:
                    self.errors.append(f"restore bgerror: {type(exc).__name__}: {exc}")
        return self.report()

    def report(self):
        checks = {}
        try:
            checks.update(self.state_checks(self.before) if self.before is not None else {"pre_idle": False})
            checks.update({"post_" + k: v for k, v in self.state_checks(self.after).items()}
                          if self.after is not None else {"post_idle": False})
            checks.update(
                draft_identity=self.session.draft is self.draft,
                baseline_identity=self.session.snapshot is self.baseline,
                typed_model=self.deps.equal(self.config, self.session.draft.config),
                baseline_model=self.deps.equal(self.config, self.session.snapshot.config),
                bytes=self.deps.file_sha256(self.session.path) == self.initial_hash,
                zero_starts=self.controller.starts == 0,
            )
        except Exception as exc:
            self.errors.append(f"invariants: {type(exc).__name__}: {exc}")
            checks["data_available"] = False
        after_info = None
        closed = bool(self.app is not None and self.app.closed)
        tray_alive = None
        try:
            tray_alive = self.tray.is_alive() if self.tray is not None else None
            if self.app is not None:
                after_info = list(self.app.tk.splitlist(self.app.tk.call("after", "info")))
        except Exception as exc:
            self.errors.append(f"after_info: {type(exc).__name__}: {exc}")
        checks["teardown"] = closed and tray_alive is False and after_info == []
        checks["idle_complete"] = (self.ready and self.before is not None and self.after is not None
                                   and self.idle_begin_ns is not None and self.idle_end_ns is not None
                                   and self.idle_end_ns > self.idle_begin_ns)
        checks["renders_complete"] = all(
            name in self.timings and self.timings[name]["status"] == "complete"
            for name in ("render_complete", "render_rules"))
        checks["geometry_gate"] = self.geometry_gate["status"] == (
            "not_required" if self.options.profile == "H-F" else "confirmed")
        checks["qa_callbacks_cancelled"] = not self.owned_callbacks
        if self.options.query != "none":
            checks["query_complete_and_reset"] = self.query_finished
        if not all(checks.values()) and not self.errors:
            self.errors.append("invariants failed: " + ", ".join(k for k, v in checks.items() if not v))
        if self.errors:
            for timing in self.timings.values():
                timing["comparable"] = False
                timing["run_invalid_reason"] = self.errors[0]
        result = dict(ok=not self.errors and all(checks.values()), profile=self.options.profile,
                      rules=self.options.rules, warmup_s=self.options.warmup, idle_s=self.options.idle,
                      **self.identity, idle_begin_ns=self.idle_begin_ns, idle_end_ns=self.idle_end_ns,
                      timings=self.timings, geometry=self.geometry, versions=getattr(self, "versions", {}),
                      timing_schema_version=2, geometry_gate=self.geometry_gate,
                      qa_callbacks_pending=len(self.owned_callbacks),
                      query=dict(query_schema_version=1, mode=self.options.query, complete=self.query_finished,
                                 packets=self.query_packets,
                                 partial=(self.query_probe.packet() if self.query_probe is not None
                                          and not self.query_probe.finished else None)),
                      invariants=dict(before=self.before, after=self.after, checks=checks),
                      errors=self.errors, closed=closed, tray_alive=tray_alive, after_info=after_info,
                      exploratory=True, acceptance=False)
        self.publish("report.json", result)
        return result


def run_worker(options, dependencies=None, *, workspace=None, clock=perf_counter_ns):
    options.validate()
    root = validate_run_dir(options.run_dir, workspace or Path(__file__).resolve().parents[1])
    options = Options(root, options.rules, options.profile, options.warmup, options.idle, options.query)
    deps = _native_dependencies() if dependencies is None else dependencies
    return Worker(options, deps, clock).execute()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--rules", required=True, type=int, choices=(0, 100, 1000))
    parser.add_argument("--profile", required=True, choices=("H-F", "G-P", "T-P"))
    parser.add_argument("--warmup", type=float, default=2.0)
    parser.add_argument("--idle", type=float, default=5.0)
    parser.add_argument("--query", choices=("none", "single", "burst", "spaced"), default="none")
    args = parser.parse_args(argv)
    try:
        report = run_worker(Options(**vars(args)))
    except Exception as exc:
        print(f"QA worker failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

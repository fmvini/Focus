"""Internal exploratory QA worker; importing this module never imports a GUI.

Run with python -B -m tools.perf_gui_worker and an existing isolated R_N run.
Timings contain start_ns, return_ns, layout_start_ns, layout_end_ns,
duration_ns (call only), layout_duration_ns, instrumentation_duration_ns
(hook setup between return and layout), and through_layout_ns (total).
Each timing records requested/reported geometry: build 1000x740, subsequent
renders 880x660. Layout is not presented pixels; Windows DPI is unknown.
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

    def validate(self):
        if type(self.rules) is not int or self.rules not in (0, 100, 1000):
            raise ValueError("rules must be 0, 100 or 1000")
        if self.profile not in ("H-F", "G-P", "T-P"):
            raise ValueError("invalid profile")
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

    def publish(self, name, value):
        # Reject nonfinite values even if the injected writer is permissive.
        json.dumps(value, allow_nan=False)
        self.deps.write_json(self.options.run_dir / name, value)

    def fail(self, exc):
        if self.idle_begin_ns is not None and self.idle_end_ns is None:
            self.idle_end_ns = self.clock()
        self.errors.append(f"{type(exc).__name__}: {exc}")
        if self.app is not None and not self.app.closed and not self.app.closing:
            self.app.close_editor()

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

    def restore_error_hooks(self):
        if self.bgerror_installed:
            self.app.tk.deletecommand("bgerror")
            self.bgerror_installed = False
        if self.bgerror_saved is not None:
            self.app.tk.call("rename", self.bgerror_saved, "bgerror")
            self.bgerror_saved = None

    def geometry_data(self, requested):
        return dict(requested_logical=requested, geometry=self.app.geometry(),
                    client_width=self.app.winfo_width(), client_height=self.app.winfo_height(),
                    tk_scaling=float(self.app.tk.call("tk", "scaling")),
                    tk_version=self.app.tk.call("info", "patchlevel"),
                    windows_scale=None, monitor_dpi=None, layout_is_pixels=False)

    def callback(self, operation):
        def invoke():
            try:
                operation()
            except Exception as exc:
                self.fail(exc)
        return invoke

    def timed(self, name, operation):
        begin = self.clock()
        result = operation()
        returned = self.clock()
        app = result if name == "build" else self.app
        # Retain ownership even if build-layout fails.
        if name == "build":
            self.app = app
            self.install_error_hooks()
        layout_start = self.clock()
        app.update_idletasks()
        layout = self.clock()
        self.timings[name] = dict(start_ns=begin, return_ns=returned,
                                 layout_start_ns=layout_start,
                                 layout_end_ns=layout, duration_ns=returned - begin,
                                 layout_duration_ns=layout - layout_start,
                                 instrumentation_duration_ns=layout_start - returned,
                                 through_layout_ns=layout - begin,
                                 geometry=self.geometry_data("1000x740" if name == "build" else "880x660"))
        return result

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
        # All diagnostics and IO precede the idle marker.
        self.before = self.observe()
        if not all(self.state_checks(self.before).values()):
            raise RuntimeError("invalid pre-idle invariants")
        self.app.after(math.ceil(self.options.idle * 1000), self.callback(self.end_idle))
        self.idle_begin_ns = self.clock()

    def end_idle(self):
        self.idle_end_ns = self.clock()
        self.after = self.observe()
        self.app.close_editor()

    def profile_ready(self):
        state = self.observe()
        if not all(self.state_checks(state).values()):
            raise RuntimeError("invalid ready invariants")
        self.geometry = self.geometry_data("880x660")
        self.publish("ready.json", dict(ok=True, profile=self.options.profile,
                     rules=self.options.rules, **self.identity, timings=self.timings,
                     geometry=self.geometry, ready_ns=self.clock()))
        self.ready = True
        self.app.after(math.ceil(self.options.warmup * 1000), self.callback(self.begin_idle))

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
            self.app.after(50, self.callback(self.await_tray))

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
            self.timed("build", lambda: self.deps.build(self.session, self.controller, self.tray, self.mailbox))
            original_tray_error = self.app.tray_error

            def tray_error(detail):
                original_tray_error(detail)
                self.fail(RuntimeError(f"real tray: {detail}"))

            self.app.tray_error = tray_error
            self.app.geometry("880x660")
            self.app.tabs.set("Jogos / Apps")
            self.app.update_idletasks()
            self.timed("render_complete", self.app.render)
            self.timed("render_rules", self.app.render_rules)
            if self.options.profile == "H-F":
                self.app.withdraw()
                self.app.after(0, self.callback(self.profile_ready))
            else:
                self.tray_deadline_ns = self.clock() + 10_000_000_000
                if self.options.profile == "T-P":
                    self.app.send_to_tray()
                else:
                    self.tray.start()
                self.app.after(50, self.callback(self.await_tray))
            self.app.mainloop()
        except Exception as exc:
            self.errors.append(f"{type(exc).__name__}: {exc}")
        finally:
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
        if not all(checks.values()) and not self.errors:
            self.errors.append("invariants failed: " + ", ".join(k for k, v in checks.items() if not v))
        result = dict(ok=not self.errors and all(checks.values()), profile=self.options.profile,
                      rules=self.options.rules, warmup_s=self.options.warmup, idle_s=self.options.idle,
                      **self.identity, idle_begin_ns=self.idle_begin_ns, idle_end_ns=self.idle_end_ns,
                      timings=self.timings, geometry=self.geometry, versions=getattr(self, "versions", {}),
                      invariants=dict(before=self.before, after=self.after, checks=checks),
                      errors=self.errors, closed=closed, tray_alive=tray_alive, after_info=after_info,
                      exploratory=True, acceptance=False)
        self.publish("report.json", result)
        return result


def run_worker(options, dependencies=None, *, workspace=None, clock=perf_counter_ns):
    options.validate()
    root = validate_run_dir(options.run_dir, workspace or Path(__file__).resolve().parents[1])
    options = Options(root, options.rules, options.profile, options.warmup, options.idle)
    deps = _native_dependencies() if dependencies is None else dependencies
    return Worker(options, deps, clock).execute()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, type=Path)
    parser.add_argument("--rules", required=True, type=int, choices=(0, 100, 1000))
    parser.add_argument("--profile", required=True, choices=("H-F", "G-P", "T-P"))
    parser.add_argument("--warmup", type=float, default=2.0)
    parser.add_argument("--idle", type=float, default=5.0)
    args = parser.parse_args(argv)
    try:
        report = run_worker(Options(**vars(args)))
    except Exception as exc:
        print(f"QA worker failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

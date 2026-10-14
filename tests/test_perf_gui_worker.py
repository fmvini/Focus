"""Worker orchestration using fake GUI/controller/tray/artifact interfaces only."""

from copy import deepcopy
import hashlib
import heapq
import importlib.util
import io
import json
from pathlib import Path
import sys
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from tools import perf_gui_worker as worker


class Clock:
    def __init__(self):
        self.now = 10_000_000_000

    def __call__(self):
        return self.now

    def advance(self, ns):
        self.now += ns


class Mailbox:
    def __init__(self):
        self.events = []

    def post(self, action, detail=None):
        self.events.append((action, detail))

    def close(self):
        self.events.clear()


class Controller:
    def __init__(self):
        self.starts = self.stops = 0

    def start(self):
        self.starts += 1
        raise AssertionError("native controller start must never be called")

    def snapshot(self):
        return SimpleNamespace(state="idle")

    def is_alive(self):
        return False

    def stop(self):
        self.stops += 1


class Tray:
    def __init__(self, mailbox, harness):
        self.mailbox, self.harness = mailbox, harness
        self.alive, self.starts = False, 0
        self.waited = False

    def start(self):
        self.starts += 1
        self.alive = True
        if self.harness.tray_mode == "ready":
            self.mailbox.post("ready")
        elif self.harness.tray_mode == "error":
            self.mailbox.post("error", "NIM_ADD rejected")

    def stop(self):
        self.alive = False

    def is_alive(self):
        return self.alive

    def wait(self, timeout=None):
        assert not self.harness.app.in_mainloop, "tray wait inside Tk"
        self.waited = True


class App:
    def __init__(self, harness, session, controller, tray, mailbox):
        self.harness, self.session = harness, session
        self.controller, self.tray, self.mailbox = controller, tray, mailbox
        self.closed = self.closing = self.in_mainloop = False
        self.tray_ready = self.tray_hidden = self.tray_pending = self.tray_stopping = False
        self.rule_selection_mode = self.rule_search_pending = False
        self.rule_selection_indices = set()
        self.rule_search_timer = None
        self.visual_rule_order = "registered"
        self.rule_search = SimpleNamespace(get=lambda: "")
        self.tabs = SimpleNamespace(set=lambda name: self.harness.events.append(("tab:" + name, self.harness.clock())))
        self.commands = {"bgerror": lambda message: None}
        self.tk = SimpleNamespace(call=self.tk_call, splitlist=lambda values: tuple(values),
                                  createcommand=lambda name, callback: self.commands.__setitem__(name, callback),
                                  deletecommand=lambda name: self.commands.pop(name))
        self.queue, self.timers, self.seq = [], {}, 0
        self.window_state, self.size = "normal", "1000x740"
        self.build_view()
        self.after(250, self.poll)
        self.harness.events.append(("build", self.harness.clock()))
        self.harness.clock.advance(13)

    def build_view(self):
        count = len(self.session.draft.config.block_exes)
        self.rule_view_context = (0, "block_exes", tuple(range(count)))
        self.rule_page_result = SimpleNamespace(page=0, page_count=max(1, (count + 24) // 25))
        self.review_rows = {("block_exes", i): object() for i in range(min(25, count))}

    def geometry(self, value=None):
        if value is not None:
            self.size = value
        return self.size

    def state(self):
        return self.window_state

    def winfo_width(self):
        return int(self.size.split("x")[0])

    def winfo_height(self):
        return int(self.size.split("x")[1])

    def tk_call(self, *args):
        if args == ("info", "commands", "bgerror"):
            return "bgerror" if "bgerror" in self.commands else ""
        if args[0] == "rename":
            self.commands[args[2]] = self.commands.pop(args[1])
            return ""
        if args == ("set", "errorInfo"):
            return "fake Tcl errorInfo with stack"
        if args == ("tk", "scaling"):
            return 1.333
        if args == ("info", "patchlevel"):
            return "fake-tk"
        if args == ("after", "info"):
            if self.harness.after_error:
                raise RuntimeError("interpreter unavailable")
            return tuple(self.timers)
        raise AssertionError(args)

    def update_idletasks(self):
        self.harness.events.append(("layout", self.harness.clock()))
        self.harness.clock.advance(7)

    def render(self):
        self.harness.events.append(("render_complete", self.harness.clock()))
        self.harness.clock.advance(11)
        self.build_view()

    def render_rules(self):
        self.harness.events.append(("render_rules", self.harness.clock()))
        self.harness.clock.advance(5)
        self.build_view()

    def withdraw(self):
        self.window_state = "withdrawn"

    def send_to_tray(self):
        self.harness.events.append(("send_to_tray", self.harness.clock()))
        self.tray_pending = True
        self.tray.start()

    def tray_error(self, detail):
        self.tray_stopping = True
        self.tray.stop()
        self.window_state = "normal"

    def after(self, delay, callback):
        self.seq += 1
        token = str(self.seq)
        self.timers[token] = callback
        heapq.heappush(self.queue, (self.harness.clock() + delay * 1_000_000, self.seq, token))
        return token

    def poll(self):
        events, self.mailbox.events = self.mailbox.events, []
        for action, detail in events:
            if action == "ready":
                self.tray_ready = True
                if self.tray_pending:
                    self.withdraw()
                    self.tray_hidden = True
                    self.tray_pending = False
            elif action == "error":
                self.tray_error(detail)
        self.harness.polls += 1
        if not self.closed:
            self.after(250, self.poll)

    def mainloop(self):
        self.in_mainloop = True
        try:
            for _ in range(1000):
                if self.closed or not self.queue:
                    return
                when, _, token = heapq.heappop(self.queue)
                callback = self.timers.pop(token, None)
                if callback is not None:
                    self.harness.clock.now = max(when, self.harness.clock())
                    callback()
            raise AssertionError("fake event loop did not terminate")
        finally:
            self.in_mainloop = False

    def close_editor(self):
        self.harness.events.append(("close", self.harness.clock()))
        self.closing = True
        self.controller.stop()
        self.tray.stop()
        self.mailbox.close()
        self.poll_close()

    def poll_close(self):
        self.finish_close()
        if not self.closed:
            self.after(100, self.poll_close)

    def finish_close(self):
        if self.tray.is_alive():
            return
        self.closed = True
        self.timers.clear()


class Harness:
    def __init__(self, root, rules):
        self.root, self.rules = root, rules
        self.clock, self.events = Clock(), []
        self.polls, self.tray_mode, self.after_error = 0, "ready", False
        self.native_controller = Controller()
        self.app = self.tray_instance = None
        data = dict(windows=[], block_exes=[f"qa-{i:04}.exe" for i in range(rules)])
        (root / "config.json").write_text(json.dumps(data), encoding="utf-8")
        config = SimpleNamespace(windows=(), block_exes=tuple(data["block_exes"]),
                                 block_folders=(), safelist_exes=(), block_cmdline=(), extra={})
        self.session = SimpleNamespace(path=root / "config.json", dirty=False, is_new=False,
                                       draft=SimpleNamespace(config=config, can_undo=False, can_redo=False),
                                       snapshot=SimpleNamespace(config=deepcopy(config)))
        self.deps = SimpleNamespace(
            session=lambda path: self.session, build=self.build,
            controller=lambda path: self.native_controller,
            idle_snapshot=lambda: SimpleNamespace(state="idle"),
            mailbox=Mailbox, tray=self.make_tray, write_json=self.write_json,
            file_sha256=self.file_hash, equal=lambda left, right: left == right,
            identity=lambda: dict(pid=1234, create_time=123.5), versions=lambda: {"all": "fake"})

    def build(self, session, controller, tray, mailbox):
        self.app = App(self, session, controller, tray, mailbox)
        return self.app

    def make_tray(self, mailbox):
        self.tray_instance = Tray(mailbox, self)
        return self.tray_instance

    def file_hash(self, path):
        self.events.append(("hash", self.clock()))
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    def write_json(self, path, data):
        self.events.append((Path(path).name, self.clock()))
        with Path(path).open("x", encoding="utf-8") as stream:
            json.dump(data, stream, allow_nan=False)


class PerfGuiWorkerTests(unittest.TestCase):
    def setUp(self):
        qa = (Path(__file__).resolve().parents[1] / ".qa").resolve()
        self.workspace = qa / ("perf-worker-fake-" + uuid4().hex)
        self.workspace.mkdir()
        def cleanup():
            resolved = self.workspace.resolve()
            if resolved.parent != qa or self.workspace.is_symlink() or self.workspace.is_junction():
                raise ValueError("refusing cleanup outside dedicated test fixture")
            shutil.rmtree(resolved)
        self.addCleanup(cleanup)

    def new_run(self, rules=100):
        root = self.workspace / ".qa" / "performance" / ("run-" + uuid4().hex)
        root.mkdir(parents=True)
        return Harness(root, rules)

    def run_fake(self, harness, profile="H-F", warmup=0.5, idle=1.0):
        return worker.run_worker(worker.Options(harness.root, harness.rules, profile, warmup, idle),
                                 harness.deps, workspace=self.workspace, clock=harness.clock)

    def test_all_profiles_counts_layout_endpoints_ready_before_warmup_idle_and_no_start(self):
        for rules in (0, 100, 1000):
            for profile in ("H-F", "G-P", "T-P"):
                with self.subTest(rules=rules, profile=profile):
                    h = self.new_run(rules)
                    original = (h.root / "config.json").read_bytes()
                    with patch.object(worker, "_native_dependencies", side_effect=AssertionError("native import")):
                        report = self.run_fake(h, profile)
                    self.assertTrue(report["ok"], report["errors"])
                    self.assertTrue(all(report["invariants"]["checks"].values()))
                    self.assertEqual(report["idle_end_ns"] - report["idle_begin_ns"], 1_000_000_000)
                    ready = json.loads((h.root / "ready.json").read_text())
                    self.assertEqual((ready["pid"], ready["create_time"]), (1234, 123.5))
                    self.assertEqual(report["idle_begin_ns"] - ready["ready_ns"], 500_000_000)
                    self.assertEqual(list(report["timings"]), ["build", "render_complete", "render_rules"])
                    for name, duration in (("build", 13), ("render_complete", 11), ("render_rules", 5)):
                        timing = report["timings"][name]
                        self.assertEqual(timing["duration_ns"], duration)
                        self.assertEqual(timing["layout_duration_ns"], 7)
                        self.assertEqual(timing["through_layout_ns"], duration + 7)
                        expected_size = "1000x740" if name == "build" else "880x660"
                        self.assertEqual(timing["geometry"]["requested_logical"], expected_size)
                        self.assertEqual(timing["geometry"]["geometry"], expected_size)
                    self.assertGreater(h.polls, 0)
                    self.assertEqual(h.native_controller.starts, 0)
                    self.assertEqual(report["after_info"], [])
                    self.assertTrue(report["closed"])
                    self.assertFalse(report["tray_alive"])
                    self.assertFalse(report["acceptance"])
                    self.assertIsNone(report["geometry"]["windows_scale"])
                    self.assertEqual((h.root / "config.json").read_bytes(), original)
                    if profile == "H-F":
                        self.assertIsNone(h.tray_instance)
                    else:
                        self.assertTrue(h.tray_instance.waited)
                        self.assertEqual(h.tray_instance.starts, 1)
                    sends = [event for event in h.events if event[0] == "send_to_tray"]
                    self.assertEqual(len(sends), int(profile == "T-P"))
                    idle_events = [name for name, timestamp in h.events
                                   if report["idle_begin_ns"] < timestamp < report["idle_end_ns"]]
                    self.assertEqual(idle_events, [])

    def test_real_tray_failure_and_timeout_invalidate_without_fake_fallback(self):
        for profile in ("G-P", "T-P"):
            for mode in ("error", "timeout"):
                with self.subTest(profile=profile, mode=mode):
                    h = self.new_run()
                    h.tray_mode = mode
                    report = self.run_fake(h, profile)
                    self.assertFalse(report["ok"])
                    self.assertIsNone(report["idle_begin_ns"])
                    self.assertFalse((h.root / "ready.json").exists())
                    self.assertTrue(any("tray" in error for error in report["errors"]))
                    self.assertTrue(h.tray_instance.waited)
                    self.assertTrue(report["closed"])
                    self.assertFalse(report["tray_alive"])

    def test_callback_errors_and_attempted_start_abort_idle_without_delegation(self):
        for action in ("tk_error", "bgerror", "start", "tray_error"):
            with self.subTest(action=action):
                h = self.new_run()
                original_build = h.deps.build
                def build(*args):
                    app = original_build(*args)
                    def fail():
                        if action == "tk_error":
                            app.report_callback_exception(RuntimeError, RuntimeError("Tk background"), None)
                        elif action == "bgerror":
                            app.commands["bgerror"]("Tcl native background failure")
                        elif action == "tray_error":
                            app.tray_error("lost icon")
                        else:
                            try:
                                app.controller.start()
                            except Exception as exc:
                                app.report_callback_exception(type(exc), exc, None)
                    app.after(750, fail)
                    return app
                h.deps.build = build
                report = self.run_fake(h)
                self.assertFalse(report["ok"])
                self.assertTrue(report["errors"])
                self.assertIsNotNone(report["idle_end_ns"])
                self.assertFalse(report["invariants"]["checks"]["idle_complete"])
                self.assertEqual(h.native_controller.starts, 0)
                self.assertTrue(report["closed"])
                self.assertEqual(list(h.app.commands), ["bgerror"])
                if action == "bgerror":
                    self.assertTrue(any("errorInfo with stack" in error for error in report["errors"]))

    def test_changed_bytes_model_owner_and_lost_profile_fail_final_checks(self):
        for action in ("bytes", "model", "owner", "window"):
            with self.subTest(action=action):
                h = self.new_run()
                original_build = h.deps.build
                def build(*args):
                    app = original_build(*args)
                    def change():
                        if action == "bytes":
                            (h.root / "config.json").write_bytes(b"external fixture edit")
                        elif action == "model":
                            h.session.draft.config.extra["typed"] = True
                        elif action == "owner":
                            h.session.draft = deepcopy(h.session.draft)
                        else:
                            app.window_state = "normal"
                    app.after(750, change)
                    return app
                h.deps.build = build
                report = self.run_fake(h)
                self.assertFalse(report["ok"])
                checks = report["invariants"]["checks"]
                self.assertFalse(checks[{"bytes": "bytes", "model": "baseline_model",
                                         "owner": "draft_identity", "window": "post_profile"}[action]])

    def test_unavailable_after_info_is_not_empty_success(self):
        h = self.new_run()
        h.after_error = True
        report = self.run_fake(h)
        self.assertFalse(report["ok"])
        self.assertIsNone(report["after_info"])
        self.assertFalse(report["invariants"]["checks"]["teardown"])

    def test_delayed_tray_stop_is_polled_without_wait_in_mainloop_and_warmup_zero(self):
        h = self.new_run()
        original_make = h.deps.tray
        def make(mailbox):
            tray = original_make(mailbox)
            pending = False
            def stop():
                nonlocal pending
                if tray.alive and not pending:
                    pending = True
                    self.assertTrue(h.app.in_mainloop)
                    h.app.after(50, lambda: setattr(tray, "alive", False))
            tray.stop = stop
            return tray
        h.deps.tray = make
        report = self.run_fake(h, "T-P", warmup=0)
        self.assertTrue(report["ok"], report["errors"])
        self.assertTrue(h.tray_instance.waited)
        self.assertEqual(report["after_info"], [])
        ready = json.loads((h.root / "ready.json").read_text())
        self.assertEqual(report["idle_begin_ns"], ready["ready_ns"])
        self.assertGreater(h.clock(), report["idle_end_ns"])

    def test_invalid_fixture_identity_and_build_failure_preserve_invalid_report(self):
        for action in ("fixture", "identity", "build"):
            with self.subTest(action=action):
                h = self.new_run()
                if action == "fixture":
                    h.session.draft.config.windows = (object(),)
                elif action == "identity":
                    h.deps.identity = lambda: dict(pid=1234, create_time=float("nan"))
                else:
                    h.deps.build = Mock(side_effect=RuntimeError("build failed"))
                report = self.run_fake(h)
                self.assertFalse(report["ok"])
                self.assertTrue(report["errors"])
                self.assertFalse((h.root / "ready.json").exists())
                json.dumps(report, allow_nan=False)

    def test_paths_existing_artifacts_and_nonfinite_options_rejected_before_imports(self):
        h = self.new_run()
        loader = Mock(side_effect=AssertionError("native loading forbidden"))
        with patch.object(worker, "_native_dependencies", loader):
            for name in ("warmup", "idle"):
                for value in (float("nan"), float("inf"), -1, True):
                    options = dict(run_dir=h.root, rules=100, profile="H-F", warmup=0, idle=1)
                    options[name] = value
                    with self.assertRaises(ValueError):
                        worker.run_worker(worker.Options(**options), workspace=self.workspace)
            for root in (self.workspace, self.workspace / "run-" / uuid4().hex):
                with self.assertRaises(ValueError):
                    worker.run_worker(worker.Options(root, 100, "H-F"), workspace=self.workspace)
            for name in ("ready.json", "report.json"):
                target = h.root / name
                target.write_bytes(b"preserve")
                with self.assertRaises(ValueError):
                    worker.run_worker(worker.Options(h.root, 100, "H-F"), workspace=self.workspace)
                self.assertEqual(target.read_bytes(), b"preserve")
                target.unlink()
            loader.assert_not_called()

    def test_linked_fixture_and_ancestor_rejected_without_platform_symlink_privileges(self):
        h = self.new_run()
        original = Path.is_symlink
        for linked in (h.root / "config.json", h.root, h.root.parent, self.workspace / ".qa"):
            with self.subTest(linked=linked), patch.object(Path, "is_symlink", lambda p: p == linked or original(p)):
                with self.assertRaises(ValueError):
                    worker.validate_run_dir(h.root, self.workspace)

    def test_run_name_requires_exact_lowercase_hex_before_native_or_injected_dependencies(self):
        h = self.new_run()
        self.assertEqual(worker.validate_run_dir(h.root, self.workspace), h.root)
        for name in ("run-" + str(uuid4()), "run-" + uuid4().hex.upper(),
                     "run-aBcDeF0123456789abcdef0123456789", "run-" + "a" * 31,
                     "run-" + "a" * 33, "run-" + "g" * 32):
            with self.subTest(name=name):
                root = h.root.parent / name
                root.mkdir()
                (root / "config.json").write_text('{"windows": []}', encoding="utf-8")
                options = worker.Options(root, 0, "H-F")
                with patch.object(worker, "_native_dependencies", side_effect=AssertionError("native loader")) as loader, \
                        patch.object(h.deps, "session", side_effect=AssertionError("session loader")) as session:
                    for deps in (None, h.deps):
                        with self.assertRaisesRegex(ValueError, "32 lowercase hex"):
                            worker.run_worker(options, deps, workspace=self.workspace)
                    loader.assert_not_called()
                    session.assert_not_called()
                self.assertFalse((root / "ready.json").exists())
                self.assertFalse((root / "report.json").exists())

    def test_lazy_module_import_and_cli_do_not_import_gui_or_artifacts(self):
        forbidden = ("customtkinter", "tkinter", "ui.config_gui", "ui.windows_tray", "tools.perf_artifacts")
        import builtins
        original_import = builtins.__import__
        def guarded(name, *args, **kwargs):
            if any(name == item or name.startswith(item + ".") for item in forbidden):
                raise AssertionError("forbidden import: " + name)
            return original_import(name, *args, **kwargs)
        spec = importlib.util.spec_from_file_location("isolated_perf_worker", worker.__file__)
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {spec.name: module}), patch.object(builtins, "__import__", guarded):
            spec.loader.exec_module(module)
            with patch.object(module, "run_worker", return_value={"ok": True}) as run:
                self.assertEqual(module.main(["--run-dir", "fake", "--rules", "100", "--profile", "H-F",
                                              "--warmup", "0", "--idle", "1"]), 0)
                self.assertEqual(run.call_args.args[0].warmup, 0)
            with patch.object(module, "run_worker", side_effect=ValueError("refused")), \
                    patch("sys.stderr", new=io.StringIO()) as stderr:
                self.assertEqual(module.main(["--run-dir", "fake", "--rules", "0", "--profile", "G-P"]), 1)
                self.assertIn("refused", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()

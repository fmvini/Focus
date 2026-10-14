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
        self.idle_queue = []
        self.window_state, self.requested_size, self.size = "normal", "1000x740", "200x200"
        self.raw_width, self.raw_height, self.mapped = 200, 200, False
        self.protocols = {}
        self.build_view()
        self.after(250, self.poll)
        self.after(75, self.map_when_requested)
        self.harness.events.append(("build", self.harness.clock()))
        self.harness.clock.advance(13)

    def build_view(self):
        count = len(self.session.draft.config.block_exes)
        self.rule_view_context = (0, "block_exes", tuple(range(count)))
        self.rule_page_result = SimpleNamespace(page=0, page_count=max(1, (count + 24) // 25))
        self.review_rows = {("block_exes", i): object() for i in range(min(25, count))}

    def geometry(self, value=None):
        if value is not None:
            self.requested_size = value
        elif self.harness.geometry_hook is not None:
            self.harness.geometry_hook(self)
        return self.size

    def map_when_requested(self):
        if self.window_state != "normal" or self.harness.map_mode == "never":
            return
        self.harness.maps += 1
        self.mapped = True
        self.size = self.harness.mapped_getter
        self.raw_width, self.raw_height = self.harness.mapped_raw
        if self.harness.map_mode == "iconic":
            self.window_state = "iconic"

    def winfo_ismapped(self):
        return self.mapped and self.window_state == "normal"

    def protocol(self, name, callback):
        self.protocols[name] = callback

    def state(self):
        return self.window_state

    def winfo_width(self):
        return self.raw_width

    def winfo_height(self):
        return self.raw_height

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
        assert not self.in_mainloop, "update_idletasks must be startup build only"
        self.harness.events.append(("layout", self.harness.clock()))
        self.harness.clock.advance(7)

    def update(self):
        raise AssertionError("reentrant update forbidden")

    def render(self):
        assert self.in_mainloop, "render outside mainloop"
        self.harness.render_turns.append(("render_complete", self.harness.turn, self.window_state))
        self.harness.events.append(("render_complete", self.harness.clock()))
        self.harness.clock.advance(11)
        self.build_view()
        if self.harness.render_hook is not None:
            self.harness.render_hook("render_complete", self)

    def render_rules(self):
        assert self.in_mainloop, "render outside mainloop"
        self.harness.render_turns.append(("render_rules", self.harness.turn, self.window_state))
        self.harness.events.append(("render_rules", self.harness.clock()))
        self.harness.clock.advance(5)
        self.build_view()
        if self.harness.render_hook is not None:
            self.harness.render_hook("render_rules", self)

    def withdraw(self):
        self.window_state = "withdrawn"
        self.mapped = False

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
        self.harness.scheduled.append(("after", delay, callback))
        heapq.heappush(self.queue, (self.harness.clock() + delay * 1_000_000, self.seq, token))
        return token

    def after_idle(self, callback):
        self.seq += 1
        token = str(self.seq)
        self.timers[token] = callback
        self.harness.scheduled.append(("after_idle", None, callback))
        self.idle_queue.append(token)
        return token

    def after_cancel(self, token):
        self.timers.pop(token, None)

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
        assert not self.in_mainloop, "reentrant mainloop forbidden"
        self.in_mainloop = True
        try:
            for _ in range(1000):
                if self.closed:
                    return
                if (self.idle_queue and not self.harness.starve_idle
                        and (not self.queue or self.queue[0][0] > self.harness.clock())):
                    token = self.idle_queue.pop(0)
                    self.harness.clock.advance(self.harness.idle_delay_ns)
                elif self.queue:
                    when, _, token = heapq.heappop(self.queue)
                    self.harness.clock.now = max(when, self.harness.clock())
                else:
                    return
                callback = self.timers.pop(token, None)
                if callback is not None:
                    self.harness.turn += 1
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
        self.scheduled, self.render_turns = [], []
        self.turn, self.maps = 0, 0
        self.map_mode, self.mapped_getter, self.mapped_raw = "ready", "880x660+10-20", (1100, 825)
        self.geometry_hook = self.render_hook = None
        self.starve_idle, self.idle_delay_ns = False, 17
        self.ready_hook = None
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
        if Path(path).name == "ready.json" and self.ready_hook is not None:
            self.ready_hook()


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
        original_worker = worker.Worker
        def capture(*args, **kwargs):
            harness.worker = original_worker(*args, **kwargs)
            return harness.worker
        with patch.object(worker, "Worker", side_effect=capture), \
                patch("time.sleep", side_effect=AssertionError("sleep forbidden")):
            return worker.run_worker(worker.Options(harness.root, harness.rules, profile, warmup, idle),
                                     harness.deps, workspace=self.workspace, clock=harness.clock)

    def test_geometry_gate_resets_unstable_polls_and_accepts_scaled_raw_dimensions(self):
        h = self.new_run()
        sizes = [(1100, 825), (1200, 900), (1100, 825), (1100, 825)]
        def geometry(app):
            if app.in_mainloop and app.mapped and h.worker.phase == "geometry_wait" and sizes:
                app.raw_width, app.raw_height = sizes.pop(0)
        h.geometry_hook = geometry
        report = self.run_fake(h, "G-P")
        self.assertTrue(report["ok"], report["errors"])
        observations = report["geometry_gate"]["observations"]
        self.assertEqual([(g["client_width"], g["client_height"]) for g in observations[-4:]],
                         [(1100, 825), (1200, 900), (1100, 825), (1100, 825)])
        self.assertGreaterEqual(observations[-1]["observed_ns"] - observations[-2]["observed_ns"], 50_000_000)
        self.assertLess(observations[-1]["observation_end_ns"], report["timings"]["render_complete"]["start_ns"])

    def test_geometry_unavailable_unmapped_bad_logical_or_nonpositive_raw_cannot_render(self):
        for mode in ("never", "iconic", "bad_getter", "wrong_logical", "zero", "getter_error", "unstable"):
            with self.subTest(mode=mode):
                h = self.new_run()
                if mode in ("never", "iconic"):
                    h.map_mode = mode
                elif mode == "bad_getter":
                    h.mapped_getter = "unavailable"
                elif mode == "wrong_logical":
                    h.mapped_getter = "881x660+10-20"
                elif mode == "zero":
                    h.mapped_raw = (0, 825)
                elif mode == "getter_error":
                    def fail_getter(app):
                        if app.in_mainloop:
                            raise RuntimeError("geometry getter unavailable")
                    h.geometry_hook = fail_getter
                else:
                    def unstable(app):
                        if app.in_mainloop and app.mapped and h.worker.phase == "geometry_wait":
                            app.raw_width = 1200 if app.raw_width == 1100 else 1100
                    h.geometry_hook = unstable
                report = self.run_fake(h, "G-P")
                self.assertFalse(report["ok"])
                self.assertEqual(report["geometry_gate"]["status"], "invalid")
                self.assertTrue(report["geometry_gate"]["reason"])
                self.assertEqual(h.render_turns, [])
                self.assertFalse((h.root / "ready.json").exists())
                self.assertIsNone(report["idle_begin_ns"])
                self.assertEqual(h.tray_instance.starts, 0)
                self.assertTrue(report["closed"])
                self.assertEqual(report["after_info"], [])

    def test_gate_observation_cannot_cross_its_deadline_and_cancel_the_watchdog(self):
        h = self.new_run()
        mapped_reads = 0
        def geometry(app):
            nonlocal mapped_reads
            if app.in_mainloop and app.mapped and h.worker.phase == "geometry_wait":
                mapped_reads += 1
                if mapped_reads == 2:
                    h.clock.advance(10_000_000_000)
        h.geometry_hook = geometry
        report = self.run_fake(h, "G-P")
        self.assertFalse(report["ok"])
        self.assertEqual(report["geometry_gate"]["status"], "invalid")
        self.assertIn("mapped geometry timeout", report["geometry_gate"]["reason"])
        self.assertEqual(h.render_turns, [])
        self.assertFalse((h.root / "ready.json").exists())

    def test_changes_before_during_after_and_between_renders_keep_invalid_partial_timings(self):
        for moment in ("before", "during", "after", "between"):
            for change in ("resize", "unmap"):
                with self.subTest(moment=moment, change=change):
                    h = self.new_run()
                    changed = False
                    def mutate(app):
                        nonlocal changed
                        if not changed:
                            changed = True
                            if change == "resize":
                                app.raw_width += 1
                            else:
                                app.mapped = False
                    def geometry(app):
                        phase = h.worker.phase
                        expected = {"before": "render_complete_call", "after": "render_complete_observation",
                                    "between": "render_rules_call"}.get(moment)
                        if phase == expected:
                            mutate(app)
                    def render(name, app):
                        if moment == "during" and name == "render_complete":
                            mutate(app)
                    h.geometry_hook, h.render_hook = geometry, render
                    report = self.run_fake(h, "G-P")
                    self.assertFalse(report["ok"])
                    self.assertFalse((h.root / "ready.json").exists())
                    self.assertIsNone(report["idle_begin_ns"])
                    name = "render_rules" if moment == "between" else "render_complete"
                    timing = report["timings"][name]
                    self.assertEqual(timing["status"], "invalid")
                    self.assertTrue(timing["reason"])
                    self.assertFalse(timing["geometry_verified"])
                    self.assertFalse(timing["comparable"])
                    self.assertEqual(len(h.render_turns), 0 if moment == "before" else 1)
                    if moment in ("before", "between"):
                        self.assertIsNone(timing["start_ns"])
                    else:
                        self.assertEqual(timing["duration_ns"], 11)
                        self.assertIsNotNone(timing["return_ns"])
                    if moment == "after":
                        self.assertIsNotNone(timing["geometry_after"])
                        self.assertEqual(timing["layout_wait_ns"], h.idle_delay_ns)
                    if moment == "between":
                        self.assertEqual(report["timings"]["render_complete"]["status"], "complete")
                        self.assertFalse(report["timings"]["render_complete"]["comparable"])
                    self.assertEqual(h.tray_instance.starts, 0)

    def test_after_idle_starvation_is_bounded_by_positive_owned_watchdog(self):
        for profile in ("H-F", "G-P", "T-P"):
            with self.subTest(profile=profile):
                h = self.new_run()
                h.starve_idle = True
                report = self.run_fake(h, profile)
                self.assertFalse(report["ok"])
                timing = report["timings"]["render_complete"]
                self.assertEqual(timing["status"], "invalid")
                self.assertIn("after_idle observation timeout", timing["reason"])
                self.assertEqual(timing["duration_ns"], 11)
                self.assertIsNone(timing["geometry_after"])
                self.assertIsNone(timing["layout_duration_ns"])
                self.assertGreaterEqual(timing["partial_layout_wait_ns"], 10_000_000_000)
                self.assertIsNone(report["idle_begin_ns"])
                self.assertFalse((h.root / "ready.json").exists())
                self.assertTrue(any(kind == "after" and delay == 10_000 for kind, delay, _ in h.scheduled))
                self.assertEqual(report["qa_callbacks_pending"], 0)
                self.assertEqual(report["after_info"], [])
                self.assertTrue(report["closed"])

    def test_stale_owned_callbacks_are_inert_before_ready_and_after_close(self):
        h = self.new_run()
        def probe_ready():
            self.assertEqual(h.worker.owned_callbacks, {})
            with patch.object(h.app, "geometry", side_effect=AssertionError("stale geometry getter")), \
                    patch.object(h.app, "state", side_effect=AssertionError("stale state getter")), \
                    patch.object(h.app, "winfo_ismapped", side_effect=AssertionError("stale mapped getter")):
                for _, _, callback in h.scheduled:
                    if getattr(callback, "__name__", "") == "invoke":
                        callback()
        h.ready_hook = probe_ready
        report = self.run_fake(h, "G-P")
        self.assertTrue(report["ok"], report["errors"])
        probe_ready()

    def test_final_hf_watchdog_cancel_failure_blocks_profile_ready_and_idle(self):
        h = self.new_run()
        original_build = h.deps.build
        failed_handles = []
        def build(*args):
            app = original_build(*args)
            original_cancel = app.after_cancel
            def cancel(handle):
                if h.worker.phase == "render_rules_observation":
                    failed_handles.append(handle)
                    raise RuntimeError("final H-F watchdog cancellation failed")
                original_cancel(handle)
            app.after_cancel = cancel
            return app
        h.deps.build = build
        report = self.run_fake(h)
        self.assertEqual(len(failed_handles), 1)
        self.assertFalse(report["ok"])
        self.assertTrue(any("final H-F watchdog cancellation failed" in e for e in report["errors"]))
        self.assertFalse((h.root / "ready.json").exists())
        self.assertFalse(h.worker.ready)
        self.assertIsNone(report["idle_begin_ns"])
        self.assertIsNone(report["idle_end_ns"])
        self.assertEqual(report["qa_callbacks_pending"], 0)
        self.assertEqual(report["after_info"], [])
        self.assertTrue(report["closed"])
        self.assertEqual(sum(event == "close" for event, _ in h.events), 1)
        self.assertEqual(h.worker.phase, "closing")
        for name in ("render_complete", "render_rules"):
            self.assertEqual(report["timings"][name]["status"], "complete")
            self.assertFalse(report["timings"][name]["comparable"])

    def test_previous_errors_refuse_normal_entries_before_getters_or_scheduling(self):
        h = self.new_run()
        subject = worker.Worker(worker.Options(h.root, 100, "H-F"), h.deps, h.clock)
        app = h.build(h.session, worker.ControllerGate(Controller()), worker.FakeTray(), Mailbox())
        subject.app = app
        subject.install_error_hooks()
        handle = subject.schedule(lambda: self.fail("invalidated operation ran"), delay=50)
        callback = app.timers[handle]
        subject.errors.append("prior cancellation error")
        with patch.object(subject, "observe", side_effect=AssertionError("observe after error")), \
                patch.object(app, "geometry", side_effect=AssertionError("getter after error")), \
                patch.object(app, "after", side_effect=AssertionError("schedule after error")), \
                patch.object(h.deps, "write_json", side_effect=AssertionError("publish after error")):
            for operation in (subject.profile_ready, subject.begin_idle, subject.start_profile,
                              subject.prepare_renders,
                              lambda: subject.render_call("render_complete"),
                              lambda: subject.render_observed("render_complete"),
                              lambda: subject.timed_build(lambda: self.fail("build after error")),
                              lambda: subject.schedule(lambda: None),
                              lambda: subject.publish("ready.json", {"ok": True}),
                              lambda: subject.transition("ready")):
                with self.assertRaisesRegex(RuntimeError, "previous error"):
                    operation()
            self.assertEqual(subject.owned_callbacks, {})
            callback()
            app.close_editor()
        self.assertTrue(app.closed)
        self.assertEqual(subject.phase, "closing")
        self.assertEqual(subject.errors, ["prior cancellation error"])
        self.assertEqual(sum(event == "close" for event, _ in h.events), 1)
        self.assertFalse(subject.ready)
        self.assertIsNone(subject.idle_begin_ns)

    def test_observation_watchdog_uses_only_remaining_window_with_positive_ceil(self):
        for consumed, delay, starve in ((6_500_000_001, 3500, True),
                                        (9_999_999_999, 1, False)):
            with self.subTest(consumed=consumed):
                h = self.new_run()
                reads = 0
                def geometry(app):
                    nonlocal reads
                    if h.worker.phase == "render_complete_call":
                        reads += 1
                        if reads == 2:
                            h.clock.advance(consumed)
                h.geometry_hook = geometry
                h.starve_idle = starve
                report = self.run_fake(h, "G-P")
                self.assertFalse(report["ok"])
                timing = report["timings"]["render_complete"]
                self.assertEqual(timing["duration_ns"], 11)
                self.assertEqual(timing["status"], "invalid")
                self.assertIn("after_idle observation timeout", timing["reason"])
                self.assertEqual(timing["geometry_at_return"]["observation_end_ns"] - timing["return_ns"], consumed)
                self.assertTrue(any(kind == "after" and ms == delay for kind, ms, _ in h.scheduled))
                self.assertIsNone(timing["geometry_after"])
                self.assertGreaterEqual(timing["failed_ns"], timing["observation_deadline_ns"])
                # Rounded watchdog fires within one ms of the original deadline,
                # rather than granting another ten seconds after instrumentation.
                self.assertLess(timing["failed_ns"] - timing["observation_deadline_ns"], 1_000_000)
                self.assertFalse((h.root / "ready.json").exists())
                self.assertIsNone(report["idle_begin_ns"])
                self.assertTrue(report["closed"])

    def test_getter_exhausting_observation_window_preserves_partial_and_cancel_errors(self):
        for cancel_failure in (False, True):
            with self.subTest(cancel_failure=cancel_failure):
                h = self.new_run()
                reads = 0
                def geometry(app):
                    nonlocal reads
                    if h.worker.phase == "render_complete_call":
                        reads += 1
                        if reads == 2:
                            h.clock.advance(10_000_000_001)
                h.geometry_hook = geometry
                original_build = h.deps.build
                def build(*args):
                    app = original_build(*args)
                    original_cancel = app.after_cancel
                    def cancel(handle):
                        if cancel_failure and h.worker.phase == "render_complete_call":
                            raise RuntimeError("cancel after exhausted getter failed")
                        original_cancel(handle)
                    app.after_cancel = cancel
                    return app
                h.deps.build = build
                report = self.run_fake(h, "G-P")
                self.assertFalse(report["ok"])
                timing = report["timings"]["render_complete"]
                self.assertEqual(timing["duration_ns"], 11)
                self.assertEqual(timing["status"], "invalid")
                self.assertIn("after_idle observation timeout", timing["reason"])
                self.assertIsNotNone(timing["geometry_at_return"])
                self.assertIsNone(timing["geometry_after"])
                self.assertGreater(timing["partial_layout_wait_ns"], 10_000_000_000)
                self.assertFalse(any(kind == "after_idle" for kind, _, _ in h.scheduled))
                self.assertEqual(any("cancel after exhausted getter failed" in e for e in report["errors"]),
                                 cancel_failure)
                self.assertFalse((h.root / "ready.json").exists())
                self.assertIsNone(report["idle_begin_ns"])
                self.assertIsNone(report["idle_end_ns"])
                self.assertEqual(report["qa_callbacks_pending"], 0)
                self.assertTrue(report["closed"])
                self.assertEqual(sum(event == "close" for event, _ in h.events), 1)

    def test_observation_deadline_is_checked_after_watchdog_and_idle_registration(self):
        for registration in ("after", "after_idle"):
            with self.subTest(registration=registration):
                h = self.new_run()
                original_build = h.deps.build
                def build(*args):
                    app = original_build(*args)
                    original_register = getattr(app, registration)
                    def register(*args):
                        handle = original_register(*args)
                        if h.worker.phase == "render_complete_observation":
                            h.clock.advance(10_000_000_000)
                        return handle
                    setattr(app, registration, register)
                    return app
                h.deps.build = build
                report = self.run_fake(h, "G-P")
                self.assertFalse(report["ok"])
                timing = report["timings"]["render_complete"]
                self.assertEqual(timing["status"], "invalid")
                self.assertIn("after_idle observation timeout", timing["reason"])
                self.assertIsNone(timing["geometry_after"])
                self.assertEqual(sum(kind == "after_idle" for kind, _, _ in h.scheduled),
                                 1 if registration == "after_idle" else 0)
                self.assertFalse((h.root / "ready.json").exists())
                self.assertIsNone(report["idle_begin_ns"])
                self.assertEqual(report["qa_callbacks_pending"], 0)
                self.assertEqual(report["after_info"], [])
                self.assertTrue(report["closed"])

    def test_owned_token_guard_never_erases_new_handle_or_reads_tk(self):
        h = self.new_run()
        subject = worker.Worker(worker.Options(h.root, 100, "H-F"), h.deps, h.clock)
        app = h.build(h.session, worker.ControllerGate(Controller()), worker.FakeTray(), Mailbox())
        subject.app = app
        subject.transition("old")
        subject.schedule(lambda: app.geometry(), delay=50)
        old = h.scheduled[-1][2]
        subject.transition("new")
        handle = subject.schedule(lambda: app.geometry(), delay=50)
        with patch.object(app, "geometry", side_effect=AssertionError("old getter")):
            old()
        self.assertIn(handle, subject.owned_callbacks)
        self.assertIn(handle, app.timers)
        subject.cancel_owned()

    def test_consumed_geometry_poll_cannot_be_repeated_in_the_same_phase(self):
        h = self.new_run()
        subject = worker.Worker(worker.Options(h.root, 100, "G-P"), h.deps, h.clock)
        app = h.build(h.session, worker.ControllerGate(Controller()), worker.FakeTray(), Mailbox())
        subject.app = app
        app.mapped, app.size = True, "880x660"
        app.raw_width, app.raw_height = 1100, 825
        subject.transition("geometry_wait")
        subject.geometry_gate["status"] = "waiting"
        subject.geometry_deadline_ns = h.clock() + 10_000_000_000
        subject.previous_geometry = None
        handle = subject.schedule(subject.poll_geometry, delay=50)
        callback = app.timers.pop(handle)
        h.clock.advance(50_000_000)
        callback()
        self.assertEqual(len(subject.geometry_gate["observations"]), 1)
        self.assertEqual(subject.phase, "geometry_wait")
        current = dict(subject.owned_callbacks)
        with patch.object(app, "geometry", side_effect=AssertionError("consumed getter")), \
                patch.object(app, "winfo_ismapped", side_effect=AssertionError("consumed mapped getter")):
            callback()
            callback()
        self.assertEqual(subject.owned_callbacks, current)
        self.assertEqual(len(subject.geometry_gate["observations"]), 1)
        subject.cancel_owned()

    def test_late_after_idle_callback_fails_before_getters_even_when_ordered_before_watchdog(self):
        h = self.new_run()
        h.idle_delay_ns = 10_000_000_001
        observed_getters = []
        def geometry(app):
            if h.worker.phase.endswith("_observation"):
                observed_getters.append(h.clock())
                raise AssertionError("late callback must not read geometry")
        h.geometry_hook = geometry
        report = self.run_fake(h, "G-P")
        self.assertFalse(report["ok"])
        self.assertEqual(observed_getters, [])
        timing = report["timings"]["render_complete"]
        self.assertEqual(timing["status"], "invalid")
        self.assertIn("after_idle observation timeout", timing["reason"])
        self.assertEqual(timing["duration_ns"], 11)
        self.assertIsNone(timing["geometry_after"])
        self.assertGreater(timing["failed_ns"], timing["observation_deadline_ns"])
        self.assertEqual(report["qa_callbacks_pending"], 0)

    def test_long_render_call_is_not_treated_as_starvation_of_its_continuation(self):
        h = self.new_run()
        def render(name, app):
            if name == "render_complete":
                h.clock.advance(12_000_000_000)
        h.render_hook = render
        report = self.run_fake(h, "G-P")
        self.assertTrue(report["ok"], report["errors"])
        timing = report["timings"]["render_complete"]
        self.assertEqual(timing["duration_ns"], 12_000_000_011)
        self.assertEqual(timing["layout_wait_ns"], h.idle_delay_ns)
        self.assertEqual(timing["observation_deadline_ns"] - timing["return_ns"], 10_000_000_000)
        self.assertEqual(timing["status"], "complete")

    def test_close_or_exception_inside_render_preserves_partial_measurement_and_cancels(self):
        for action in ("close", "error"):
            with self.subTest(action=action):
                h = self.new_run()
                def render(name, app):
                    if name == "render_complete":
                        if action == "close":
                            app.protocols["WM_DELETE_WINDOW"]()
                        else:
                            raise RuntimeError("render failed after partial work")
                h.render_hook = render
                report = self.run_fake(h, "G-P")
                self.assertFalse(report["ok"])
                timing = report["timings"]["render_complete"]
                self.assertEqual(timing["status"], "invalid")
                self.assertTrue(timing["reason"])
                self.assertEqual(timing["partial_total_ns"], 11)
                self.assertIsNone(timing["geometry_after"])
                self.assertEqual(len(h.render_turns), 1)
                self.assertTrue(report["closed"])
                self.assertEqual(report["qa_callbacks_pending"], 0)
                self.assertFalse((h.root / "ready.json").exists())

    def test_wm_close_during_geometry_wait_cancels_before_getters_and_never_ready(self):
        h = self.new_run()
        original_build = h.deps.build
        def build(*args):
            app = original_build(*args)
            app.after(100, lambda: app.protocols["WM_DELETE_WINDOW"]())
            return app
        h.deps.build = build
        report = self.run_fake(h, "G-P")
        self.assertFalse(report["ok"])
        self.assertEqual(h.render_turns, [])
        self.assertEqual(report["qa_callbacks_pending"], 0)
        self.assertEqual(report["geometry_gate"]["status"], "invalid")
        self.assertTrue(report["closed"])
        self.assertFalse((h.root / "ready.json").exists())

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
                    self.assertEqual(report["timing_schema_version"], 2)
                    for name, duration in (("build", 13), ("render_complete", 11), ("render_rules", 5)):
                        timing = report["timings"][name]
                        self.assertEqual(timing["duration_ns"], duration)
                        self.assertEqual(timing["status"], "complete")
                        self.assertEqual(timing["timing_schema_version"], 2)
                        if name == "build":
                            self.assertEqual(timing["layout_duration_ns"], 7)
                            self.assertIsNone(timing["layout_wait_ns"])
                            self.assertEqual(timing["geometry"]["geometry"], "200x200")
                            self.assertFalse(timing["geometry_verified"])
                        else:
                            self.assertIsNone(timing["layout_duration_ns"])
                            self.assertEqual(timing["layout_wait_ns"], h.idle_delay_ns)
                            self.assertEqual(timing["geometry_verified"], profile != "H-F")
                            self.assertEqual(timing["comparable"], profile != "H-F")
                        expected_size = "1000x740" if name == "build" else "880x660"
                        self.assertEqual(timing["geometry"]["requested_logical"], expected_size)
                        self.assertEqual(timing["through_layout_ns"], duration + (7 if name == "build" else h.idle_delay_ns))
                        self.assertEqual(timing["geometry"]["getter_units"], "ctk_logical")
                        self.assertEqual(timing["geometry"]["client_units"], "winfo_raw")
                    self.assertNotEqual(h.render_turns[0][1], h.render_turns[1][1])
                    self.assertEqual([state for _, _, state in h.render_turns],
                                     ["withdrawn", "withdrawn"] if profile == "H-F" else ["normal", "normal"])
                    self.assertEqual(sum(name == "layout" for name, _ in h.events), 1)
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
                        self.assertEqual(h.maps, 0)
                        self.assertEqual(report["geometry_gate"]["status"], "not_required")
                    else:
                        self.assertTrue(h.tray_instance.waited)
                        self.assertEqual(h.tray_instance.starts, 1)
                        self.assertEqual(report["geometry_gate"]["status"], "confirmed")
                        confirmed = report["geometry_gate"]["observations"][-2:]
                        self.assertGreaterEqual(confirmed[1]["observed_ns"] - confirmed[0]["observed_ns"], 50_000_000)
                        self.assertEqual(confirmed[1]["logical_size"], [880, 660])
                        self.assertEqual((confirmed[1]["client_width"], confirmed[1]["client_height"]), (1100, 825))
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

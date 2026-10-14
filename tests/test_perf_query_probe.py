"""Probe and worker integration with fake Tk scheduling, never native GUI."""

from types import SimpleNamespace
import unittest
from unittest.mock import patch

from tests.test_perf_gui_worker import PerfGuiWorkerTests
from tools.perf_query_probe import QueryProbe
from tools import perf_gui_worker as worker


def add_search(h):
    original_build = h.deps.build
    def build(*args):
        app = original_build(*args)
        app.rule_search_revision = app.rule_search_ticket = 0
        value = ""
        def render(*args, **kwargs):
            app.rule_search_ticket += 1
            app.rule_search_pending = False
            app.rule_search_timer = None
            count = min(h.rules, 100) if value == "qa-00" else h.rules
            app.rule_view_context = (0, "block_exes", tuple(range(count)), None, None, value, "registered")
            app.rule_page_result = SimpleNamespace(page=0, page_count=max(1, (count + 24) // 25))
            app.review_rows = {("block_exes", i): object() for i in range(min(25, count))}
            h.events.append(("query_render", h.clock()))
            h.clock.advance(5 if value == "" else 120_000_000)
        def set_value(query):
            nonlocal value
            if app.rule_search_timer is not None:
                app.after_cancel(app.rule_search_timer)
            value = query
            app.rule_search_revision += 1
            app.rule_search_ticket += 1
            app.rule_search_pending = True
            app.rule_view_context = None
            ticket = app.rule_search_ticket
            def complete():
                if app.closed or ticket != app.rule_search_ticket or app.rule_search_timer is None:
                    return
                app.rule_search_timer = None
                app.render_rules()
            app.rule_search_timer = app.after(200, complete)
            h.clock.advance(10)
        app.rule_search = SimpleNamespace(get=lambda: value, set=set_value)
        app.render_rules = render
        h.session.draft._undo, h.session.draft._redo = [], []
        return app
    h.deps.build = build


class QueryIntegrationTests(PerfGuiWorkerTests):
    # Inherited setup/cleanup only; inherited cases remain in their own module.
    def run_query(self, h, mode):
        add_search(h)
        return worker.run_worker(worker.Options(h.root, h.rules, "G-P", 0, 1, mode),
                                 h.deps, workspace=self.workspace, clock=h.clock)

    def test_query_patterns_reset_before_ready_preserve_data_and_restore_hooks(self):
        for mode in ("single", "burst", "spaced"):
            with self.subTest(mode=mode):
                h = self.new_run(1000)
                original = (h.root / "config.json").read_bytes()
                with patch.object(worker, "_native_dependencies", side_effect=AssertionError("native import")):
                    report = self.run_query(h, mode)
                self.assertTrue(report["ok"], report["errors"])
                self.assertTrue(report["query"]["complete"])
                packets = report["query"]["packets"]
                self.assertEqual([p["mode"] for p in packets], [mode, "reset"])
                self.assertTrue(all(p["summary"]["ok"] for p in packets))
                self.assertEqual(packets[0]["summary"]["final_query"], "qa-00")
                self.assertEqual(packets[-1]["summary"]["final_query"], "")
                self.assertEqual(h.app.rule_search.get(), "")
                self.assertEqual(len(h.app.rule_view_context[2]), 1000)
                self.assertNotIn("after", h.app.__dict__)
                self.assertNotIn("after_cancel", h.app.__dict__)
                self.assertNotIsInstance(getattr(h.app.render_rules, "__self__", None), QueryProbe)
                self.assertEqual((h.root / "config.json").read_bytes(), original)
                self.assertEqual(report["qa_callbacks_pending"], 0)
                self.assertEqual(h.native_controller.starts, 0)

    def test_query_error_preserves_partial_and_restores_before_closing(self):
        h = self.new_run()
        add_search(h)
        original = h.deps.build
        def broken(*args):
            app = original(*args)
            set_value = app.rule_search.set
            def set_and_fail(text):
                set_value(text)
                raise RuntimeError("setter failure")
            app.rule_search.set = set_and_fail
            return app
        h.deps.build = broken
        report = worker.run_worker(worker.Options(h.root, 100, "G-P", 0, 1, "burst"),
                                   h.deps, workspace=self.workspace, clock=h.clock)
        self.assertFalse(report["ok"])
        self.assertIsNone(report["idle_begin_ns"])
        self.assertFalse((h.root / "ready.json").exists())
        self.assertTrue(report["closed"])
        self.assertNotIn("after", h.app.__dict__)
        self.assertEqual(report["query"]["partial"]["status"], "partial")

    def test_non_gp_query_rejected_before_dependencies_or_artifacts(self):
        for profile in ("H-F", "T-P"):
            with self.subTest(profile=profile):
                h = self.new_run()
                with self.assertRaises(ValueError):
                    worker.run_worker(worker.Options(h.root, 100, profile, 0, 1, "single"),
                                      h.deps, workspace=self.workspace, clock=h.clock)
                self.assertIsNone(h.app)
                self.assertFalse((h.root / "report.json").exists())

    def test_swallowed_trace_and_render_errors_stop_before_closed_getters(self):
        for point in ("setter", "render"):
            with self.subTest(point=point):
                h = self.new_run()
                add_search(h)
                build_original = h.deps.build
                def build(*args):
                    app = build_original(*args)
                    set_original, render_original = app.rule_search.set, app.render_rules
                    def fail():
                        app.report_callback_exception(RuntimeError, RuntimeError("swallowed Tk error"), None)
                        app.rule_search.get = lambda: (_ for _ in ()).throw(AssertionError("getter after close"))
                    def set_value(value):
                        set_original(value)
                        if point == "setter":
                            fail()
                    def render(*args, **kwargs):
                        result = render_original(*args, **kwargs)
                        if point == "render" and app.rule_search.get():
                            fail()
                        return result
                    app.rule_search.set, app.render_rules = set_value, render
                    return app
                h.deps.build = build
                report = worker.run_worker(worker.Options(h.root, 100, "G-P", 0, 1, "single"),
                                           h.deps, workspace=self.workspace, clock=h.clock)
                self.assertFalse(report["ok"])
                self.assertTrue(report["closed"])
                self.assertIsNone(report["idle_begin_ns"])
                self.assertFalse(any("getter after close" in error for error in report["errors"]))

    def test_slow_instrumentation_rejects_before_query_set(self):
        h = self.new_run()
        add_search(h)
        build_original = h.deps.build
        def build(*args):
            app = build_original(*args)
            original = app.geometry
            calls = 0
            def geometry(*args):
                nonlocal calls
                if "after" in app.__dict__:  # Probe installed, outside startup geometry v2.
                    calls += 1
                    h.clock.advance(31_000_000_000)
                return original(*args)
            app.geometry = geometry
            return app
        h.deps.build = build
        report = worker.run_worker(worker.Options(h.root, 100, "G-P", 0, 1, "single"),
                                   h.deps, workspace=self.workspace, clock=h.clock)
        self.assertFalse(report["ok"])
        self.assertEqual(report["query"]["partial"]["writes"], [])
        self.assertIsNone(report["idle_begin_ns"])


# Avoid discovering the imported base suite or duplicating its 28 cases here.
for _name in dir(PerfGuiWorkerTests):
    if _name.startswith("test_"):
        setattr(QueryIntegrationTests, _name, None)
del PerfGuiWorkerTests


class ProbeCallbackTests(unittest.TestCase):
    def test_cancelled_consumed_and_closed_callbacks_never_delegate_twice(self):
        for refusal in ("cancelled", "consumed", "closed", "ticket"):
            with self.subTest(refusal=refusal):
                captured, delegated = [], []
                app = SimpleNamespace(closed=False, closing=False, rule_search_revision=1,
                                      rule_search_ticket=1)
                app.after = lambda delay, callback, *args: captured.append(callback) or "timer"
                app.after_cancel = lambda handle: None
                app.render_rules = lambda: None
                probe = QueryProbe(app, "single", 100, clock=lambda: 1,
                                   schedule=lambda *args, **kwargs: None,
                                   geometry_check=lambda: None, done=lambda probe: None)
                probe.start()
                row = dict(timer_id=None, callback_enter_ns=None, cancelled_ns=None)
                probe.active_write = row
                app.after(200, lambda: delegated.append(True))
                probe.active_write = None
                if refusal == "cancelled":
                    app.after_cancel("timer")
                elif refusal == "consumed":
                    captured[0]()
                elif refusal == "closed":
                    app.closed = True
                else:
                    app.rule_search_ticket += 1
                captured[0]()
                self.assertEqual(len(delegated), int(refusal == "consumed"))
                probe.close()

    def test_ambiguous_debounce_registration_fails_and_restores_exact_override(self):
        app = SimpleNamespace(closed=False, closing=False, rule_search_revision=1,
                              rule_search_ticket=1)
        original = lambda delay, callback, *args: "timer"
        app.after, app.after_cancel, app.render_rules = original, lambda handle: None, lambda: None
        probe = QueryProbe(app, "single", 100, clock=lambda: 1,
                           schedule=lambda *args, **kwargs: None,
                           geometry_check=lambda: None, done=lambda probe: None)
        probe.start()
        probe.active_write = dict(timer_id=None, callback_enter_ns=None, cancelled_ns=None)
        app.after(200, lambda: None)
        with self.assertRaisesRegex(RuntimeError, "multiple debounce"):
            app.after(200, lambda: None)
        probe.close()
        probe.close()
        self.assertIs(app.after, original)

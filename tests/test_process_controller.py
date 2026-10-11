"""Lifecycle/gates concorrentes com Events e adaptadores sem processos reais."""

from dataclasses import FrozenInstanceError
from datetime import datetime, time, timezone
from pathlib import Path
from queue import Queue
import subprocess
import sys
from threading import Barrier, Event, Thread, current_thread
import unittest
from unittest.mock import Mock, patch

from core.config import ConfigError
from core.models import AppConfig, ScheduleWindow
from core.proc_blocker import (
    ProcessBlocker, ProcessBlockerError, ProcessIdentity, ProcessResult,
    ScanReport, TerminationEvent, WaitResult,
)
from core.process_controller import ProcessController, RuntimeSnapshot
from tests.test_proc_blocker import FakeAdapter, process


ACTIVE = AppConfig(windows=(ScheduleWindow(time(8), time(9), (0,)),),
                   block_exes=("game.exe",))
NOW = datetime(2026, 10, 5, 8, 30)
EMPTY_REPORT = ScanReport((), ())


class FakeBlocker:
    def __init__(self, callback=None):
        self.callback = callback
        self.calls = []

    def scan(self, config, may_act):
        self.calls.append((config, may_act))
        return self.callback(config, may_act) if self.callback else EMPTY_REPORT


class StepWaiter:
    """O teste libera cada espera; nenhum atraso de relógio real é usado."""

    def __init__(self):
        self.tick = 0.0
        self.waits = Queue()
        self.releases = []

    def monotonic(self):
        return self.tick

    def __call__(self, stop_event, timeout):
        release = Event()
        self.releases.append(release)
        self.waits.put((timeout, release))
        if not release.wait(2):
            raise AssertionError("espera fake não liberada")
        if not stop_event.is_set():
            self.tick += timeout
        return stop_event.is_set()


class ProcessControllerTests(unittest.TestCase):
    def setUp(self):
        self.controllers = []
        self.releases = []
        self.steps = []

    def tearDown(self):
        for controller in self.controllers:
            controller.stop()
        for release in self.releases:
            release.set()
        for step in self.steps:
            for release in step.releases:
                release.set()
        for controller in self.controllers:
            controller.wait(2)
            self.assertFalse(controller.is_alive(), "worker não encerrou")

    def event(self):
        release = Event()
        self.releases.append(release)
        return release

    def reached(self, event):
        self.assertTrue(event.wait(2), "worker não alcançou checkpoint")

    def controller(self, blocker=None, **kwargs):
        defaults = dict(blocker_factory=lambda: blocker or FakeBlocker(),
                        loader=lambda path: ACTIVE, clock=lambda: NOW)
        defaults.update(kwargs)
        controller = ProcessController("persisted.json", **defaults)
        self.controllers.append(controller)
        return controller

    def stepper(self):
        step = StepWaiter()
        self.steps.append(step)
        return step

    def test_import_and_default_construction_never_import_psutil(self):
        script = '''
import builtins
real_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == 'psutil' or name == 'core.proc_blocker':
        raise AssertionError('process import before start')
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded
from core.process_controller import ProcessController, RuntimeSnapshot
controller = ProcessController('missing.json')
assert controller.snapshot() == RuntimeSnapshot()
assert not controller.is_alive()
controller.stop()
controller.wait(0)
'''
        result = subprocess.run([sys.executable, "-B", "-c", script],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_construction_and_idle_methods_have_no_io_clock_factory_or_thread(self):
        boundary = Mock(side_effect=AssertionError("efeito na construção"))
        with patch.object(Path, "open", boundary), \
             patch("core.process_controller.Thread", boundary):
            controller = ProcessController("missing.json", blocker_factory=boundary,
                                           loader=boundary, clock=boundary,
                                           monotonic=boundary, waiter=boundary)
            self.assertEqual(controller.snapshot(), RuntimeSnapshot())
            controller.stop()
            controller.stop()
            controller.wait(0)
            self.assertFalse(controller.is_alive())
        boundary.assert_not_called()

    def test_interval_validation_without_effects(self):
        for value in (0, -1, float("nan"), float("inf"), True, None, "5"):
            with self.subTest(interval=value), self.assertRaises(ValueError):
                ProcessController("missing.json", interval=value)

    def test_snapshot_frozen_and_running_published_before_lazy_factory(self):
        entered, release = Event(), self.event()
        factory_threads = []

        def factory():
            factory_threads.append(current_thread())
            entered.set()
            self.assertTrue(release.wait(2))
            return FakeBlocker()

        controller = self.controller(blocker_factory=factory)
        self.assertTrue(controller.start())
        self.reached(entered)
        snapshot = controller.snapshot()
        self.assertEqual(snapshot, RuntimeSnapshot(state="running"))
        self.assertIsNot(factory_threads[0], current_thread())
        self.assertFalse(factory_threads[0].daemon)
        with self.assertRaises(FrozenInstanceError):
            snapshot.state = "idle"
        self.assertFalse(controller.start())
        controller.stop()
        self.assertEqual(controller.snapshot(), RuntimeSnapshot(state="stopping"))
        release.set()
        controller.wait(2)
        self.assertEqual(controller.snapshot(), RuntimeSnapshot())
        self.assertEqual(snapshot.state, "running")

    def test_default_factory_is_created_only_on_worker(self):
        waiting = Event()
        fake = FakeBlocker()

        def factory():
            self.assertIsNot(current_thread(), main_thread)
            return fake

        def waiter(stop_event, timeout):
            waiting.set()
            return stop_event.wait(timeout)

        main_thread = current_thread()
        with patch("core.proc_blocker.ProcessBlocker", side_effect=factory) as factory_mock:
            controller = self.controller(blocker_factory=None, waiter=waiter)
            factory_mock.assert_not_called()
            self.assertTrue(controller.start())
            self.reached(waiting)
            controller.stop()
            controller.wait(2)
            factory_mock.assert_called_once_with()
        self.assertEqual(len(fake.calls), 1)

    def test_concurrent_start_creates_exactly_one_worker(self):
        entered, release = Event(), self.event()
        factory_calls = []

        def factory():
            factory_calls.append(1)
            entered.set()
            self.assertTrue(release.wait(2))
            return FakeBlocker()

        controller = self.controller(blocker_factory=factory)
        barrier = Barrier(9)
        results = Queue()

        def start():
            barrier.wait(2)
            results.put(controller.start())

        callers = [Thread(target=start) for _ in range(8)]
        for caller in callers:
            caller.start()
        barrier.wait(2)
        for caller in callers:
            caller.join(2)
            self.assertFalse(caller.is_alive())
        self.reached(entered)
        self.assertEqual(sum(results.get(timeout=2) for _ in callers), 1)
        self.assertEqual(factory_calls, [1])

    def test_stop_during_factory_skips_loading_and_scan(self):
        entered, release = Event(), self.event()
        loader = Mock(return_value=ACTIVE)
        fake = FakeBlocker()

        def factory():
            entered.set()
            self.assertTrue(release.wait(2))
            return fake

        controller = self.controller(blocker_factory=factory, loader=loader)
        controller.start()
        self.reached(entered)
        controller.stop()
        controller.wait(0)
        self.assertTrue(controller.is_alive())
        self.assertFalse(controller.start())
        release.set()
        controller.wait(2)
        loader.assert_not_called()
        self.assertEqual(fake.calls, [])
        self.assertIsNone(controller.snapshot().active)

    def test_stop_during_loader_skips_scan_and_preserves_unknown_agenda(self):
        entered, release = Event(), self.event()
        fake = FakeBlocker()

        def loader(path):
            entered.set()
            self.assertTrue(release.wait(2))
            return ACTIVE

        controller = self.controller(fake, loader=loader)
        controller.start()
        self.reached(entered)
        controller.stop()
        self.assertEqual(controller.snapshot().state, "stopping")
        release.set()
        controller.wait(2)
        self.assertEqual(fake.calls, [])
        self.assertEqual(controller.snapshot(), RuntimeSnapshot())

    def test_stop_interrupts_default_wait_and_preserves_last_agenda_report(self):
        waiting = Event()

        def waiter(stop_event, timeout):
            waiting.set()
            return stop_event.wait(timeout)

        fake = FakeBlocker()
        controller = self.controller(fake, interval=3600, waiter=waiter)
        controller.start()
        self.reached(waiting)
        before = controller.snapshot()
        self.assertEqual(before, RuntimeSnapshot("running", True, NOW, EMPTY_REPORT))
        controller.stop()
        controller.stop()
        controller.wait(2)
        self.assertFalse(controller.is_alive())
        self.assertEqual(controller.snapshot(), RuntimeSnapshot("idle", True, NOW, EMPTY_REPORT))
        self.assertFalse(fake.calls[0][1]())

    def test_stop_during_scan_is_nonblocking_and_finishing_report_is_retained(self):
        entered, release = Event(), self.event()
        gates = []

        def scan(config, gate):
            gates.append(gate)
            entered.set()
            self.assertTrue(release.wait(2))
            self.assertFalse(gate())
            return EMPTY_REPORT

        controller = self.controller(FakeBlocker(scan))
        controller.start()
        self.reached(entered)
        controller.stop()
        controller.stop()
        self.assertEqual(controller.snapshot().state, "stopping")
        self.assertTrue(controller.snapshot().active)
        self.assertFalse(gates[0]())
        self.assertTrue(controller.is_alive())
        self.assertFalse(controller.start())
        controller.wait(0)
        self.assertTrue(controller.is_alive())
        release.set()
        controller.wait(2)
        self.assertEqual(controller.snapshot(), RuntimeSnapshot("idle", True, NOW, EMPTY_REPORT))

    def test_gate_rechecks_clock_and_snapshot_pairs_agenda_with_observation(self):
        clocks = iter([NOW, datetime(2026, 10, 5, 8, 59), datetime(2026, 10, 5, 9)])
        done = Event()
        decisions = []

        def scan(config, gate):
            decisions.extend([gate(), gate()])
            done.set()
            controller.stop()
            return EMPTY_REPORT

        controller = self.controller(FakeBlocker(scan), clock=lambda: next(clocks))
        controller.start()
        self.reached(done)
        controller.wait(2)
        self.assertEqual(decisions, [True, False])
        self.assertEqual(controller.snapshot(), RuntimeSnapshot(
            "idle", False, datetime(2026, 10, 5, 9), EMPTY_REPORT,
        ))

    def test_stop_racing_gate_clock_prevents_true_return_and_stale_publication(self):
        entered, release = Event(), self.event()
        calls = 0
        decisions = []

        def clock():
            nonlocal calls
            calls += 1
            if calls == 2:
                entered.set()
                self.assertTrue(release.wait(2))
                return datetime(2026, 10, 5, 8, 31)
            return NOW

        def scan(config, gate):
            decisions.append(gate())
            return EMPTY_REPORT

        controller = self.controller(FakeBlocker(scan), clock=clock)
        controller.start()
        self.reached(entered)
        controller.stop()
        self.assertEqual(controller.snapshot().last_scan, NOW)
        release.set()
        controller.wait(2)
        self.assertEqual(decisions, [False])
        self.assertEqual(controller.snapshot(), RuntimeSnapshot("idle", True, NOW, EMPTY_REPORT))

    def test_inactive_agenda_still_scans_for_reconciliation_with_closed_gate(self):
        decisions = []

        def scan(config, gate):
            decisions.append(gate())
            controller.stop()
            return EMPTY_REPORT

        controller = self.controller(FakeBlocker(scan), loader=lambda path: AppConfig())
        controller.start()
        controller.wait(2)
        self.assertEqual(decisions, [False])
        self.assertEqual(controller.snapshot(), RuntimeSnapshot("idle", False, NOW, EMPTY_REPORT))

    def test_cadence_discounts_scan_time_skips_late_slots_and_never_overlaps(self):
        step = self.stepper()
        scan_times = []
        in_scan = 0

        def scan(config, gate):
            nonlocal in_scan
            in_scan += 1
            self.assertEqual(in_scan, 1)
            scan_times.append(step.tick)
            step.tick += (2 if len(scan_times) == 1 else 7)
            in_scan -= 1
            return EMPTY_REPORT

        fake = FakeBlocker(scan)
        loader = Mock(return_value=ACTIVE)
        controller = self.controller(fake, loader=loader, monotonic=step.monotonic, waiter=step)
        controller.start()
        timeout, release = step.waits.get(timeout=2)
        self.assertEqual(timeout, 3.0)
        self.assertEqual(scan_times, [0.0])
        release.set()
        timeout, release = step.waits.get(timeout=2)
        self.assertEqual(timeout, 3.0)  # scan 5->12: pula slot 10, próximo 15.
        self.assertEqual(scan_times, [0.0, 5.0])
        self.assertEqual(loader.call_count, 2)
        controller.stop()
        release.set()
        controller.wait(2)
        self.assertEqual(len(fake.calls), 2)

    def test_scan_finishing_exactly_on_slot_does_not_skip_that_slot(self):
        step = self.stepper()
        times = []

        def scan(config, gate):
            times.append(step.tick)
            if len(times) == 1:
                step.tick = 5.0
            else:
                controller.stop()
            return EMPTY_REPORT

        controller = self.controller(FakeBlocker(scan), monotonic=step.monotonic, waiter=step)
        controller.start()
        controller.wait(2)
        self.assertEqual(times, [0.0, 5.0])
        self.assertTrue(step.waits.empty())

    def test_each_cycle_reloads_config_and_gate_captures_that_cycle(self):
        step = self.stepper()
        configs = [ACTIVE, AppConfig()]
        loader = Mock(side_effect=configs)
        decisions = []

        def scan(config, gate):
            decisions.append(gate())
            if len(decisions) == 2:
                controller.stop()
            return EMPTY_REPORT

        fake = FakeBlocker(scan)
        controller = self.controller(fake, loader=loader, monotonic=step.monotonic, waiter=step)
        controller.start()
        _, release = step.waits.get(timeout=2)
        release.set()
        controller.wait(2)
        self.assertEqual(decisions, [True, False])
        self.assertEqual([call[0] for call in fake.calls], configs)
        self.assertEqual(loader.call_args_list, [(('persisted.json',),)] * 2)

    def test_reload_failure_closes_old_gate_and_does_not_scan_stale_config(self):
        step = self.stepper()
        loader = Mock(side_effect=[ACTIVE, ConfigError("JSON externo inválido")])
        fake = FakeBlocker()
        controller = self.controller(fake, loader=loader, monotonic=step.monotonic, waiter=step)
        controller.start()
        _, release = step.waits.get(timeout=2)
        old_gate = fake.calls[0][1]
        self.assertTrue(old_gate())
        release.set()
        controller.wait(2)
        self.assertEqual(len(fake.calls), 1)
        self.assertFalse(old_gate())
        snapshot = controller.snapshot()
        self.assertEqual(snapshot.state, "error")
        self.assertTrue(snapshot.active)
        self.assertEqual(snapshot.last_scan, NOW)
        self.assertIsNone(snapshot.report)
        self.assertIn("JSON externo inválido", snapshot.error)
        controller.stop()
        self.assertEqual(controller.snapshot(), snapshot)

    def test_factory_and_initial_config_errors_keep_unknown_agenda(self):
        for boundary in ("blocker_factory", "loader", "clock", "monotonic"):
            with self.subTest(boundary=boundary):
                failure = Mock(side_effect=RuntimeError("falha " + boundary))
                controller = self.controller(**{boundary: failure})
                self.assertTrue(controller.start())
                controller.wait(2)
                self.assertFalse(controller.is_alive())
                snapshot = controller.snapshot()
                self.assertEqual(snapshot.state, "error")
                self.assertIsNone(snapshot.active)
                self.assertIsNone(snapshot.last_scan)
                self.assertIsNone(snapshot.report)
                self.assertIn("falha " + boundary, snapshot.error)

    def test_global_scan_error_retains_partial_and_last_active_observation(self):
        partial = ScanReport(
            (ProcessResult(100, "game.exe", "terminated", "exit_confirmed"),),
            (TerminationEvent(ProcessIdentity(100, 1100), NOW.replace(tzinfo=timezone.utc)),),
        )

        def scan(config, gate):
            self.assertTrue(gate())
            raise ProcessBlockerError("falha global", partial_report=partial)

        fake = FakeBlocker(scan)
        controller = self.controller(fake)
        controller.start()
        controller.wait(2)
        snapshot = controller.snapshot()
        self.assertEqual(snapshot.state, "error")
        self.assertTrue(snapshot.active)
        self.assertEqual(snapshot.last_scan, NOW)
        self.assertIs(snapshot.report, partial)
        self.assertIn("falha global", snapshot.error)
        self.assertFalse(fake.calls[0][1]())

    def test_waiter_failure_closes_gate_and_does_not_reuse_success_report(self):
        waiter = Mock(side_effect=RuntimeError("espera falhou"))
        fake = FakeBlocker()
        controller = self.controller(fake, waiter=waiter)
        controller.start()
        controller.wait(2)
        snapshot = controller.snapshot()
        self.assertEqual(snapshot.state, "error")
        self.assertTrue(snapshot.active)
        self.assertEqual(snapshot.last_scan, NOW)
        self.assertIsNone(snapshot.report)
        self.assertIn("espera falhou", snapshot.error)
        self.assertFalse(fake.calls[0][1]())

    def test_gate_error_preserves_original_clock_cause_and_real_blocker_partial(self):
        clocks = Mock(side_effect=[NOW, RuntimeError("relógio original indisponível")])
        adapter = FakeAdapter(process())
        real_blocker = ProcessBlocker(adapter, clock=lambda: datetime.now(timezone.utc))
        controller = self.controller(real_blocker, clock=clocks)
        controller.start()
        controller.wait(2)
        snapshot = controller.snapshot()
        self.assertEqual(snapshot.state, "error")
        self.assertTrue(snapshot.active)
        self.assertEqual(snapshot.last_scan, NOW)
        self.assertIn("Blocking gate could not be evaluated", snapshot.error)
        self.assertIn("relógio original indisponível", snapshot.error)
        self.assertEqual(snapshot.report, EMPTY_REPORT)
        self.assertEqual(adapter.actions, [])

    def test_retry_requires_previous_worker_dead_and_never_reopens_old_gate(self):
        finished, release = Event(), self.event()
        retry_entered, retry_release = Event(), self.event()

        class HeldController(ProcessController):
            def _run(self, stop_event):
                super()._run(stop_event)
                finished.set()
                if not release.wait(2):
                    raise AssertionError("worker final não liberado")

        old_gate = []

        def scan(config, gate):
            old_gate.append(gate)
            raise ProcessBlockerError("primeira falha")

        first = FakeBlocker(scan)
        second = FakeBlocker()
        def make_blocker():
            if factory.call_count == 1:
                return first
            retry_entered.set()
            self.assertTrue(retry_release.wait(2))
            return second

        factory = Mock(side_effect=make_blocker)
        controller = HeldController("persisted.json", blocker_factory=factory,
                                    loader=lambda path: ACTIVE, clock=lambda: NOW)
        self.controllers.append(controller)
        controller.start()
        self.reached(finished)
        self.assertEqual(controller.snapshot().state, "error")
        self.assertTrue(controller.is_alive())
        self.assertFalse(controller.start())
        self.assertFalse(old_gate[0]())
        release.set()
        controller.wait(2)
        self.assertTrue(controller.start())
        self.reached(retry_entered)
        self.assertEqual(controller.snapshot(), RuntimeSnapshot(state="running"))
        self.assertFalse(old_gate[0]())
        controller.stop()
        retry_release.set()
        controller.wait(2)
        self.assertFalse(old_gate[0]())
        self.assertEqual(factory.call_count, 2)
        self.assertEqual(controller.snapshot().state, "idle")
        self.assertIsNone(controller.snapshot().error)

    def test_thread_start_failure_is_reported_and_wait_is_safe(self):
        with patch("core.process_controller.Thread") as thread:
            thread.return_value.start.side_effect = RuntimeError("sem thread")
            controller = self.controller()
            self.assertFalse(controller.start())
        self.assertFalse(controller.is_alive())
        controller.wait(0)
        self.assertEqual(controller.snapshot().state, "error")
        self.assertIsNone(controller.snapshot().active)
        self.assertIn("sem thread", controller.snapshot().error)

    def test_thread_creation_failure_is_reported_and_can_retry(self):
        with patch("core.process_controller.Thread", side_effect=RuntimeError("sem recursos")):
            controller = self.controller()
            self.assertFalse(controller.start())
        self.assertFalse(controller.is_alive())
        controller.wait(0)
        self.assertIn("sem recursos", controller.snapshot().error)
        waiting = Event()

        def waiter(stop_event, timeout):
            waiting.set()
            return stop_event.wait(timeout)

        controller._waiter = waiter
        self.assertTrue(controller.start())
        self.reached(waiting)
        self.assertIsNone(controller.snapshot().error)

    def test_stop_before_real_blocker_terminate_prevents_new_action(self):
        entered, release = Event(), self.event()

        class Adapter(FakeAdapter):
            def inspect_fresh(self, pid):
                entered.set()
                if not release.wait(2):
                    raise AssertionError("inspeção não liberada")
                return super().inspect_fresh(pid)

        adapter = Adapter(process())
        controller = self.controller(ProcessBlocker(adapter))
        controller.start()
        self.reached(entered)
        controller.stop()
        release.set()
        controller.wait(2)
        self.assertEqual(adapter.actions, [])
        self.assertTrue(controller.snapshot().active)
        self.assertEqual(controller.snapshot().report.results[0].status, "inactive")

    def test_stop_after_terminate_before_kill_preserves_already_started_call(self):
        entered, release = Event(), self.event()

        class Adapter(FakeAdapter):
            def terminate(self, ref):
                # Representa uma chamada já iniciada quando a parada ocorre.
                entered.set()
                if not release.wait(2):
                    raise AssertionError("terminate fake não liberado")
                super().terminate(ref)

            def wait_many(self, refs, timeout):
                return WaitResult(alive=refs)

        adapter = Adapter(process())
        controller = self.controller(ProcessBlocker(adapter))
        controller.start()
        self.reached(entered)
        controller.stop()
        self.assertTrue(controller.is_alive())
        release.set()
        controller.wait(2)
        self.assertEqual([kind for kind, _ in adapter.actions], ["terminate"])
        self.assertTrue(controller.snapshot().active)
        self.assertEqual(controller.snapshot().report.results[0].status, "inactive")

    def test_real_blocker_rechecks_clock_before_terminate_and_before_kill(self):
        for clocks, expected in (
            ([NOW, NOW, datetime(2026, 10, 5, 9)], []),
            ([NOW, NOW, NOW, datetime(2026, 10, 5, 9)], ["terminate"]),
        ):
            with self.subTest(expected=expected):
                adapter = FakeAdapter(process())
                adapter.wait_outcomes = ["alive", "alive"]
                clock = Mock(side_effect=clocks)
                done = Event()
                real_blocker = ProcessBlocker(adapter)

                def scan(config, gate):
                    report = real_blocker.scan(config, gate)
                    controller.stop()
                    done.set()
                    return report

                controller = self.controller(FakeBlocker(scan), clock=clock)
                controller.start()
                self.reached(done)
                controller.wait(2)
                self.assertEqual([kind for kind, _ in adapter.actions], expected)
                self.assertFalse(controller.snapshot().active)
                self.assertEqual(controller.snapshot().last_scan, datetime(2026, 10, 5, 9))


if __name__ == "__main__":
    unittest.main()

"""Blocking lifecycle checks use only an in-memory process adapter."""

from dataclasses import replace
from datetime import datetime, timezone
import ntpath
import unittest

from core.models import AppConfig, CmdlineRule
from core.proc_blocker import (
    Ancestor, ProcessBlocker, ProcessBlockerError, ProcessDiscovery, ProcessGone,
    ProcessIdentity, ProcessReference, ProcessSnapshot, ProcessUnavailable,
    ProtectionContext, WaitResult,
)


def process(pid=100, **changes):
    baseline = ProcessSnapshot(pid, "game.exe", 1000.0 + pid, rf"C:\Games\Game{pid}\game.exe", (), "PC\\Student")
    return replace(baseline, **changes)


class FakeAdapter:
    def __init__(self, *snapshots):
        self.snapshots = snapshots
        self.fresh = {p.pid: [p] for p in snapshots}
        self.context = ProtectionContext(999, frozenset({ProcessIdentity(888, 10.0)}), r"C:\Windows")
        self.context_error = None
        self.enum_error = None
        self.enum_count = 0
        self.discovered_configs = []
        self.context_count = 0
        self.actions = []
        self.waits = []
        self.wait_outcomes = []
        self.action_errors = {}
        self.destinations = {}

    def protection_context(self):
        self.context_count += 1
        if self.context_error:
            raise self.context_error
        return self.context

    def iter_snapshots(self, config=None):
        self.enum_count += 1
        self.discovered_configs.append(config)
        yield from self.snapshots
        if self.enum_error:
            raise self.enum_error

    def inspect_fresh(self, pid):
        queue = self.fresh[pid]
        value = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(value, BaseException):
            raise value
        return ProcessReference(value, object())

    def resolve_path(self, path):
        value = self.destinations.get(path, path)
        if isinstance(value, Exception):
            raise value
        return ntpath.normpath(value)

    def _act(self, kind, ref):
        error = self.action_errors.get((kind, ref.snapshot.pid))
        if error:
            raise error
        self.actions.append((kind, ref.snapshot.identity))

    def terminate(self, ref):
        self._act("terminate", ref)

    def kill(self, ref):
        self._act("kill", ref)

    def wait_many(self, references, timeout):
        self.waits.append((references, timeout))
        outcome = self.wait_outcomes.pop(0) if self.wait_outcomes else "gone"
        if isinstance(outcome, BaseException):
            raise outcome
        if callable(outcome):
            return outcome(references)
        return WaitResult(**{outcome: references})


class ProcessBlockerTests(unittest.TestCase):
    CONFIG = AppConfig(block_exes=("GAME.EXE",))

    def run_scan(self, adapter, config=None, gate=lambda: True):
        blocker = ProcessBlocker(adapter)
        return blocker, blocker.scan(config or self.CONFIG, gate)

    def test_empty_config_has_no_targets_or_default_active_rules(self):
        adapter = FakeAdapter(process())
        _, report = self.run_scan(adapter, AppConfig())
        self.assertEqual(report.results[0].status, "unmatched")
        self.assertEqual(adapter.actions, [])

    def test_discovery_receives_config_and_light_results_never_get_inspected(self):
        discovered = (
            ProcessDiscovery(100, "other.exe", "unmatched", "no_name_rule_candidate"),
            ProcessDiscovery(101, "Code.exe", "protected", "mandatory_or_user_safelist"),
            ProcessDiscovery(102, "unknown.exe", "unavailable", "discovery_metadata_denied"),
        )
        adapter = FakeAdapter(*discovered)
        def forbidden(pid):
            self.fail("Light discovery must not authorize fresh inspection/effects")
        adapter.inspect_fresh = forbidden
        _, report = self.run_scan(adapter)
        self.assertEqual(adapter.discovered_configs, [self.CONFIG])
        self.assertEqual([r.status for r in report.results], ["unmatched", "protected", "unavailable"])
        self.assertEqual(adapter.actions, [])
        self.assertEqual(adapter.waits, [])
        self.assertEqual(report.events, ())

    def test_discovery_cannot_represent_actionable_target_or_fake_identity(self):
        with self.assertRaises(ValueError):
            ProcessDiscovery(100, "game.exe", "target", "executable_rule")
        light = ProcessDiscovery(100, "game.exe", "unmatched", "no_rule")
        for absent_field in ("identity", "cmdline", "username", "ancestors", "create_time"):
            self.assertFalse(hasattr(light, absent_field))

    def test_full_name_case_insensitive_not_substring(self):
        adapter = FakeAdapter(process(name="GAME.EXE"), process(101, name="othergame.exe"))
        _, report = self.run_scan(adapter)
        self.assertEqual([r.status for r in report.results], ["terminated", "unmatched"])
        self.assertEqual(len(report.events), 1)

    def test_protection_wins_over_every_rule_and_unreadable_other_fields(self):
        for name in ("Code.exe", "IDEA64.EXE", "pycharm64.exe", "cmd.exe", "powershell.exe", "WindowsTerminal.exe", "brave.exe", "codex.exe", "custom.exe"):
            with self.subTest(name=name):
                adapter = FakeAdapter(process(name=name, exe=None, cmdline=None, username=None, errors=("ancestors", "exe")))
                cfg = AppConfig(block_exes=(name,), block_folders=(r"C:\Games",), block_cmdline=(CmdlineRule(name, "x"),), safelist_exes=("CUSTOM.EXE",))
                _, report = self.run_scan(adapter, cfg)
                self.assertEqual(report.results[0].status, "protected")
                self.assertEqual(adapter.actions, [])

    def test_special_self_and_own_ancestors_are_protected(self):
        for p in (process(0), process(4), process(999), process(888, create_time=10.0)):
            adapter = FakeAdapter(p)
            _, report = self.run_scan(adapter)
            self.assertEqual(report.results[0].status, "protected")
            self.assertEqual(adapter.actions, [])

    def test_reused_own_ancestor_pid_is_not_automatically_protected(self):
        adapter = FakeAdapter(process(888, create_time=20.0))
        _, report = self.run_scan(adapter)
        self.assertEqual(report.results[0].status, "terminated")

    def test_windows_paths_and_system_accounts_are_protected(self):
        for changes in ({"exe": r"C:\WINDOWS\System32\thing.exe"}, {"username": "NT AUTHORITY\\SYSTEM"}, {"username": "NT AUTHORITY\\NETWORK SERVICE"}):
            adapter = FakeAdapter(process(**changes))
            _, report = self.run_scan(adapter)
            self.assertEqual(report.results[0].status, "protected")
            self.assertEqual(adapter.actions, [])

    def test_helpers_inherit_ide_browser_but_terminal_does_not_veto_game(self):
        for name, expected in (("idea64.exe", "protected"), ("brave.exe", "protected"), ("codex.exe", "protected"), ("WindowsTerminal.exe", "terminated")):
            with self.subTest(name=name):
                parent = Ancestor(ProcessIdentity(50, 10.0), name)
                adapter = FakeAdapter(process(ancestors=(parent,)))
                _, report = self.run_scan(adapter)
                self.assertEqual(report.results[0].status, expected)

    def test_incomplete_protection_metadata_preserves_target(self):
        variants = ({"create_time": None}, {"create_time": float("nan")}, {"create_time": float("inf")}, {"create_time": "1100"}, {"create_time": []}, {"create_time": True}, {"name": None}, {"username": None}, {"exe": ""}, {"exe": None}, {"errors": ("ancestors",)}, {"errors": ("name",)}, {"errors": ("create_time",)}, {"ancestors": (Ancestor(ProcessIdentity(3, 1.0), None),)})
        for changes in variants:
            with self.subTest(changes=changes):
                adapter = FakeAdapter(process(**changes))
                _, report = self.run_scan(adapter)
                self.assertEqual(report.results[0].status, "unavailable")
                self.assertEqual(adapter.actions, [])
                self.assertEqual(report.events, ())

    def test_invalid_pid_does_not_create_identity_or_raise_type_error(self):
        for pid in (None, "100", True, False, -1, 1.0):
            with self.subTest(pid=pid):
                p = process(pid=100)
                p = replace(p, pid=pid)
                self.assertIsNone(p.identity)
                if pid in (True, False):
                    # False compares equal to special PID0, which still cannot act.
                    self.assertNotEqual(ProcessBlocker(FakeAdapter())._decision(p, self.CONFIG, FakeAdapter().context)[0], "target")
                else:
                    _, report = self.run_scan(FakeAdapter(p))
                    self.assertEqual(report.results[0].status, "unavailable")

    def test_configured_unknown_executable_needs_no_new_manual_policy(self):
        adapter = FakeAdapter(process(name="chosen.exe"))
        _, report = self.run_scan(adapter, AppConfig(block_exes=("chosen.exe",)))
        self.assertEqual(report.results[0].status, "terminated")

    def test_folder_uses_components_subfolders_and_resolved_destination(self):
        adapter = FakeAdapter(process(exe=r"C:\Games\nested\a.exe"), process(101, exe=r"C:\GamesOther\b.exe"), process(102, exe=r"D:\Link\game.exe"))
        adapter.destinations[r"D:\Link\game.exe"] = r"C:\Games\resolved\game.exe"
        _, report = self.run_scan(adapter, AppConfig(block_folders=(r"c:\games",)))
        self.assertEqual([r.status for r in report.results], ["terminated", "unmatched", "terminated"])

    def test_destination_resolution_failure_preserves(self):
        for path in (r"C:\Games", process().exe):
            adapter = FakeAdapter(process())
            adapter.destinations[path] = OSError("unverifiable junction")
            _, report = self.run_scan(adapter, AppConfig(block_folders=(r"C:\Games",)))
            self.assertEqual(report.results[0].status, "unavailable")
            self.assertEqual(adapter.actions, [])

    def test_java_requires_executable_and_contains_ignores_case_per_argument(self):
        adapter = FakeAdapter(process(name="javaw.exe", cmdline=("javaw.exe", r"C:\User\.MINECRAFT\game")), process(101, name="other.exe", cmdline=(".minecraft",)), process(102, name="javaw.exe", cmdline=(".mine", "craft")), process(103, name="javaw.exe", cmdline=("ide.jar",)))
        _, report = self.run_scan(adapter, AppConfig(block_cmdline=(CmdlineRule("JAVAW.EXE", ".minecraft"),)))
        self.assertEqual([r.status for r in report.results], ["terminated", "unmatched", "unmatched", "unmatched"])

    def test_literal_is_not_regex(self):
        adapter = FakeAdapter(process(name="javaw.exe", cmdline=("minecraft",)))
        _, report = self.run_scan(adapter, AppConfig(block_cmdline=(CmdlineRule("javaw.exe", ".*"),)))
        self.assertEqual(report.results[0].status, "unmatched")

    def test_inaccessible_cmdline_preserves_conjunction_not_other_fields(self):
        adapter = FakeAdapter(process(name="javaw.exe", cmdline=None, errors=("cmdline",)))
        _, report = self.run_scan(adapter, AppConfig(block_cmdline=(CmdlineRule("javaw.exe", ".minecraft"),)))
        self.assertEqual(report.results[0].status, "unavailable")
        self.assertEqual(report.results[0].name, "javaw.exe")

    def test_identity_and_metadata_are_rechecked_before_terminate(self):
        for fresh, expected in ((process(create_time=9999.0), "unavailable"), (process(name="Code.exe"), "protected"), (process(exe=r"C:\Windows\System32\game.exe"), "protected"), (process(errors=("ancestors",)), "unavailable"), (ProcessGone(), "gone")):
            adapter = FakeAdapter(process())
            adapter.fresh[100] = [fresh]
            _, report = self.run_scan(adapter)
            self.assertEqual(report.results[0].status, expected)
            self.assertEqual(adapter.actions, [])

    def test_gate_closes_before_terminate(self):
        adapter = FakeAdapter(process())
        answers = iter((True, False))
        _, report = self.run_scan(adapter, gate=lambda: next(answers))
        self.assertEqual(report.results[0].status, "inactive")
        self.assertEqual(adapter.actions, [])

    def test_one_collective_two_second_wait_then_zero_for_many_targets(self):
        adapter = FakeAdapter(*(process(pid) for pid in range(100, 115)))
        adapter.wait_outcomes = ["alive", "gone"]
        _, report = self.run_scan(adapter)
        self.assertEqual([timeout for _, timeout in adapter.waits], [2.0, 0.0])
        self.assertEqual(len(adapter.waits[0][0]), 15)
        self.assertEqual(len(report.events), 15)
        self.assertEqual([kind for kind, _ in adapter.actions], ["terminate"] * 15 + ["kill"] * 15)

    def test_before_kill_revalidates_identity_protection_and_metadata(self):
        for changed, expected in ((process(create_time=2000.0), "unavailable"), (process(name="Code.exe"), "protected"), (process(exe=None), "unavailable")):
            adapter = FakeAdapter(process())
            adapter.fresh[100] = [process(), changed]
            adapter.wait_outcomes = ["alive", "alive"]
            _, report = self.run_scan(adapter)
            self.assertEqual(report.results[0].status, expected)
            self.assertEqual([kind for kind, _ in adapter.actions], ["terminate"])
            self.assertEqual(report.events, ())

    def test_gate_closes_before_kill(self):
        adapter = FakeAdapter(process())
        adapter.wait_outcomes = ["alive", "alive"]
        answers = iter((True, True, False))
        _, report = self.run_scan(adapter, gate=lambda: next(answers))
        self.assertEqual(report.results[0].status, "inactive")
        self.assertEqual([kind for kind, _ in adapter.actions], ["terminate"])

    def test_pending_confirmed_outside_window_without_enumeration_or_effects(self):
        adapter = FakeAdapter(process())
        adapter.wait_outcomes = ["alive", "alive", "gone"]
        blocker, first = self.run_scan(adapter)
        self.assertEqual(first.results[0].status, "pending")
        self.assertEqual(first.events, ())
        counts = (adapter.enum_count, adapter.context_count, len(adapter.actions))
        adapter.enum_error = AssertionError("enumeration forbidden")
        adapter.context_error = AssertionError("context forbidden")
        report = blocker.scan(self.CONFIG, lambda: False)
        self.assertEqual(report.results[0].status, "terminated")
        self.assertEqual(len(report.events), 1)
        self.assertEqual((adapter.enum_count, adapter.context_count, len(adapter.actions)), counts)
        self.assertEqual(adapter.waits[-1][1], 0.0)
        self.assertEqual(blocker.scan(self.CONFIG, lambda: False).events, ())

    def test_false_gate_without_pending_never_enumerates_or_builds_context(self):
        adapter = FakeAdapter(process())
        adapter.enum_error = AssertionError()
        adapter.context_error = AssertionError()
        _, report = self.run_scan(adapter, gate=lambda: False)
        self.assertEqual(report.results, ())
        self.assertEqual((adapter.enum_count, adapter.context_count, adapter.actions, adapter.waits), (0, 0, [], []))

    def test_pending_alive_next_cycle_is_not_signalled_again(self):
        adapter = FakeAdapter(process())
        adapter.wait_outcomes = ["alive", "alive", "alive"]
        blocker, _ = self.run_scan(adapter)
        report = blocker.scan(self.CONFIG, lambda: True)
        self.assertEqual(report.results[0].status, "pending")
        self.assertEqual([kind for kind, _ in adapter.actions], ["terminate", "kill"])
        self.assertEqual([timeout for _, timeout in adapter.waits], [2.0, 0.0, 0.0])

    def test_no_event_for_preexisting_absence_or_denied_request(self):
        for error, expected in ((ProcessGone(), "gone"), (ProcessUnavailable(), "unavailable"), (OSError(), "failed")):
            adapter = FakeAdapter(process())
            adapter.action_errors[("terminate", 100)] = error
            _, report = self.run_scan(adapter)
            self.assertEqual(report.results[0].status, expected)
            self.assertEqual(report.events, ())
            self.assertEqual(adapter.waits, [])

    def test_target_failure_does_not_stop_other_targets(self):
        adapter = FakeAdapter(process(), process(101))
        adapter.action_errors[("terminate", 100)] = ProcessUnavailable()
        _, report = self.run_scan(adapter)
        self.assertEqual([r.status for r in report.results], ["unavailable", "terminated"])
        self.assertEqual(len(report.events), 1)

    def test_wait_failure_does_not_report_false_success_and_reconciles_later(self):
        adapter = FakeAdapter(process())
        adapter.wait_outcomes = [OSError(), OSError(), "gone"]
        blocker, first = self.run_scan(adapter)
        self.assertEqual(first.results[0].status, "failed")
        self.assertEqual(first.events, ())
        report = blocker.scan(self.CONFIG, lambda: False)
        self.assertEqual(len(report.events), 1)
        self.assertEqual([kind for kind, _ in adapter.actions], ["terminate"])

    def test_wait_unavailable_is_visible_and_retains_pending(self):
        adapter = FakeAdapter(process())
        adapter.wait_outcomes = ["unavailable", "unavailable", "gone"]
        blocker, first = self.run_scan(adapter)
        self.assertEqual(first.results[0].status, "unavailable")
        self.assertEqual(first.events, ())
        self.assertEqual(len(blocker.scan(self.CONFIG, lambda: False).events), 1)

    def test_kill_failure_is_visible_without_counting_success(self):
        adapter = FakeAdapter(process())
        adapter.wait_outcomes = ["alive", "alive"]
        adapter.action_errors[("kill", 100)] = OSError()
        _, report = self.run_scan(adapter)
        self.assertEqual(report.results[0].status, "failed")
        self.assertEqual(report.events, ())

    def test_multiple_rules_duplicate_discovery_and_cycles_count_one_identity(self):
        p = process(cmdline=("trigger",))
        adapter = FakeAdapter(p, p)
        cfg = AppConfig(block_exes=("game.exe",), block_folders=(r"C:\Games",), block_cmdline=(CmdlineRule("game.exe", "trigger"),))
        blocker, first = self.run_scan(adapter, cfg)
        self.assertEqual(len(first.events), 1)
        self.assertEqual(len(adapter.actions), 1)
        self.assertEqual(blocker.scan(cfg, lambda: True).events, ())
        adapter.snapshots = (replace(p, create_time=5000.0),)
        adapter.fresh[100] = list(adapter.snapshots)
        reopened = blocker.scan(cfg, lambda: True)
        self.assertEqual(len(reopened.events), 1)
        self.assertNotEqual(first.events[0].identity, reopened.events[0].identity)

    def test_confirmation_time_is_aware_and_injected(self):
        adapter = FakeAdapter(process())
        observed = datetime(2026, 10, 5, 20, tzinfo=timezone.utc)
        report = ProcessBlocker(adapter, clock=lambda: observed).scan(self.CONFIG, lambda: True)
        self.assertEqual(report.events[0].confirmed_at, observed)

    def test_global_context_and_partial_enumeration_fail_before_effects(self):
        for field in ("context_error", "enum_error"):
            adapter = FakeAdapter(process())
            setattr(adapter, field, OSError())
            with self.assertRaises(ProcessBlockerError):
                ProcessBlocker(adapter).scan(self.CONFIG, lambda: True)
            self.assertEqual(adapter.actions, [])

    def test_global_context_failure_on_refresh_aborts(self):
        adapter = FakeAdapter(process())
        old = adapter.protection_context
        def context():
            if adapter.context_count == 1:
                raise OSError("context changed")
            return old()
        adapter.protection_context = context
        with self.assertRaises(ProcessBlockerError):
            ProcessBlocker(adapter).scan(self.CONFIG, lambda: True)
        self.assertEqual(adapter.actions, [])

    def test_global_failure_delivers_confirmed_event_in_partial_report_once(self):
        adapter = FakeAdapter(process())
        adapter.wait_outcomes = ["alive", "alive", "gone"]
        blocker, _ = self.run_scan(adapter)
        adapter.enum_error = OSError()
        with self.assertRaises(ProcessBlockerError) as caught:
            blocker.scan(self.CONFIG, lambda: True)
        partial = caught.exception.partial_report
        self.assertEqual(len(partial.events), 1)
        self.assertEqual(partial.results[0].status, "terminated")
        self.assertEqual(blocker.scan(self.CONFIG, lambda: False).events, ())

    def test_global_failure_after_accepted_action_exposes_partial_pending(self):
        adapter = FakeAdapter(process(), process(101))
        old = adapter.protection_context
        def context():
            if adapter.context_count >= 2:
                raise OSError("context failed after first action")
            return old()
        adapter.protection_context = context
        blocker = ProcessBlocker(adapter)
        with self.assertRaises(ProcessBlockerError) as caught:
            blocker.scan(self.CONFIG, lambda: True)
        partial = caught.exception.partial_report
        self.assertEqual([r.status for r in partial.results], ["pending"])
        self.assertEqual(partial.events, ())
        self.assertEqual([kind for kind, _ in adapter.actions], ["terminate"])
        confirmed = blocker.scan(self.CONFIG, lambda: False)
        self.assertEqual(len(confirmed.events), 1)

    def test_gate_failure_is_global_and_keyboard_interrupt_not_swallowed(self):
        for error in (ValueError(), KeyboardInterrupt()):
            adapter = FakeAdapter(process())
            def gate():
                raise error
            expected = ProcessBlockerError if isinstance(error, Exception) else KeyboardInterrupt
            with self.assertRaises(expected):
                ProcessBlocker(adapter).scan(self.CONFIG, gate)
            self.assertEqual(adapter.actions, [])

    def test_keyboard_interrupt_from_target_releases_cycle_lock(self):
        adapter = FakeAdapter(process())
        adapter.fresh[100] = [KeyboardInterrupt()]
        blocker = ProcessBlocker(adapter)
        with self.assertRaises(KeyboardInterrupt):
            blocker.scan(self.CONFIG, lambda: True)
        self.assertEqual(blocker.scan(self.CONFIG, lambda: False).results, ())

    def test_concurrent_cycle_refused(self):
        blocker = ProcessBlocker(FakeAdapter())
        blocker._lock.acquire()
        try:
            with self.assertRaises(ProcessBlockerError):
                blocker.scan(self.CONFIG, lambda: True)
        finally:
            blocker._lock.release()


if __name__ == "__main__":
    unittest.main()

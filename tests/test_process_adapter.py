"""The real adapter is driven by fake psutil processes; no real process effects."""

from types import SimpleNamespace
from unittest.mock import patch
import os
import unittest

import psutil

from core.proc_blocker import (
    ProcessBlocker, ProcessBlockerError, ProcessDiscovery, ProcessGone, ProcessReference,
    ProcessSnapshot, ProcessUnavailable, PsutilAdapter,
)
from core.models import AppConfig, CmdlineRule


class StubProcess:
    def __init__(self, pid, name="game.exe", parent=None, ppid=0):
        self.pid = pid
        self.values = {"name": name, "create_time": 1000.0 + pid, "exe": rf"C:\Games\{name}", "cmdline": [name, ".minecraft"], "username": "PC\\Student"}
        self.parent_process = parent
        self.parent_pid = parent.pid if parent is not None else ppid
        self.denied = set()
        self.gone_at = set()
        self.alive = True
        self.actions = []
        self.confirm_exit = False

    def _read(self, attr):
        if attr in self.denied:
            raise psutil.AccessDenied(self.pid)
        if attr in self.gone_at:
            raise psutil.NoSuchProcess(self.pid)
        return self.values[attr]

    def name(self): return self._read("name")
    def create_time(self): return self._read("create_time")
    def exe(self): return self._read("exe")
    def cmdline(self): return self._read("cmdline")
    def username(self): return self._read("username")

    def parent(self):
        if "parent" in self.denied:
            raise psutil.AccessDenied(self.pid)
        return self.parent_process

    def ppid(self): return self.parent_pid

    def is_running(self):
        if "is_running" in self.denied:
            raise psutil.AccessDenied(self.pid)
        return self.alive

    def terminate(self):
        if "terminate" in self.denied:
            raise psutil.AccessDenied(self.pid)
        if "terminate" in self.gone_at:
            raise psutil.NoSuchProcess(self.pid)
        self.actions.append("terminate")

    def kill(self):
        if "kill" in self.denied:
            raise psutil.AccessDenied(self.pid)
        self.actions.append("kill")

    def wait(self, timeout):
        if "wait" in self.denied:
            raise psutil.AccessDenied(self.pid)
        if self.confirm_exit:
            self.alive = False
            return 0
        raise psutil.TimeoutExpired(timeout, pid=self.pid)


class FakePsutil:
    AccessDenied = psutil.AccessDenied
    NoSuchProcess = psutil.NoSuchProcess
    TimeoutExpired = psutil.TimeoutExpired
    wait_procs = staticmethod(psutil.wait_procs)

    def __init__(self, *processes):
        self.processes = {p.pid: p for p in processes}
        self.process_calls = []
        self.discovered = tuple(SimpleNamespace(pid=p.pid) for p in processes)

    def Process(self, pid):
        self.process_calls.append(pid)
        value = self.processes.get(pid)
        if isinstance(value, Exception):
            raise value
        if value is None:
            raise psutil.NoSuchProcess(pid)
        return value

    def process_iter(self):
        return iter(self.discovered)


def adapter_for(*processes, own_pid=999):
    return PsutilAdapter(psutil_module=FakePsutil(*processes), path_resolver=lambda value: value, windows_directory=r"C:\Windows", own_pid=own_pid)


class PsutilAdapterTests(unittest.TestCase):
    def forbid_metadata(self, process, *methods):
        mocks = []
        for method in methods:
            mocks.append(self.enterContext(patch.object(process, method, side_effect=AssertionError("Unexpected metadata read: " + method))))
        return mocks

    def assert_no_reads(self, mocks):
        for mock in mocks:
            mock.assert_not_called()

    def test_empty_rules_prefilter_names_without_expensive_metadata_or_paths(self):
        processes = [StubProcess(pid, "other.exe") for pid in range(100, 200)]
        adapter = adapter_for(*processes)
        forbidden = []
        for p in processes:
            forbidden.extend(self.forbid_metadata(p, "exe", "cmdline", "username", "parent", "ppid", "create_time", "is_running"))
        with patch.object(adapter, "resolve_path", side_effect=AssertionError("Path read not needed")) as resolver:
            discovered = tuple(adapter.iter_snapshots(AppConfig()))
        self.assertEqual(len(discovered), 100)
        self.assertTrue(all(isinstance(p, ProcessDiscovery) and p.status == "unmatched" for p in discovered))
        self.assertTrue(all(not hasattr(p, "identity") for p in discovered))
        self.assert_no_reads(forbidden)
        resolver.assert_not_called()

    def test_mandatory_and_user_safelist_skip_all_full_metadata_even_with_rules(self):
        processes = [StubProcess(100, "Code.exe"), StubProcess(101, "brave.exe"), StubProcess(102, "chosen-safe.exe")]
        adapter = adapter_for(*processes)
        forbidden = []
        for p in processes:
            forbidden.extend(self.forbid_metadata(p, "exe", "cmdline", "username", "parent", "ppid", "create_time", "is_running"))
        cfg = AppConfig(block_exes=("Code.exe", "brave.exe", "chosen-safe.exe"), block_folders=(r"C:\Games",), safelist_exes=("CHOSEN-SAFE.EXE",))
        discovered = tuple(adapter.iter_snapshots(cfg))
        self.assertEqual([p.status for p in discovered], ["protected"] * 3)
        self.assert_no_reads(forbidden)

    def test_special_and_own_pids_skip_name_lookup_too(self):
        processes = [StubProcess(pid) for pid in (0, 4, 999)]
        adapter = adapter_for(*processes)
        forbidden = []
        for p in processes:
            forbidden.extend(self.forbid_metadata(p, "name", "exe", "cmdline", "username", "parent", "ppid", "create_time", "is_running"))
        discovered = tuple(adapter.iter_snapshots(AppConfig(block_exes=("game.exe",))))
        self.assertEqual([p.status for p in discovered], ["protected"] * 3)
        self.assert_no_reads(forbidden)
        self.assertEqual(adapter.psutil.process_calls, [])

    def test_nonmatching_names_without_folders_do_not_read_cmdline_or_ancestry(self):
        p = StubProcess(100, "other.exe")
        adapter = adapter_for(p)
        forbidden = self.forbid_metadata(p, "exe", "cmdline", "username", "parent", "ppid", "create_time", "is_running")
        cfg = AppConfig(block_exes=("game.exe",), block_cmdline=(CmdlineRule("javaw.exe", ".minecraft"),))
        result = tuple(adapter.iter_snapshots(cfg))[0]
        self.assertIsInstance(result, ProcessDiscovery)
        self.assertEqual(result.status, "unmatched")
        self.assert_no_reads(forbidden)

    def test_name_and_cmdline_candidates_still_get_complete_fresh_inspection(self):
        for cfg, name in ((AppConfig(block_exes=("GAME.EXE",)), "game.exe"), (AppConfig(block_cmdline=(CmdlineRule("JAVAW.EXE", ".minecraft"),)), "javaw.exe")):
            with self.subTest(name=name):
                p = StubProcess(100, name)
                adapter = adapter_for(p)
                with patch.object(p, "cmdline", wraps=p.cmdline) as cmdline, patch.object(p, "username", wraps=p.username) as username, patch.object(p, "parent", wraps=p.parent) as ancestry:
                    snapshot = tuple(adapter.iter_snapshots(cfg))[0]
                self.assertIsInstance(snapshot, ProcessSnapshot)
                self.assertIsNotNone(snapshot.identity)
                self.assertIsNotNone(snapshot.cmdline)
                self.assertEqual(snapshot.errors, ())
                cmdline.assert_called_once()
                username.assert_called_once()
                ancestry.assert_called_once()
                self.assertEqual(adapter.psutil.process_calls, [100, 100])

    def test_folder_discovery_skips_full_metadata_for_windows_and_nonmatches(self):
        windows, outside, sibling, candidate = (StubProcess(pid, "unknown.exe") for pid in range(100, 104))
        windows.values["exe"] = r"C:\Windows\System32\unknown.exe"
        outside.values["exe"] = r"C:\Tools\unknown.exe"
        sibling.values["exe"] = r"C:\GamesOther\unknown.exe"
        candidate.values["exe"] = r"C:\Games\nested\unknown.exe"
        adapter = adapter_for(windows, outside, sibling, candidate)
        forbidden = []
        for p in (windows, outside, sibling):
            forbidden.extend(self.forbid_metadata(p, "cmdline", "username", "parent", "ppid", "create_time", "is_running"))
        with patch.object(candidate, "cmdline", wraps=candidate.cmdline) as cmdline, patch.object(candidate, "parent", wraps=candidate.parent) as ancestry:
            found = tuple(adapter.iter_snapshots(AppConfig(block_folders=(r"C:\Games",))))
        self.assertEqual([p.status for p in found[:3]], ["protected", "unmatched", "unmatched"])
        self.assertIsInstance(found[3], ProcessSnapshot)
        self.assertIsNotNone(found[3].identity)
        self.assertEqual(found[3].errors, ())
        self.assert_no_reads(forbidden)
        cmdline.assert_called_once()
        ancestry.assert_called_once()

    def test_name_candidate_does_not_get_discarded_by_nonmatching_folder(self):
        p = StubProcess(100)
        adapter = adapter_for(p)
        cfg = AppConfig(block_exes=("game.exe",), block_folders=(r"D:\Other",))
        snapshot = tuple(adapter.iter_snapshots(cfg))[0]
        self.assertIsInstance(snapshot, ProcessSnapshot)
        self.assertIsNotNone(snapshot.identity)

    def test_folder_destination_resolution_failure_preserves_without_full_reads(self):
        for failing_path in (r"C:\Games", r"C:\Games\game.exe"):
            with self.subTest(failing_path=failing_path):
                p = StubProcess(100)
                adapter = adapter_for(p)
                forbidden = self.forbid_metadata(p, "cmdline", "username", "parent", "ppid", "create_time", "is_running")
                def resolve(value):
                    if value == failing_path:
                        raise PermissionError("Unverifiable junction")
                    return value
                adapter._resolver = resolve
                result = tuple(adapter.iter_snapshots(AppConfig(block_folders=(r"C:\Games",))))[0]
                self.assertIsInstance(result, ProcessDiscovery)
                self.assertEqual(result.status, "unavailable")
                self.assert_no_reads(forbidden)

    def test_discovery_name_and_exe_denials_visible_without_other_reads(self):
        for field, cfg in (("name", AppConfig(block_exes=("game.exe",))), ("exe", AppConfig(block_folders=(r"C:\Games",)))):
            p = StubProcess(100)
            p.denied.add(field)
            adapter = adapter_for(p)
            forbidden = self.forbid_metadata(p, "cmdline", "username", "parent", "ppid", "create_time", "is_running")
            result = tuple(adapter.iter_snapshots(cfg))[0]
            self.assertEqual(result.status, "unavailable")
            self.assert_no_reads(forbidden)

    def test_folder_resolution_cache_lasts_one_discovery_not_across_cycles(self):
        processes = [StubProcess(pid, "other.exe") for pid in (100, 101, 102)]
        for p in processes:
            p.values["exe"] = r"D:\Link\other.exe"
        adapter = adapter_for(*processes)
        destination = r"C:\Tools\other.exe"
        def resolve(value):
            return destination if value == r"D:\Link\other.exe" else value
        adapter._resolver = resolve
        cfg = AppConfig(block_folders=(r"C:\Games",))
        with patch.object(adapter, "resolve_path", wraps=adapter.resolve_path) as resolver:
            first = tuple(adapter.iter_snapshots(cfg))
        self.assertTrue(all(p.status == "unmatched" for p in first))
        self.assertEqual([call.args[0] for call in resolver.call_args_list].count(r"D:\Link\other.exe"), 1)
        destination = r"C:\Games\other.exe"
        second = tuple(adapter.iter_snapshots(cfg))
        self.assertTrue(all(isinstance(p, ProcessSnapshot) for p in second))

    def test_light_match_becomes_full_snapshot_before_metadata_protection_decision(self):
        parent = StubProcess(50, "idea64.exe")
        p = StubProcess(100, parent=parent)
        adapter = adapter_for(p)
        snapshot = tuple(adapter.iter_snapshots(AppConfig(block_exes=("game.exe",))))[0]
        self.assertIsInstance(snapshot, ProcessSnapshot)
        context = adapter_for(StubProcess(999)).protection_context()
        status, reason = ProcessBlocker(adapter)._decision(snapshot, AppConfig(block_exes=("game.exe",)), context)
        self.assertEqual((status, reason), ("protected", "ide_browser_or_tool_ancestor"))
        self.assertEqual(p.actions, [])

    def test_optimized_candidate_revalidates_full_identity_and_protection_before_action(self):
        for change, expected in (("identity", "unavailable"), ("system_account", "protected"), ("ide_ancestor", "protected"), ("access_denied", "unavailable")):
            with self.subTest(change=change):
                p, own = StubProcess(100), StubProcess(999)
                adapter = adapter_for(p, own)
                inspect = adapter.inspect_fresh
                candidate_inspections = []
                def refreshed(pid):
                    if pid == 100:
                        candidate_inspections.append(pid)
                        if len(candidate_inspections) == 2:
                            if change == "identity":
                                p.values["create_time"] = 9000.0
                            elif change == "system_account":
                                p.values["username"] = "NT AUTHORITY\\SYSTEM"
                            elif change == "ide_ancestor":
                                p.parent_process = StubProcess(50, "Code.exe")
                                p.parent_pid = 50
                            else:
                                p.denied.add("username")
                    return inspect(pid)
                with patch.object(adapter, "inspect_fresh", side_effect=refreshed):
                    report = ProcessBlocker(adapter).scan(AppConfig(block_exes=("game.exe",)), lambda: True)
                target_result = next(result for result in report.results if result.pid == 100)
                self.assertEqual(target_result.status, expected)
                self.assertEqual(len(candidate_inspections), 2)
                self.assertEqual(p.actions, [])
                self.assertEqual(report.events, ())

    def test_optimized_discovery_preserves_candidate_with_incomplete_ancestry(self):
        p, old_parent, own = StubProcess(100, ppid=50), StubProcess(50, "launcher.exe"), StubProcess(999)
        adapter = adapter_for(p, old_parent, own)
        report = ProcessBlocker(adapter).scan(AppConfig(block_exes=("game.exe",)), lambda: True)
        target = next(result for result in report.results if result.pid == 100)
        self.assertEqual(target.status, "unavailable")
        self.assertEqual(p.actions, [])
        self.assertEqual(old_parent.actions, [])
        self.assertEqual(report.events, ())

    def test_access_denied_field_preserves_all_other_metadata_and_pid(self):
        p = StubProcess(100)
        p.denied.add("cmdline")
        snapshot = adapter_for(p).inspect_fresh(100).snapshot
        self.assertEqual(snapshot.pid, 100)
        self.assertEqual(snapshot.name, "game.exe")
        self.assertEqual(snapshot.exe, p.values["exe"])
        self.assertIsNotNone(snapshot.identity)
        self.assertIsNone(snapshot.cmdline)
        self.assertIn("cmdline", snapshot.errors)

    def test_access_denied_create_time_never_falls_back_to_pid(self):
        p = StubProcess(100)
        p.denied.add("create_time")
        snapshot = adapter_for(p).inspect_fresh(100).snapshot
        self.assertIsNone(snapshot.identity)
        self.assertEqual(snapshot.name, "game.exe")
        self.assertIn("create_time", snapshot.errors)

    def test_empty_exe_remains_empty_not_access_denied(self):
        p = StubProcess(100)
        p.values["exe"] = ""
        snapshot = adapter_for(p).inspect_fresh(100).snapshot
        self.assertEqual(snapshot.exe, "")
        self.assertNotIn("exe", snapshot.errors)

    def test_disappearance_retains_fields_already_read(self):
        p = StubProcess(100)
        p.gone_at.add("exe")
        snapshot = adapter_for(p).inspect_fresh(100).snapshot
        self.assertTrue(snapshot.gone)
        self.assertEqual(snapshot.name, "game.exe")
        self.assertEqual(snapshot.create_time, 1100.0)

    def test_discovery_opens_fresh_process_instead_of_cached_metadata(self):
        p = StubProcess(100)
        adapter = adapter_for(p)
        adapter.psutil.discovered = (SimpleNamespace(pid=100, name=lambda: "Code.exe"),)
        snapshots = tuple(adapter.iter_snapshots())
        self.assertEqual(snapshots[0].name, "game.exe")
        self.assertEqual(adapter.psutil.process_calls, [100])

    def test_discovery_denied_and_gone_targets_remain_visible(self):
        adapter = adapter_for()
        adapter.psutil.discovered = (SimpleNamespace(pid=100), SimpleNamespace(pid=101))
        adapter.psutil.processes[100] = psutil.AccessDenied(100)
        snapshots = tuple(adapter.iter_snapshots())
        self.assertEqual([p.pid for p in snapshots], [100, 101])
        self.assertIsNone(snapshots[0].identity)
        self.assertTrue(snapshots[1].gone)

    def test_confirmed_absent_parent_ends_living_chain(self):
        p = StubProcess(100, ppid=50)
        adapter = adapter_for(p)
        snapshot = adapter.inspect_fresh(100).snapshot
        self.assertNotIn("ancestors", snapshot.errors)
        self.assertEqual(adapter.psutil.process_calls, [100, 50])

    def test_extant_older_parent_unexpectedly_missing_preserves(self):
        p = StubProcess(100, ppid=50)
        former = StubProcess(50)
        adapter = adapter_for(p, former)
        snapshot = adapter.inspect_fresh(100).snapshot
        self.assertIn("ancestors", snapshot.errors)
        context = adapter_for(StubProcess(999)).protection_context()
        status, reason = ProcessBlocker(adapter)._decision(snapshot, AppConfig(block_exes=("game.exe",)), context)
        self.assertEqual(status, "unavailable")
        self.assertEqual(reason, "protection_metadata_unavailable")

    def test_confirmed_absent_parent_deeper_in_chain_keeps_living_ancestry(self):
        parent = StubProcess(50, "launcher.exe", ppid=40)
        p = StubProcess(100, parent=parent)
        snapshot = adapter_for(p).inspect_fresh(100).snapshot
        self.assertEqual(snapshot.ancestors[0].identity.pid, 50)
        self.assertNotIn("ancestors", snapshot.errors)

    def test_reused_parent_pid_newer_than_child_is_not_an_ancestor(self):
        p = StubProcess(100, ppid=50)
        replacement = StubProcess(50, "Code.exe")
        replacement.values["create_time"] = 9999.0
        adapter = adapter_for(p, replacement)
        snapshot = adapter.inspect_fresh(100).snapshot
        self.assertNotIn("ancestors", snapshot.errors)
        self.assertEqual(snapshot.ancestors, ())
        self.assertEqual(replacement.actions, [])

    def test_unknown_parent_permission_and_creation_time_stay_unsafe(self):
        for denial in ("Process", "create_time", "is_running"):
            p = StubProcess(100, ppid=50)
            former = StubProcess(50)
            adapter = adapter_for(p, former)
            if denial == "Process":
                adapter.psutil.processes[50] = psutil.AccessDenied(50)
            else:
                former.denied.add(denial)
            self.assertIn("ancestors", adapter.inspect_fresh(100).snapshot.errors)

    def test_missing_parent_disappears_during_lifetime_probe_is_safe_end(self):
        p = StubProcess(100, ppid=50)
        former = StubProcess(50)
        former.gone_at.add("create_time")
        snapshot = adapter_for(p, former).inspect_fresh(100).snapshot
        self.assertNotIn("ancestors", snapshot.errors)

    def test_parent_permission_failure_and_reused_identity_are_incomplete(self):
        for variant in ("denied", "gone"):
            parent = StubProcess(50, "launcher.exe")
            p = StubProcess(100, parent=parent)
            if variant == "denied":
                p.denied.add("parent")
            else:
                parent.alive = False
            snapshot = adapter_for(p).inspect_fresh(100).snapshot
            self.assertIn("ancestors", snapshot.errors)

    def test_cycle_in_ancestry_is_incomplete(self):
        p = StubProcess(100)
        p.parent_process = p
        p.parent_pid = 100
        snapshot = adapter_for(p).inspect_fresh(100).snapshot
        self.assertIn("ancestors", snapshot.errors)

    def test_own_ancestry_and_resolved_windows_root_build_context(self):
        parent = StubProcess(50, "powershell.exe")
        own = StubProcess(999, parent=parent)
        adapter = adapter_for(own)
        context = adapter.protection_context()
        self.assertEqual(context.own_pid, 999)
        self.assertEqual({i.pid for i in context.identities}, {999, 50})
        self.assertEqual(context.windows_directory, r"C:\Windows")

    def test_incomplete_own_ancestry_is_global_error(self):
        own = StubProcess(999, ppid=50)
        with self.assertRaises(ProcessBlockerError):
            adapter_for(own, StubProcess(50)).protection_context()

    def test_own_chain_ending_in_exited_initialization_parent_is_usable(self):
        explorer = StubProcess(50, "explorer.exe", ppid=40)
        own = StubProcess(999, parent=explorer)
        context = adapter_for(own).protection_context()
        self.assertEqual({i.pid for i in context.identities}, {999, 50})

    def test_own_identity_permission_failure_is_global(self):
        own = StubProcess(999)
        own.denied.add("create_time")
        with self.assertRaises(ProcessBlockerError):
            adapter_for(own).protection_context()

    def test_identity_changed_during_inspection_cannot_be_actionable(self):
        p = StubProcess(100)
        p.alive = False
        snapshot = adapter_for(p).inspect_fresh(100).snapshot
        self.assertTrue(snapshot.gone)
        p.alive = True
        p.denied.add("is_running")
        snapshot = adapter_for(p).inspect_fresh(100).snapshot
        self.assertIsNone(snapshot.identity)

    def test_variables_resolved_without_invented_installation(self):
        adapter = adapter_for()
        with patch.dict(os.environ, {"FOCUS_TEST_ROOT": r"D:\Chosen"}):
            self.assertEqual(adapter.resolve_path(r"%FOCUS_TEST_ROOT%\Games"), r"D:\Chosen\Games")
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(ProcessUnavailable):
                adapter.resolve_path(r"%FOCUS_TEST_ROOT%\Games")

    def test_path_resolver_must_supply_verifiable_absolute_destination(self):
        adapter = adapter_for()
        for source in (r"Games\foo.exe", r"C:foo.exe", r"\Games\foo.exe", r"C:\Games\*.exe", r"\\?\C:\Games\foo.exe", r"\\.\Device\foo.exe"):
            with self.subTest(source=source), self.assertRaises(ProcessUnavailable):
                adapter.resolve_path(source)
        adapter._resolver = lambda value: "relative"
        with self.assertRaises(ProcessUnavailable):
            adapter.resolve_path(r"C:\Games")

    def test_strict_resolution_errors_propagate_for_target_preservation(self):
        adapter = PsutilAdapter(psutil_module=FakePsutil())
        with patch("core.proc_blocker.Path.resolve", side_effect=PermissionError()) as resolver:
            with self.assertRaises(PermissionError):
                adapter.resolve_path(r"C:\UnreadableJunction")
            resolver.assert_called_once_with(strict=True)

    def test_signal_uses_bound_identity_and_translates_permission_failure(self):
        p = StubProcess(100)
        adapter = adapter_for(p)
        ref = adapter.inspect_fresh(100)
        adapter.terminate(ref)
        adapter.kill(ref)
        self.assertEqual(p.actions, ["terminate", "kill"])
        p.denied.add("terminate")
        with self.assertRaises(ProcessUnavailable):
            adapter.terminate(ref)

    def test_signal_never_uses_recycled_or_unknown_identity(self):
        p = StubProcess(100)
        adapter = adapter_for(p)
        ref = adapter.inspect_fresh(100)
        p.values["create_time"] = 9999.0
        with self.assertRaises(ProcessGone):
            adapter.terminate(ref)
        p.alive = False
        with self.assertRaises(ProcessGone):
            adapter.kill(ref)
        unknown = ProcessReference(ProcessSnapshot(100), p)
        with self.assertRaises(ProcessUnavailable):
            adapter.terminate(unknown)
        self.assertEqual(p.actions, [])

    def test_psutil_no_such_process_during_signal_translates_without_success(self):
        p = StubProcess(100)
        adapter = adapter_for(p)
        ref = adapter.inspect_fresh(100)
        p.gone_at.add("terminate")
        with self.assertRaises(ProcessGone):
            adapter.terminate(ref)
        self.assertEqual(p.actions, [])

    def test_installed_collective_wait_zero_uses_original_fake_references(self):
        gone, alive, denied = StubProcess(100), StubProcess(101), StubProcess(102)
        adapter = adapter_for(gone, alive, denied)
        refs = tuple(adapter.inspect_fresh(p.pid) for p in (gone, alive, denied))
        gone.confirm_exit = True
        denied.denied.add("wait")
        outcome = adapter.wait_many(refs, 0.0)
        self.assertEqual(outcome.gone, (refs[0],))
        self.assertEqual(outcome.alive, (refs[1],))
        self.assertEqual(outcome.unavailable, (refs[2],))
        self.assertEqual([p.actions for p in (gone, alive, denied)], [[], [], []])

    def test_wait_unavailable_identity_cannot_be_reported_gone(self):
        p = StubProcess(100)
        adapter = adapter_for(p)
        ref = adapter.inspect_fresh(100)
        p.denied.add("is_running")
        outcome = adapter.wait_many((ref,), 0.0)
        self.assertEqual(outcome.gone, ())
        self.assertEqual(outcome.unavailable, (ref,))

    def test_original_reused_pid_is_confirmed_without_signalling_replacement(self):
        p = StubProcess(100)
        adapter = adapter_for(p)
        ref = adapter.inspect_fresh(100)
        p.alive = False
        replacement = StubProcess(100)
        adapter.psutil.processes[100] = replacement
        outcome = adapter.wait_many((ref,), 0.0)
        self.assertEqual(outcome.gone, (ref,))
        self.assertEqual(replacement.actions, [])
        self.assertEqual(adapter.psutil.process_calls, [100])

    def test_wait_keyboard_interrupt_is_not_swallowed(self):
        p = StubProcess(100)
        adapter = adapter_for(p)
        ref = adapter.inspect_fresh(100)
        def interrupted(timeout):
            raise KeyboardInterrupt()
        p.wait = interrupted
        with self.assertRaises(KeyboardInterrupt):
            adapter.wait_many((ref,), 0.0)


if __name__ == "__main__":
    unittest.main()

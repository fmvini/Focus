"""Supervisor com processos simulados; nenhum GUI ou benchmark."""

import hashlib
import json
from pathlib import Path
import shutil
import signal
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from tools.measure_gui import Dependencies, cleanup, collect, parser, validate, verify_owned


class SupervisorTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / ".qa" / f"supervisor-tests-{uuid4().hex}"
        self.root.mkdir(exist_ok=False)
        self.addCleanup(self.remove_root)
        self.options = parser().parse_args(["--runtime", sys.executable, "--idle", "1", "--interval", "0.1"])
        self.cleanups = []
        self.sample_reads = 0
        self.ready_mode = "valid"
        self.report_mode = "valid"
        self.return_code = 0
        self.change_fixture = False
        self.ownership_error = False
        self.change_sources = False
        self.metadata_reads = 0
        self.metadata_error = False
        self.initial_metadata_error = False
        self.interrupt_samples = False
        self.child_ended = True
        self.now = 0

        class Artifacts:
            def create_run(inner, workspace, out_parent):
                self.run_dir = self.root / f"run-{uuid4().hex}"
                self.run_dir.mkdir()
                return self.run_dir

            def make_fixture(inner, run_dir, rules):
                path = run_dir / "config.json"
                path.write_bytes(b'{"windows": []}\n')
                return path

            def file_sha256(inner, path):
                return hashlib.sha256(path.read_bytes()).hexdigest()

            def write_json(inner, path, data):
                with path.open("x", encoding="utf-8") as stream:
                    json.dump(data, stream, allow_nan=False)

            def write_jsonl(inner, path, data):
                with path.open("x", encoding="utf-8") as stream:
                    for record in data:
                        stream.write(json.dumps(record, allow_nan=False) + "\n")

        self.artifacts = Artifacts()
        self.deps = Dependencies(self.artifacts, self.sampler, self.summary, metadata=self.metadata,
                                 launch=self.launch, verify_owned=self.verify_owned,
                                 cleanup=self.cleanup_process, await_target_exit=self.target_exit,
                                 clock_ns=self.clock, sleep=lambda delay: None)

    def remove_root(self):
        qa = Path(__file__).resolve().parents[1] / ".qa"
        if self.root.resolve().parent != qa.resolve() or self.root.is_symlink() or self.root.is_junction():
            raise ValueError("unexpected test cleanup path")
        shutil.rmtree(self.root)

    def clock(self):
        self.now += 100_000_000
        return self.now

    def metadata(self):
        self.metadata_reads += 1
        if self.initial_metadata_error and self.metadata_reads == 1:
            raise OSError("initial metadata unavailable")
        if self.metadata_error and self.metadata_reads == 2:
            raise OSError("source removed during final hashing")
        return {"logical_cpus": 8, "source_hashes": {"source": str(self.metadata_reads) if self.change_sources else "frozen"}}

    def launch(self, command, **kwargs):
        self.command = command
        kwargs["stderr"].write(b"synthetic diagnostic\n")
        self.identity = {"pid": 401, "create_time": 123.5}
        if self.ready_mode != "missing":
            ready = {"ok": True, "profile": self.options.profile, "rules": self.options.rules, **self.identity}
            if self.options.query != "none":
                ready.update(query_mode=self.options.query, query_schema_version=1)
                if self.ready_mode == "missing_query":
                    del ready["query_mode"]
                elif self.ready_mode == "wrong_query":
                    ready["query_mode"] = "single"
                elif self.ready_mode == "bool_query_schema":
                    ready["query_schema_version"] = True
            if self.ready_mode == "invalid":
                ready["pid"] = True
            self.artifacts.write_json(self.run_dir / "ready.json", ready)
        report = {"ok": True, "profile": self.options.profile, **self.identity,
                  "idle_begin_ns": 0, "idle_end_ns": 1_000_000_000,
                  "closed": True, "tray_alive": False, "after_info": [], "errors": [],
                  "invariants": {"checks": {"zero_starts": True, "bytes": True}}}
        if self.options.query != "none":
            from tests.test_perf_query import events
            from tools.perf_query import summarize_query
            packets = []
            for mode in (self.options.query, "reset"):
                writes, renders = events(mode, self.options.rules)
                if mode == "reset":
                    for record in writes + renders:
                        for key, value in record.items():
                            if key.endswith("_ns") and value is not None:
                                record[key] += 10_000_000_000
                        record["revision"] += 100
                packets.append(dict(query_schema_version=1, mode=mode, status="complete",
                                    writes=writes, renders=renders,
                                    summary=summarize_query(writes, renders, mode, self.options.rules),
                                    data_checks={key: True for key in ("bytes", "draft", "baseline", "model",
                                                "baseline_model", "history_empty", "clean", "zero_starts")}))
            report["query"] = {"query_schema_version": 1, "mode": self.options.query, "complete": True,
                               "packets": packets, "partial": None}
            if self.report_mode == "bad_query":
                report["query"]["packets"][-1]["summary"]["ok"] = False
            elif self.report_mode == "missing_query_events":
                del packets[0]["writes"]
            elif self.report_mode == "query_summary_only":
                packets[0]["summary"] = {"ok": True}
            elif self.report_mode == "query_checks_only_bytes":
                packets[0]["data_checks"] = {"bytes": True}
            elif self.report_mode == "query_summary_tampered":
                packets[0]["summary"]["last_write_to_observation_ns"] += 1
            elif self.report_mode == "query_float_schema":
                packets[0]["query_schema_version"] = 1.0
        if self.report_mode == "failed":
            report.update(ok=False, errors=["NIM_ADD"])
        elif self.report_mode == "wrong_identity":
            report["create_time"] = 124.5
        elif self.report_mode == "teardown":
            report["after_info"] = ["owned-timer"]
        elif self.report_mode == "missing_timers":
            del report["after_info"]
        elif self.report_mode == "false_timers":
            report["after_info"] = 0
        elif self.report_mode == "text_timers":
            report["after_info"] = ""
        self.pending_report = report
        self.report_published = False
        if self.change_fixture:
            (self.run_dir / "config.json").write_bytes(b"changed externally")
        self.process = SimpleNamespace(pid=400, poll=self.poll, wait=lambda timeout: self.return_code)
        self.poll_count = 0
        return self.process

    def poll(self):
        self.poll_count += 1
        if self.ready_mode == "missing":
            return None
        if self.poll_count > 3 and not self.report_published:
            self.artifacts.write_json(self.run_dir / "report.json", self.pending_report)
            self.report_published = True
        return None if self.poll_count <= 3 else self.return_code

    def verify_owned(self, process, ready):
        if self.ownership_error:
            raise ValueError("foreign PID")
        return self.identity

    def cleanup_process(self, process, identity):
        self.cleanups.append(identity)
        return []

    def target_exit(self, identity, timeout):
        self.assertEqual(identity, self.identity)
        return {"ended": self.child_ended}

    def sampler(self, pid, create_time):
        self.assertEqual((pid, create_time), (401, 123.5))
        return SimpleNamespace(read=self.sample)

    def sample(self):
        self.sample_reads += 1
        if self.interrupt_samples and self.sample_reads == 2:
            raise KeyboardInterrupt()
        return {"ok": True, "seq": self.sample_reads}

    def summary(self, records, begin, end, logical):
        self.assertEqual((begin, end, logical), (0, 1_000_000_000, 8))
        return {"ok": len(records) >= 2, "used": len(records)}

    def test_completed_run_preserves_raw_evidence_identity_and_fixture(self):
        result = collect(self.options, self.deps)
        self.assertTrue(result["ok"], result)
        self.assertFalse(result["rnf_accepted"])
        self.assertEqual(result["samples_count"], 3)
        self.assertEqual(result["config_sha256_before"], result["config_sha256_after"])
        self.assertTrue(result["sources_unchanged"])
        self.assertEqual(self.cleanups, [])
        manifest = json.loads((self.run_dir / "manifest.json").read_text())
        self.assertEqual(manifest["worker_command"], self.command)
        self.assertEqual(manifest["profile"], "H-F")
        self.assertEqual((self.run_dir / "stderr.log").read_bytes(), b"synthetic diagnostic\n")
        self.assertEqual(len((self.run_dir / "samples.jsonl").read_text().splitlines()), 3)
        self.assertEqual(json.loads((self.run_dir / "summary.json").read_text()), result)

    def test_invalid_or_foreign_identity_never_samples_that_pid(self):
        for mode in ("invalid", "foreign"):
            with self.subTest(mode=mode):
                self.ready_mode = "invalid" if mode == "invalid" else "valid"
                self.ownership_error = mode == "foreign"
                result = collect(self.options, self.deps)
                self.assertFalse(result["ok"])
                self.assertEqual(result["samples_count"], 0)
                self.assertEqual(self.cleanups[-1], None)
        self.assertEqual(self.sample_reads, 0)

    def test_worker_failure_or_unfinished_teardown_is_not_success(self):
        for mode in ("failed", "teardown", "wrong_identity", "missing_timers", "false_timers", "text_timers"):
            with self.subTest(mode=mode):
                self.report_mode = mode
                result = collect(self.options, self.deps)
                self.assertFalse(result["ok"])
                self.assertTrue(result["errors"])
                self.assertEqual(result["samples_count"], 3)
                self.poll_count = 0
        self.assertEqual(len(self.cleanups), 6)

    def test_startup_timeout_conserves_artifacts_and_has_no_target_identity(self):
        self.ready_mode = "missing"
        self.options.startup_timeout = 0.25
        result = collect(self.options, self.deps)
        self.assertFalse(result["ok"])
        self.assertTrue(any("TimeoutError" in error for error in result["errors"]))
        self.assertEqual(result["samples_count"], 0)
        self.assertEqual(self.cleanups, [None])
        self.assertTrue((self.run_dir / "manifest.json").exists())
        self.assertTrue((self.run_dir / "summary.json").exists())

    def test_config_or_source_change_invalidates_completed_run(self):
        for change in ("fixture", "source"):
            with self.subTest(change=change):
                self.change_fixture = change == "fixture"
                self.change_sources = change == "source"
                result = collect(self.options, self.deps)
                self.assertFalse(result["ok"])
                self.assertTrue(any("alterad" in error for error in result["errors"]))

    def test_final_metadata_failure_still_writes_raw_and_failed_summary(self):
        self.metadata_error = True
        result = collect(self.options, self.deps)
        self.assertFalse(result["ok"])
        self.assertEqual(result["samples_count"], 3)
        self.assertIsNone(result["sources_unchanged"])
        self.assertTrue(any("metadados finais" in error for error in result["errors"]))
        self.assertEqual(len((self.run_dir / "samples.jsonl").read_text().splitlines()), 3)
        self.assertEqual(json.loads((self.run_dir / "summary.json").read_text()), result)

    def test_initial_metadata_failure_preserves_structured_preparation_result(self):
        self.initial_metadata_error = True
        result = collect(self.options, self.deps)
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "preparation")
        self.assertEqual((self.run_dir / "samples.jsonl").read_bytes(), b"")
        self.assertTrue((self.run_dir / "manifest.json").exists())
        self.assertEqual(json.loads((self.run_dir / "summary.json").read_text()), result)
        self.assertFalse(hasattr(self, "process"))

    def test_keyboard_interrupt_retains_completed_samples_and_cleans_owned_process(self):
        self.interrupt_samples = True
        result = collect(self.options, self.deps)
        self.assertFalse(result["ok"])
        self.assertTrue(result["interrupted"])
        self.assertEqual(result["samples_count"], 1)
        self.assertEqual(self.cleanups, [self.identity])
        self.assertEqual(len((self.run_dir / "samples.jsonl").read_text().splitlines()), 1)
        self.assertEqual(json.loads((self.run_dir / "summary.json").read_text()), result)

    def test_config_stat_failure_is_preparation_failure_with_empty_raw(self):
        original = Path.stat
        def failing_stat(path, *args, **kwargs):
            if path.name == "config.json" and path.is_relative_to(self.root):
                raise OSError("config stat denied")
            return original(path, *args, **kwargs)
        with patch.object(Path, "stat", failing_stat):
            result = collect(self.options, self.deps)
        self.assertFalse(result["ok"])
        self.assertEqual(result["stage"], "preparation")
        self.assertEqual((self.run_dir / "samples.jsonl").read_bytes(), b"")
        self.assertFalse(hasattr(self, "process"))

    def test_final_hash_interrupt_does_not_lose_raw(self):
        original = self.artifacts.file_sha256
        hashes = []
        def interrupted_hash(path):
            hashes.append(path)
            if len(hashes) == 2:
                raise KeyboardInterrupt()
            return original(path)
        self.artifacts.file_sha256 = interrupted_hash
        result = collect(self.options, self.deps)
        self.assertTrue(result["interrupted"])
        self.assertFalse(result["ok"])
        self.assertEqual(result["samples_count"], 3)
        self.assertEqual(len((self.run_dir / "samples.jsonl").read_text().splitlines()), 3)

    def test_sigint_during_retention_is_shielded_then_original_handler_restored(self):
        original_writer = self.artifacts.write_jsonl
        previous = signal.getsignal(signal.SIGINT)
        def publishing(path, records):
            signal.raise_signal(signal.SIGINT)
            original_writer(path, records)
        self.artifacts.write_jsonl = publishing
        result = collect(self.options, self.deps)
        self.assertTrue(result["ok"], result)
        self.assertEqual(signal.getsignal(signal.SIGINT), previous)
        self.assertEqual(json.loads((self.run_dir / "summary.json").read_text()), result)

    def test_launcher_exit_does_not_hide_a_living_measured_child(self):
        self.child_ended = False
        result = collect(self.options, self.deps)
        self.assertFalse(result["ok"])
        self.assertEqual(result["target_exit"], {"ended": False})
        self.assertTrue(any("PID medido" in error for error in result["errors"]))
        self.assertEqual(self.cleanups, [self.identity])

    def test_parameters_rejected_before_creating_run_or_launching_worker(self):
        for name, invalid in (("idle", 0), ("interval", -1), ("warmup", float("nan")),
                              ("finish_timeout", True), ("rules", True), ("profile", "G-R")):
            with self.subTest(name=name):
                options = SimpleNamespace(**vars(self.options))
                setattr(options, name, invalid)
                with self.assertRaises(ValueError):
                    validate(options)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_query_relay_and_failed_reset_invalidate_supervisor(self):
        self.options.profile, self.options.query = "G-P", "burst"
        result = collect(self.options, self.deps)
        self.assertTrue(result["ok"], result)
        self.assertEqual(self.command[-2:], ["--query", "burst"])
        self.report_mode = "bad_query"
        result = collect(self.options, self.deps)
        self.assertFalse(result["ok"])
        self.assertTrue(any("consulta/reset" in error for error in result["errors"]))

    def test_query_profile_rejection_before_run_registration(self):
        self.options.query = "single"
        with self.assertRaisesRegex(ValueError, "G-P"):
            collect(self.options, self.deps)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_query_ready_requires_mode_and_integer_schema_before_sampling(self):
        self.options.profile, self.options.query = "G-P", "burst"
        for mode in ("missing_query", "wrong_query", "bool_query_schema"):
            with self.subTest(mode=mode):
                self.ready_mode = mode
                result = collect(self.options, self.deps)
                self.assertFalse(result["ok"])
                self.assertEqual(result["samples_count"], 0)
                self.assertTrue(any("modo/schema" in error for error in result["errors"]))

    def test_query_report_needs_events_full_checks_and_recomputed_summary(self):
        self.options.profile, self.options.query = "G-P", "burst"
        for mode in ("missing_query_events", "query_summary_only", "query_checks_only_bytes",
                     "query_summary_tampered", "query_float_schema"):
            with self.subTest(mode=mode):
                self.report_mode = mode
                result = collect(self.options, self.deps)
                self.assertFalse(result["ok"])
                self.assertTrue(any("consulta/reset" in error for error in result["errors"]))

    def test_ownership_uses_fresh_identity_and_optional_metadata_can_be_denied(self):
        class Denied(Exception):
            pass
        first = SimpleNamespace(pid=401, ppid=lambda: 400, create_time=lambda: 123.5,
                                exe=Mock(side_effect=Denied("exe denied")), cpu_affinity=lambda: [0, 1])
        fresh = SimpleNamespace(ppid=lambda: 400, create_time=lambda: 123.5)
        psutil = SimpleNamespace(Process=Mock(side_effect=[first, fresh]), Error=Denied)
        with patch.dict(sys.modules, psutil=psutil):
            identity = verify_owned(SimpleNamespace(pid=400), {"pid": 401, "create_time": 123.5})
        self.assertEqual(psutil.Process.call_count, 2)
        self.assertEqual(identity["pid"], 401)
        self.assertIsNone(identity["exe"])
        self.assertEqual(identity["affinity"], [0, 1])
        self.assertEqual(len(identity["metadata_errors"]), 1)
        fresh.create_time = lambda: 124.5
        psutil.Process = Mock(side_effect=[first, fresh])
        with patch.dict(sys.modules, psutil=psutil), self.assertRaisesRegex(ValueError, "mudou"):
            verify_owned(SimpleNamespace(pid=400), {"pid": 401, "create_time": 123.5})

    def test_cleanup_refuses_reused_child_and_never_terminates_it(self):
        class Missing(Exception):
            pass
        class PsError(Exception):
            pass
        target = SimpleNamespace(create_time=lambda: 999.0, ppid=lambda: 400, terminate=Mock())
        launcher = SimpleNamespace(pid=400, poll=lambda: 0, terminate=Mock())
        psutil = SimpleNamespace(Process=lambda pid: target, Error=PsError, NoSuchProcess=Missing)
        with patch.dict(sys.modules, psutil=psutil):
            details = cleanup(launcher, {"pid": 401, "create_time": 123.5})
        target.terminate.assert_not_called()
        launcher.terminate.assert_not_called()
        self.assertTrue(any("recusado" in detail for detail in details))


if __name__ == "__main__":
    unittest.main()

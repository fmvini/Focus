"""Metrics tests use synthetic identities, clocks and counters, never the OS."""

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from tools.perf_metrics import ProcessSampler, summarize


NS = 1_000_000_000


class AccessDenied(Exception):
    pass


class NoSuchProcess(Exception):
    pass


def sample(at, *, user=1.0, system=0.5, **changes):
    result = {
        "ok": True, "pid": 42, "create_time": 123.5,
        "read_start_ns": at - 10, "read_end_ns": at + 10, "mono_ns": at,
        "user_s": user, "system_s": system, "rss_bytes": 80_000_000,
        "peak_wset_bytes": 90_000_000, "private_bytes": 100_000_000,
        "vms_bytes": 100_000_000, "error": None, "errors": [],
    }
    result.update(changes)
    return result


class ProcessSamplerTests(unittest.TestCase):
    def process(self, *, identity=123.5, pid=42):
        return SimpleNamespace(
            pid=pid, create_time=Mock(return_value=identity),
            cpu_times=Mock(return_value=SimpleNamespace(user=1.25, system=0.5)),
            memory_info=Mock(return_value=SimpleNamespace(
                rss=80_000_000, peak_wset=90_000_000, private=100_000_000, vms=100_000_000)),
        )

    def read(self, before, after=None, *, clocks=(100, 110, 130, 200)):
        factory = Mock(side_effect=[before, after or self.process()])
        module = SimpleNamespace(Process=factory)
        with patch("tools.perf_metrics.import_module", return_value=module), \
                patch("tools.perf_metrics.perf_counter_ns", side_effect=clocks):
            result = ProcessSampler(42, 123.5).read()
        return result, factory

    def test_import_constructor_and_pure_summary_do_not_import_psutil_or_gui(self):
        # Load a separate module while all external dependency imports fail.
        spec = importlib.util.spec_from_file_location(
            "metrics_lazy_probe", Path(__file__).parents[1] / "tools" / "perf_metrics.py")
        module = importlib.util.module_from_spec(spec)
        import_builtin = __import__
        attempted = []

        def guarded(name, *args, **kwargs):
            if name.split(".")[0] in {"psutil", "tkinter", "customtkinter", "pystray"}:
                attempted.append(name)
                raise AssertionError("External dependency at import time")
            return import_builtin(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=guarded), \
                patch("importlib.import_module", side_effect=AssertionError("Dynamic import")):
            spec.loader.exec_module(module)
            module.ProcessSampler(42, 123.5)
            self.assertFalse(module.summarize([], 0, NS, None)["ok"])
        self.assertEqual(attempted, [])

    def test_raw_read_midpoint_of_cpu_not_entire_read_and_fresh_identity(self):
        before = self.process()
        after = self.process()
        result, factory = self.read(before, after)
        self.assertTrue(result["ok"])
        self.assertEqual(result["pid"], 42)
        self.assertEqual(result["create_time"], 123.5)
        self.assertEqual((result["read_start_ns"], result["mono_ns"], result["read_end_ns"]), (100, 120, 200))
        self.assertEqual((result["user_s"], result["system_s"]), (1.25, 0.5))
        self.assertEqual(result["rss_bytes"], 80_000_000)
        self.assertEqual(result["peak_wset_bytes"], 90_000_000)
        self.assertEqual(result["private_bytes"], result["vms_bytes"])
        self.assertEqual(factory.call_args_list, [unittest.mock.call(42), unittest.mock.call(42)])
        before.create_time.assert_called_once_with()
        after.create_time.assert_called_once_with()
        after.cpu_times.assert_not_called()
        json.dumps(result, allow_nan=False)

    def test_identity_changed_before_read_precedes_all_counter_getters(self):
        for changes in ({"identity": 999.0}, {"identity": True}, {"pid": 7}):
            with self.subTest(changes=changes):
                before = self.process(**changes)
                result, factory = self.read(before, clocks=(100, 200))
                self.assertFalse(result["ok"])
                self.assertIn("identity", result["error"])
                self.assertEqual(factory.call_count, 1)
                before.cpu_times.assert_not_called()
                before.memory_info.assert_not_called()
                self.assertIsNone(result["user_s"])
                self.assertIsNone(result["rss_bytes"])

    def test_identity_race_after_read_discards_all_provisional_counters(self):
        before, after = self.process(), self.process(identity=999.0)
        result, factory = self.read(before, after)
        self.assertFalse(result["ok"])
        self.assertEqual(result["errors"][0]["stage"], "identity_after")
        self.assertEqual(factory.call_count, 2)
        before.cpu_times.assert_called_once_with()
        before.memory_info.assert_called_once_with()
        for field in ("user_s", "system_s", "rss_bytes", "private_bytes", "vms_bytes", "peak_wset_bytes"):
            self.assertIsNone(result[field])

    def test_access_denied_and_disappearance_preserve_reasons_and_end_guard(self):
        for where in ("identity_before", "cpu", "memory", "identity_after"):
            for exception in (AccessDenied("denied"), NoSuchProcess("gone")):
                with self.subTest(where=where, exception=type(exception)):
                    before, after = self.process(), self.process()
                    owner = after if where == "identity_after" else before
                    attribute = {"identity_before": "create_time", "identity_after": "create_time",
                                 "cpu": "cpu_times", "memory": "memory_info"}[where]
                    getattr(owner, attribute).side_effect = exception
                    result, factory = self.read(before, after,
                                                clocks=(100, 200) if where == "identity_before" else (100, 110, 130, 200))
                    self.assertFalse(result["ok"])
                    self.assertIn(str(exception), result["error"])
                    self.assertEqual(result["errors"][0]["type"], type(exception).__name__)
                    self.assertEqual(result["errors"][0]["stage"], where)
                    self.assertIsNotNone(result["read_end_ns"])
                    self.assertEqual(factory.call_count, 1 if where == "identity_before" else 2)
        before, after = self.process(), self.process(identity=999)
        before.cpu_times.side_effect = AccessDenied("first failure")
        result, _ = self.read(before, after)
        self.assertEqual([item["stage"] for item in result["errors"]], ["cpu", "identity_after"])
        self.assertIsNone(result["rss_bytes"])

    def test_missing_psutil_returns_error_without_zero_counters(self):
        with patch("tools.perf_metrics.import_module", side_effect=ModuleNotFoundError("psutil")), \
                patch("tools.perf_metrics.perf_counter_ns", side_effect=(100, 200)):
            result = ProcessSampler(42, 123.5).read()
        self.assertFalse(result["ok"])
        self.assertIn("ModuleNotFoundError", result["error"])
        self.assertIsNone(result["user_s"])
        self.assertIsNone(result["rss_bytes"])

    def test_missing_windows_fields_are_none_not_rss_or_vms_aliases(self):
        before = self.process()
        before.memory_info.return_value = SimpleNamespace(rss=80_000_000, vms=90_000_000)
        result, _ = self.read(before)
        self.assertTrue(result["ok"])
        self.assertIsNone(result["private_bytes"])
        self.assertIsNone(result["peak_wset_bytes"])
        self.assertEqual(result["rss_bytes"], 80_000_000)
        self.assertEqual(result["vms_bytes"], 90_000_000)

    def test_constructor_rejects_coerced_types_and_nonfinite_identity(self):
        for pid in (True, False, "42", 42.0, 0, -1, None):
            with self.subTest(pid=pid), self.assertRaises(ValueError):
                ProcessSampler(pid, 123.5)
        for identity in (True, "123.5", -1, None, float("nan"), float("inf"), 10**1000):
            with self.subTest(identity=identity), self.assertRaises(ValueError):
                ProcessSampler(42, identity)

    def test_invalid_counter_types_and_clock_are_records_not_measurements(self):
        for value in (True, "1", -1, float("nan"), float("inf")):
            with self.subTest(cpu=value):
                before = self.process()
                before.cpu_times.return_value = SimpleNamespace(user=value, system=0)
                result, _ = self.read(before)
                self.assertFalse(result["ok"])
                self.assertIn("user_s", result["error"])
        for value in (True, 1.0, "1", -1, float("nan"), 10**1000):
            with self.subTest(memory=value):
                before = self.process()
                before.memory_info.return_value.rss = value
                result, _ = self.read(before)
                self.assertFalse(result["ok"])
                self.assertIn("rss_bytes", result["error"])
        for clocks in ((100, 90, 130, 200), (100, 110, 90, 200), (100, 110, 130, 120),
                       (100, True, 200), (True, 200)):
            with self.subTest(clocks=clocks):
                result, _ = self.read(self.process(), clocks=clocks)
                self.assertFalse(result["ok"])
                self.assertIn("clock", result["error"].lower())


class SummaryTests(unittest.TestCase):
    def summarize(self, samples, *, logical=8):
        return summarize(samples, 0, 10 * NS, logical)

    def test_cpu_uses_actual_idle_coverage_and_both_denominators(self):
        records = [sample(2 * NS, user=10, system=2),
                   sample(8 * NS, user=10.045, system=2.015)]
        result = self.summarize(records)
        self.assertTrue(result["ok"])
        self.assertEqual(result["coverage_wall_s"], 6)
        self.assertEqual(result["coverage_fraction"], 0.6)
        self.assertAlmostEqual(result["delta_cpu_s"], 0.06)
        self.assertAlmostEqual(result["cpu_pct_1_logico"], 1)
        self.assertAlmostEqual(result["cpu_pct_total_maquina"], 0.125)
        self.assertEqual(result["coverage_begin_ns"], 2 * NS)
        self.assertEqual(result["coverage_end_ns"], 8 * NS)
        self.assertEqual(result["mode"], "exploratory")
        self.assertNotIn("rnf01_accepted", result)

    def test_ram_absolute_exact_bytes_conversions_and_lifetime_peak(self):
        result = self.summarize([sample(NS, rss_bytes=80_000_000),
                                 sample(9 * NS, rss_bytes=83_886_080)])
        rss = result["ram"]["rss_bytes"]
        self.assertEqual(rss["min_bytes"], 80_000_000)
        self.assertEqual(rss["max_bytes"], 83_886_080)
        self.assertEqual(rss["min_mb"], 80)
        self.assertEqual(rss["max_mib"], 80)
        self.assertEqual(rss["mean_bytes"], 81_943_040)
        self.assertEqual(rss["median_bytes"], 81_943_040)
        self.assertEqual(result["rss_sampled_peak_bytes"], 83_886_080)
        self.assertEqual(result["peak_wset_lifetime_bytes"], 90_000_000)
        self.assertEqual(result["ram"]["private_bytes"]["max_mb"], 100)

    def test_only_wholly_inside_reads_contribute_with_inclusive_boundaries(self):
        records = [sample(0, read_start_ns=-1), sample(NS, read_start_ns=0),
                   sample(9 * NS, read_end_ns=10 * NS),
                   sample(10 * NS, read_end_ns=10 * NS + 1)]
        # Negative ns is malformed, not a valid outside sample.
        result = self.summarize(records)
        self.assertEqual(result["samples_valid"], 2)
        self.assertEqual(result["samples_outside_idle"], 1)
        self.assertEqual(result["coverage_wall_s"], 8)
        self.assertEqual(len(result["errors"]), 1)
        outside = sample(11 * NS, rss_bytes=999_999_999, peak_wset_bytes=999_999_999)
        result = self.summarize([sample(NS), sample(9 * NS), outside])
        self.assertTrue(result["ok"])
        self.assertEqual(result["ram"]["rss_bytes"]["count"], 2)
        self.assertEqual(result["rss_sampled_peak_bytes"], 80_000_000)

    def test_invalid_samples_and_errors_preserved_and_inputs_unchanged(self):
        failed = sample(3 * NS, ok=False, error="AccessDenied: raw denial", user_s=999,
                        errors=[{"type": "AccessDenied", "message": "raw denial"}])
        records = [sample(NS), failed, sample(9 * NS), sample(11 * NS, ok=False, error="gone")]
        before = copy.deepcopy(records)
        result = self.summarize(iter(records))
        self.assertFalse(result["ok"])
        self.assertEqual(result["samples_total"], 4)
        self.assertEqual(result["samples_valid"], 2)
        self.assertEqual([item["error"] for item in result["errors"]], ["AccessDenied: raw denial", "gone"])
        self.assertEqual(result["errors"][0]["sample"], failed)
        self.assertEqual(result["delta_cpu_s"], 0)
        self.assertEqual(records, before)
        json.dumps(result, allow_nan=False)

    def test_empty_single_missing_cpu_and_unknown_count_are_explicitly_insufficient(self):
        for records in ([], [sample(NS)], [sample(NS, user_s=None), sample(9 * NS, system_s=None)]):
            with self.subTest(records=records):
                result = self.summarize(records)
                self.assertFalse(result["ok"])
                self.assertIsNone(result["delta_cpu_s"])
                self.assertIsNone(result["coverage_wall_s"])
                self.assertIsNone(result["cpu_pct_1_logico"])
                self.assertTrue(result["insufficient"])
        result = self.summarize([sample(NS), sample(9 * NS)], logical=None)
        self.assertEqual(result["cpu_pct_1_logico"], 0)
        self.assertIsNone(result["cpu_pct_total_maquina"])
        self.assertFalse(result["ok"])

    def test_absent_windows_metrics_report_none_and_insufficient_without_aliases(self):
        records = [sample(NS, private_bytes=None, peak_wset_bytes=None),
                   sample(9 * NS, private_bytes=None, peak_wset_bytes=None)]
        result = self.summarize(records)
        self.assertFalse(result["ok"])
        self.assertIsNone(result["peak_wset_lifetime_bytes"])
        stats = result["ram"]["private_bytes"]
        self.assertEqual(stats["count"], 0)
        self.assertTrue(all(value is None for key, value in stats.items() if key != "count"))
        self.assertEqual(result["ram"]["vms_bytes"]["count"], 2)
        self.assertIn("No valid private_bytes samples inside idle", result["insufficient"])

    def test_mixed_identity_never_combines_deltas_or_memory(self):
        for changes in ({"pid": 43}, {"create_time": 124}):
            with self.subTest(changes=changes):
                result = self.summarize([sample(NS), sample(5 * NS, **changes), sample(9 * NS)])
                self.assertFalse(result["ok"])
                self.assertIsNone(result["delta_cpu_s"])
                self.assertEqual(result["ram"]["rss_bytes"]["count"], 2)
                self.assertIn("Mixed process identities", result["insufficient"])

    def test_decreasing_component_nonincreasing_and_overlap_not_sorted_or_hidden(self):
        cases = [
            [sample(NS, user=5, system=0), sample(9 * NS, user=4, system=10)],
            [sample(NS, user=0, system=5), sample(9 * NS, user=10, system=4)],
            [sample(9 * NS), sample(NS)],
            [sample(NS), sample(NS)],
            [sample(NS, read_end_ns=3 * NS), sample(2 * NS)],
            [sample(NS, user=5), sample(5 * NS, user=4, system_s=None), sample(9 * NS, user=6)],
            [sample(NS), sample(5 * NS, user_s=None, read_end_ns=9 * NS + 1), sample(9 * NS)],
        ]
        for records in cases:
            with self.subTest(records=records):
                result = self.summarize(records)
                self.assertFalse(result["ok"])
                self.assertIsNone(result["delta_cpu_s"])
                self.assertIsNone(result["cpu_pct_1_logico"])
                self.assertTrue(result["insufficient"])

    def test_cpu_above_one_logical_and_zero_deltas_are_not_clamped(self):
        result = self.summarize([sample(NS, user=0, system=0), sample(9 * NS, user=12, system=4)])
        self.assertEqual(result["cpu_pct_1_logico"], 200)
        self.assertEqual(result["cpu_pct_total_maquina"], 25)
        result = self.summarize([sample(NS), sample(9 * NS)])
        self.assertTrue(result["ok"])
        self.assertEqual(result["delta_cpu_s"], 0)
        self.assertEqual(result["cpu_pct_1_logico"], 0)

    def test_invalid_sample_types_timestamps_counters_and_bounds(self):
        for changes in ({"ok": 1}, {"pid": True}, {"create_time": float("nan")},
                        {"mono_ns": True}, {"read_start_ns": 2 * NS},
                        {"user_s": True}, {"system_s": float("inf")},
                        {"rss_bytes": 1.0}, {"private_bytes": -1}):
            with self.subTest(changes=changes):
                result = self.summarize([sample(NS, **changes), sample(9 * NS)])
                self.assertFalse(result["ok"])
                self.assertEqual(len(result["errors"]), 1)
                self.assertIsNone(result["delta_cpu_s"])
        for begin, end, logical in ((True, NS, 8), (0, 0, 8), (NS, 0, 8), (0, 1.0, 8),
                                    (0, NS, True), (0, NS, 0), (0, NS, 8.0), (0, NS, -1),
                                    (0, 10**1000, 8), (0, NS, 10**1000)):
            with self.subTest(bounds=(begin, end, logical)), self.assertRaises(ValueError):
                summarize([], begin, end, logical)
        result = self.summarize([None, sample(NS)])
        self.assertFalse(result["ok"])
        self.assertEqual(result["errors"][0]["sample"], None)

    def test_nonfinite_derived_cpu_is_unavailable_not_json_infinity(self):
        result = self.summarize([sample(NS, user=0, system=0),
                                 sample(9 * NS, user=1e308, system=1e308)])
        self.assertIsNone(result["cpu_pct_1_logico"])
        self.assertIn("CPU arithmetic is not finite", result["insufficient"])
        json.dumps(result, allow_nan=False)


if __name__ == "__main__":
    unittest.main()

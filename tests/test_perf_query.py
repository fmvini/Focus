"""Independent synthetic event oracles; never import a toolkit or probe."""

import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from tools.perf_query import QueryStep, query_plan, summarize_query


MS = 1_000_000
NS = 1_000_000_000
TEXTS = ("q", "qa", "qa-", "qa-0", "qa-00")


def writes_for(mode, *, gap_ns=None):
    texts = ("",) if mode == "reset" else ("qa-00",) if mode == "single" else TEXTS
    gap = (500 if mode == "spaced" else 50) * MS if gap_ns is None else gap_ns
    result = []
    begin = NS
    for index, query in enumerate(texts):
        result.append(dict(seq=index + 1, query=query, begin_ns=begin,
                           schedule_begin_ns=begin + 2, schedule_return_ns=begin + 4,
                           set_return_ns=begin + 6, revision=20 + index, ticket=40 + 2 * index,
                           timer_id=f"after-{index}", delay_ms=200,
                           callback_enter_ns=None, cancelled_ns=None))
        begin += 6 + gap
    return result


def rendered(write, rules, *, start_ns=None, observation_ns=None):
    write["callback_enter_ns"] = write["schedule_return_ns"] + 250 * MS
    start = write["callback_enter_ns"] + 17 if start_ns is None else start_ns
    returned = start + 30 * MS
    full = min(rules, 100) if write["query"] == "qa-00" else rules
    return dict(write_seq=write["seq"], revision=write["revision"], query=write["query"],
                ticket_original=write["ticket"], start_ns=start, return_ns=returned,
                observation_ns=returned + 2 * MS if observation_ns is None else observation_ns,
                settled=True, pending=False, timer_id=None, full_indices=list(range(full)),
                rows=min(25, full), page=0, page_count=max(1, (full + 24) // 25))


def events(mode="single", rules=1000):
    writes = writes_for(mode)
    if mode == "burst":
        for left, right in zip(writes, writes[1:]):
            left["cancelled_ns"] = right["begin_ns"] + 1
        renders = [rendered(writes[-1], rules)]
    else:
        renders = [rendered(write, rules) for write in writes]
    return writes, renders


class QueryPlanTests(unittest.TestCase):
    def test_explicit_public_plans_and_internal_reset_are_immutable_tuples(self):
        expected = {
            "none": (), "single": (QueryStep("qa-00", 0),), "reset": (QueryStep("", 0),),
            "burst": tuple(QueryStep(text, 0 if i == 0 else 50) for i, text in enumerate(TEXTS)),
            "spaced": tuple(QueryStep(text, 0 if i == 0 else 500) for i, text in enumerate(TEXTS)),
        }
        for mode, steps in expected.items():
            with self.subTest(mode=mode):
                result = query_plan(mode)
                self.assertIs(type(result), tuple)
                self.assertEqual(result, steps)
                for step in result:
                    self.assertIsInstance(step, QueryStep)
                    self.assertIs(type(step.query), str)
                    self.assertIs(type(step.delay_ms), int)
                    with self.assertRaises(AttributeError):
                        step.query = "altered"

    def test_invalid_mode_and_rules_fail_before_consuming_event_iterators(self):
        def unwanted():
            raise AssertionError("invalid parameters consumed events")
            yield
        for mode in (None, True, 1, "BURST", "unknown", [], b"single"):
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                summarize_query(unwanted(), unwanted(), mode, 100)
        for rules in (None, True, 100.0, "100", -1, 25, 1001):
            with self.subTest(rules=rules), self.assertRaises(ValueError):
                summarize_query(unwanted(), unwanted(), "single", rules)

    def test_import_and_summary_do_not_access_clock_io_or_external_dependencies(self):
        spec = importlib.util.spec_from_file_location("pure_query_probe", Path(__file__).parents[1] / "tools/perf_query.py")
        module = importlib.util.module_from_spec(spec)
        original_import = __import__
        attempted = []
        def guarded(name, *args, **kwargs):
            if name.split(".")[0] in {"tkinter", "customtkinter", "psutil", "time", "core", "ui"}:
                attempted.append(name)
                raise AssertionError("impure import")
            return original_import(name, *args, **kwargs)
        records = events()
        with patch("builtins.__import__", side_effect=guarded):
            spec.loader.exec_module(module)
            with patch("builtins.open", side_effect=AssertionError("IO")), \
                    patch("time.perf_counter_ns", side_effect=AssertionError("clock")), \
                    patch("time.sleep", side_effect=AssertionError("sleep")):
                self.assertTrue(module.summarize_query(*records, "single", 1000)["ok"])
        self.assertEqual(attempted, [])


class QuerySummaryTests(unittest.TestCase):
    def summarize(self, writes, renders, mode="single", rules=1000):
        return summarize_query(writes, renders, mode, rules)

    def assert_failed(self, result):
        self.assertFalse(result["ok"])
        self.assertTrue(result["errors"] or result["insufficient"])

    def test_single_exact_endpoint_math_does_not_subtract_200ms(self):
        writes, renders = events()
        result = self.summarize(writes, renders)
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["last_write_to_observation_ns"], 282 * MS + 21)
        self.assertEqual(result["first_write_to_observation_ns"], 282 * MS + 21)
        self.assertEqual(result["final_observation_ns"], renders[-1]["observation_ns"])
        self.assertEqual(result["final_revision"], 20)
        self.assertEqual(result["final_query"], "qa-00")
        write = result["write_timings"][0]
        self.assertEqual(write["set_call_ns"], 6)
        self.assertEqual(write["write_to_callback_ns"], 250 * MS + 4)
        self.assertEqual(write["callback_wait_ns"], 250 * MS)
        render = result["render_timings"][0]
        self.assertEqual(render["callback_to_render_ns"], 17)
        self.assertEqual(render["render_call_ns"], 30 * MS)
        self.assertEqual(render["layout_wait_ns"], 2 * MS)

    def test_burst_final_and_first_latency_actual_intervals_and_cancelled_intermediates(self):
        writes, renders = events("burst")
        result = self.summarize(writes, renders, "burst")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["requested_delays_ms"], [0, 50, 50, 50, 50])
        self.assertEqual(result["actual_intervals_ns"], [50 * MS + 6] * 4)
        self.assertEqual(result["actual_gaps_ns"], [50 * MS] * 4)
        self.assertEqual(result["last_write_to_observation_ns"], 282 * MS + 21)
        self.assertEqual(result["first_write_to_observation_ns"], 482 * MS + 45)
        self.assertEqual(result["renders_count"], 1)
        self.assertEqual([item["status"] for item in result["write_timings"]], ["cancelled"] * 4 + ["settled"])

    def test_spaced_all_settled_and_nonuniform_real_gaps_not_assumed_500ms(self):
        writes = writes_for("spaced", gap_ns=900 * MS + 7)
        renders = [rendered(write, 1000) for write in writes]
        result = self.summarize(writes, renders, "spaced")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["requested_delays_ms"], [0, 500, 500, 500, 500])
        self.assertEqual(result["actual_gaps_ns"], [900 * MS + 7] * 4)
        self.assertEqual(result["renders_count"], 5)
        self.assertEqual(result["first_write_to_observation_ns"], 3882 * MS + 73)
        self.assertEqual([item["status"] for item in result["render_timings"]], ["settled"] * 5)

    def test_unobserved_intermediate_renders_are_superseded_without_required_count(self):
        for mode in ("burst", "spaced"):
            with self.subTest(mode=mode):
                writes = writes_for(mode, gap_ns=700 * MS)
                renders = [rendered(write, 1000) for write in writes]
                for render in renders[:-1]:
                    render.update(observation_ns=None, settled=False, pending=None, timer_id=None)
                # A further render of the final original revision is allowed;
                # the first final render was not observed, the latest was.
                renders[-1].update(observation_ns=None, settled=False, pending=None)
                extra = rendered(writes[-1], 1000, start_ns=renders[-1]["return_ns"] + MS)
                renders.append(extra)
                result = self.summarize(writes, renders, mode)
                self.assertTrue(result["ok"], result)
                self.assertEqual(result["renders_count"], 6)
                self.assertEqual([row["status"] for row in result["render_timings"][:4]], ["superseded"] * 4)
                self.assertEqual(result["final_observation_ns"], extra["observation_ns"])

    def test_observed_superseded_intermediate_is_acceptable_but_cannot_settle(self):
        writes = writes_for("spaced")
        renders = [rendered(write, 1000) for write in writes]
        renders[0].update(observation_ns=writes[-1]["begin_ns"] + 10,
                          settled=False, pending=True, timer_id=writes[-1]["timer_id"])
        result = self.summarize(writes, renders, "spaced")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["render_timings"][0]["status"], "superseded")
        renders[0].update(settled=True, pending=False, timer_id=None)
        self.assert_failed(self.summarize(writes, renders, "spaced"))

    def test_final_and_reset_oracle_for_every_R_N_has_original_indices_and_pages(self):
        for rules in (0, 100, 1000):
            for mode in ("single", "reset"):
                with self.subTest(rules=rules, mode=mode):
                    writes, renders = events(mode, rules)
                    result = self.summarize(writes, renders, mode, rules)
                    self.assertTrue(result["ok"], result)
                    count = rules if mode == "reset" else min(rules, 100)
                    self.assertEqual(renders[-1]["full_indices"], list(range(count)))
                    self.assertEqual(renders[-1]["page_count"], 40 if mode == "reset" and rules == 1000 else 4 if count == 100 else 1)
                    self.assertEqual(result["final_query"], "" if mode == "reset" else "qa-00")
                    self.assertEqual(result["last_write_to_observation_ns"], 282 * MS + 21)

    def test_bad_original_indices_duplicates_order_rows_page_and_types_do_not_pass_oracle(self):
        for changes in ({"full_indices": list(range(99))}, {"full_indices": [0] * 100},
                        {"full_indices": list(reversed(range(100)))}, {"full_indices": [False] + list(range(1, 100))},
                        {"full_indices": "0..99"}, {"full_indices": None}, {"rows": 100},
                        {"page": 1}, {"page": False}, {"page_count": 40}, {"rows": 25.0}):
            with self.subTest(changes=changes):
                writes, renders = events()
                renders[-1].update(changes)
                result = self.summarize(writes, renders)
                self.assert_failed(result)
                self.assertIsNone(result["final_observation_ns"])

    def test_final_cancelled_callback_cannot_win_even_with_entry_and_old_observation(self):
        for where in ("before_callback", "after_observation"):
            with self.subTest(where=where):
                writes, renders = events()
                writes[-1]["cancelled_ns"] = (writes[-1]["callback_enter_ns"] - 1 if where == "before_callback"
                                               else renders[-1]["observation_ns"] + 1)
                result = self.summarize(writes, renders)
                self.assert_failed(result)
                self.assertIsNone(result["last_write_to_observation_ns"])
                self.assertIsNone(result["final_observation_ns"])

    def test_earlier_settled_render_does_not_prove_later_unobserved_final_render(self):
        writes, renders = events()
        later = rendered(writes[-1], 1000, start_ns=renders[-1]["observation_ns"] + MS)
        later.update(observation_ns=None, settled=False, pending=None)
        renders.append(later)
        result = self.summarize(writes, renders)
        self.assert_failed(result)
        self.assertIsNone(result["final_observation_ns"])
        self.assertIsNone(result["last_write_to_observation_ns"])
        self.assertEqual(result["write_timings"][-1]["status"], "partial")

    def test_registration_or_callback_alone_and_partial_final_never_complete(self):
        for scenario in ("no_render", "no_callback", "no_observation", "not_settled", "pending", "timer", "no_return", "no_timer_key"):
            with self.subTest(scenario=scenario):
                writes, renders = events()
                if scenario == "no_render": renders = []
                elif scenario == "no_callback": writes[-1]["callback_enter_ns"] = None
                elif scenario == "no_observation": renders[-1].update(observation_ns=None, settled=False, pending=None)
                elif scenario == "not_settled": renders[-1]["settled"] = False
                elif scenario == "pending": renders[-1]["pending"] = True
                elif scenario == "timer": renders[-1]["timer_id"] = writes[-1]["timer_id"]
                elif scenario == "no_return": renders[-1]["return_ns"] = None
                else: del renders[-1]["timer_id"]
                result = self.summarize(writes, renders)
                self.assert_failed(result)
                self.assertIsNone(result["final_observation_ns"])
                self.assertIsNone(result["last_write_to_observation_ns"])

    def test_same_final_text_with_old_revision_ticket_or_unknown_owner_is_not_final(self):
        for changes in ({"revision": 19}, {"ticket_original": 41}, {"write_seq": 0},
                        {"query": "qa"}, {"write_seq": True}):
            with self.subTest(changes=changes):
                writes, renders = events()
                renders[-1].update(changes)
                result = self.summarize(writes, renders)
                self.assert_failed(result)
                self.assertIsNone(result["final_observation_ns"])

    def test_stale_render_cannot_start_after_newer_write_even_without_cancel_record(self):
        writes = writes_for("spaced")
        renders = [rendered(writes[0], 1000, start_ns=writes[1]["set_return_ns"] + 1),
                   rendered(writes[-1], 1000)]
        renders[0].update(observation_ns=None, settled=False, pending=None)
        result = self.summarize(writes, renders, "spaced")
        self.assert_failed(result)
        self.assertTrue(any("superseded" in value for value in result["errors"]))

    def test_partial_plan_and_partial_records_keep_missing_metrics_none(self):
        result = self.summarize([], [])
        self.assert_failed(result)
        self.assertEqual(result["writes_count"], 0)
        self.assertIsNone(result["final_revision"])
        for records in ([None], [{"seq": 1, "query": "qa-00", "begin_ns": NS}]):
            with self.subTest(records=records):
                result = self.summarize(records, [None])
                self.assert_failed(result)
                self.assertEqual(result["writes_count"], 1)
                self.assertEqual(result["renders_count"], 1)
                self.assertIsNone(result["first_write_to_observation_ns"])
        writes = writes_for("burst")[:-1]
        renders = [rendered(writes[-1], 1000)]
        result = self.summarize(writes, renders, "burst")
        self.assert_failed(result)
        self.assertIsNone(result["final_observation_ns"])

    def test_strict_write_types_order_duplicate_timers_and_missing_registration(self):
        for changes in ({"seq": True}, {"begin_ns": False}, {"set_return_ns": 1.0},
                        {"revision": "20"}, {"ticket": 40.0}, {"timer_id": ""},
                        {"timer_id": None}, {"delay_ms": 201}, {"delay_ms": True},
                        {"callback_enter_ns": float("nan")}, {"cancelled_ns": False},
                        {"schedule_begin_ns": NS - 1}, {"schedule_return_ns": None}, {"query": b"qa-00"}):
            with self.subTest(changes=changes):
                writes, renders = events()
                writes[-1].update(changes)
                self.assert_failed(self.summarize(writes, renders))
        for field in ("seq", "revision", "ticket", "timer_id"):
            writes, renders = events("burst")
            writes[-1][field] = writes[-2][field]
            self.assert_failed(self.summarize(writes, renders, "burst"))
        writes, renders = events("burst")
        self.assert_failed(self.summarize(list(reversed(writes)), renders, "burst"))

    def test_render_type_and_chronology_errors_do_not_produce_negative_latency(self):
        for changes in ({"start_ns": NS - 1}, {"return_ns": NS - 2},
                        {"observation_ns": NS - 1}, {"settled": 1}, {"pending": 0},
                        {"timer_id": 0}, {"revision": True}, {"ticket_original": []},
                        {"return_ns": float("inf")}):
            with self.subTest(changes=changes):
                writes, renders = events()
                renders[-1].update(changes)
                result = self.summarize(writes, renders)
                self.assert_failed(result)
                for key in ("render_call_ns", "layout_wait_ns", "callback_to_render_ns"):
                    value = result["render_timings"][0][key]
                    self.assertTrue(value is None or value >= 0)
        writes, renders = events("spaced")
        self.assert_failed(self.summarize(writes, list(reversed(renders)), "spaced"))

    def test_invalid_record_keeps_actual_interval_slots_and_does_not_mutate_inputs(self):
        writes, renders = events("burst")
        before = copy.deepcopy((writes, renders))
        result = self.summarize(iter(writes), iter(renders), "burst")
        self.assertTrue(result["ok"], result)
        self.assertEqual((writes, renders), before)
        json.dumps(result, allow_nan=False)
        writes[1] = None
        result = self.summarize(writes, renders, "burst")
        self.assert_failed(result)
        self.assertEqual(len(result["actual_intervals_ns"]), 4)
        self.assertEqual(result["actual_intervals_ns"][:2], [None, None])
        self.assertEqual(result["actual_gaps_ns"][:2], [None, None])

    def test_none_is_explicitly_disabled_not_invented_zero_latency(self):
        result = self.summarize([], [], "none")
        self.assertTrue(result["ok"], result)
        self.assertEqual(result["expected_writes"], 0)
        self.assertEqual(result["write_timings"], [])
        self.assertIsNone(result["last_write_to_observation_ns"])
        writes, renders = events()
        self.assert_failed(self.summarize(writes, renders, "none"))


if __name__ == "__main__":
    unittest.main()

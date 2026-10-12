"""Remoção por posições originais: lote atômico, uma edição e seleção pura."""

from datetime import time
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from core.config import ConfigError
from core.config_comparison import configs_equal
from core.config_editor import ConfigDraft
from core.models import AppConfig, CmdlineRule, ScheduleWindow


FIELDS = ("block_exes", "block_folders", "safelist_exes", "block_cmdline")


def sample_config():
    return AppConfig(
        windows=(ScheduleWindow(time(22), time(2), (6, 0)), ScheduleWindow(time(9), time(10), ())),
        block_exes=("z.exe", "same.exe", "a.exe", "same.exe", "SAME.exe"),
        block_folders=(r"C:\Zed", r"C:\Same", r"C:\Alpha", r"C:\Same", r"C:\SAME"),
        safelist_exes=("z.exe", "same.exe", "a.exe", "same.exe", "SAME.exe"),
        block_cmdline=(CmdlineRule("z.exe", "z"), CmdlineRule("a.exe", " same "),
                       CmdlineRule("a.exe", "a"), CmdlineRule("a.exe", " same "), CmdlineRule("A.exe", " SAME ")),
        extra={"typed": {"values": [True, 1, 1.0, False, 0, 0.0], "order": ["z", "a", "z"]}},
    )


class OneShot:
    def __init__(self, values):
        self.values = values
        self.calls = 0

    def __iter__(self):
        self.calls += 1
        if self.calls != 1:
            raise AssertionError("seleção consumida novamente")
        yield from self.values


class RuleBulkRemoveTests(unittest.TestCase):
    def draft_with_redo(self):
        draft = ConfigDraft(sample_config())
        draft.add_rule("block_exes", "redo.exe")
        draft.undo()
        return draft

    def capture_state(self, draft):
        return draft.config, tuple(draft._undo), tuple(draft._redo)

    def assert_state_intact(self, draft, state):
        config, undo, redo = state
        self.assertTrue(configs_equal(draft.config, config))
        for actual, expected in ((tuple(draft._undo), undo), (tuple(draft._redo), redo)):
            self.assertEqual(len(actual), len(expected))
            self.assertTrue(all(configs_equal(a, b) for a, b in zip(actual, expected)))

    def test_all_fields_remove_original_positions_preserve_survivor_order_and_duplicate_values(self):
        source = sample_config()
        for field in FIELDS:
            with self.subTest(field=field):
                draft = ConfigDraft(source)
                self.assertEqual(draft.remove_rules(field, [2, 0, 2]), 2)
                result = draft.config
                self.assertEqual(getattr(result, field), tuple(getattr(source, field)[i] for i in (1, 3, 4)))
                self.assertEqual(getattr(result, field)[0], getattr(result, field)[1])
                for other in FIELDS:
                    if other != field:
                        self.assertEqual(getattr(result, other), getattr(source, other))
                self.assertEqual(result.windows, source.windows)
                self.assertTrue(configs_equal(AppConfig(extra=result.extra), AppConfig(extra=source.extra)))

    def test_remove_every_position_counts_distinct_positions_and_leaves_empty_list(self):
        for field in FIELDS:
            with self.subTest(field=field):
                draft = ConfigDraft(sample_config())
                self.assertEqual(draft.remove_rules(field, [4, 3, 2, 1, 0, 4, 0]), 5)
                self.assertEqual(getattr(draft.config, field), ())
                self.assertTrue(draft.undo())
                self.assertTrue(configs_equal(draft.config, sample_config()))
                self.assertFalse(draft.undo())

    def test_one_shot_iterable_is_consumed_exactly_once_and_input_list_is_unchanged(self):
        draft = ConfigDraft(sample_config())
        values = [3, 1, 3]
        selection = OneShot(values)
        self.assertEqual(draft.remove_rules("block_exes", selection), 2)
        self.assertEqual(selection.calls, 1)
        self.assertEqual(values, [3, 1, 3])
        self.assertEqual(draft.config.block_exes, ("z.exe", "a.exe", "SAME.exe"))

    def test_late_iterator_failure_has_original_cause_and_preserves_model_undo_redo(self):
        for failure in (RuntimeError("late"), ValueError("late"), TypeError("late"), ConfigError("late"), OSError("late")):
            with self.subTest(failure=type(failure)):
                draft = self.draft_with_redo()
                state = self.capture_state(draft)

                def failing():
                    yield 1
                    yield 3
                    raise failure

                with self.assertRaises(ConfigError) as caught:
                    draft.remove_rules("block_exes", failing())
                self.assertIs(caught.exception.__cause__, failure)
                self.assert_state_intact(draft, state)
                self.assertTrue(draft.redo())
                self.assertEqual(draft.config.block_exes[-1], "redo.exe")

    def test_noniterable_and_iterator_start_failure_are_config_errors_with_cause(self):
        failure = RuntimeError("iter failed")

        class Broken:
            def __iter__(self):
                raise failure

        for selection in (None, True, 1, 1.0, object(), Broken()):
            with self.subTest(selection=type(selection)):
                draft = self.draft_with_redo()
                state = self.capture_state(draft)
                with self.assertRaises(ConfigError) as caught:
                    draft.remove_rules("block_exes", selection)
                self.assertIsNotNone(caught.exception.__cause__)
                if isinstance(selection, Broken):
                    self.assertIs(caught.exception.__cause__, failure)
                self.assert_state_intact(draft, state)

    def test_keyboard_interrupt_and_system_exit_propagate_without_mutation(self):
        for failure in (KeyboardInterrupt(), SystemExit(12)):
            for late in (False, True):
                with self.subTest(failure=type(failure), late=late):
                    draft = self.draft_with_redo()
                    state = self.capture_state(draft)

                    def interrupted():
                        if late:
                            yield 1
                        raise failure

                    with self.assertRaises(type(failure)) as caught:
                        draft.remove_rules("block_exes", interrupted())
                    self.assertIs(caught.exception, failure)
                    self.assert_state_intact(draft, state)

    def test_each_index_is_strict_int_before_dedup_even_bool_aliases_after_valid_indices(self):
        class IntSubclass(int):
            pass

        for invalid in (True, False, 1.0, "1", None, [], {}, IntSubclass(1)):
            with self.subTest(index=invalid):
                draft = self.draft_with_redo()
                state = self.capture_state(draft)
                with self.assertRaises(ConfigError):
                    draft.remove_rules("block_exes", [0, 1, invalid])
                self.assert_state_intact(draft, state)

    def test_range_uses_original_list_and_invalid_positions_are_atomic(self):
        for invalid in (-1, 5, 1000):
            with self.subTest(index=invalid):
                draft = self.draft_with_redo()
                state = self.capture_state(draft)
                with self.assertRaises(ConfigError):
                    draft.remove_rules("block_exes", [4, 0, invalid])
                self.assert_state_intact(draft, state)
        draft = ConfigDraft(AppConfig())
        with self.assertRaises(ConfigError):
            draft.remove_rules("block_exes", [0])
        self.assertFalse(draft.can_undo)

    def test_invalid_field_is_rejected_even_empty_and_before_consuming_selection(self):
        for field in ("windows", "extra", "unknown", "BLOCK_EXES", "", None, True, []):
            for values in ((), (0,)):
                with self.subTest(field=field, values=values):
                    draft = self.draft_with_redo()
                    state = self.capture_state(draft)
                    selection = OneShot(values)
                    with self.assertRaises(ConfigError):
                        draft.remove_rules(field, selection)
                    self.assertEqual(selection.calls, 0)
                    self.assert_state_intact(draft, state)

    def test_text_bytes_and_bytearray_are_rejected_even_empty(self):
        for selection in ("", "01", b"", bytes((0, 1)), bytearray(), bytearray((0, 1))):
            with self.subTest(selection=selection):
                draft = self.draft_with_redo()
                state = self.capture_state(draft)
                with self.assertRaises(ConfigError):
                    draft.remove_rules("block_exes", selection)
                self.assert_state_intact(draft, state)

    def test_empty_selection_returns_zero_before_serialization_validation_accept_and_keeps_redo(self):
        draft = self.draft_with_redo()
        state = self.capture_state(draft)
        with patch("core.config_editor.config_to_dict", side_effect=AssertionError("serialize")), \
                patch("core.config_editor.parse_config", side_effect=AssertionError("validation")), \
                patch.object(draft, "_accept", side_effect=AssertionError("accept")):
            for field in FIELDS:
                selection = OneShot(())
                self.assertEqual(draft.remove_rules(field, selection), 0)
                self.assertEqual(selection.calls, 1)
                self.assert_state_intact(draft, state)
        self.assertTrue(draft.redo())
        self.assertEqual(draft.config.block_exes[-1], "redo.exe")

    def test_nonempty_batch_accepts_once_and_is_one_undo_redo_branch(self):
        draft = self.draft_with_redo()
        before = draft.config
        with patch.object(draft, "_accept", wraps=draft._accept) as accept:
            self.assertEqual(draft.remove_rules("block_exes", [3, 1, 3]), 2)
            accept.assert_called_once()
        after = draft.config
        self.assertFalse(draft.can_redo)
        self.assertFalse(draft.redo())
        self.assertTrue(draft.undo())
        self.assertTrue(configs_equal(draft.config, before))
        self.assertFalse(draft.undo())
        self.assertTrue(draft.redo())
        self.assertTrue(configs_equal(draft.config, after))
        self.assertFalse(draft.redo())

    def test_serialization_and_accept_validation_failures_preserve_complete_state(self):
        for target in ("core.config_editor.config_to_dict", "core.config_editor.parse_config"):
            with self.subTest(target=target):
                draft = self.draft_with_redo()
                state = self.capture_state(draft)
                failure = ConfigError("model no longer validates")
                with patch(target, side_effect=failure), self.assertRaises(ConfigError) as caught:
                    draft.remove_rules("block_exes", [1, 3])
                self.assertIs(caught.exception, failure)
                self.assert_state_intact(draft, state)

    def test_source_exposed_copies_typed_extras_and_windows_remain_independent(self):
        source = sample_config()
        draft = ConfigDraft(source)
        exposed = draft.config
        self.assertEqual(draft.remove_rules("block_exes", [0, 2]), 2)
        self.assertEqual(source.block_exes, exposed.block_exes)
        self.assertEqual(draft.config.windows, source.windows)
        expected_types = [bool, int, float, bool, int, float]
        for config in (source, exposed, draft.config):
            self.assertEqual([type(value) for value in config.extra["typed"]["values"]], expected_types)
        source.extra["typed"]["values"].clear()
        exposed.extra["typed"]["order"].append("copy change")
        result = draft.config
        result.extra["typed"]["values"].clear()
        self.assertEqual(draft.config.extra["typed"]["order"], ["z", "a", "z"])
        self.assertEqual([type(value) for value in draft.config.extra["typed"]["values"]], expected_types)
        self.assertTrue(draft.undo())
        self.assertEqual([type(value) for value in draft.config.extra["typed"]["values"]], expected_types)

    def test_removal_has_no_io_clock_discovery_or_runtime_and_fresh_import_is_lazy(self):
        draft = ConfigDraft(sample_config())
        with patch("builtins.open", side_effect=AssertionError("IO")), \
                patch.object(Path, "read_bytes", side_effect=AssertionError("IO")), \
                patch.object(Path, "resolve", side_effect=AssertionError("discovery")), \
                patch("time.time", side_effect=AssertionError("clock")), \
                patch("subprocess.Popen", side_effect=AssertionError("runtime")):
            self.assertEqual(draft.remove_rules("block_exes", [1, 3]), 2)
        script = '''
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith(('psutil', 'tkinter', 'customtkinter', 'pystray', 'PIL')) or name in ('core.proc_blocker', 'core.process_controller', 'ui.config_gui'):
        raise AssertionError(name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from core.config_editor import ConfigDraft
from core.models import AppConfig
draft = ConfigDraft(AppConfig(block_exes=('same.exe', 'same.exe', 'other.exe')))
assert draft.remove_rules('block_exes', iter((1, 1))) == 1
assert draft.config.block_exes == ('same.exe', 'other.exe')
assert draft.undo()
'''
        result = subprocess.run([sys.executable, "-B", "-c", script], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

"""Diff de listas ordenadas com expectativas fixas, sem widgets ou runtime."""

from copy import deepcopy
from dataclasses import FrozenInstanceError, replace
from datetime import time
from itertools import combinations_with_replacement, product
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from core.config_comparison import configs_equal
from core.config_diff import ConfigChange, ConfigDiff, diff_config
from core.models import AppConfig, CmdlineRule, ScheduleWindow


FIELDS = ("windows", "block_exes", "block_folders", "safelist_exes", "block_cmdline")


class ConfigDiffTests(unittest.TestCase):
    def test_empty_existing_and_new_file_are_distinguished_without_changes(self):
        self.assertEqual(diff_config(AppConfig(), AppConfig()), ConfigDiff(False, (), False))
        self.assertEqual(diff_config(None, AppConfig()), ConfigDiff(True, (), False))

    def test_each_field_insert_and_delete_use_original_indices_and_absent_side_none(self):
        values = (
            (ScheduleWindow(time(9), time(12), (0, 2)), "09:00–12:00 · dias: seg, qua"),
            ("Game.EXE", "Game.EXE"),
            (r"C:\Jogos\ação", r"C:\Jogos\ação"),
            ("Keep.EXE", "Keep.EXE"),
            (CmdlineRule("javaw.exe", " .MineCraft "), "javaw.exe + trecho: ' .MineCraft '"),
        )
        for field, (value, text) in zip(FIELDS, values):
            populated = AppConfig(**{field: (value,)})
            with self.subTest(field=field):
                self.assertEqual(diff_config(AppConfig(), populated), ConfigDiff(False, (
                    ConfigChange(field, "insert", None, 0, None, text),
                ), False))
                self.assertEqual(diff_config(populated, AppConfig()), ConfigDiff(False, (
                    ConfigChange(field, "delete", 0, None, text, None),
                ), False))
                self.assertEqual(diff_config(None, populated), ConfigDiff(True, (
                    ConfigChange(field, "insert", None, 0, None, text),
                ), False))

    def test_first_file_changes_follow_field_order_and_extras_are_indicator_only(self):
        draft = AppConfig(
            windows=(ScheduleWindow(time(22, 30), time(2, 15), (6, 0)),),
            block_exes=("a.exe", "a.exe"), block_folders=(r"D:\Games",),
            safelist_exes=("keep.exe",), block_cmdline=(CmdlineRule("javaw.exe", ".minecraft"),),
            extra={"secret": "DO_NOT_EXPOSE", "values": [True, 1, 1.0]},
        )
        result = diff_config(None, draft)
        self.assertEqual(result, ConfigDiff(True, (
            ConfigChange("windows", "insert", None, 0, None, "22:30–02:15 · dias: dom, seg"),
            ConfigChange("block_exes", "insert", None, 0, None, "a.exe"),
            ConfigChange("block_exes", "insert", None, 1, None, "a.exe"),
            ConfigChange("block_folders", "insert", None, 0, None, r"D:\Games"),
            ConfigChange("safelist_exes", "insert", None, 0, None, "keep.exe"),
            ConfigChange("block_cmdline", "insert", None, 0, None, "javaw.exe + trecho: '.minecraft'"),
        ), True))
        self.assertNotIn("DO_NOT_EXPOSE", repr(result))
        self.assertNotIn("secret", repr(result))

    def test_insert_and_delete_in_middle_leave_equal_neighbors_out_of_report(self):
        base = AppConfig(block_exes=("a.exe", "c.exe"))
        draft = AppConfig(block_exes=("a.exe", "b.exe", "c.exe"))
        self.assertEqual(diff_config(base, draft).changes, (
            ConfigChange("block_exes", "insert", None, 1, None, "b.exe"),
        ))
        self.assertEqual(diff_config(draft, base).changes, (
            ConfigChange("block_exes", "delete", 1, None, "b.exe", None),
        ))

    def test_equal_length_replace_blocks_pair_each_original_position(self):
        base = AppConfig(block_exes=("a.exe", "b.exe", "c.exe", "d.exe"))
        draft = AppConfig(block_exes=("a.exe", "x.exe", "y.exe", "d.exe"))
        self.assertEqual(diff_config(base, draft).changes, (
            ConfigChange("block_exes", "replace", 1, 1, "b.exe", "x.exe"),
            ConfigChange("block_exes", "replace", 2, 2, "c.exe", "y.exe"),
        ))

    def test_replace_block_with_more_new_items_pairs_then_inserts_remainder(self):
        base = AppConfig(block_exes=("a.exe", "b.exe", "c.exe"))
        draft = AppConfig(block_exes=("a.exe", "x.exe", "y.exe", "c.exe"))
        self.assertEqual(diff_config(base, draft).changes, (
            ConfigChange("block_exes", "replace", 1, 1, "b.exe", "x.exe"),
            ConfigChange("block_exes", "insert", None, 2, None, "y.exe"),
        ))

    def test_replace_block_with_more_old_items_pairs_then_deletes_remainder(self):
        base = AppConfig(block_exes=("a.exe", "x.exe", "y.exe", "c.exe"))
        draft = AppConfig(block_exes=("a.exe", "b.exe", "c.exe"))
        self.assertEqual(diff_config(base, draft).changes, (
            ConfigChange("block_exes", "replace", 1, 1, "x.exe", "b.exe"),
            ConfigChange("block_exes", "delete", 2, None, "y.exe", None),
        ))

    def test_mixed_opcodes_keep_before_and_after_indices_independently(self):
        base = AppConfig(block_exes=("a.exe", "b.exe", "c.exe", "d.exe", "e.exe"))
        draft = AppConfig(block_exes=("x.exe", "a.exe", "b.exe", "y.exe", "d.exe", "e.exe", "z.exe"))
        self.assertEqual(diff_config(base, draft).changes, (
            ConfigChange("block_exes", "insert", None, 0, None, "x.exe"),
            ConfigChange("block_exes", "replace", 2, 3, "c.exe", "y.exe"),
            ConfigChange("block_exes", "insert", None, 6, None, "z.exe"),
        ))

    def test_duplicates_preserved_with_deterministic_matching_indices(self):
        base = AppConfig(block_exes=("a.exe", "a.exe", "b.exe"))
        draft = AppConfig(block_exes=("a.exe", "b.exe"))
        self.assertEqual(diff_config(base, draft).changes, (
            ConfigChange("block_exes", "delete", 1, None, "a.exe", None),
        ))
        self.assertEqual(diff_config(draft, base).changes, (
            ConfigChange("block_exes", "insert", None, 1, None, "a.exe"),
        ))
        self.assertEqual(diff_config(base, deepcopy(base)).changes, ())

    def test_reordering_is_not_hidden_as_set_equality_or_paired_normalization(self):
        base = AppConfig(block_exes=("a.exe", "b.exe"))
        draft = AppConfig(block_exes=("b.exe", "a.exe"))
        expected = ConfigDiff(False, (
            ConfigChange("block_exes", "insert", None, 0, None, "b.exe"),
            ConfigChange("block_exes", "delete", 1, None, "b.exe", None),
        ), False)
        self.assertEqual(diff_config(base, draft), expected)
        self.assertEqual(diff_config(base, draft), expected)

    def test_long_repeated_lists_trim_to_one_central_replacement(self):
        base = AppConfig(block_exes=("a.exe",) * 210 + ("old.exe",) + ("a.exe",) * 210)
        draft = AppConfig(block_exes=("a.exe",) * 210 + ("new.exe",) + ("a.exe",) * 210)
        self.assertEqual(diff_config(base, draft).changes, (
            ConfigChange("block_exes", "replace", 210, 210, "old.exe", "new.exe"),
        ))

    def test_exact_noop_does_not_invoke_matcher_even_for_long_duplicate_lists(self):
        config = AppConfig(
            windows=(ScheduleWindow(time(9), time(10), (0,)),) * 2000,
            block_exes=("same.exe",) * 2000, block_folders=(r"C:\Games",) * 2000,
            safelist_exes=("keep.exe",) * 2000,
            block_cmdline=(CmdlineRule("javaw.exe", " .Minecraft "),) * 2000,
            extra={"nested": {"flag": True}},
        )
        other = deepcopy(config)
        with patch("core.config_diff.SequenceMatcher", side_effect=AssertionError("noop matcher")):
            self.assertEqual(diff_config(config, other), ConfigDiff(False, (), False))
            self.assertEqual(diff_config(config, replace(other, extra={"nested": {"flag": 1}})),
                             ConfigDiff(False, (), True))

    def test_central_change_in_uniform_duplicates_is_one_replace_at_global_index(self):
        base = AppConfig(block_exes=("same.exe",) * 1000)
        draft = AppConfig(block_exes=("same.exe",) * 500 + ("changed.exe",) + ("same.exe",) * 499)
        self.assertEqual(diff_config(base, draft).changes, (
            ConfigChange("block_exes", "replace", 500, 500, "same.exe", "changed.exe"),
        ))

    def test_trimmed_replace_with_unequal_middle_lengths_remaps_both_sides(self):
        base = AppConfig(block_exes=("p.exe", "p.exe", "old1.exe", "old2.exe", "s.exe", "s.exe"))
        draft = AppConfig(block_exes=("p.exe", "p.exe", "new.exe", "s.exe", "s.exe"))
        self.assertEqual(diff_config(base, draft).changes, (
            ConfigChange("block_exes", "replace", 2, 2, "old1.exe", "new.exe"),
            ConfigChange("block_exes", "delete", 3, None, "old2.exe", None),
        ))
        self.assertEqual(diff_config(draft, base).changes, (
            ConfigChange("block_exes", "replace", 2, 2, "new.exe", "old1.exe"),
            ConfigChange("block_exes", "insert", None, 3, None, "old2.exe"),
        ))

    def test_prefix_suffix_and_empty_seams_do_not_overlap_or_drop_duplicates(self):
        cases = (
            ((), ("a.exe",) * 3, tuple(ConfigChange("block_exes", "insert", None, i, None, "a.exe")
                                      for i in range(3))),
            (("a.exe",) * 3, (), tuple(ConfigChange("block_exes", "delete", i, None, "a.exe", None)
                                      for i in range(3))),
            (("a.exe",) * 2, ("a.exe",) * 3,
             (ConfigChange("block_exes", "insert", None, 2, None, "a.exe"),)),
            (("a.exe",) * 3, ("a.exe",) * 2,
             (ConfigChange("block_exes", "delete", 2, None, "a.exe", None),)),
            (("a.exe",) * 3, ("b.exe", "a.exe", "a.exe"),
             (ConfigChange("block_exes", "replace", 0, 0, "a.exe", "b.exe"),)),
            (("a.exe",) * 3, ("a.exe", "a.exe", "b.exe"),
             (ConfigChange("block_exes", "replace", 2, 2, "a.exe", "b.exe"),)),
            (("a.exe",) * 3, ("a.exe", "b.exe", "a.exe"),
             (ConfigChange("block_exes", "replace", 1, 1, "a.exe", "b.exe"),)),
        )
        for before, after, expected in cases:
            with self.subTest(before=before, after=after):
                self.assertEqual(diff_config(AppConfig(block_exes=before),
                                             AppConfig(block_exes=after)).changes, expected)

    def test_reordering_inside_equal_borders_keeps_global_indices(self):
        base = AppConfig(block_exes=("p.exe", "a.exe", "b.exe", "s.exe"))
        draft = AppConfig(block_exes=("p.exe", "b.exe", "a.exe", "s.exe"))
        self.assertEqual(diff_config(base, draft).changes, (
            ConfigChange("block_exes", "insert", None, 1, None, "b.exe"),
            ConfigChange("block_exes", "delete", 2, None, "b.exe", None),
        ))

    def test_autojunk_disabled_on_large_repetitive_middle_without_equal_borders(self):
        base = AppConfig(block_exes=("old_head.exe",) + ("a.exe",) * 210 + ("old.exe",)
                         + ("a.exe",) * 210 + ("old_tail.exe",))
        draft = AppConfig(block_exes=("new_head.exe",) + ("a.exe",) * 210 + ("new.exe",)
                          + ("a.exe",) * 210 + ("new_tail.exe",))
        self.assertEqual(diff_config(base, draft).changes, (
            ConfigChange("block_exes", "replace", 0, 0, "old_head.exe", "new_head.exe"),
            ConfigChange("block_exes", "replace", 211, 211, "old.exe", "new.exe"),
            ConfigChange("block_exes", "replace", 422, 422, "old_tail.exe", "new_tail.exe"),
        ))

    def test_bidirectional_reconstruction_of_small_duplicate_sequences(self):
        sequences = [items for length in range(5) for items in product(("a.exe", "b.exe"), repeat=length)]
        for left, right in combinations_with_replacement(sequences, 2):
            # Inversão reconstroi conteúdo; não exige opcodes inversos idênticos.
            for before, after in ((left, right), (right, left)):
                with self.subTest(before=before, after=after):
                    baseline, draft = AppConfig(block_exes=before), AppConfig(block_exes=after)
                    result = diff_config(baseline, draft)
                    self.assertEqual(result, diff_config(baseline, draft))
                    removed, placed = set(), {}
                    for change in result.changes:
                        self.assertEqual(change.field, "block_exes")
                        self.assertIn(change.kind, ("insert", "delete", "replace"))
                        if change.kind in ("delete", "replace"):
                            self.assertIs(type(change.before_index), int)
                            self.assertTrue(0 <= change.before_index < len(before))
                            self.assertNotIn(change.before_index, removed)
                            self.assertEqual(change.before, before[change.before_index])
                            removed.add(change.before_index)
                        else:
                            self.assertIsNone(change.before_index)
                            self.assertIsNone(change.before)
                        if change.kind in ("insert", "replace"):
                            self.assertIs(type(change.after_index), int)
                            self.assertTrue(0 <= change.after_index < len(after))
                            self.assertNotIn(change.after_index, placed)
                            self.assertEqual(change.after, after[change.after_index])
                            placed[change.after_index] = change.after
                        else:
                            self.assertIsNone(change.after_index)
                            self.assertIsNone(change.after)
                    remaining = iter(value for index, value in enumerate(before) if index not in removed)
                    reconstructed = tuple(placed[index] if index in placed else next(remaining)
                                          for index in range(len(after)))
                    self.assertEqual(reconstructed, after)
                    self.assertEqual(tuple(remaining), ())
                    self.assertEqual(baseline.block_exes, before)
                    self.assertEqual(draft.block_exes, after)

    def test_case_unicode_and_folder_spelling_are_preserved_without_casefold(self):
        for field, before, after in (
            ("block_exes", "ſteam.exe", "steam.exe"),
            ("block_exes", "Game.EXE", "game.exe"),
            ("safelist_exes", "Keep.EXE", "keep.exe"),
            ("block_folders", r"C:\Games", r"c:\games"),
            ("block_folders", r"C:\Games", "C:/Games"),
            ("block_folders", r"C:\Games", r"C:\Games\..\Games"),
            ("block_exes", "ação.exe", "日本語.exe"),
        ):
            with self.subTest(field=field, before=before, after=after):
                base = AppConfig(**{field: (before,)})
                draft = AppConfig(**{field: (after,)})
                self.assertEqual(diff_config(base, draft).changes, (
                    ConfigChange(field, "replace", 0, 0, before, after),
                ))

    def test_window_descriptions_include_minutes_overnight_all_days_and_disabled(self):
        draft = AppConfig(windows=(
            ScheduleWindow(time(9, 5), time(10, 7), (2, 0)),
            ScheduleWindow(time(22, 30), time(2, 15), (6,)),
            ScheduleWindow(time(8), time(9), tuple(range(7))),
            ScheduleWindow(time(8), time(9), ()),
        ))
        self.assertEqual([change.after for change in diff_config(None, draft).changes], [
            "09:05–10:07 · dias: qua, seg",
            "22:30–02:15 · dias: dom",
            "08:00–09:00 · dias: seg, ter, qua, qui, sex, sáb, dom",
            "08:00–09:00 · desativado (sem dias)",
        ])

    def test_literal_rule_text_preserves_internal_spaces_and_unicode(self):
        for field, before, after in (
            ("block_exes", "My Game.exe", "My  Game.exe"),
            ("safelist_exes", "Minha Ferramenta.exe", "Minha  Ferramenta.exe"),
            ("block_folders", r"C:\Program Files\ação", r"C:\Program  Files\ação"),
        ):
            with self.subTest(field=field):
                self.assertEqual(diff_config(AppConfig(**{field: (before,)}),
                                             AppConfig(**{field: (after,)})).changes, (
                    ConfigChange(field, "replace", 0, 0, before, after),
                ))

    def test_window_days_order_change_and_disabled_transition_are_real_replacements(self):
        before = ScheduleWindow(time(9), time(12), (0, 2))
        reordered = replace(before, days=(2, 0))
        self.assertEqual(diff_config(AppConfig(windows=(before,)), AppConfig(windows=(reordered,))).changes, (
            ConfigChange("windows", "replace", 0, 0, "09:00–12:00 · dias: seg, qua",
                         "09:00–12:00 · dias: qua, seg"),
        ))
        disabled = replace(before, days=())
        self.assertEqual(diff_config(AppConfig(windows=(before,)), AppConfig(windows=(disabled,))).changes, (
            ConfigChange("windows", "replace", 0, 0, "09:00–12:00 · dias: seg, qua",
                         "09:00–12:00 · desativado (sem dias)"),
        ))

    def test_cmdline_replacement_contains_full_pair_and_spaces_case_quotes_remain_visible(self):
        before = CmdlineRule("JAVAW.EXE", " .Minecraft ")
        after = CmdlineRule("javaw.exe", ".minecraft")
        self.assertEqual(diff_config(AppConfig(block_cmdline=(before,)), AppConfig(block_cmdline=(after,))).changes, (
            ConfigChange("block_cmdline", "replace", 0, 0, "JAVAW.EXE + trecho: ' .Minecraft '",
                         "javaw.exe + trecho: '.minecraft'"),
        ))
        text = ' literal "quoted" .* \\ path '
        result = diff_config(None, AppConfig(block_cmdline=(CmdlineRule("custom.exe", text),)))
        self.assertEqual(result.changes[0].after, "custom.exe + trecho: " + repr(text))

    def test_duplicate_cmdline_pairs_and_window_rows_are_not_deduplicated(self):
        item = CmdlineRule("javaw.exe", ".minecraft")
        window = ScheduleWindow(time(9), time(10), (0,))
        result = diff_config(AppConfig(block_cmdline=(item,), windows=(window,)),
                             AppConfig(block_cmdline=(item, item), windows=(window, window)))
        self.assertEqual(result.changes, (
            ConfigChange("windows", "insert", None, 1, None, "09:00–10:00 · dias: seg"),
            ConfigChange("block_cmdline", "insert", None, 1, None, "javaw.exe + trecho: '.minecraft'"),
        ))

    def test_extras_only_bool_int_float_nested_types_changes_are_flagged_without_values(self):
        for before, after in ((True, 1), (False, 0), (1, 1.0), (0, 0.0),
                              ([True, 1], [1, True]), ([1], (1,)), (None, {})):
            with self.subTest(before=before, after=after):
                base = AppConfig(extra={"secret": {"nested": [before]}})
                draft = AppConfig(extra={"secret": {"nested": [after]}})
                self.assertEqual(diff_config(base, draft), ConfigDiff(False, (), True))
        self.assertEqual(diff_config(None, AppConfig(extra={"secret": "private"})),
                         ConfigDiff(True, (), True))
        self.assertEqual(diff_config(AppConfig(extra={"secret": "private"}), AppConfig()),
                         ConfigDiff(False, (), True))

    def test_dict_order_is_noop_but_list_order_and_extra_keys_are_not(self):
        base = AppConfig(extra={"first": {"a": True, "b": [1, 2]}, "second": None})
        reordered = AppConfig(extra={"second": None, "first": {"b": [1, 2], "a": True}})
        self.assertEqual(diff_config(base, reordered), ConfigDiff(False, (), False))
        changed_list = AppConfig(extra={"second": None, "first": {"b": [2, 1], "a": True}})
        self.assertEqual(diff_config(base, changed_list), ConfigDiff(False, (), True))
        changed_key = AppConfig(extra={"first": {"a": True, "b": [1, 2]}, "third": None})
        self.assertEqual(diff_config(base, changed_key), ConfigDiff(False, (), True))

    def test_extras_use_shared_typed_comparison_without_mixing_list_differences(self):
        base = AppConfig(block_exes=("old.exe",), extra={"v": True})
        draft = AppConfig(block_exes=("new.exe",), extra={"v": 1})
        with patch("core.config_diff.configs_equal", wraps=configs_equal) as comparison:
            result = diff_config(base, draft)
            comparison.assert_called_once_with(AppConfig(extra=base.extra), AppConfig(extra=draft.extra))
        self.assertTrue(result.extras_changed)
        self.assertEqual(result.changes, (
            ConfigChange("block_exes", "replace", 0, 0, "old.exe", "new.exe"),
        ))

    def test_all_equal_models_and_source_copies_produce_noop_without_mutating_inputs(self):
        base = AppConfig(
            windows=(ScheduleWindow(time(22), time(2), (6, 0)),),
            block_exes=("a.exe", "a.exe"), block_folders=(r"C:\Games",),
            safelist_exes=("keep.exe",), block_cmdline=(CmdlineRule("javaw.exe", " .minecraft "),),
            extra={"future": {"values": [True, 1, 1.0]}},
        )
        draft = deepcopy(base)
        before_base, before_draft = deepcopy(base), deepcopy(draft)
        self.assertEqual(diff_config(base, draft), ConfigDiff(False, (), False))
        self.assertTrue(configs_equal(base, before_base))
        self.assertTrue(configs_equal(draft, before_draft))

    def test_result_is_frozen_tuple_and_has_no_mutable_references_to_models(self):
        base = AppConfig(extra={"future": [True]})
        draft = AppConfig(block_exes=("game.exe",), extra={"future": [1]})
        result = diff_config(base, draft)
        self.assertIsInstance(result.changes, tuple)
        with self.assertRaises(FrozenInstanceError):
            result.is_new = True
        with self.assertRaises(FrozenInstanceError):
            result.extras_changed = False
        with self.assertRaises(FrozenInstanceError):
            result.changes[0].after = "changed.exe"
        base.extra["future"].clear()
        draft.extra["future"].append("later")
        self.assertEqual(result, ConfigDiff(False, (
            ConfigChange("block_exes", "insert", None, 0, None, "game.exe"),
        ), True))

    def test_non_model_top_level_inputs_raise_type_error(self):
        for invalid in ({}, [], (), "config", True, 1, iter(())):
            with self.subTest(argument="baseline", invalid=invalid), self.assertRaises(TypeError):
                diff_config(invalid, AppConfig())
        for invalid in (None, {}, [], (), "config", True, 1, iter(())):
            with self.subTest(argument="draft", invalid=invalid), self.assertRaises(TypeError):
                diff_config(None, invalid)

    def test_pure_no_io_clock_discovery_serialization_or_environment_revalidation(self):
        base = AppConfig(block_folders=(r"%MISSING_DIFF_VAR%\Games",), extra={"flag": True})
        draft = replace(base, extra={"flag": 1})
        with patch.dict(os.environ, {}, clear=True), \
             patch("core.config.config_to_dict", side_effect=AssertionError("validation")), \
             patch("core.config.parse_config", side_effect=AssertionError("validation")), \
             patch("json.dumps", side_effect=AssertionError("serialization")), \
             patch.object(Path, "open", side_effect=AssertionError("IO")), \
             patch.object(Path, "resolve", side_effect=AssertionError("discovery")), \
             patch("os.stat", side_effect=AssertionError("discovery")), \
             patch("time.time", side_effect=AssertionError("clock")), \
             patch("subprocess.Popen", side_effect=AssertionError("process")):
            self.assertEqual(diff_config(base, draft), ConfigDiff(False, (), True))
            inserted = diff_config(None, draft)
            self.assertEqual(inserted.changes[0].after, r"%MISSING_DIFF_VAR%\Games")
            self.assertTrue(inserted.extras_changed)

    def test_fresh_import_and_diff_never_import_gui_psutil_controller_or_config_validator(self):
        script = '''
import builtins
real_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith(('psutil','tkinter','customtkinter','pystray','PIL')) or name in (
        'core.config','core.proc_blocker','core.process_controller','ui.config_gui'):
        raise AssertionError(name)
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded
from core.config_diff import diff_config
from core.models import AppConfig
assert diff_config(None, AppConfig()).is_new
result = diff_config(AppConfig(extra={'flag':True}), AppConfig(block_exes=('a.exe',),extra={'flag':1}))
assert result.extras_changed and result.changes[0].after == 'a.exe'
'''
        result = subprocess.run([sys.executable, "-B", "-c", script],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

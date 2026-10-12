"""A ordem visual preserva os índices, duplicatas e dados de cadastro."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import time
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from core.models import AppConfig, CmdlineRule, ScheduleWindow
from ui.rule_list_view import rule_view_indices


class RuleListViewTests(unittest.TestCase):
    def test_defaults_registered_empty_query_all_fields_and_empty_lists(self):
        config = AppConfig(
            block_exes=("z.exe", "a.exe", "z.exe"),
            block_folders=(r"Z:\Games", r"A:\Games", r"Z:\Games"),
            safelist_exes=("z.exe", "a.exe", "z.exe"),
            block_cmdline=(CmdlineRule("z.exe", "x"), CmdlineRule("a.exe", "x"), CmdlineRule("z.exe", "x")),
        )
        for field in ("block_exes", "block_folders", "safelist_exes", "block_cmdline"):
            with self.subTest(field=field):
                self.assertEqual(rule_view_indices(config, field), (0, 1, 2))
                for order in ("registered", "name_asc", "name_desc"):
                    self.assertEqual(rule_view_indices(AppConfig(), field, order=order), ())

    def test_string_fields_filter_trimmed_casefold_and_keep_original_duplicate_indices(self):
        for field in ("block_exes", "block_folders", "safelist_exes"):
            config = AppConfig(**{field: ("skip", "Straße", "other", "STRASSE", "Straße")})
            with self.subTest(field=field):
                self.assertEqual(rule_view_indices(config, field, " \tSTRASSE\n "), (1, 3, 4))
                self.assertEqual(rule_view_indices(config, field, "absent"), ())
                self.assertEqual(rule_view_indices(config, field, " \t\n"), (0, 1, 2, 3, 4))

    def test_ascending_and_descending_stable_casefold_ties_in_all_string_fields(self):
        for field in ("block_exes", "block_folders", "safelist_exes"):
            config = AppConfig(**{field: ("z", "Beta", "alpha", "BETA", "beta", "z")})
            with self.subTest(field=field):
                self.assertEqual(rule_view_indices(config, field, order="name_asc"), (2, 1, 3, 4, 0, 5))
                self.assertEqual(rule_view_indices(config, field, order="name_desc"), (0, 5, 1, 3, 4, 2))
                self.assertEqual(rule_view_indices(config, field, "beta", "name_desc"), (1, 3, 4))

    def test_filter_then_sort_returns_original_indices_not_visible_positions(self):
        config = AppConfig(block_exes=("skip", "target Z", "skip", "target A", "TARGET z"))
        self.assertEqual(rule_view_indices(config, "block_exes", "target", "name_asc"), (3, 1, 4))
        self.assertEqual(rule_view_indices(config, "block_exes", "target", "name_desc"), (1, 4, 3))
        self.assertEqual(rule_view_indices(config, "block_exes", "target"), (1, 3, 4))

    def test_cmdline_searches_both_fields_and_the_same_newline_join_as_gui(self):
        config = AppConfig(block_cmdline=(
            CmdlineRule("Launcher.EXE", "-mode idle"),
            CmdlineRule("other.exe", "--LAUNCHER active"),
            CmdlineRule("unrelated.exe", "--active"),
            CmdlineRule("prefix.exe", "Suffix"),
        ))
        self.assertEqual(rule_view_indices(config, "block_cmdline", " launcher "), (0, 1))
        self.assertEqual(rule_view_indices(config, "block_cmdline", "ACTIVE"), (1, 2))
        self.assertEqual(rule_view_indices(config, "block_cmdline", "EXE\nsuffix"), (3,))
        self.assertEqual(rule_view_indices(config, "block_cmdline", "exesuffix"), ())

    def test_cmdline_sort_uses_casefold_pair_and_stable_full_pair_ties(self):
        config = AppConfig(block_cmdline=(
            CmdlineRule("z.exe", "a"),
            CmdlineRule("A.exe", "z"),
            CmdlineRule("a.EXE", "B"),
            CmdlineRule("A.EXE", "b"),
            CmdlineRule("a.exe", "a"),
            CmdlineRule("z.exe", "a"),
        ))
        self.assertEqual(rule_view_indices(config, "block_cmdline", order="name_asc"), (4, 2, 3, 1, 0, 5))
        self.assertEqual(rule_view_indices(config, "block_cmdline", order="name_desc"), (0, 5, 1, 2, 3, 4))
        self.assertEqual(rule_view_indices(config, "block_cmdline", "a.exe", "name_desc"), (1, 2, 3, 4))

    def test_cmdline_pair_order_does_not_use_ambiguous_string_concatenation(self):
        config = AppConfig(block_cmdline=(CmdlineRule("ab", "a"), CmdlineRule("a", "z")))
        self.assertEqual(rule_view_indices(config, "block_cmdline", order="name_asc"), (1, 0))
        self.assertEqual(rule_view_indices(config, "block_cmdline", order="name_desc"), (0, 1))

    def test_folder_search_and_sort_use_literal_paths_and_keep_spaces(self):
        config = AppConfig(block_folders=(r"%ZZ_RULE_VIEW%\Games", r"C:\Games\..\Alpha", r"c:/Games", " C:\\Games ", r"~\Games"))
        self.assertEqual(rule_view_indices(config, "block_folders", "zz_rule_view"), (0,))
        self.assertEqual(rule_view_indices(config, "block_folders", ".."), (1,))
        self.assertEqual(rule_view_indices(config, "block_folders", "c:/"), (2,))
        self.assertEqual(rule_view_indices(config, "block_folders", order="name_asc"), (3, 0, 2, 1, 4))
        self.assertEqual(rule_view_indices(config, "block_folders", order="name_desc"), (4, 1, 2, 0, 3))

    def test_spaces_in_rules_are_not_stripped_for_sort(self):
        config = AppConfig(block_exes=("beta", " alpha", "alpha", "alpha "))
        self.assertEqual(rule_view_indices(config, "block_exes", order="name_asc"), (1, 2, 3, 0))
        config = AppConfig(block_cmdline=(CmdlineRule("a", "z"), CmdlineRule("a", " z"), CmdlineRule("a ", "a")))
        self.assertEqual(rule_view_indices(config, "block_cmdline", order="name_asc"), (1, 0, 2))

    def test_wrong_argument_types_raise_type_error(self):
        config = AppConfig()
        for invalid in (None, {}, (), "config", True):
            with self.subTest(config=invalid), self.assertRaises(TypeError):
                rule_view_indices(invalid, "block_exes")
        for name in ("field", "query", "order"):
            for invalid in (None, True, 1, 1.0, [], {}):
                args = {"field": "block_exes", "query": "", "order": "registered", name: invalid}
                with self.subTest(argument=name, value=invalid), self.assertRaises(TypeError):
                    rule_view_indices(config, **args)

    def test_unknown_fields_and_orders_raise_value_error_without_normalization(self):
        for field in ("windows", "extra", "", "BLOCK_EXES", " block_exes "):
            with self.subTest(field=field), self.assertRaises(ValueError):
                rule_view_indices(AppConfig(), field)
        for order in ("", "name", "REGISTERED", " registered ", "reverse"):
            with self.subTest(order=order), self.assertRaises(ValueError):
                rule_view_indices(AppConfig(), "block_exes", order=order)

    def test_tuple_result_and_models_nested_extras_preserved_across_calls(self):
        config = AppConfig(
            windows=(ScheduleWindow(time(9), time(10), (0,)),),
            block_exes=("z.exe", "a.exe", "z.exe"),
            extra={"nested": {"items": [True, 1, "literal"]}},
        )
        original = deepcopy(config)
        values = config.block_exes
        result = rule_view_indices(config, "block_exes", order="name_asc")
        self.assertIsInstance(result, tuple)
        self.assertEqual(result, (1, 0, 2))
        with self.assertRaises(TypeError):
            result[0] = 99
        with self.assertRaises(FrozenInstanceError):
            config.block_exes = ()
        self.assertEqual(rule_view_indices(config, "block_exes"), (0, 1, 2))
        self.assertEqual(config, original)
        self.assertIs(config.block_exes, values)

    def test_pure_helper_never_resolves_paths_reads_environment_validates_or_runs_io(self):
        config = AppConfig(block_folders=(r"%ZZ_RULE_VIEW%\Games", r"~\Other"))
        with patch.dict(os.environ, {}, clear=True), \
                patch("builtins.open", side_effect=AssertionError("IO")), \
                patch.object(Path, "resolve", side_effect=AssertionError("resolve")), \
                patch("os.path.expandvars", side_effect=AssertionError("env")), \
                patch("os.path.expanduser", side_effect=AssertionError("home")), \
                patch("core.config.parse_config", side_effect=AssertionError("validation")), \
                patch("core.config.config_to_dict", side_effect=AssertionError("serialization")), \
                patch("time.time", side_effect=AssertionError("clock")), \
                patch("subprocess.Popen", side_effect=AssertionError("runtime")):
            self.assertEqual(rule_view_indices(config, "block_folders", "games", "name_desc"), (0,))
            self.assertEqual(rule_view_indices(config, "block_folders", order="name_asc"), (0, 1))

    def test_fresh_import_and_call_need_only_models_without_gui_or_config_runtime(self):
        script = '''
import builtins
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name.startswith(('psutil', 'tkinter', 'customtkinter', 'pystray', 'PIL')) or name in (
        'core.config', 'core.process_controller', 'core.proc_blocker', 'ui.config_gui'):
        raise AssertionError(name)
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
from ui.rule_list_view import rule_view_indices
from core.models import AppConfig
assert rule_view_indices(AppConfig(block_exes=('z', 'a', 'z')), 'block_exes', order='name_desc') == (0, 2, 1)
'''
        result = subprocess.run([sys.executable, "-B", "-c", script], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

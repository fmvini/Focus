"""Igualdade tipada sem normalizar, serializar, validar ambiente ou mutar."""

from copy import deepcopy
from dataclasses import replace
from datetime import time
from pathlib import Path
import os
import unittest
from unittest.mock import patch

from core.config_comparison import configs_equal
from core.models import AppConfig, CmdlineRule, ScheduleWindow


class ConfigComparisonTests(unittest.TestCase):
    def test_scalar_types_values_and_nested_json_are_distinguished(self):
        values = (None, False, True, 0, 1, 0.0, 1.0, "", "1", "ação 日本語")
        for left in values:
            for right in values:
                expected = type(left) is type(right) and left == right
                with self.subTest(left=left, right=right, types=(type(left), type(right))):
                    for wrap in (lambda value: value, lambda value: [value],
                                 lambda value: {"nested": [{"value": value}]}):
                        self.assertEqual(configs_equal(
                            AppConfig(extra={"future": wrap(left)}),
                            AppConfig(extra={"future": wrap(right)}),
                        ), expected)

    def test_dict_order_is_ignored_recursively_but_keys_and_types_are_not(self):
        left = AppConfig(extra={"future": {"a": True, "b": [1, {"x": 0.0, "y": None}]}, "text": "ação"})
        reordered = AppConfig(extra={"text": "ação", "future": {"b": [1, {"y": None, "x": 0.0}], "a": True}})
        changed = AppConfig(extra={"text": "ação", "future": {"b": [1, {"y": None, "x": 0.0}], "a": 1}})
        self.assertTrue(configs_equal(left, reordered))
        self.assertTrue(configs_equal(reordered, left))
        self.assertFalse(configs_equal(left, changed))
        self.assertFalse(configs_equal(changed, left))
        self.assertFalse(configs_equal(left, AppConfig(extra={"other": left.extra["future"]})))

    def test_list_order_duplicates_length_and_list_tuple_difference_are_preserved(self):
        left = AppConfig(extra={"values": [True, 1, 1.0]})
        for values in ([1, True, 1.0], [True, 1.0, 1], [True, 1], [True, 1, 1.0, 1.0], (True, 1, 1.0)):
            with self.subTest(values=values):
                self.assertFalse(configs_equal(left, AppConfig(extra={"values": values})))
        self.assertTrue(configs_equal(left, deepcopy(left)))

    def test_all_typed_model_fields_are_compared_without_case_or_order_normalization(self):
        window = ScheduleWindow(time(22), time(2), (6, 0))
        base = AppConfig(
            windows=(window,), block_exes=("Game.EXE", "Game.EXE"),
            block_folders=(r"C:\Games",), safelist_exes=("Keep.EXE",),
            block_cmdline=(CmdlineRule("javaw.exe", " .Minecraft "),),
        )
        self.assertTrue(configs_equal(base, deepcopy(base)))
        variants = (
            replace(base, windows=()),
            replace(base, windows=(replace(window, start=time(21)),)),
            replace(base, windows=(replace(window, end=time(3)),)),
            replace(base, windows=(replace(window, days=(0, 6)),)),
            replace(base, block_exes=("Game.EXE",)),
            replace(base, block_exes=("game.exe", "Game.EXE")),
            replace(base, block_folders=(r"c:\games",)),
            replace(base, safelist_exes=("keep.exe",)),
            replace(base, block_cmdline=(CmdlineRule("JAVAW.EXE", " .Minecraft "),)),
            replace(base, block_cmdline=(CmdlineRule("javaw.exe", ".Minecraft"),)),
        )
        for variant in variants:
            with self.subTest(variant=variant):
                self.assertFalse(configs_equal(base, variant))
                self.assertFalse(configs_equal(variant, base))

    def test_comparison_is_pure_and_never_revalidates_environment_or_serializes(self):
        source = AppConfig(block_folders=(r"%MISSING_COMPARISON_VAR%\Games",), extra={"future": [{"flag": True}]})
        other = deepcopy(source)
        before = deepcopy(source)
        with patch.dict(os.environ, {}, clear=True), \
                patch("core.config.config_to_dict", side_effect=AssertionError("validation")), \
                patch("core.config.parse_config", side_effect=AssertionError("validation")), \
                patch("core.config._serialize_config", side_effect=AssertionError("serialization")), \
                patch("json.dumps", side_effect=AssertionError("serialization")), \
                patch.object(Path, "open", side_effect=AssertionError("IO")), \
                patch.object(Path, "resolve", side_effect=AssertionError("discovery")):
            self.assertTrue(configs_equal(source, other))
            self.assertFalse(configs_equal(source, replace(other, extra={"future": [{"flag": 1}]})))
        self.assertEqual(source, before)
        self.assertIs(type(source.extra["future"][0]["flag"]), bool)
        self.assertEqual(other, before)

    def test_empty_configs_and_none_string_empty_containers_are_distinct(self):
        self.assertTrue(configs_equal(AppConfig(), AppConfig()))
        values = (None, "", [], {})
        for left in values:
            for right in values:
                with self.subTest(left=left, right=right):
                    self.assertEqual(configs_equal(AppConfig(extra={"v": left}), AppConfig(extra={"v": right})),
                                     type(left) is type(right))

    def test_function_does_not_accept_non_config_arguments(self):
        for invalid in (None, {}, [], True, 1):
            with self.subTest(invalid=invalid):
                with self.assertRaises(TypeError):
                    configs_equal(invalid, AppConfig())
                with self.assertRaises(TypeError):
                    configs_equal(AppConfig(), invalid)


if __name__ == "__main__":
    unittest.main()

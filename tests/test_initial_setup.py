"""Catálogo literal do escopo e inclusão pura/atômica em snapshots isolados."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import time
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from core.config import ConfigError, config_to_dict, parse_config
from core.initial_setup import ProcessSuggestion, PROCESS_SUGGESTIONS, with_process_suggestions
from core.models import AppConfig, CmdlineRule, ScheduleWindow


# Expectativas independentes: nomes/capitalização/ordem transcritos do §6.
CATALOG = (
    ("steam", "steam.exe", None),
    ("steam_webhelper", "steamwebhelper.exe", None),
    ("epic_games_launcher", "EpicGamesLauncher.exe", None),
    ("epic_webhelper", "EpicWebHelper.exe", None),
    ("battle_net", "Battle.net.exe", None),
    ("riot_client_services", "RiotClientServices.exe", None),
    ("minecraft", "Minecraft.exe", None),
    ("minecraft_launcher", "MinecraftLauncher.exe", None),
    ("minecraft_java", "javaw.exe", ".minecraft"),
    ("roblox_player", "RobloxPlayerBeta.exe", None),
    ("roblox_launcher", "RobloxPlayerLauncher.exe", None),
    ("league_client", "LeagueClient.exe", None),
    ("valorant", "VALORANT-Win64-Shipping.exe", None),
)


class InitialSetupTests(unittest.TestCase):
    def rich_config(self):
        return AppConfig(
            windows=(ScheduleWindow(time(22), time(2), (6, 0)),
                     ScheduleWindow(time(8), time(9), ())),
            block_exes=("old.exe", "old.exe"),
            block_folders=(r"C:\Jogos", r"C:\Jogos"),
            safelist_exes=("code.exe", "STEAM.EXE", "code.exe"),
            block_cmdline=(CmdlineRule("custom.exe", " literal.* "),) * 2,
            extra={"sites": {"future": ["example.org"]},
                   "pause": {"wait": [None, True]}, "warn_minutes": [5, 1],
                   "dev_apps": ["opaque"], "ação": {"日本語": ["🎮"]}},
        )

    def assert_rejected_without_change(self, config, keys):
        before = deepcopy(config)
        with self.assertRaises(ConfigError):
            with_process_suggestions(config, keys)
        self.assertEqual(config, before)

    def test_exact_catalog_keys_executables_order_and_java_pair(self):
        self.assertIsInstance(PROCESS_SUGGESTIONS, tuple)
        self.assertEqual(tuple((item.key, item.executable, item.contains)
                               for item in PROCESS_SUGGESTIONS), CATALOG)
        self.assertEqual(len({item.key for item in PROCESS_SUGGESTIONS}), 13)
        self.assertTrue(all(isinstance(item, ProcessSuggestion) and item.label.strip()
                            for item in PROCESS_SUGGESTIONS))
        self.assertEqual([item.key for item in PROCESS_SUGGESTIONS if item.contains is not None],
                         ["minecraft_java"])

    def test_suggestion_is_frozen_and_contains_defaults_to_none(self):
        item = ProcessSuggestion("custom", "Custom", "custom.exe")
        self.assertIsNone(item.contains)
        for field, value in (("key", "changed"), ("label", "changed"),
                             ("executable", "changed.exe"), ("contains", "changed")):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError):
                setattr(item, field, value)
        with self.assertRaises(FrozenInstanceError):
            PROCESS_SUGGESTIONS[0].key = "changed"

    def test_each_independent_selection_adds_only_expected_rule(self):
        for key, executable, contains in CATALOG:
            with self.subTest(key=key):
                source = AppConfig()
                result = with_process_suggestions(source, [key])
                expected = (AppConfig(block_exes=(executable,)) if contains is None
                            else AppConfig(block_cmdline=(CmdlineRule(executable, contains),)))
                self.assertEqual(result, expected)
                self.assertEqual(source, AppConfig())
                self.assertEqual(result.windows, ())
                self.assertEqual(result.block_folders, ())
                self.assertEqual(result.safelist_exes, ())
                self.assertEqual(result.extra, {})

    def test_all_selected_reverse_repeated_ids_use_catalog_order(self):
        keys = [item[0] for item in reversed(CATALOG)] * 3
        result = with_process_suggestions(AppConfig(), keys)
        self.assertEqual(result.block_exes, (
            "steam.exe", "steamwebhelper.exe", "EpicGamesLauncher.exe", "EpicWebHelper.exe",
            "Battle.net.exe", "RiotClientServices.exe", "Minecraft.exe", "MinecraftLauncher.exe",
            "RobloxPlayerBeta.exe", "RobloxPlayerLauncher.exe", "LeagueClient.exe",
            "VALORANT-Win64-Shipping.exe",
        ))
        self.assertEqual(result.block_cmdline, (CmdlineRule("javaw.exe", ".minecraft"),))
        self.assertEqual(result.windows, ())
        self.assertEqual(result.block_folders, ())
        self.assertEqual(result.safelist_exes, ())
        self.assertEqual(result.extra, {})

    def test_subset_order_is_independent_of_input_order_or_set_iteration(self):
        selected = ["valorant", "minecraft_java", "steam", "roblox_player"]
        expected = AppConfig(
            block_exes=("steam.exe", "RobloxPlayerBeta.exe", "VALORANT-Win64-Shipping.exe"),
            block_cmdline=(CmdlineRule("javaw.exe", ".minecraft"),),
        )
        for keys in (selected, tuple(reversed(selected)), set(selected), dict.fromkeys(selected)):
            with self.subTest(keys=type(keys).__name__):
                self.assertEqual(with_process_suggestions(AppConfig(), keys), expected)

    def test_empty_selection_returns_independent_validated_copy(self):
        source = self.rich_config()
        for keys in ([], (), iter(()), (key for key in ())):
            with self.subTest(keys=type(keys).__name__):
                result = with_process_suggestions(source, keys)
                self.assertEqual(result, source)
                self.assertIsNot(result, source)
                self.assertIsNot(result.extra, source.extra)
                result.extra["sites"]["future"].append("changed.org")
                self.assertEqual(source.extra["sites"]["future"], ["example.org"])

    def test_preserves_all_other_rules_agenda_extras_existing_order_and_duplicates(self):
        source = self.rich_config()
        before = deepcopy(source)
        result = with_process_suggestions(source, ["steam", "minecraft_java", "epic_games_launcher"])
        self.assertEqual(result.block_exes, ("old.exe", "old.exe", "steam.exe", "EpicGamesLauncher.exe"))
        self.assertEqual(result.block_cmdline, (
            CmdlineRule("custom.exe", " literal.* "), CmdlineRule("custom.exe", " literal.* "),
            CmdlineRule("javaw.exe", ".minecraft"),
        ))
        for field in ("windows", "block_folders", "safelist_exes", "extra"):
            self.assertEqual(getattr(result, field), getattr(source, field))
        self.assertEqual(source, before)
        self.assertEqual(parse_config(config_to_dict(result)), result)

    def test_result_nested_extras_and_source_are_independent_in_both_directions(self):
        source = self.rich_config()
        result = with_process_suggestions(source, ["steam"])
        source.extra["sites"]["future"].append("source.org")
        source.extra["ação"]["日本語"].append("source")
        result.extra["pause"]["wait"].clear()
        result.extra["ação"]["日本語"].append("result")
        self.assertEqual(result.extra["sites"]["future"], ["example.org"])
        self.assertEqual(result.extra["ação"]["日本語"], ["🎮", "result"])
        self.assertEqual(source.extra["pause"]["wait"], [None, True])
        self.assertEqual(source.extra["ação"]["日本語"], ["🎮", "source"])

    def test_existing_executables_casefold_preserves_duplicates_and_original_spelling(self):
        source = AppConfig(block_exes=("STEAM.EXE", "Steam.exe", "RobloxPlayerBeta.EXE", "old.exe"))
        result = with_process_suggestions(source, ["steam", "roblox_player", "valorant"])
        self.assertEqual(result.block_exes, (*source.block_exes, "VALORANT-Win64-Shipping.exe"))

    def test_casefold_not_lower_matches_long_s_unicode_executable(self):
        source = AppConfig(block_exes=("ſteam.exe",))
        self.assertNotEqual(source.block_exes[0].lower(), "steam.exe")
        self.assertEqual(source.block_exes[0].casefold(), "steam.exe")
        self.assertEqual(with_process_suggestions(source, ["steam"]).block_exes, source.block_exes)

    def test_existing_java_pairs_casefold_preserves_duplicates_and_literal_text(self):
        source = AppConfig(block_cmdline=(
            CmdlineRule("JAVAW.EXE", ".MineCraft"), CmdlineRule("javaw.exe", ".MINECRAFT"),
            CmdlineRule("javaw.exe", " .minecraft "), CmdlineRule("other.exe", ".minecraft"),
        ))
        self.assertEqual(with_process_suggestions(source, ["minecraft_java"]), source)

    def test_java_pair_matches_both_components_without_trimming_or_substring(self):
        for rule in (CmdlineRule("java.exe", ".minecraft"), CmdlineRule("javaw.exe", "other"),
                     CmdlineRule("javaw.exe", " .minecraft "), CmdlineRule("javaw.exe", ".minecraft-extra")):
            with self.subTest(rule=rule):
                source = AppConfig(block_cmdline=(rule,))
                result = with_process_suggestions(source, ["minecraft_java"])
                self.assertEqual(result.block_cmdline, (rule, CmdlineRule("javaw.exe", ".minecraft")))
                self.assertEqual(result.block_exes, ())

    def test_lists_are_deduplicated_independently_without_rewriting_existing_java_name(self):
        source = AppConfig(
            block_exes=("javaw.exe",),
            safelist_exes=("steam.exe",),
            block_cmdline=(CmdlineRule("steam.exe", "custom"),),
        )
        result = with_process_suggestions(source, ["steam", "minecraft_java"])
        self.assertEqual(result.block_exes, ("javaw.exe", "steam.exe"))
        self.assertEqual(result.block_cmdline, (CmdlineRule("steam.exe", "custom"),
                                              CmdlineRule("javaw.exe", ".minecraft")))
        self.assertEqual(result.safelist_exes, source.safelist_exes)

    def test_repeated_calls_and_duplicate_keys_do_not_append_equivalent_new_rules(self):
        keys = [key for key, _, _ in CATALOG] * 2
        first = with_process_suggestions(self.rich_config(), keys)
        second = with_process_suggestions(first, reversed(keys))
        self.assertEqual(second, first)
        self.assertIsNot(second, first)
        self.assertIsNot(second.extra, first.extra)

    def test_one_shot_iterable_consumed_once_and_keys_input_is_unchanged(self):
        keys = ["valorant", "steam", "minecraft_java"]

        class Once:
            used = False

            def __iter__(self):
                if self.used:
                    raise AssertionError("second iteration")
                self.used = True
                return iter(keys)

        expected = AppConfig(block_exes=("steam.exe", "VALORANT-Win64-Shipping.exe"),
                             block_cmdline=(CmdlineRule("javaw.exe", ".minecraft"),))
        for selected in (Once(), iter(keys), (key for key in keys), keys):
            with self.subTest(selected=type(selected).__name__):
                self.assertEqual(with_process_suggestions(AppConfig(), selected), expected)
        self.assertEqual(keys, ["valorant", "steam", "minecraft_java"])

    def test_invalid_ids_types_and_iterables_raise_config_error_without_changes(self):
        source = self.rich_config()
        invalid = (
            ["missing"], ["STEAM"], ["steam.exe"], [" steam"], ["steam "], [""],
            [None], [True], [0], [1.0], [[]], [{}], [b"steam"],
            None, True, 0, "steam", "", b"steam", bytearray(),
            ["steam", "minecraft_java", "missing"],
        )
        for keys in invalid:
            with self.subTest(keys=keys):
                self.assert_rejected_without_change(source, keys)

    def test_failing_iterator_creation_and_midstream_are_atomic_with_cause(self):
        source = self.rich_config()
        before = deepcopy(source)
        for error in (TypeError, ValueError, RuntimeError, OverflowError, OSError, LookupError):
            failure = error("selection failure")

            class FailingIterable:
                def __iter__(self):
                    raise failure

            def failing_generator():
                yield "steam"
                yield "minecraft_java"
                raise failure

            for keys in (FailingIterable(), failing_generator()):
                with self.subTest(error=error, keys=type(keys).__name__):
                    with self.assertRaises(ConfigError) as caught:
                        with_process_suggestions(source, keys)
                    self.assertIs(caught.exception.__cause__, failure)
                    self.assertEqual(source, before)
        result = with_process_suggestions(source, ["steam"])
        self.assertEqual(result.block_exes, ("old.exe", "old.exe", "steam.exe"))

    def test_invalid_direct_models_rejected_even_for_empty_selection(self):
        invalid = (
            None, {}, AppConfig(block_exes=("game",)),
            AppConfig(windows=(ScheduleWindow(time(8), time(8)),)),
            AppConfig(windows=(ScheduleWindow(time(8), time(9), (True,)),)),
            AppConfig(block_cmdline=(CmdlineRule("javaw.exe", ""),)),
            AppConfig(block_cmdline=(CmdlineRule("javaw.exe", "\n"),)),
            AppConfig(safelist_exes=("code",)), AppConfig(block_folders=("relative",)),
            AppConfig(extra={"block_exes": ["reserved.exe"]}),
        )
        for source in invalid:
            for keys in ([], ["steam"]):
                with self.subTest(source=source, keys=keys):
                    self.assert_rejected_without_change(source, keys)

    def test_final_validation_failure_does_not_mutate_source(self):
        source = self.rich_config()
        before = deepcopy(source)
        with patch("core.initial_setup.parse_config", side_effect=ConfigError("final validation")):
            with self.assertRaisesRegex(ConfigError, "final validation"):
                with_process_suggestions(source, ["steam", "minecraft_java"])
        self.assertEqual(source, before)

    def test_existing_folder_variables_use_config_validation_without_discovery(self):
        source = AppConfig(block_folders=(r"%FOCUS_SETUP_TEST%\Games",))
        with patch.dict(os.environ, {"FOCUS_SETUP_TEST": r"C:\Study"}):
            result = with_process_suggestions(source, ["steam"])
            self.assertEqual(result.block_folders, source.block_folders)
        with patch.dict(os.environ, {}, clear=True):
            self.assert_rejected_without_change(source, [])

    def test_function_does_not_open_files_discover_installations_or_create_processes(self):
        with patch.object(Path, "open", side_effect=AssertionError("file IO")), \
             patch.object(Path, "resolve", side_effect=AssertionError("discovery")), \
             patch.object(Path, "glob", side_effect=AssertionError("discovery")), \
             patch("os.replace", side_effect=AssertionError("file write")), \
             patch("os.mkdir", side_effect=AssertionError("directory write")), \
             patch("subprocess.Popen", side_effect=AssertionError("process effect")), \
             patch("time.time", side_effect=AssertionError("clock")):
            result = with_process_suggestions(self.rich_config(), [key for key, _, _ in CATALOG])
        self.assertEqual(result.windows, self.rich_config().windows)
        self.assertNotIn("javaw.exe", result.block_exes)

    def test_module_and_function_do_not_import_psutil_gui_or_blocker(self):
        script = '''
import builtins
real_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name in ('psutil', 'tkinter', 'customtkinter', 'pystray', 'core.proc_blocker', 'core.process_controller'):
        raise AssertionError('effect dependency imported')
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded
from core.initial_setup import with_process_suggestions, PROCESS_SUGGESTIONS
from core.models import AppConfig
source = AppConfig()
assert with_process_suggestions(source, []).windows == ()
result = with_process_suggestions(source, [item.key for item in PROCESS_SUGGESTIONS])
assert result.windows == () and source == AppConfig()
assert 'javaw.exe' not in result.block_exes
assert result.block_cmdline[0].contains == '.minecraft'
'''
        result = subprocess.run([sys.executable, "-B", "-c", script],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

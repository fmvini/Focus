"""Revisão estática informativa com fonte única das proteções obrigatórias."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import time
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from core.config import ConfigError
from core.config_review import review_config
from core.models import AppConfig, CmdlineRule, ScheduleWindow


WINDOW = ScheduleWindow(time(9), time(12), (0, 2))


class ConfigReviewTests(unittest.TestCase):
    def test_empty_disabled_and_target_counts_exclude_safelist(self):
        report = review_config(AppConfig(safelist_exes=("keep.exe",)))
        self.assertEqual((report.active_windows, report.target_rules), (0, 0))
        self.assertEqual([item.code for item in report.items], ["no_windows", "no_targets"])
        disabled = ScheduleWindow(time(9), time(12), ())
        report = review_config(AppConfig(windows=(disabled,), block_exes=("game.exe",)))
        self.assertEqual((report.active_windows, report.target_rules), (0, 1))
        self.assertEqual([item.code for item in report.items], ["no_windows"])

    def test_valid_independent_rules_have_no_static_items(self):
        report = review_config(AppConfig(windows=(WINDOW,), block_exes=("game.exe",),
                                        block_folders=(r"C:\Games",), safelist_exes=("code.exe",),
                                        block_cmdline=(CmdlineRule("javaw.exe", ".minecraft"),)))
        self.assertEqual(report.items, ())
        self.assertEqual((report.active_windows, report.target_rules), (1, 3))

    def test_duplicate_indices_original_order_and_literal_pairs(self):
        source = AppConfig(windows=(WINDOW, ScheduleWindow(time(9), time(12), (2, 0))),
                           block_exes=("ſteam.exe", "STEAM.EXE"),
                           block_folders=(r"C:\Games", r"c:\games", r"C:\Games\..\Games"),
                           safelist_exes=("keep.exe", "KEEP.EXE"),
                           block_cmdline=(CmdlineRule("javaw.exe", ".Minecraft"),
                                          CmdlineRule("JAVAW.EXE", ".MINECRAFT"),
                                          CmdlineRule("javaw.exe", " .minecraft ")))
        report = review_config(source)
        duplicates = [(item.field, item.index) for item in report.items if item.code == "duplicate"]
        self.assertEqual(duplicates, [("windows", 1), ("block_exes", 1), ("block_folders", 1),
                                      ("safelist_exes", 1), ("block_cmdline", 1)])
        self.assertTrue(all("item 1" in item.detail for item in report.items if item.code == "duplicate"))

    def test_mandatory_and_user_protections_precede_name_and_cmdline_rules(self):
        source = AppConfig(windows=(WINDOW,), block_exes=("CODE.EXE", "game.exe"),
                           safelist_exes=("GAME.EXE", "code.exe"),
                           block_cmdline=(CmdlineRule("BRAVE.EXE", "target"), CmdlineRule("Game.exe", "target")))
        report = review_config(source)
        self.assertEqual([(item.code, item.field, item.index) for item in report.items], [
            ("mandatory_protection", "block_exes", 0), ("user_protection", "block_exes", 1),
            ("mandatory_protection", "block_cmdline", 0), ("user_protection", "block_cmdline", 1),
        ])
        self.assertEqual(report.target_rules, 4)  # Configured count, not predicted terminations.

    def test_java_name_note_does_not_flag_combined_rule_or_unknown_names(self):
        source = AppConfig(windows=(WINDOW,), block_exes=("JAVAW.EXE", "unknown.exe"),
                           block_cmdline=(CmdlineRule("javaw.exe", ".minecraft"),))
        report = review_config(source)
        self.assertEqual([(item.code, item.index) for item in report.items], [("java_name", 0)])

    def test_frozen_report_and_source_unchanged_with_nested_extras(self):
        source = AppConfig(windows=(WINDOW,), block_exes=("same.exe", "SAME.EXE"),
                           extra={"future": {"Unicode": ["日本語"]}})
        before = deepcopy(source)
        report = review_config(source)
        self.assertEqual(source, before)
        self.assertIsInstance(report.items, tuple)
        with self.assertRaises(FrozenInstanceError):
            report.target_rules = 0
        with self.assertRaises(FrozenInstanceError):
            report.items[0].detail = "changed"

    def test_invalid_direct_model_is_rejected_and_review_has_no_io_or_clock(self):
        for source in (None, AppConfig(block_exes=("invalid",)),
                       AppConfig(windows=(ScheduleWindow(time(9), time(9)),))):
            with self.subTest(source=source), self.assertRaises(ConfigError):
                review_config(source)
        with patch.object(Path, "open", side_effect=AssertionError("IO")), \
                patch.object(Path, "resolve", side_effect=AssertionError("discovery")), \
                patch("subprocess.Popen", side_effect=AssertionError("process")), \
                patch("time.time", side_effect=AssertionError("clock")):
            report = review_config(AppConfig(windows=(WINDOW,), block_exes=("game.exe",)))
        self.assertEqual(report.items, ())

    def test_import_does_not_load_controller_blocker_psutil_or_graphics(self):
        script = '''
import builtins,sys
original = builtins.__import__
def guarded(name,*args,**kwargs):
    if name.startswith(('psutil','tkinter','customtkinter','pystray','PIL')) or name in ('core.proc_blocker','core.process_controller'):
        raise AssertionError(name)
    return original(name,*args,**kwargs)
builtins.__import__ = guarded
from core.config_review import review_config
from core.models import AppConfig
assert review_config(AppConfig()).target_rules == 0
'''
        result = subprocess.run([sys.executable, "-B", "-c", script], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_blocker_and_review_use_identical_catalog_object(self):
        from core.proc_blocker import MANDATORY_NAMES as blocker_names
        from core.process_catalog import MANDATORY_NAMES
        self.assertIs(blocker_names, MANDATORY_NAMES)
        for name in MANDATORY_NAMES:
            if not name.endswith(".exe"):
                continue
            report = review_config(AppConfig(windows=(WINDOW,), block_exes=(name,)))
            self.assertEqual([item.code for item in report.items], ["mandatory_protection"])


if __name__ == "__main__":
    unittest.main()

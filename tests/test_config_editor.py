"""CRUD e isolamento do rascunho, sem arquivos ou efeitos no Windows."""

from datetime import time
import os
from pathlib import Path
import unittest
from unittest.mock import patch

from core.config import ConfigError, config_to_dict, parse_config
from core.config_editor import ConfigDraft
from core.models import AppConfig, CmdlineRule, ScheduleWindow


class ConfigDraftTests(unittest.TestCase):
    def assert_rejected_without_change(self, draft, action):
        before = draft.config
        with self.assertRaises(ConfigError):
            action()
        self.assertEqual(draft.config, before)

    def test_constructor_validates_direct_models_without_changing_source(self):
        invalid = (
            None,
            AppConfig(windows=(ScheduleWindow(time(8), time(8)),)),
            AppConfig(windows=(ScheduleWindow(time(8), time(9), (True,)),)),
            AppConfig(block_exes=("game",)),
            AppConfig(block_cmdline=(CmdlineRule("javaw.exe", ""),)),
            AppConfig(extra={"block_exes": ["game.exe"]}),
        )
        for config in invalid:
            with self.subTest(config=config), self.assertRaises(ConfigError):
                ConfigDraft(config)

    def test_constructor_and_property_defend_nested_extras(self):
        opaque = {"sites": {"Study": ["example.org"]}, "pause": {"future": [1]}}
        source = AppConfig(extra=opaque)
        draft = ConfigDraft(source)
        opaque["sites"]["Study"].append("source-change.org")
        first = draft.config
        first.extra["sites"]["Study"].append("snapshot-change.org")
        first.extra["pause"]["future"].clear()
        first.extra["new"] = True
        self.assertEqual(draft.config.extra, {
            "sites": {"Study": ["example.org"]}, "pause": {"future": [1]},
        })
        self.assertIsNot(draft.config, draft.config)

    def test_window_crud_defaults_disabled_overnight_and_order(self):
        draft = ConfigDraft(AppConfig())
        draft.add_window("08:00", "12:00")
        draft.add_window("22:00", "02:00", (day for day in (0, 4)))
        draft.add_window("14:00", "18:00", [])
        self.assertEqual([w.days for w in draft.config.windows], [tuple(range(7)), (0, 4), ()])
        draft.update_window(1, "23:00", "01:00", (6,))
        self.assertEqual(draft.config.windows[1], ScheduleWindow(time(23), time(1), (6,)))
        draft.update_window(1, "22:30", "02:30")
        self.assertEqual(draft.config.windows[1].days, tuple(range(7)))
        draft.remove_window(0)
        self.assertEqual([w.start for w in draft.config.windows], [time(22, 30), time(14)])
        draft.remove_window(1)
        draft.remove_window(0)
        self.assertEqual(draft.config.windows, ())

    def test_days_are_copied_without_coercion(self):
        days = [4, 0]
        draft = ConfigDraft(AppConfig())
        draft.add_window("08:00", "09:00", days)
        days.clear()
        self.assertEqual(draft.config.windows[0].days, (4, 0))

    def test_failed_days_iteration_preserves_draft_and_allows_retry(self):
        draft = ConfigDraft(AppConfig(extra={"opaque": {"values": [1]}}))
        draft.add_window("08:00", "09:00", [4])

        def failing_days(error):
            yield 0
            raise error("dias interrompidos")

        for error in (TypeError, ValueError, RuntimeError, OverflowError):
            with self.subTest(error=error):
                self.assert_rejected_without_change(
                    draft, lambda: draft.add_window("10:00", "11:00", failing_days(error)),
                )
                self.assert_rejected_without_change(
                    draft, lambda: draft.update_window(0, "10:00", "11:00", failing_days(error)),
                )

        draft.update_window(0, "10:00", "11:00", range(2))
        self.assertEqual(draft.config.windows, (ScheduleWindow(time(10), time(11), (0, 1)),))
        self.assertEqual(draft.config.extra, {"opaque": {"values": [1]}})

    def test_bad_window_values_preserve_whole_draft(self):
        draft = ConfigDraft(AppConfig(extra={"opaque": [1]}))
        draft.add_window("08:00", "09:00", [0])
        invalid = (
            ("8:00", "09:00", None),
            ("08:00", "08:00", None),
            ("24:00", "09:00", None),
            ("08:00:00", "09:00", None),
            (None, "09:00", None),
            ("08:00", "09:00", True),
            ("08:00", "09:00", 0),
            ("08:00", "09:00", "0,1"),
            ("08:00", "09:00", [False]),
            ("08:00", "09:00", [1.0]),
            ("08:00", "09:00", [0, 0]),
            ("08:00", "09:00", [-1]),
            ("08:00", "09:00", [7]),
        )
        for start, end, days in invalid:
            with self.subTest(start=start, end=end, days=days):
                self.assert_rejected_without_change(draft, lambda: draft.add_window(start, end, days))
                self.assert_rejected_without_change(draft, lambda: draft.update_window(0, start, end, days))

    def test_rule_crud_for_each_typed_field_preserves_duplicates_and_order(self):
        cases = (
            ("block_exes", "GAME.EXE", "other.exe"),
            ("safelist_exes", "Code.exe", "custom.exe"),
            ("block_folders", r"C:\Games", r"D:\Other"),
            ("block_cmdline", {"executable": "javaw.exe", "contains": ".Minecraft"},
             {"executable": "game.exe", "contains": "literal.*"}),
        )
        for field, first, second in cases:
            with self.subTest(field=field):
                draft = ConfigDraft(AppConfig())
                draft.add_rule(field, first)
                draft.add_rule(field, first)
                draft.add_rule(field, second)
                self.assertEqual(config_to_dict(draft.config)[field], [first, first, second])
                draft.update_rule(field, 1, second)
                self.assertEqual(config_to_dict(draft.config)[field], [first, second, second])
                draft.remove_rule(field, 0)
                self.assertEqual(config_to_dict(draft.config)[field], [second, second])
                draft.remove_rule(field, 1)
                draft.remove_rule(field, 0)
                self.assertEqual(getattr(draft.config, field), ())

    def test_cmdline_inputs_are_copied_and_literal_is_preserved(self):
        draft = ConfigDraft(AppConfig())
        added = {"executable": "javaw.exe", "contains": " .Minecraft "}
        draft.add_rule("block_cmdline", added)
        added["contains"] = "changed"
        self.assertEqual(draft.config.block_cmdline, (CmdlineRule("javaw.exe", " .Minecraft "),))
        updated = {"executable": "GAME.EXE", "contains": "literal.*"}
        draft.update_rule("block_cmdline", 0, updated)
        updated.clear()
        self.assertEqual(draft.config.block_cmdline, (CmdlineRule("GAME.EXE", "literal.*"),))

    def test_folder_variables_use_existing_validation_and_preserve_input(self):
        with patch.dict(os.environ, {"FOCUS_EDITOR_FOLDER": r"C:\Student\Local"}):
            draft = ConfigDraft(AppConfig())
            draft.add_rule("block_folders", r"%FOCUS_EDITOR_FOLDER%\Games")
            self.assertEqual(draft.config.block_folders, (r"%FOCUS_EDITOR_FOLDER%\Games",))
            self.assert_rejected_without_change(draft, lambda: draft.add_rule("block_folders", "relative"))
            self.assert_rejected_without_change(draft, lambda: draft.add_rule("block_folders", r"C:\Games\*"))
        with patch.dict(os.environ, {}, clear=True):
            draft = ConfigDraft(AppConfig())
            self.assert_rejected_without_change(draft, lambda: draft.add_rule("block_folders", r"%FOCUS_EDITOR_MISSING%\Games"))

    def test_bad_rule_values_preserve_whole_draft(self):
        cases = (
            ("block_exes", "game.exe", ("game", " game.exe", r"C:\game.exe", None)),
            ("safelist_exes", "code.exe", ("*", "", ["code.exe"], False)),
            ("block_folders", r"C:\Games", ("relative", "", r"C:\Games\*", None)),
            ("block_cmdline", {"executable": "javaw.exe", "contains": ".minecraft"}, (
                ".minecraft", {"contains": ".minecraft"}, {"executable": "javaw.exe"},
                {"executable": "javaw.exe", "contains": " "},
                {"executable": "javaw.exe", "contains": "line\nnext"},
                {"executable": "javaw.exe", "contains": "ok", "unknown": True},
                CmdlineRule("javaw.exe", ".minecraft"),
            )),
        )
        for field, valid, invalid in cases:
            draft = ConfigDraft(AppConfig(extra={"opaque": {"values": [1]}}))
            draft.add_rule(field, valid)
            for value in invalid:
                with self.subTest(field=field, value=value):
                    self.assert_rejected_without_change(draft, lambda: draft.add_rule(field, value))
                    self.assert_rejected_without_change(draft, lambda: draft.update_rule(field, 0, value))

    def test_unknown_fields_cannot_edit_extras_or_windows(self):
        draft = ConfigDraft(AppConfig(extra={"sites": {"group": ["example.org"]}}))
        for field in ("sites", "windows", "dev_apps", "pause", "", None, [], {}):
            with self.subTest(field=field):
                self.assert_rejected_without_change(draft, lambda: draft.add_rule(field, "game.exe"))
                self.assert_rejected_without_change(draft, lambda: draft.update_rule(field, 0, "game.exe"))
                self.assert_rejected_without_change(draft, lambda: draft.remove_rule(field, 0))

    def test_strict_zero_based_indices_for_all_mutations(self):
        class IntSubclass(int):
            pass

        draft = ConfigDraft(AppConfig())
        draft.add_window("08:00", "09:00")
        for field in ("block_exes", "block_folders", "safelist_exes", "block_cmdline"):
            value = ({"executable": "game.exe", "contains": "x"} if field == "block_cmdline"
                     else r"C:\Games" if field == "block_folders" else "game.exe")
            draft.add_rule(field, value)
        for index in (-1, 1, 50, True, False, 0.0, "0", None, [], IntSubclass(0)):
            with self.subTest(index=index):
                self.assert_rejected_without_change(draft, lambda: draft.update_window(index, "09:00", "10:00"))
                self.assert_rejected_without_change(draft, lambda: draft.remove_window(index))
                for field in ("block_exes", "block_folders", "safelist_exes", "block_cmdline"):
                    self.assert_rejected_without_change(draft, lambda: draft.update_rule(field, index, None))
                    self.assert_rejected_without_change(draft, lambda: draft.remove_rule(field, index))
        empty = ConfigDraft(AppConfig())
        self.assert_rejected_without_change(empty, lambda: empty.update_window(0, "08:00", "09:00"))
        self.assert_rejected_without_change(empty, lambda: empty.remove_window(0))
        for field in ("block_exes", "block_folders", "safelist_exes", "block_cmdline"):
            with self.subTest(empty_field=field):
                self.assert_rejected_without_change(empty, lambda: empty.update_rule(field, 0, None))
                self.assert_rejected_without_change(empty, lambda: empty.remove_rule(field, 0))

    def test_roundtrip_retains_all_extras_and_other_typed_fields(self):
        source = parse_config({
            "windows": [{"start": "08:00", "end": "09:00", "days": [0]}],
            "block_exes": ["old.exe"], "block_folders": [r"C:\Games"],
            "safelist_exes": ["code.exe"],
            "block_cmdline": [{"executable": "javaw.exe", "contains": ".minecraft"}],
            "sites": {"future": ["example.org"]}, "dev_apps": ["opaque"],
            "pause": {"unvalidated": "preserved"}, "warn_minutes": [5, 1],
            "unknown": [None, {"nested": True}],
        })
        draft = ConfigDraft(source)
        draft.update_rule("block_exes", 0, "new.exe")
        draft.update_window(0, "22:00", "02:00", [])
        published = draft.config
        self.assertEqual(published.extra, source.extra)
        self.assertEqual(published.block_folders, source.block_folders)
        self.assertEqual(published.safelist_exes, source.safelist_exes)
        self.assertEqual(published.block_cmdline, source.block_cmdline)
        self.assertEqual(parse_config(config_to_dict(published)), published)
        self.assertEqual(source.block_exes, ("old.exe",))
        self.assertEqual(source.windows[0].days, (0,))

    def test_draft_operations_do_not_read_or_write_files(self):
        with patch.object(Path, "open", side_effect=AssertionError("IO proibido")), \
             patch.object(Path, "mkdir", side_effect=AssertionError("IO proibido")), \
             patch("os.replace", side_effect=AssertionError("IO proibido")):
            draft = ConfigDraft(AppConfig(extra={"sites": ["opaque"]}))
            draft.add_window("08:00", "09:00")
            draft.update_window(0, "09:00", "10:00", [])
            draft.remove_window(0)
            draft.add_rule("block_exes", "game.exe")
            draft.update_rule("block_exes", 0, "other.exe")
            draft.remove_rule("block_exes", 0)
            self.assertEqual(draft.config, AppConfig(extra={"sites": ["opaque"]}))


if __name__ == "__main__":
    unittest.main()

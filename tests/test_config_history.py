"""Histórico em memória: restaurar modelos validados sem gravar arquivos."""

from pathlib import Path
import os
import shutil
import unittest
from unittest.mock import patch
from uuid import uuid4

from core.config import ConfigError, _serialize_config
from core.config_editor import ConfigDraft
from core.config_session import ConfigSession
from core.initial_setup import with_process_suggestions
from core.models import AppConfig


class ConfigHistoryTests(unittest.TestCase):
    def test_replace_changes_numeric_json_types_and_undo_redo_restore_exact_types(self):
        for before, after in ((True, 1), (False, 0), (1, 1.0), (0, 0.0), (1.0, True)):
            with self.subTest(before=before, after=after):
                draft = ConfigDraft(AppConfig(extra={"future": {"values": [before]}}))
                draft.replace_config(AppConfig(extra={"future": {"values": [after]}}))
                self.assertIs(type(draft.config.extra["future"]["values"][0]), type(after))
                self.assertTrue(draft.can_undo)
                self.assertFalse(draft.can_redo)
                self.assertTrue(draft.undo())
                self.assertIs(type(draft.config.extra["future"]["values"][0]), type(before))
                self.assertTrue(draft.redo())
                self.assertIs(type(draft.config.extra["future"]["values"][0]), type(after))

    def test_real_dict_reorder_noop_preserves_redo_but_type_change_creates_branch(self):
        draft = ConfigDraft(AppConfig(extra={"future": {"a": True, "b": [0.0]}}))
        draft.add_rule("block_exes", "old-branch.exe")
        draft.undo()
        reordered = AppConfig(extra={"future": {"b": [0.0], "a": True}})
        draft.replace_config(reordered)
        self.assertTrue(draft.can_redo)
        self.assertFalse(draft.can_undo)
        with self.assertRaises(ConfigError):
            draft.replace_config(AppConfig(extra=reordered.extra, block_exes=("invalid",)))
        self.assertTrue(draft.can_redo)
        draft.replace_config(AppConfig(extra={"future": {"b": [0.0], "a": 1}}))
        self.assertFalse(draft.can_redo)
        self.assertFalse(draft.redo())
        self.assertTrue(draft.can_undo)
        draft.undo()
        self.assertIs(type(draft.config.extra["future"]["a"]), bool)
        draft.redo()
        self.assertIs(type(draft.config.extra["future"]["a"]), int)
        self.assertEqual(draft.config.block_exes, ())

    def test_initial_history_empty_and_public_copies_cannot_mutate_restored_state(self):
        source = AppConfig(extra={"future": {"values": [1]}})
        draft = ConfigDraft(source)
        self.assertFalse(draft.can_undo)
        self.assertFalse(draft.can_redo)
        self.assertFalse(draft.undo())
        self.assertFalse(draft.redo())
        draft.add_rule("block_exes", "game.exe")
        exposed = draft.config
        exposed.extra["future"]["values"].append(2)
        source.extra["future"]["values"].append(3)
        self.assertTrue(draft.undo())
        self.assertEqual(draft.config.extra, {"future": {"values": [1]}})
        self.assertTrue(draft.redo())
        self.assertEqual(draft.config.extra, {"future": {"values": [1]}})

    def test_window_and_rule_operations_restore_complete_ordered_snapshots(self):
        draft = ConfigDraft(AppConfig())
        states = [draft.config]
        operations = (
            lambda: draft.add_window("22:00", "02:00", [6]),
            lambda: draft.duplicate_window(0),
            lambda: draft.update_window(1, "09:00", "11:00", []),
            lambda: draft.add_rule("block_exes", "game.exe"),
            lambda: draft.add_rule("block_cmdline", {"executable": "javaw.exe", "contains": ".minecraft"}),
            lambda: draft.update_rule("block_exes", 0, "other.exe"),
            lambda: draft.remove_window(0),
            lambda: draft.remove_rule("block_cmdline", 0),
        )
        for operation in operations:
            operation()
            states.append(draft.config)
        for expected in reversed(states[:-1]):
            self.assertTrue(draft.undo())
            self.assertEqual(draft.config, expected)
        self.assertFalse(draft.undo())
        for expected in states[1:]:
            self.assertTrue(draft.redo())
            self.assertEqual(draft.config, expected)
        self.assertFalse(draft.redo())

    def test_invalid_and_noop_edits_preserve_redo(self):
        draft = ConfigDraft(AppConfig())
        draft.add_rule("block_exes", "first.exe")
        draft.add_rule("block_exes", "second.exe")
        draft.undo()
        draft.update_rule("block_exes", 0, "first.exe")
        self.assertEqual(draft.add_executable_paths("block_exes", ["FIRST.EXE"]), 0)
        with self.assertRaises(ConfigError):
            draft.add_rule("block_exes", "invalid")
        self.assertTrue(draft.can_redo)
        draft.redo()
        self.assertEqual(draft.config.block_exes, ("first.exe", "second.exe"))
        draft.undo()
        draft.undo()
        self.assertEqual(draft.config.block_exes, ())

    def test_branch_after_undo_discards_old_redo_only_after_success(self):
        draft = ConfigDraft(AppConfig())
        draft.add_rule("block_exes", "first.exe")
        draft.add_rule("block_exes", "second.exe")
        draft.undo()
        draft.add_rule("block_exes", "branch.exe")
        self.assertFalse(draft.can_redo)
        self.assertFalse(draft.redo())
        draft.undo()
        self.assertEqual(draft.config.block_exes, ("first.exe",))
        draft.redo()
        self.assertEqual(draft.config.block_exes, ("first.exe", "branch.exe"))

    def test_suggestions_and_file_batch_are_single_undoable_edits(self):
        draft = ConfigDraft(AppConfig())
        draft.add_executable_paths("block_exes", ["first.exe", "second.exe"])
        draft.replace_config(with_process_suggestions(draft.config, ["steam", "minecraft_java"]))
        draft.undo()
        self.assertEqual(draft.config.block_exes, ("first.exe", "second.exe"))
        self.assertEqual(draft.config.block_cmdline, ())
        draft.undo()
        self.assertEqual(draft.config, AppConfig())
        draft.redo()
        draft.redo()
        self.assertEqual(draft.config.block_exes, ("first.exe", "second.exe", "steam.exe"))

    def test_history_is_bounded_to_fifty_successful_edits(self):
        draft = ConfigDraft(AppConfig())
        for index in range(55):
            draft.add_rule("block_exes", f"game{index}.exe")
        for _ in range(50):
            self.assertTrue(draft.undo())
        self.assertFalse(draft.undo())
        self.assertEqual(draft.config.block_exes, tuple(f"game{i}.exe" for i in range(5)))
        for _ in range(50):
            self.assertTrue(draft.redo())
        self.assertFalse(draft.redo())
        self.assertEqual(len(draft.config.block_exes), 55)

    def test_restore_validation_failure_preserves_both_history_and_config(self):
        with patch.dict(os.environ, {"FOCUS_HISTORY_ROOT": r"C:\Games"}):
            draft = ConfigDraft(AppConfig(block_folders=(r"%FOCUS_HISTORY_ROOT%\Library",)))
            draft.remove_rule("block_folders", 0)
            with patch.dict(os.environ, {}, clear=True):
                with self.assertRaises(ConfigError):
                    draft.undo()
                self.assertEqual(draft.config.block_folders, ())
                self.assertTrue(draft.can_undo)
                self.assertFalse(draft.can_redo)
            self.assertTrue(draft.undo())
            before = draft.config
            with patch("core.config_editor.parse_config", side_effect=ConfigError("validation")):
                with self.assertRaises(ConfigError):
                    draft.redo()
                self.assertEqual(draft.config, before)
                self.assertTrue(draft.can_redo)
            self.assertTrue(draft.redo())
            self.assertEqual(draft.config.block_folders, ())

    def test_save_keeps_history_dirty_tracks_baseline_import_reload_reset_history(self):
        root = Path(__file__).resolve().parents[1] / f".editor-integration-{uuid4().hex}"
        root.mkdir()
        self.addCleanup(shutil.rmtree, root)
        path = root / "config.json"
        session = ConfigSession.for_new(path)
        session.draft.add_rule("block_exes", "game.exe")
        session.save()
        saved = path.read_bytes()
        self.assertTrue(session.draft.can_undo)
        session.draft.undo()
        self.assertTrue(session.dirty)
        self.assertEqual(path.read_bytes(), saved)
        session.draft.redo()
        self.assertFalse(session.dirty)
        source = root / "import.json"
        source.write_bytes(_serialize_config(AppConfig(block_exes=("imported.exe",))))
        session.import_config(source)
        self.assertFalse(session.draft.can_undo)
        self.assertFalse(session.draft.can_redo)
        session.draft.add_rule("block_exes", "extra.exe")
        session.reload()
        self.assertFalse(session.draft.can_undo)
        self.assertEqual(session.draft.config.block_exes, ("game.exe",))

    def test_undo_redo_are_pure_and_replace_invalid_model_is_atomic(self):
        draft = ConfigDraft(AppConfig())
        draft.add_rule("safelist_exes", "keep.exe")
        with self.assertRaises(ConfigError):
            draft.replace_config(AppConfig(block_exes=("invalid",)))
        with patch.object(Path, "open", side_effect=AssertionError("IO")), \
                patch("os.replace", side_effect=AssertionError("write")), \
                patch("subprocess.Popen", side_effect=AssertionError("process")):
            self.assertTrue(draft.undo())
            self.assertEqual(draft.config, AppConfig())
            self.assertTrue(draft.redo())
            self.assertEqual(draft.config.safelist_exes, ("keep.exe",))


if __name__ == "__main__":
    unittest.main()

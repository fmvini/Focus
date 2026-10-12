"""Sessão gráfica com repositório real e arquivos isolados."""

from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from uuid import uuid4

from core.config import ConfigError, load_config
from core.models import AppConfig
from core.config_repository import ConfigConflictError
from core.config_session import ConfigSession


class ConfigSessionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / f".editor-integration-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = self.root / "config.json"
        self.path.write_text(json.dumps({"windows": [], "future": {"keep": ["ação", 12]}}), encoding="utf-8")
        self.session = ConfigSession(self.path)

    def test_import_changed_json_types_is_dirty_keeps_baseline_and_saves_exact_types(self):
        source = self.root / "import.json"
        for before, after in ((True, 1), (False, 0), (1, 1.0), (0, 0.0), (1.0, True)):
            with self.subTest(before=before, after=after):
                self.path.write_text(json.dumps({"windows": [], "future": [{"value": before}]}), encoding="utf-8")
                session = ConfigSession(self.path)
                baseline = session.snapshot
                original = self.path.read_bytes()
                session.draft.add_rule("block_exes", "pending.exe")
                session.draft.undo()
                self.assertTrue(session.draft.can_redo)
                source.write_text(json.dumps({"windows": [], "future": [{"value": after}]}), encoding="utf-8")
                source_bytes = source.read_bytes()
                session.import_config(source)
                self.assertTrue(session.dirty)
                self.assertFalse(session.is_new)
                self.assertIs(session.snapshot, baseline)
                self.assertIs(type(baseline.config.extra["future"][0]["value"]), type(before))
                self.assertIs(type(session.draft.config.extra["future"][0]["value"]), type(after))
                self.assertFalse(session.draft.can_undo)
                self.assertFalse(session.draft.can_redo)
                self.assertEqual(self.path.read_bytes(), original)
                session.save()
                self.assertFalse(session.dirty)
                self.assertIs(type(load_config(self.path).extra["future"][0]["value"]), type(after))
                self.assertIs(type(session.snapshot.config.extra["future"][0]["value"]), type(after))
                self.assertEqual(session.snapshot.contents, self.path.read_bytes())
                self.assertEqual(source.read_bytes(), source_bytes)

    def test_typed_import_conflict_preserves_external_bytes_baseline_and_history(self):
        self.path.write_bytes(b'{"windows":[],"future":{"flag":true}}')
        session = ConfigSession(self.path)
        baseline = session.snapshot
        source = self.root / "import.json"
        source.write_bytes(b'{"windows":[],"future":{"flag":1}}')
        session.import_config(source)
        draft = session.draft
        draft.add_rule("block_exes", "redo.exe")
        draft.undo()
        external = b'{"windows":[],"future":{"external":0}}'
        self.path.write_bytes(external)
        with self.assertRaises(ConfigConflictError):
            session.save()
        self.assertTrue(session.dirty)
        self.assertIs(session.snapshot, baseline)
        self.assertIs(session.draft, draft)
        self.assertTrue(draft.can_redo)
        self.assertIs(type(draft.config.extra["future"]["flag"]), int)
        self.assertIs(type(baseline.config.extra["future"]["flag"]), bool)
        self.assertEqual(self.path.read_bytes(), external)
        draft.redo()
        self.assertEqual(draft.config.block_exes, ("redo.exe",))
        session.reload()
        self.assertFalse(session.dirty)
        self.assertFalse(session.draft.can_redo)
        self.assertFalse(session.draft.can_undo)
        self.assertEqual(session.snapshot.contents, external)

    def test_failed_typed_save_keeps_history_and_success_keeps_undo_dirty_against_saved_type(self):
        self.path.write_bytes(b'{"windows":[],"future":{"flag":false}}')
        session = ConfigSession(self.path)
        baseline = session.snapshot
        original = self.path.read_bytes()
        draft = session.draft
        draft.replace_config(AppConfig(extra={"future": {"flag": 0}}))
        self.assertTrue(session.dirty)
        with patch("core.config.os.replace", side_effect=PermissionError("denied")):
            with self.assertRaises(ConfigError):
                session.save()
        self.assertIs(session.snapshot, baseline)
        self.assertIs(session.draft, draft)
        self.assertTrue(session.dirty)
        self.assertEqual(self.path.read_bytes(), original)
        draft.undo()
        self.assertFalse(session.dirty)
        self.assertIs(type(draft.config.extra["future"]["flag"]), bool)
        draft.redo()
        self.assertTrue(session.dirty)
        session.save()
        saved = self.path.read_bytes()
        self.assertFalse(session.dirty)
        self.assertTrue(draft.can_undo)
        self.assertIs(type(session.snapshot.config.extra["future"]["flag"]), int)
        draft.undo()
        self.assertTrue(session.dirty)
        self.assertEqual(self.path.read_bytes(), saved)
        draft.redo()
        self.assertFalse(session.dirty)
        self.assertIs(type(draft.config.extra["future"]["flag"]), int)

    def test_dirty_ignores_dict_order_but_preserves_list_order_and_json_types(self):
        self.path.write_bytes(b'{"windows":[],"future":{"a":true,"b":[1,1.0]}}')
        session = ConfigSession(self.path)
        source = self.root / "import.json"
        source.write_bytes(b'{"future":{"b":[1,1.0],"a":true},"windows":[]}')
        session.import_config(source)
        self.assertFalse(session.dirty)
        source.write_bytes(b'{"future":{"b":[1.0,1],"a":true},"windows":[]}')
        session.import_config(source)
        self.assertTrue(session.dirty)

    def test_dirty_never_revalidates_folder_environment_or_serializes(self):
        variable = "FOCUS_DIRTY_ROOT"
        with patch.dict(os.environ, {variable: r"C:\Games"}):
            self.path.write_text(json.dumps({"windows": [], "block_folders": [rf"%{variable}%\Library"]}), encoding="utf-8")
            session = ConfigSession(self.path)
            session.draft.add_rule("block_exes", "game.exe")
            session.draft.undo()
        with patch.dict(os.environ, {}, clear=True), \
                patch("core.config.config_to_dict", side_effect=AssertionError("validation")), \
                patch("core.config.parse_config", side_effect=AssertionError("validation")), \
                patch("core.config._serialize_config", side_effect=AssertionError("serialization")), \
                patch.object(Path, "open", side_effect=AssertionError("IO")), \
                patch.object(Path, "resolve", side_effect=AssertionError("discovery")):
            self.assertFalse(session.dirty)
            self.assertTrue(session.draft.can_redo)
        # O restante das APIs mantém a validação de ambiente original.
        with patch.dict(os.environ, {variable: r"C:\Games"}):
            session.draft.redo()
        with patch.dict(os.environ, {}, clear=True):
            self.assertTrue(session.dirty)

    def test_failed_import_and_reload_preserve_typed_draft_and_redo(self):
        self.path.write_bytes(b'{"windows":[],"future":{"flag":true}}')
        session = ConfigSession(self.path)
        baseline = session.snapshot
        draft = session.draft
        draft.replace_config(AppConfig(extra={"future": {"flag": 1}}))
        draft.add_rule("block_exes", "redo.exe")
        draft.undo()
        source = self.root / "invalid.json"
        source.write_bytes(b"invalid")
        with self.assertRaises(ConfigError):
            session.import_config(source)
        self.assertIs(session.draft, draft)
        self.assertTrue(session.dirty)
        self.assertTrue(draft.can_redo)
        self.path.write_bytes(b"invalid external")
        with self.assertRaises(ConfigError):
            session.reload()
        self.assertIs(session.snapshot, baseline)
        self.assertIs(session.draft, draft)
        self.assertTrue(session.dirty)
        self.assertTrue(draft.can_redo)
        self.assertIs(type(draft.config.extra["future"]["flag"]), int)
        self.assertIs(type(baseline.config.extra["future"]["flag"]), bool)

    def test_edit_and_save_preserve_extras_and_publish_no_unrequested_fields(self):
        original = self.path.read_bytes()
        self.assertFalse(self.session.dirty)
        self.session.draft.add_window("22:00", "02:00", [0])
        self.session.draft.add_rule("block_cmdline", {"executable": "javaw.exe", "contains": ".minecraft"})
        self.assertTrue(self.session.dirty)
        self.assertEqual(self.path.read_bytes(), original)
        self.session.save()
        self.assertFalse(self.session.dirty)
        actual = load_config(self.path)
        self.assertEqual(actual, self.session.draft.config)
        self.assertEqual(actual.extra, {"future": {"keep": ["ação", 12]}})
        self.assertEqual(actual.windows[0].days, (0,))
        self.assertEqual(set(self.root.iterdir()), {self.path})

    def test_agenda_uses_saved_baseline_not_unsaved_changes_and_handles_night_boundary(self):
        inside = datetime(2026, 10, 6, 1)
        self.session.draft.add_window("22:00", "02:00", [0])
        self.assertFalse(self.session.agenda_status(inside).active)
        self.assertIsNone(self.session.agenda_status(inside).next_start)
        self.assertIsNone(self.session.agenda_status(inside).current_end)
        self.session.save()
        self.assertTrue(self.session.agenda_status(inside).active)
        self.assertEqual(self.session.agenda_status(inside).current_end, datetime(2026, 10, 6, 2))
        self.assertFalse(self.session.agenda_status(datetime(2026, 10, 6, 2)).active)
        self.assertEqual(self.session.agenda_status(inside).next_start, datetime(2026, 10, 12, 22))

    def test_disabled_days_are_saved_without_enabling_a_window(self):
        self.session.draft.add_window("09:00", "10:00", [])
        self.session.save()
        self.assertFalse(self.session.agenda_status(datetime(2026, 10, 9, 9, 30)).active)
        self.assertEqual(load_config(self.path).windows[0].days, ())

    def test_reverting_edits_clears_dirty_flag(self):
        self.session.draft.add_rule("block_exes", "game.exe")
        self.assertTrue(self.session.dirty)
        self.session.draft.remove_rule("block_exes", 0)
        self.assertFalse(self.session.dirty)

    def test_invalid_edit_preserves_draft_and_file(self):
        original = self.path.read_bytes()
        with self.assertRaises(ConfigError):
            self.session.draft.add_window("10:00", "10:00")
        self.assertFalse(self.session.dirty)
        self.assertEqual(self.path.read_bytes(), original)

    def test_external_conflict_preserves_draft_and_baseline_until_reload(self):
        self.session.draft.add_rule("block_exes", "game.exe")
        baseline = self.session.snapshot
        external = b'{"windows":[],"future":{"external":true}}'
        self.path.write_bytes(external)
        with self.assertRaises(ConfigConflictError):
            self.session.save()
        self.assertIs(self.session.snapshot, baseline)
        self.assertTrue(self.session.dirty)
        self.assertEqual(self.path.read_bytes(), external)
        self.session.reload()
        self.assertFalse(self.session.dirty)
        self.assertEqual(self.session.draft.config.block_exes, ())
        self.assertEqual(self.session.draft.config.extra, {"future": {"external": True}})

    def test_noop_save_still_detects_external_modification(self):
        self.path.write_bytes(b'{"windows":[],"other":true}')
        with self.assertRaises(ConfigConflictError):
            self.session.save()

    def test_removed_file_cannot_be_recreated_by_save(self):
        self.session.draft.add_rule("block_exes", "game.exe")
        self.path.unlink()
        with self.assertRaises(ConfigConflictError):
            self.session.save()
        self.assertFalse(self.path.exists())
        self.assertTrue(self.session.dirty)

    def test_failed_reload_keeps_previous_snapshot_and_draft(self):
        self.session.draft.add_rule("safelist_exes", "Code.exe")
        baseline, draft = self.session.snapshot, self.session.draft
        self.path.write_bytes(b'{"windows":broken}')
        with self.assertRaises(ConfigError):
            self.session.reload()
        self.assertIs(self.session.snapshot, baseline)
        self.assertIs(self.session.draft, draft)
        self.assertTrue(self.session.dirty)

    def test_failed_save_can_be_retried_without_discarding_edits(self):
        self.session.draft.add_rule("block_exes", "game.exe")
        baseline = self.session.snapshot
        original = self.path.read_bytes()
        with patch("core.config.os.replace", side_effect=PermissionError("negado")):
            with self.assertRaises(ConfigError):
                self.session.save()
        self.assertIs(self.session.snapshot, baseline)
        self.assertTrue(self.session.dirty)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(set(self.root.iterdir()), {self.path})
        self.session.save()
        self.assertFalse(self.session.dirty)
        self.assertEqual(load_config(self.path).block_exes, ("game.exe",))

    def test_save_baseline_represents_own_publication_not_a_later_writer(self):
        self.session.draft.add_rule("block_exes", "game.exe")
        real_replace = os.replace

        def replace_then_external(source, destination):
            real_replace(source, destination)
            self.path.write_bytes(b'{"windows":[],"external":true}')

        with patch("core.config.os.replace", side_effect=replace_then_external):
            self.session.save()
        self.assertFalse(self.session.dirty)
        self.assertEqual(self.session.snapshot.config.block_exes, ("game.exe",))
        with self.assertRaises(ConfigConflictError):
            self.session.save()


if __name__ == "__main__":
    unittest.main()

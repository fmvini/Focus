"""Primeira configuração com arquivos reais e publicação sem sobrescrita."""

from datetime import datetime
from pathlib import Path
import os
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from uuid import uuid4

from core.config import ConfigError, _serialize_config, default_config, load_config
from core.config_editor import ConfigDraft
from core.config_portability import create_new_config, export_new_config
from core.config_repository import ConfigConflictError
from core.config_session import ConfigSession
from core.initial_setup import with_process_suggestions
from core.models import AppConfig


class NewConfigSessionTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / f".editor-integration-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = self.root / "nested" / "config.json"

    def new_session(self):
        return ConfigSession.for_new(self.path)

    def assert_new_unchanged(self, session, draft):
        self.assertTrue(session.is_new)
        self.assertTrue(session.dirty)
        self.assertIsNone(session.snapshot)
        self.assertIs(session.draft, draft)

    def test_open_new_without_writing_and_saved_agenda_ignores_draft(self):
        session = self.new_session()
        self.assertEqual(session.draft.config, default_config())
        self.assert_new_unchanged(session, session.draft)
        self.assertFalse(self.path.parent.exists())
        session.draft.add_window("22:00", "02:00", [0])
        status = session.agenda_status(datetime(2026, 10, 12, 23))
        self.assertFalse(status.active)
        self.assertIsNone(status.next_start)
        self.assertFalse(self.path.exists())

    def test_first_save_unicode_suggestions_and_night_window_then_normal_conflict(self):
        session = self.new_session()
        session.draft = ConfigDraft(with_process_suggestions(
            AppConfig(extra={"future": {"text": "日本語 🎮", "keep": [1, None]}}),
            ["minecraft_java", "steam"],
        ))
        session.draft.add_window("22:00", "02:00", [0])
        expected = session.draft.config
        self.assertIsNone(session.save())
        self.assertFalse(session.is_new)
        self.assertFalse(session.dirty)
        self.assertEqual(load_config(self.path), expected)
        self.assertEqual(session.snapshot.contents, self.path.read_bytes())
        self.assertTrue(session.agenda_status(datetime(2026, 10, 13, 1)).active)
        external = _serialize_config(AppConfig(extra={"writer": "external"}))
        self.path.write_bytes(external)
        with self.assertRaises(ConfigConflictError):
            session.save()
        self.assertEqual(self.path.read_bytes(), external)
        self.assertEqual(session.snapshot.config, expected)

    def test_save_empty_explicitly_is_valid_and_does_not_activate_anything(self):
        session = self.new_session()
        session.save()
        self.assertEqual(load_config(self.path), default_config())
        self.assertFalse(session.is_new)
        self.assertFalse(session.dirty)

    def test_constructor_strict_and_new_refuses_existing_file_directory_and_alias(self):
        with self.assertRaises(ConfigError):
            ConfigSession(self.path)
        self.path.parent.mkdir()
        for contents in (b"broken JSON", _serialize_config(default_config())):
            self.path.write_bytes(contents)
            for path in (self.path, self.path.parent / "." / self.path.name):
                with self.subTest(path=path, contents=contents), self.assertRaises(ConfigError):
                    ConfigSession.for_new(path)
            self.assertEqual(self.path.read_bytes(), contents)
        self.path.unlink()
        self.path.mkdir()
        with self.assertRaises(ConfigError):
            ConfigSession.for_new(self.path)
        self.assertTrue(self.path.is_dir())

    def test_for_new_permission_failure_and_broken_link_detection_do_not_write(self):
        with patch.object(Path, "lstat", side_effect=PermissionError("denied")):
            with self.assertRaises(ConfigError):
                self.new_session()
        # lstat finds a node even when reading its target would fail; no symlink privilege required.
        with patch.object(Path, "lstat", return_value=SimpleNamespace(st_mode=0)):
            with self.assertRaises(ConfigError):
                self.new_session()
        self.assertFalse(self.path.parent.exists())

    def test_import_export_remain_draft_only_and_active_alias_is_refused(self):
        session = self.new_session()
        source = self.root / "source.json"
        source.write_bytes(_serialize_config(with_process_suggestions(default_config(), ["steam"])))
        session.import_config(source)
        session.export_config(self.root / "export.json")
        self.assert_new_unchanged(session, session.draft)
        self.assertEqual(load_config(self.root / "export.json"), load_config(source))
        self.assertFalse(self.path.parent.exists())
        with self.assertRaises(ConfigError):
            session.export_config(self.path)
        self.assertFalse(self.path.exists())
        session.save()
        self.assertEqual(load_config(self.path).block_exes, ("steam.exe",))

    def test_reload_missing_or_invalid_retains_new_draft_then_external_file_is_adopted(self):
        session = self.new_session()
        session.draft.add_rule("block_exes", "chosen.exe")
        draft = session.draft
        with self.assertRaises(ConfigError):
            session.reload()
        self.assert_new_unchanged(session, draft)
        self.path.parent.mkdir()
        self.path.write_bytes(b"invalid")
        with self.assertRaises(ConfigError):
            session.reload()
        self.assert_new_unchanged(session, draft)
        external = AppConfig(block_exes=("external.exe",))
        self.path.write_bytes(_serialize_config(external))
        session.reload()
        self.assertFalse(session.is_new)
        self.assertFalse(session.dirty)
        self.assertEqual(session.draft.config, external)

    def test_concurrent_file_before_save_retains_new_draft_and_external_bytes(self):
        session = self.new_session()
        draft = session.draft
        self.path.parent.mkdir()
        external = b"external even when invalid"
        self.path.write_bytes(external)
        with self.assertRaises(ConfigConflictError):
            session.save()
        self.assert_new_unchanged(session, draft)
        self.assertEqual(self.path.read_bytes(), external)

    def test_invalid_draft_is_rejected_before_creating_directories(self):
        session = self.new_session()
        draft = SimpleNamespace(config=AppConfig(block_exes=("not-an-executable",)))
        session.draft = draft
        with self.assertRaises(ConfigError):
            session.save()
        self.assert_new_unchanged(session, draft)
        self.assertFalse(self.path.parent.exists())

    def test_fsync_failure_preserves_session_cleans_temp_and_retry_succeeds(self):
        session = self.new_session()
        draft = session.draft
        with patch("core.config_portability.os.fsync", side_effect=OSError("fsync")):
            with self.assertRaises(ConfigError):
                session.save()
        self.assert_new_unchanged(session, draft)
        self.assertFalse(self.path.exists())
        self.assertEqual(list(self.path.parent.glob("*.tmp")), [])
        session.save()
        self.assertFalse(session.is_new)

    def test_real_rename_and_link_races_never_overwrite_concurrent_destination(self):
        for windows in (True, False):
            with self.subTest(windows=windows):
                session = self.new_session()
                draft = session.draft
                external = b"concurrent writer preserved"
                primitive = os.rename if windows else os.link

                def race(source, destination):
                    Path(destination).write_bytes(external)
                    return primitive(source, destination)

                # POSIX rename replaces existing files; test that branch only on Windows.
                if windows and os.name != "nt":
                    continue
                with patch("core.config_portability._WINDOWS", windows), \
                        patch("core.config_portability.os.rename" if windows else
                              "core.config_portability.os.link", side_effect=race):
                    with self.assertRaises(ConfigConflictError) as caught:
                        session.save()
                self.assertIsInstance(caught.exception.__cause__, FileExistsError)
                self.assert_new_unchanged(session, draft)
                self.assertEqual(self.path.read_bytes(), external)
                self.assertEqual(list(self.path.parent.glob("*.tmp")), [])
                self.path.unlink()

    def test_first_snapshot_never_adopts_writer_after_our_publication(self):
        import core.config_portability as portability
        session = self.new_session()
        session.draft.add_rule("block_exes", "chosen.exe")
        expected = session.draft.config
        primitive = portability._publish_new
        external = _serialize_config(AppConfig(block_exes=("external.exe",)))

        def writer_after(source, destination):
            primitive(source, destination)
            destination.write_bytes(external)

        with patch("core.config_portability._publish_new", side_effect=writer_after):
            session.save()
        self.assertEqual(session.snapshot.config, expected)
        self.assertEqual(session.snapshot.contents, _serialize_config(expected))
        self.assertEqual(self.path.read_bytes(), external)
        with self.assertRaises(ConfigConflictError):
            session.save()

    def test_create_publication_failure_or_invalid_input_never_leaves_partial_destination(self):
        for failure in (PermissionError("publish"), OSError("publish")):
            with self.subTest(failure=failure):
                with patch("core.config_portability._publish_new", side_effect=failure):
                    with self.assertRaises(ConfigError):
                        create_new_config(self.path, default_config())
                self.assertFalse(self.path.exists())
                self.assertEqual(list(self.path.parent.glob("*.tmp")), [])
        for path in (None, "bad\0path"):
            with self.subTest(path=path), self.assertRaises(ConfigError):
                create_new_config(path, default_config())

    def test_export_none_active_path_is_still_rejected_before_any_effects(self):
        with self.assertRaises(ConfigError):
            export_new_config(self.path, default_config(), active_path=None)
        self.assertFalse(self.path.parent.exists())


if __name__ == "__main__":
    unittest.main()

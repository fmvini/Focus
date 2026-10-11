"""Importação/exportação de sessão com arquivos isolados e publicação real."""

from contextlib import contextmanager
from dataclasses import replace
from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from core.config import ConfigError, load_config
from core.config_repository import ConfigConflictError
from core.config_session import ConfigSession


class ConfigPortabilityTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / f".editor-integration-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.active = self.root / "config.json"
        self.original = b'{ "windows": [], "original": true }\r\n'
        self.active.write_bytes(self.original)
        self.session = ConfigSession(self.active)
        self.baseline = self.session.snapshot
        self.path = self.session.path
        self.source = self.root / "importação.json"
        self.destination = self.root / "exportação.json"
        self.data = {
            "windows": [
                {"start": "22:00", "end": "02:00", "days": [6, 0]},
                {"start": "09:00", "end": "10:00", "days": []},
            ],
            "block_exes": ["Game.EXE", "Game.EXE"],
            "block_folders": [r"C:\Jogos\Ação"],
            "safelist_exes": ["Editor.EXE"],
            "block_cmdline": [
                {"executable": "javaw.exe", "contains": " ação.* Minecraft "},
                {"executable": "javaw.exe", "contains": " ação.* Minecraft "},
            ],
            "future": {"ação": [None, True, {"text": "日本語 🎮"}]},
            "sites": False,
            "pause": "opaco",
        }
        self.source.write_text(json.dumps(self.data, ensure_ascii=False), encoding="utf-8")

    def assert_session_preserved(self, draft, dirty):
        self.assertIs(self.session.snapshot, self.baseline)
        self.assertIs(self.session.path, self.path)
        self.assertIs(self.session.draft, draft)
        self.assertEqual(self.session.dirty, dirty)
        self.assertEqual(self.active.read_bytes(), self.original)

    def assert_no_temporary(self):
        self.assertEqual(list(self.root.glob(".*.tmp")), [])

    def test_import_replaces_only_draft_preserving_source_active_and_agenda(self):
        self.session.draft.add_rule("block_exes", "pending.exe")
        previous = self.session.draft
        source_bytes = self.source.read_bytes()
        self.assertIsNone(self.session.import_config(str(self.source)))
        self.assertIsNot(self.session.draft, previous)
        self.assert_session_preserved(self.session.draft, True)
        self.assertEqual(self.session.draft.config, load_config(self.source))
        self.assertEqual(self.source.read_bytes(), source_bytes)
        self.assertFalse(self.session.agenda_status(datetime(2026, 10, 12, 23)).active)
        self.assertEqual(previous.config.block_exes, ("pending.exe",))

    def test_roundtrip_preserves_unicode_extras_cmdline_order_and_duplicates(self):
        self.session.import_config(self.source)
        draft = self.session.draft
        self.assertIsNone(self.session.export_config(str(self.destination)))
        self.assert_session_preserved(draft, True)
        self.assertEqual(load_config(self.destination), draft.config)
        self.assertEqual(json.loads(self.destination.read_text(encoding="utf-8")), self.data)
        self.assertIn("日本語 🎮".encode(), self.destination.read_bytes())
        self.assertIn(" ação.* Minecraft ".encode(), self.destination.read_bytes())
        self.session.import_config(self.destination)
        self.assertEqual(self.session.draft.config, draft.config)
        self.session.save()
        self.assertFalse(self.session.dirty)
        self.assertEqual(load_config(self.active), load_config(self.destination))
        self.assert_no_temporary()

    def test_import_matching_baseline_is_clean_and_export_keeps_clean_state(self):
        self.session.draft.add_rule("block_exes", "pending.exe")
        self.session.import_config(self.active)
        self.assertFalse(self.session.dirty)
        draft = self.session.draft
        self.session.export_config(self.destination)
        self.assert_session_preserved(draft, False)
        self.assertEqual(load_config(self.destination), self.baseline.config)

    def test_invalid_import_preserves_entire_dirty_session_and_input(self):
        self.session.draft.add_rule("safelist_exes", "Code.exe")
        draft = self.session.draft
        expected = draft.config
        for contents in (
            b"{", b"\xff", b"[]", b'{"windows":[],"windows":[]}',
            b'{"windows":[],"future":NaN}',
            b'{"windows":[{"start":"09:00","end":"09:00"}]}',
            b'{"windows":[],"block_cmdline":[".minecraft"]}',
        ):
            with self.subTest(contents=contents):
                self.source.write_bytes(contents)
                with self.assertRaises(ConfigError):
                    self.session.import_config(self.source)
                self.assert_session_preserved(draft, True)
                self.assertEqual(draft.config, expected)
                self.assertEqual(self.source.read_bytes(), contents)

    def test_failed_import_read_missing_directory_and_permission_preserve_session(self):
        draft = self.session.draft
        for path in (self.root / "missing.json", self.root, None, "bad\0path"):
            with self.subTest(path=path), self.assertRaises(ConfigError):
                self.session.import_config(path)
            self.assert_session_preserved(draft, False)
        with patch.object(Path, "read_bytes", side_effect=PermissionError("negado")):
            with self.assertRaisesRegex(ConfigError, "negado"):
                self.session.import_config(self.source)
        self.assert_session_preserved(draft, False)

    def test_external_conflict_after_import_preserves_import_and_original_baseline(self):
        self.session.import_config(self.source)
        draft = self.session.draft
        external = b'{"windows":[],"external":true}'
        self.active.write_bytes(external)
        with self.assertRaises(ConfigConflictError):
            self.session.save()
        self.assertIs(self.session.draft, draft)
        self.assertIs(self.session.snapshot, self.baseline)
        self.assertIs(self.session.path, self.path)
        self.assertTrue(self.session.dirty)
        self.assertEqual(self.active.read_bytes(), external)
        # Export não depende de atualizar baseline nem contorna o conflito.
        self.session.export_config(self.destination)
        self.assertEqual(load_config(self.destination), draft.config)
        with self.assertRaises(ConfigConflictError):
            self.session.save()

    def test_removed_active_after_import_stays_removed_and_save_conflicts(self):
        self.session.import_config(self.source)
        self.active.unlink()
        self.session.export_config(self.destination)
        with self.assertRaises(ConfigConflictError):
            self.session.save()
        self.assertFalse(self.active.exists())
        with self.assertRaises(ConfigError):
            self.session.export_config(self.active)
        self.assertFalse(self.active.exists())
        self.assertIs(self.session.snapshot, self.baseline)

    def test_export_refuses_active_normalized_relative_and_existing_destinations(self):
        draft = self.session.draft
        self.destination.write_bytes(b"keep destination")
        for path in (
            self.active, self.active.parent / "absent" / ".." / self.active.name,
            Path(os.path.relpath(self.active)), self.destination, self.source, self.root,
        ):
            with self.subTest(path=path), self.assertRaises(ConfigError):
                self.session.export_config(path)
            self.assert_session_preserved(draft, False)
            self.assertEqual(self.destination.read_bytes(), b"keep destination")
        self.assert_no_temporary()

    @unittest.skipUnless(os.name == "nt", "Alias de caixa Windows")
    def test_export_refuses_case_alias_when_active_is_missing(self):
        self.active.unlink()
        with self.assertRaises(ConfigError):
            self.session.export_config(str(self.active).upper())
        self.assertFalse(self.active.exists())
        self.assert_no_temporary()

    def test_export_refuses_hard_link_alias_without_changing_active(self):
        alias = self.root / "hardlink.json"
        os.link(self.active, alias)
        with self.assertRaises(ConfigError):
            self.session.export_config(alias)
        self.assertTrue(alias.samefile(self.active))
        self.assert_session_preserved(self.session.draft, False)
        self.assertEqual(alias.read_bytes(), self.original)
        self.assert_no_temporary()

    def test_export_refuses_symlink_active_parent_alias_and_dangling_link(self):
        alias = self.root / "symbolic.json"
        parent_alias = self.root / "linked-parent"
        dangling = self.root / "dangling.json"
        try:
            alias.symlink_to(self.active)
            parent_alias.symlink_to(self.root, target_is_directory=True)
            dangling.symlink_to(self.root / "missing.json")
        except OSError as exc:
            self.skipTest(f"Links simbólicos indisponíveis: {exc}")
        for path in (alias, parent_alias / self.active.name, dangling):
            with self.subTest(path=path), self.assertRaises(ConfigError):
                self.session.export_config(path)
        self.assertTrue(alias.is_symlink())
        self.assertTrue(dangling.is_symlink())
        self.assertFalse((self.root / "missing.json").exists())
        self.assert_session_preserved(self.session.draft, False)
        self.assert_no_temporary()

    def test_export_invalid_draft_serialization_fails_before_filesystem_effects(self):
        for extra in ({"windows": []}, {"value": float("nan")}, {"value": object()}, {"value": "\ud800"}):
            with self.subTest(extra=extra):
                self.session.draft._config = replace(self.baseline.config, extra=extra)
                draft = self.session.draft
                with patch("core.config_portability.tempfile.NamedTemporaryFile") as create:
                    with self.assertRaises(ConfigError):
                        self.session.export_config(self.destination)
                    create.assert_not_called()
                self.assert_session_preserved(draft, True)
                self.assertFalse(self.destination.exists())
        self.assert_no_temporary()

    def test_export_invalid_path_and_prepare_failures_are_config_errors(self):
        draft = self.session.draft
        for path in (None, "bad\0path"):
            with self.subTest(path=path), self.assertRaises(ConfigError):
                self.session.export_config(path)
        for target in (
            "core.config_portability.tempfile.NamedTemporaryFile",
            "core.config_portability.os.fsync", "core.config_portability._publish_new",
        ):
            with self.subTest(target=target):
                with patch(target, side_effect=PermissionError("negado")):
                    with self.assertRaisesRegex(ConfigError, "negado"):
                        self.session.export_config(self.destination)
                self.assert_session_preserved(draft, False)
                self.assertFalse(self.destination.exists())
                self.assert_no_temporary()
        self.session.export_config(self.destination)
        self.assertEqual(load_config(self.destination), draft.config)

    def test_partial_write_and_flush_failure_clean_only_temporary(self):
        real_temporary = tempfile.NamedTemporaryFile
        draft = self.session.draft
        for fail_on in ("write", "flush"):
            @contextmanager
            def failing_stream(**kwargs):
                with real_temporary(**kwargs) as stream:
                    class Stream:
                        name = stream.name

                        def write(self, contents):
                            stream.write(contents[:10] if fail_on == "write" else contents)
                            if fail_on == "write":
                                raise OSError("escrita parcial")

                        def flush(self):
                            raise OSError("flush negado")

                    yield Stream()

            with self.subTest(fail_on=fail_on):
                with patch("core.config_portability.tempfile.NamedTemporaryFile", failing_stream):
                    with self.assertRaises(ConfigError):
                        self.session.export_config(self.destination)
                self.assert_session_preserved(draft, False)
                self.assertFalse(self.destination.exists())
                self.assert_no_temporary()

    def test_destination_created_during_preparation_is_preserved_and_not_published(self):
        external = b"created during fsync"

        def create_destination(fd):
            self.destination.write_bytes(external)

        with patch("core.config_portability.os.fsync", side_effect=create_destination):
            with patch("core.config_portability._publish_new") as publish:
                with self.assertRaises(ConfigError):
                    self.session.export_config(self.destination)
                publish.assert_not_called()
        self.assertEqual(self.destination.read_bytes(), external)
        self.assert_session_preserved(self.session.draft, False)
        self.assert_no_temporary()

    @unittest.skipUnless(os.name == "nt", "Exclusividade real de rename Windows")
    def test_windows_publication_and_rename_failure_never_fallback_to_link_or_replace(self):
        with patch("core.config_portability.os.link") as link:
            with patch("core.config_portability.os.replace") as overwrite:
                self.session.export_config(self.destination)
                self.assertEqual(load_config(self.destination), self.session.draft.config)
                self.destination.unlink()
                with patch("core.config_portability.os.rename", side_effect=PermissionError("rename negado")):
                    with self.assertRaisesRegex(ConfigError, "rename negado"):
                        self.session.export_config(self.destination)
                link.assert_not_called()
                overwrite.assert_not_called()
        self.assertFalse(self.destination.exists())
        self.assert_session_preserved(self.session.draft, False)
        self.assert_no_temporary()

    @unittest.skipUnless(os.name == "nt", "Exclusividade real de rename Windows")
    def test_real_windows_rename_race_refuses_destination_created_at_publication(self):
        real_rename = os.rename
        external = b"other writer wins Windows race"

        def race(source, destination):
            self.assertEqual(Path(destination), self.destination)
            self.destination.write_bytes(external)
            return real_rename(source, destination)

        with patch("core.config_portability.os.rename", side_effect=race) as rename:
            with patch("core.config_portability.os.link") as link:
                with self.assertRaises(ConfigError) as caught:
                    self.session.export_config(self.destination)
                rename.assert_called_once()
                link.assert_not_called()
        self.assertIsInstance(caught.exception.__cause__, FileExistsError)
        self.assertEqual(self.destination.read_bytes(), external)
        self.assert_session_preserved(self.session.draft, False)
        self.assert_no_temporary()

    def test_link_branch_real_publication_and_race_never_use_rename_or_replace(self):
        real_link = os.link
        with patch("core.config_portability._WINDOWS", False):
            with patch("core.config_portability.os.rename") as rename:
                with patch("core.config_portability.os.replace") as overwrite:
                    self.session.export_config(self.destination)
                    self.assertEqual(load_config(self.destination), self.session.draft.config)
                    self.destination.unlink()

                    def race(source, destination):
                        self.destination.write_bytes(b"other writer wins link race")
                        return real_link(source, destination)

                    with patch("core.config_portability.os.link", side_effect=race):
                        with self.assertRaises(ConfigError) as caught:
                            self.session.export_config(self.destination)
                    self.assertIsInstance(caught.exception.__cause__, FileExistsError)
                    rename.assert_not_called()
                    overwrite.assert_not_called()
        self.assertEqual(self.destination.read_bytes(), b"other writer wins link race")
        self.assert_session_preserved(self.session.draft, False)
        self.assert_no_temporary()

    def test_unsupported_link_returns_error_without_overwrite_fallback(self):
        with patch("core.config_portability._WINDOWS", False):
            with patch("core.config_portability.os.link", side_effect=OSError("hard link indisponível")):
                with patch("core.config_portability.os.rename") as rename:
                    with patch("core.config_portability.os.replace") as overwrite:
                        with self.assertRaisesRegex(ConfigError, "hard link indisponível"):
                            self.session.export_config(self.destination)
                        rename.assert_not_called()
                        overwrite.assert_not_called()
        self.assertFalse(self.destination.exists())
        self.assert_session_preserved(self.session.draft, False)
        self.assert_no_temporary()

    def test_cleanup_failure_notes_original_error_and_does_not_remove_destination(self):
        with patch("core.config_portability._publish_new", side_effect=OSError("publicação negada")):
            with patch.object(Path, "unlink", side_effect=PermissionError("cleanup negado")):
                with self.assertRaisesRegex(ConfigError, "publicação negada") as caught:
                    self.session.export_config(self.destination)
        self.assertIn("cleanup negado", caught.exception.__notes__[0])
        self.assertFalse(self.destination.exists())
        self.assertEqual(len(list(self.root.glob(".*.tmp"))), 1)
        self.assert_session_preserved(self.session.draft, False)

    def test_link_cleanup_failure_keeps_complete_new_destination(self):
        with patch("core.config_portability._WINDOWS", False):
            with patch.object(Path, "unlink", side_effect=PermissionError("cleanup negado")):
                with self.assertRaisesRegex(ConfigError, "cleanup negado"):
                    self.session.export_config(self.destination)
        self.assertEqual(load_config(self.destination), self.session.draft.config)
        self.assertEqual(len(list(self.root.glob(".*.tmp"))), 1)
        self.assert_session_preserved(self.session.draft, False)


if __name__ == "__main__":
    unittest.main()

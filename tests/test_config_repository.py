"""Persistência do editor em arquivos isolados, sem perfil/efeitos Windows."""

from contextlib import contextmanager
from dataclasses import FrozenInstanceError, replace
from datetime import time
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch
from uuid import uuid4

from core.config import ConfigError, load_config, parse_config, save_config
from core.config_repository import (
    ConfigConflictError, ConfigSnapshot, read_snapshot, save_snapshot,
)
from core.models import AppConfig, ScheduleWindow


class ConfigRepositoryTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / f"repository-test-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = self.root / "config.json"
        self.original = b'{ "windows" : [], "future": {"keep": [true, null]} }\r\n'
        self.path.write_bytes(self.original)
        self.snapshot = read_snapshot(self.path)
        self.candidate = replace(
            self.snapshot.config,
            windows=(ScheduleWindow(time(22), time(2), (0,)),),
            block_exes=("Game.EXE", "Game.EXE"),
        )

    def assert_only_destination(self, contents):
        self.assertEqual(self.path.read_bytes(), contents)
        self.assertEqual(set(self.root.iterdir()), {self.path})

    def test_snapshot_has_exact_bytes_and_frozen_fields(self):
        self.assertEqual(self.snapshot.contents, self.original)
        self.assertEqual(self.snapshot.config, load_config(self.path))
        with self.assertRaises(FrozenInstanceError):
            self.snapshot.contents = b"different"
        self.assert_only_destination(self.original)

    def test_read_validates_only_the_captured_read(self):
        original_read = Path.read_bytes
        replacement = b'{"windows":[],"future":"changed after read"}'
        calls = []

        def read_then_change(path):
            calls.append(path)
            captured = original_read(path)
            self.path.write_bytes(replacement)
            return captured

        with patch.object(Path, "read_bytes", read_then_change):
            result = read_snapshot(str(self.path))
        self.assertEqual(calls, [self.path])
        self.assertEqual(result, self.snapshot)
        self.assert_only_destination(replacement)

    def test_invalid_captured_read_is_not_rescued_by_a_later_valid_file(self):
        self.path.write_bytes(b'{"windows":[],"windows":[]}')
        original_read = Path.read_bytes

        def read_then_repair(path):
            captured = original_read(path)
            self.path.write_bytes(self.original)
            return captured

        with patch.object(Path, "read_bytes", autospec=True, side_effect=read_then_repair) as read:
            with self.assertRaisesRegex(ConfigError, "duplicada"):
                read_snapshot(self.path)
            read.assert_called_once_with(self.path)
        self.assert_only_destination(self.original)

    def test_read_rejects_invalid_utf8_json_and_fields_without_writing(self):
        invalid = (
            b"", b"{", b"\xff", b'\xef\xbb\xbf{"windows":[]}',
            b'{"windows":[],"windows":[]}',
            b'{"windows":[],"future":{"x":1,"x":2}}',
            b'{"windows":[],"future":NaN}', b'{"windows":[],"future":Infinity}',
            b'{"windows":[],"future":-Infinity}', b"[]",
            b'{"windows":[{"start":"09:00","end":"09:00"}]}',
            b'{"windows":[],"block_cmdline":[".minecraft"]}',
        )
        for contents in invalid:
            with self.subTest(contents=contents):
                self.path.write_bytes(contents)
                with self.assertRaises(ConfigError):
                    read_snapshot(self.path)
                self.assert_only_destination(contents)

    def test_missing_file_and_directory_read_are_errors_without_creation(self):
        self.path.unlink()
        with self.assertRaises(ConfigError):
            read_snapshot(self.path)
        with self.assertRaises(ConfigError):
            read_snapshot(self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_read_permission_failure_preserves_bytes(self):
        with patch.object(Path, "read_bytes", side_effect=PermissionError("read denied")):
            with self.assertRaisesRegex(ConfigError, "read denied"):
                read_snapshot(self.path)
        self.assert_only_destination(self.original)

    def test_roundtrip_preserves_extras_rules_and_disabled_windows(self):
        data = {
            "windows": [{"start": "22:00", "end": "02:00", "days": []}],
            "block_exes": ["Game.EXE", "Game.EXE"],
            "block_folders": [r"%REPOSITORY_TEST_ROOT%\Games"],
            "safelist_exes": ["Editor.EXE"],
            "block_cmdline": [{"executable": "javaw.exe", "contains": " literal.* "}],
            "future": {"ação": [True, None, {"raw": "opaque"}]},
            "sites": False, "pause": "opaque", "dev_apps": None,
        }
        with patch.dict("os.environ", {"REPOSITORY_TEST_ROOT": r"C:\Synthetic"}):
            candidate = parse_config(data)
            result = save_snapshot(str(self.path), candidate, self.snapshot)
            self.assertEqual(read_snapshot(self.path), result)
        self.assertEqual(json.loads(result.contents.decode("utf-8")), data)
        self.assertEqual(result.config, candidate)
        candidate.extra["future"]["ação"].append("caller mutation")
        self.assertEqual(result.config.extra["future"]["ação"], [True, None, {"raw": "opaque"}])
        self.assert_only_destination(result.contents)

    def test_new_baseline_allows_a_second_save_but_old_baseline_conflicts(self):
        saved = save_snapshot(self.path, self.candidate, self.snapshot)
        updated = replace(saved.config, safelist_exes=("Editor.exe",))
        next_saved = save_snapshot(self.path, updated, saved)
        self.assertEqual(next_saved, read_snapshot(self.path))
        with self.assertRaises(ConfigConflictError):
            save_snapshot(self.path, self.candidate, self.snapshot)
        self.assert_only_destination(next_saved.contents)

    def test_external_changes_including_formatting_are_conflicts_before_temp(self):
        changed = (
            b'{"windows":[],"future":"external"}', b"corrupt",
            self.original.replace(b"true", b"null"),
            self.original.replace(b"\r\n", b"\n"),
        )
        for contents in changed:
            with self.subTest(contents=contents):
                self.path.write_bytes(contents)
                with patch("core.config.tempfile.NamedTemporaryFile") as temporary:
                    with self.assertRaisesRegex(ConfigConflictError, "recarregue"):
                        save_snapshot(self.path, self.candidate, self.snapshot)
                    temporary.assert_not_called()
                self.assert_only_destination(contents)

    def test_removed_destination_is_conflict_and_is_not_created(self):
        self.path.unlink()
        with patch("core.config.tempfile.NamedTemporaryFile") as temporary:
            with self.assertRaisesRegex(ConfigConflictError, "removida"):
                save_snapshot(self.path, self.candidate, self.snapshot)
            temporary.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_recreated_destination_with_changed_bytes_is_conflict(self):
        self.path.unlink()
        external = b'{"windows":[],"new":"replacement"}'
        self.path.write_bytes(external)
        with self.assertRaises(ConfigConflictError):
            save_snapshot(self.path, self.candidate, self.snapshot)
        self.assert_only_destination(external)

    def test_revision_read_failure_prevents_writing(self):
        with patch.object(Path, "read_bytes", side_effect=PermissionError("revision denied")), \
             patch("core.config.tempfile.NamedTemporaryFile") as temporary:
            with self.assertRaisesRegex(ConfigError, "revision denied"):
                save_snapshot(self.path, self.candidate, self.snapshot)
            temporary.assert_not_called()
        self.assert_only_destination(self.original)

    def test_invalid_candidate_is_rejected_before_read_or_write(self):
        invalid = (
            AppConfig(block_exes=("bad",)), AppConfig(extra={"windows": []}),
            AppConfig(extra={"bad": object()}), AppConfig(extra={"bad": float("nan")}),
            AppConfig(extra={"bad": "\ud800"}),
        )
        for candidate in invalid:
            with self.subTest(candidate=candidate), \
                 patch.object(Path, "read_bytes") as read, \
                 patch("core.config.tempfile.NamedTemporaryFile") as temporary:
                with self.assertRaises(ConfigError):
                    save_snapshot(self.path, candidate, self.snapshot)
                read.assert_not_called()
                temporary.assert_not_called()
            self.assert_only_destination(self.original)

    def test_invalid_snapshot_is_rejected_without_writing(self):
        for snapshot in (None, self.snapshot.config, ConfigSnapshot(AppConfig(), "not bytes")):
            with self.subTest(snapshot=snapshot), \
                 patch("core.config.tempfile.NamedTemporaryFile") as temporary:
                with self.assertRaisesRegex(ConfigError, "snapshot"):
                    save_snapshot(self.path, self.candidate, snapshot)
                temporary.assert_not_called()
            self.assert_only_destination(self.original)

    def test_conflict_after_fsync_is_detected_and_temp_cleaned(self):
        external = b'{"windows":[],"future":"edited during preparation"}'
        with patch("core.config.os.fsync", side_effect=lambda _: self.path.write_bytes(external)), \
             patch("core.config.os.replace") as publish:
            with self.assertRaises(ConfigConflictError):
                save_snapshot(self.path, self.candidate, self.snapshot)
            publish.assert_not_called()
        self.assert_only_destination(external)

    def test_removal_after_fsync_is_detected_and_temp_cleaned(self):
        with patch("core.config.os.fsync", side_effect=lambda _: self.path.unlink()), \
             patch("core.config.os.replace") as publish:
            with self.assertRaises(ConfigConflictError):
                save_snapshot(self.path, self.candidate, self.snapshot)
            publish.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_second_revision_read_failure_cleans_temp_and_preserves_original(self):
        with patch.object(Path, "read_bytes", side_effect=[self.original, PermissionError("check denied")]), \
             patch("core.config.os.replace") as publish:
            with self.assertRaisesRegex(ConfigError, "check denied"):
                save_snapshot(self.path, self.candidate, self.snapshot)
            publish.assert_not_called()
        self.assert_only_destination(self.original)

    def test_temp_creation_fsync_and_replace_failures_preserve_original(self):
        for target in ("tempfile.NamedTemporaryFile", "os.fsync", "os.replace"):
            with self.subTest(target=target), \
                 patch(f"core.config.{target}", side_effect=OSError("write failure")):
                with self.assertRaisesRegex(ConfigError, "write failure"):
                    save_snapshot(self.path, self.candidate, self.snapshot)
            self.assert_only_destination(self.original)

    def test_write_and_flush_failures_clean_temp_and_preserve_original(self):
        original_temporary = tempfile.NamedTemporaryFile

        class FailingStream:
            def __init__(self, stream, operation):
                self.stream = stream
                self.operation = operation

            def __getattr__(self, name):
                return getattr(self.stream, name)

            def write(self, contents):
                if self.operation == "write":
                    self.stream.write(contents[:10])
                    raise OSError("partial write failure")
                return self.stream.write(contents)

            def flush(self):
                raise OSError("flush failure")

        for operation in ("write", "flush"):
            @contextmanager
            def failing_temporary(**kwargs):
                with original_temporary(**kwargs) as stream:
                    yield FailingStream(stream, operation)

            with self.subTest(operation=operation), \
                 patch("core.config.tempfile.NamedTemporaryFile", failing_temporary), \
                 patch("core.config.os.replace") as publish:
                with self.assertRaisesRegex(ConfigError, f"{operation} failure"):
                    save_snapshot(self.path, self.candidate, self.snapshot)
                publish.assert_not_called()
            self.assert_only_destination(self.original)

    def test_cleanup_failure_is_reported_without_hiding_conflict(self):
        external = b'{"windows":[],"future":"external"}'
        with patch("core.config.os.fsync", side_effect=lambda _: self.path.write_bytes(external)), \
             patch.object(Path, "unlink", side_effect=PermissionError("cleanup denied")):
            with self.assertRaises(ConfigConflictError) as raised:
                save_snapshot(self.path, self.candidate, self.snapshot)
        self.assertIn("cleanup denied", " ".join(raised.exception.__notes__))
        self.assertEqual(self.path.read_bytes(), external)
        self.assertEqual(len(list(self.root.glob("*.tmp"))), 1)

    def test_returned_baseline_never_adopts_a_post_publication_writer(self):
        import os
        real_replace = os.replace
        external = b'{"windows":[],"future":"later writer"}'
        published = []

        def replace_then_external(source, destination):
            published.append(Path(source).read_bytes())
            real_replace(source, destination)
            self.path.write_bytes(external)

        with patch("core.config.os.replace", side_effect=replace_then_external):
            result = save_snapshot(self.path, self.candidate, self.snapshot)
        self.assertEqual(result.config, self.candidate)
        self.assertEqual(published, [result.contents])
        self.assertEqual(parse_config(json.loads(result.contents)), result.config)
        with self.assertRaises(ConfigConflictError):
            save_snapshot(self.path, result.config, result)
        self.assert_only_destination(external)

    def test_legacy_save_and_repository_share_published_format(self):
        saved = save_snapshot(self.path, self.candidate, self.snapshot)
        legacy_path = self.root / "legacy.json"
        save_config(legacy_path, self.candidate)
        self.assertEqual(saved.contents, legacy_path.read_bytes())
        self.assertEqual(saved.config, load_config(legacy_path))


if __name__ == "__main__":
    unittest.main()

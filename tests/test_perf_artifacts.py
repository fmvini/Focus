"""QA artifact IO only, with fixtures confined to .qa; no GUI/benchmark."""

import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from uuid import UUID, uuid4

from core.config import load_config
from tools.perf_artifacts import create_run, file_sha256, make_fixture, write_json, write_jsonl


class PerfArtifactsTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Path(__file__).resolve().parents[1]
        self.root = self.workspace / ".qa" / f"artifacts-tests-{uuid4().hex}"
        if self.root.parent.is_symlink() or self.root.parent.is_junction():
            raise ValueError("QA root must not be a link/junction")
        self.root.mkdir(parents=True, exist_ok=False)
        self.addCleanup(self.cleanup)
        self.fake_workspace = self.root / "workspace"
        self.fake_workspace.mkdir()
        self.run = create_run(self.fake_workspace)

    def cleanup(self):
        qa_root = self.workspace / ".qa"
        if (qa_root.is_symlink() or qa_root.is_junction()
                or self.root.resolve().parent != qa_root
                or not self.root.resolve().is_relative_to(self.workspace)
                or self.root.is_symlink() or self.root.is_junction()):
            raise ValueError("Unexpected fixture cleanup path")
        shutil.rmtree(self.root)

    def test_cleanup_refuses_changed_qa_root_before_recursive_removal(self):
        original = Path.is_junction
        with patch.object(Path, "is_junction", lambda p: p == self.root.parent or original(p)), \
                patch("tests.test_perf_artifacts.shutil.rmtree", side_effect=AssertionError("unsafe cleanup")):
            with self.assertRaises(ValueError):
                self.cleanup()

    def test_default_and_explicit_parent_create_unique_empty_runs(self):
        self.assertEqual(self.run.parent, self.fake_workspace / ".qa" / "performance")
        self.assertEqual(UUID(self.run.name[4:]).hex, self.run.name[4:])
        self.assertEqual(list(self.run.iterdir()), [])
        other = create_run(str(self.fake_workspace), Path(".qa") / "custom" / "nested")
        self.assertNotEqual(other, self.run)
        self.assertEqual(other.parent, self.fake_workspace / ".qa" / "custom" / "nested")
        self.assertEqual(list(other.iterdir()), [])

    def test_outside_parent_and_traversal_rejected_before_mkdir(self):
        for parent in (self.root / "outside", self.fake_workspace / ".qa-other",
                       self.fake_workspace / "outer" / ".qa", Path(".qa/../outside")):
            with self.subTest(parent=parent), patch.object(Path, "mkdir", side_effect=AssertionError("unsafe IO")):
                with self.assertRaises(ValueError):
                    create_run(self.fake_workspace, parent)

    def test_links_and_junctions_in_workspace_qa_and_parent_rejected_before_io(self):
        parent = self.fake_workspace / ".qa" / "linked" / "nested"
        for guard in ("is_symlink", "is_junction"):
            original = getattr(Path, guard)
            for blocked in (self.fake_workspace, self.fake_workspace / ".qa", parent.parent):
                with self.subTest(guard=guard, blocked=blocked):
                    def check(path):
                        return path == blocked or original(path)
                    with patch.object(Path, guard, check), patch.object(Path, "mkdir", side_effect=AssertionError("unsafe IO")):
                        with self.assertRaises(ValueError):
                            create_run(self.fake_workspace, parent)

    def test_resolved_escape_rejected_before_mkdir(self):
        parent = self.fake_workspace / ".qa" / "escaped"
        original = Path.resolve
        with patch.object(Path, "resolve", lambda p: self.root if p == parent else original(p)), \
                patch.object(Path, "mkdir", side_effect=AssertionError("unsafe IO")):
            with self.assertRaises(ValueError):
                create_run(self.fake_workspace, parent)

    def test_uuid_collision_preserves_existing_run(self):
        marker = self.run / "marker.txt"
        marker.write_bytes(b"keep")
        with patch("tools.perf_artifacts.uuid4", return_value=UUID(self.run.name[4:])):
            with self.assertRaises(FileExistsError):
                create_run(self.fake_workspace)
        self.assertEqual(marker.read_bytes(), b"keep")

    def test_uniform_fixtures_parse_exact_counts_and_hash_bytes(self):
        for count in (0, 100, 1000):
            with self.subTest(count=count):
                run = create_run(self.fake_workspace)
                path = make_fixture(run, count)
                self.assertEqual(path, run / "config.json")
                config = load_config(path)
                self.assertEqual(config.block_exes, tuple(f"qa-{i:04}.exe" for i in range(count)))
                self.assertEqual((config.windows, config.block_folders, config.safelist_exes, config.block_cmdline), ((), (), (), ()))
                self.assertEqual(config.extra, {})
                contents = path.read_bytes()
                self.assertTrue(contents.endswith(b"\n"))
                self.assertNotIn(b"\r", contents)
                self.assertEqual(file_sha256(path), hashlib.sha256(contents).hexdigest())
                self.assertEqual(list(run.iterdir()), [path])

    def test_invalid_rule_counts_have_no_io(self):
        for count in (True, False, -1, 1, 101, 1001, 100.0, "100", None):
            with self.subTest(count=count), patch("tools.perf_artifacts.tempfile.mkstemp", side_effect=AssertionError("invalid IO")):
                with self.assertRaises(ValueError):
                    make_fixture(self.run, count)
        self.assertEqual(list(self.run.iterdir()), [])

    def test_json_utf8_types_spaces_and_lf(self):
        data = {"typed": [True, 1, 1.0, False, 0, 0.0, None], "text": "  ação 日本語  "}
        path = write_json(self.run / "manifest.json", data)
        contents = path.read_bytes()
        self.assertFalse(contents.startswith(b"\xef\xbb\xbf"))
        self.assertIn("ação 日本語".encode(), contents)
        self.assertTrue(contents.endswith(b"\n"))
        self.assertNotIn(b"\r", contents)
        loaded = json.loads(contents)
        self.assertEqual(loaded, data)
        self.assertEqual([type(v) for v in loaded["typed"]], [bool, int, float, bool, int, float, type(None)])

    def test_jsonl_one_shot_generator_escaping_and_empty(self):
        records = [{"text": "ação\n日本語"}, {"typed": [True, 1, 1.0]}]
        path = write_jsonl(self.run / "samples.jsonl", (record for record in records))
        contents = path.read_bytes()
        self.assertTrue(contents.endswith(b"\n"))
        lines = contents.splitlines()
        self.assertEqual(len(lines), 2)
        self.assertEqual([json.loads(line) for line in lines], records)
        self.assertEqual(write_jsonl(self.run / "empty.jsonl", iter(())).read_bytes(), b"")

    def test_all_writers_refuse_overwrite_without_touching_bytes(self):
        for name, writer in (("config.json", lambda p: make_fixture(p.parent, 100)),
                             ("manifest.json", lambda p: write_json(p, {})),
                             ("samples.jsonl", lambda p: write_jsonl(p, [{"ok": True}]))):
            with self.subTest(name=name):
                path = self.run / name
                path.write_bytes(b"existing\n")
                with patch("tools.perf_artifacts.tempfile.mkstemp", side_effect=AssertionError("overwrite IO")):
                    with self.assertRaises(FileExistsError):
                        writer(path)
                self.assertEqual(path.read_bytes(), b"existing\n")

    def test_artifact_outside_qa_missing_run_and_traversal_are_rejected(self):
        for path in (self.root / "config.json", self.fake_workspace / ".qa" / "config.json",
                     self.run / "missing" / "config.json", self.run / ".." / "config.json",
                     self.run / "config.json:stream"):
            with self.subTest(path=path), patch("tools.perf_artifacts.tempfile.mkstemp", side_effect=AssertionError("unsafe IO")):
                with self.assertRaises(ValueError):
                    write_json(path, {})

    def test_artifact_symlink_and_junction_refused_before_io(self):
        path = self.run / "manifest.json"
        for guard in ("is_symlink", "is_junction"):
            original = getattr(Path, guard)
            for blocked in (path, self.run, self.run.parent):
                with self.subTest(guard=guard, blocked=blocked):
                    with patch.object(Path, guard, lambda p: p == blocked or original(p)), \
                            patch("tools.perf_artifacts.tempfile.mkstemp", side_effect=AssertionError("link IO")):
                        with self.assertRaises(ValueError):
                            write_json(path, {})

    def test_serialization_and_generator_failure_leave_no_artifacts(self):
        def broken():
            yield {"first": True}
            raise RuntimeError("iterator failed")
        with patch("tools.perf_artifacts.tempfile.mkstemp", side_effect=AssertionError("serialization IO")):
            with self.assertRaises(TypeError):
                write_json(self.run / "bad.json", {"bad": object()})
            with self.assertRaises(RuntimeError):
                write_jsonl(self.run / "bad.jsonl", broken())
            for value in (math.nan, math.inf, -math.inf):
                with self.subTest(value=value), self.assertRaises(ValueError):
                    write_json(self.run / "bad.json", {"bad": value})
        self.assertEqual(list(self.run.iterdir()), [])

    def test_write_sync_and_publish_failure_remove_temporary_and_no_success_file(self):
        for operation in ("fsync", "rename" if os.name == "nt" else "link"):
            with self.subTest(operation=operation), patch(f"tools.perf_artifacts.os.{operation}", side_effect=OSError("disk failure")):
                with self.assertRaises(OSError):
                    write_json(self.run / "failed.json", {"ok": True})
            self.assertEqual(list(self.run.iterdir()), [])

    def test_descriptor_setup_and_partial_write_failures_leave_no_file(self):
        with patch("tools.perf_artifacts.os.fdopen", side_effect=OSError("open failure")):
            with self.assertRaises(OSError):
                write_json(self.run / "failed.json", {"ok": True})
        self.assertEqual(list(self.run.iterdir()), [])
        original = os.fdopen
        class ShortWriter:
            def __init__(self, stream):
                self.stream = stream
            def __enter__(self):
                return self
            def __exit__(self, *args):
                self.stream.close()
            def write(self, contents):
                return self.stream.write(contents[:len(contents) // 2])
        with patch("tools.perf_artifacts.os.fdopen", lambda *args: ShortWriter(original(*args))):
            with self.assertRaisesRegex(OSError, "Incomplete"):
                write_json(self.run / "failed.json", {"ok": True})
        self.assertEqual(list(self.run.iterdir()), [])

    def test_competing_writer_at_publication_is_preserved(self):
        path = self.run / "race.json"
        original = os.fsync
        def competitor(fd):
            original(fd)
            path.write_bytes(b"competitor")
        with patch("tools.perf_artifacts.os.fsync", competitor):
            with self.assertRaises(FileExistsError):
                write_json(path, {"ours": True})
        self.assertEqual(path.read_bytes(), b"competitor")
        self.assertEqual(list(self.run.iterdir()), [path])

    def test_publication_itself_refuses_a_late_competing_file(self):
        path = self.run / "late-race.json"
        operation = "rename" if os.name == "nt" else "link"
        original = getattr(os, operation)
        def publish(source, destination):
            self.assertFalse(path.exists())
            path.write_bytes(b"late competitor")
            return original(source, destination)
        with patch(f"tools.perf_artifacts.os.{operation}", publish):
            with self.assertRaises(FileExistsError):
                write_json(path, {"ours": True})
        self.assertEqual(path.read_bytes(), b"late competitor")
        self.assertEqual(list(self.run.iterdir()), [path])

    def test_hash_reads_actual_source_bytes_without_creating_artifacts(self):
        path = self.root / "source.py"
        path.write_bytes(b"# source\r\n")
        self.assertEqual(file_sha256(path), hashlib.sha256(b"# source\r\n").hexdigest())
        path.write_bytes(b"changed")
        self.assertEqual(file_sha256(path), hashlib.sha256(b"changed").hexdigest())
        with self.assertRaises(FileNotFoundError):
            file_sha256(self.root / "absent.py")


if __name__ == "__main__":
    unittest.main()

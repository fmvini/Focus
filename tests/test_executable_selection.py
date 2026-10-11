"""Seleção de arquivos só gera nomes validados; nenhuma leitura ou execução."""

from pathlib import Path
import unittest
from unittest.mock import patch

from core.config import ConfigError
from core.config_editor import ConfigDraft
from core.models import AppConfig, CmdlineRule


class ExecutableSelectionTests(unittest.TestCase):
    def test_batch_preserves_config_and_returns_added_count_in_selection_order(self):
        source = AppConfig(block_exes=("existing.exe", "existing.exe"),
                           safelist_exes=("keep.exe",), block_folders=(r"C:\Games",),
                           block_cmdline=(CmdlineRule("javaw.exe", ".minecraft"),),
                           extra={"future": {"text": ["日本語"]}})
        draft = ConfigDraft(source)
        paths = [r"C:\Games\First.exe", "D:/Games/Second.EXE", Path("third.exe")]
        self.assertEqual(draft.add_executable_paths("block_exes", paths), 3)
        self.assertEqual(draft.config.block_exes, ("existing.exe", "existing.exe", "First.exe", "Second.EXE", "third.exe"))
        self.assertEqual(draft.config.extra, source.extra)
        self.assertEqual(draft.config.safelist_exes, source.safelist_exes)
        self.assertEqual(draft.config.block_folders, source.block_folders)
        self.assertEqual(draft.config.block_cmdline, source.block_cmdline)
        self.assertEqual(source.block_exes, ("existing.exe", "existing.exe"))

    def test_casefold_dedup_different_directories_and_repeated_batches(self):
        draft = ConfigDraft(AppConfig(block_exes=("ſteam.exe", "same.exe", "same.exe")))
        paths = [r"C:\Games\steam.exe", r"C:\Games\NEW.exe", r"D:\Other\new.exe"]
        self.assertEqual(draft.add_executable_paths("block_exes", paths), 1)
        self.assertEqual(draft.config.block_exes, ("ſteam.exe", "same.exe", "same.exe", "NEW.exe"))
        self.assertEqual(draft.add_executable_paths("block_exes", paths), 0)
        self.assertEqual(len(paths), 3)

    def test_protection_list_is_independent_and_empty_selection_has_no_effect(self):
        draft = ConfigDraft(AppConfig(block_exes=("game.exe",)))
        self.assertEqual(draft.add_executable_paths("safelist_exes", [r"C:\Tools\game.exe"]), 1)
        self.assertEqual(draft.config.block_exes, ("game.exe",))
        self.assertEqual(draft.config.safelist_exes, ("game.exe",))
        before = draft.config
        self.assertEqual(draft.add_executable_paths("safelist_exes", ()), 0)
        self.assertEqual(draft.config, before)

    def test_invalid_batch_is_atomic_and_retry_succeeds(self):
        draft = ConfigDraft(AppConfig(block_exes=("keep.exe",)))
        invalid = ("", "folder/", "game.txt", ".exe", "bad?.exe", "bad\n.exe", "game.exe ",
                   "bad\0parent/game.exe", None, 1, True, b"game.exe")
        for path in invalid:
            with self.subTest(path=path):
                before = draft.config
                with self.assertRaises(ConfigError):
                    draft.add_executable_paths("block_exes", [r"C:\Games\valid.exe", path])
                self.assertEqual(draft.config, before)
        self.assertEqual(draft.add_executable_paths("block_exes", ["valid.exe"]), 1)

    def test_fields_and_collection_types_are_rejected_without_mutation(self):
        draft = ConfigDraft(AppConfig())
        for field in ("block_folders", "block_cmdline", "windows", None, [], True):
            with self.subTest(field=field), self.assertRaises(ConfigError):
                draft.add_executable_paths(field, ["game.exe"])
        for paths in (None, 1, True, "game.exe", b"game.exe", bytearray(), Path("game.exe")):
            with self.subTest(paths=paths), self.assertRaises(ConfigError):
                draft.add_executable_paths("block_exes", paths)
        self.assertEqual(draft.config, AppConfig())

    def test_one_shot_iterable_consumed_once_and_midstream_failure_preserves_draft(self):
        draft = ConfigDraft(AppConfig())
        class Once:
            used = False
            def __iter__(self):
                if self.used:
                    raise AssertionError("twice")
                self.used = True
                return iter(("one.exe", "two.exe"))
        self.assertEqual(draft.add_executable_paths("block_exes", Once()), 2)
        before = draft.config
        failure = RuntimeError("selection failed")
        def failed():
            yield "three.exe"
            raise failure
        with self.assertRaises(ConfigError) as caught:
            draft.add_executable_paths("block_exes", failed())
        self.assertIs(caught.exception.__cause__, failure)
        self.assertEqual(draft.config, before)

    def test_selection_does_not_resolve_read_discover_or_execute_files(self):
        draft = ConfigDraft(AppConfig())
        with patch.object(Path, "open", side_effect=AssertionError("read")), \
                patch.object(Path, "resolve", side_effect=AssertionError("resolve")), \
                patch("subprocess.Popen", side_effect=AssertionError("execute")), \
                patch("os.stat", side_effect=AssertionError("stat")):
            self.assertEqual(draft.add_executable_paths("block_exes", [Path("日本語.exe")]), 1)
        self.assertEqual(draft.config.block_exes, ("日本語.exe",))


if __name__ == "__main__":
    unittest.main()

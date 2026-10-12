"""Ordenação visual com sessão/JSON reais, sem importar a GUI ou aplicar regras."""

from copy import deepcopy
import json
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from uuid import uuid4

from core.config import load_config
from core.config_comparison import configs_equal
from core.config_repository import ConfigConflictError
from core.config_session import ConfigSession
from core.models import CmdlineRule
from ui.rule_list_view import rule_view_indices


class RuleListViewIntegrationTests(unittest.TestCase):
    FIELDS = ("block_exes", "block_folders", "safelist_exes", "block_cmdline")

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / f".editor-integration-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = self.root / "config.json"
        self.data = {
            "windows": [{"start": "22:00", "end": "02:00", "days": [6, 0]}],
            "block_exes": ["Zulu.EXE", "alpha.exe", "ALPHA.EXE", "beta.exe"],
            "block_folders": [r"C:\Zulu", r"C:\alpha", r"c:\ALPHA", r"C:\beta"],
            "safelist_exes": ["ZuluSafe.EXE", "alphaSafe.exe", "ALPHASAFE.EXE", "betaSafe.exe"],
            "block_cmdline": [
                {"executable": "Zulu.EXE", "contains": " target z "},
                {"executable": "alpha.exe", "contains": "Needle Alpha"},
                {"executable": "ALPHA.EXE", "contains": "NEEDLE ALPHA"},
                {"executable": "beta.exe", "contains": " target b "},
            ],
            "future": {"ação": [True, 1, 1.0, "日本語"]},
        }
        self.original_bytes = json.dumps(self.data, ensure_ascii=False).encode("utf-8")
        self.path.write_bytes(self.original_bytes)
        self.session = ConfigSession(self.path)

    def test_four_lists_view_filter_and_stable_sort_preserve_saved_session_without_io(self):
        session = self.session
        draft, snapshot = session.draft, session.snapshot
        before = draft.config
        with patch.object(Path, "read_bytes", side_effect=AssertionError("view read")), \
                patch("core.config_session.read_snapshot", side_effect=AssertionError("view repository read")), \
                patch("core.config_repository.read_snapshot", side_effect=AssertionError("view repository read")), \
                patch("core.config._serialize_config", side_effect=AssertionError("view serialize")), \
                patch("core.config_repository._serialize_config", side_effect=AssertionError("view serialize")), \
                patch.object(session, "save", side_effect=AssertionError("view save")):
            for field in self.FIELDS:
                with self.subTest(field=field):
                    self.assertEqual(rule_view_indices(draft.config, field), (0, 1, 2, 3))
                    self.assertEqual(rule_view_indices(draft.config, field, order="name_asc"), (1, 2, 3, 0))
                    self.assertEqual(rule_view_indices(draft.config, field, order="name_desc"), (0, 3, 1, 2))
                    for order in ("registered", "name_asc", "name_desc"):
                        self.assertEqual(rule_view_indices(draft.config, field, "  aLpHa  ", order), (1, 2))
                    self.assertEqual(rule_view_indices(draft.config, field, "not-present"), ())
            self.assertEqual(rule_view_indices(draft.config, "block_cmdline", "  NEEDLE ALPHA  ", "name_desc"), (1, 2))
            self.assertIs(session.draft, draft)
            self.assertIs(session.snapshot, snapshot)
            self.assertTrue(configs_equal(draft.config, before))
            self.assertFalse(session.dirty)
            self.assertFalse(draft.can_undo)
            self.assertFalse(draft.can_redo)
        self.assertEqual(self.path.read_bytes(), self.original_bytes)
        self.assertTrue(configs_equal(load_config(self.path), before))

    def test_crud_uses_returned_original_index_and_next_view_recalculates_after_removal(self):
        replacements = {
            "block_exes": "Middle.EXE", "block_folders": r"D:\Edited",
            "safelist_exes": "MiddleSafe.EXE",
            "block_cmdline": CmdlineRule("Middle.EXE", " literal.* preserved "),
        }
        for field in self.FIELDS:
            with self.subTest(field=field):
                session = ConfigSession(self.path)
                draft, snapshot = session.draft, session.snapshot
                original = draft.config
                old_values = getattr(original, field)
                selected = rule_view_indices(draft.config, field, "alpha", "name_desc")[1]
                self.assertEqual(selected, 2)  # Segunda duplicata, não posição visual 1.
                replacement = replacements[field]
                payload = ({"executable": replacement.executable, "contains": replacement.contains}
                           if field == "block_cmdline" else replacement)
                draft.update_rule(field, selected, payload)
                self.assertEqual(getattr(draft.config, field), (old_values[0], old_values[1], replacement, old_values[3]))
                remaining_alpha = rule_view_indices(draft.config, field, "alpha", "name_asc")
                self.assertEqual(remaining_alpha, (1,))
                draft.remove_rule(field, remaining_alpha[0])
                self.assertEqual(getattr(draft.config, field), (old_values[0], replacement, old_values[3]))
                asc = (2, 0, 1) if field == "block_folders" else (2, 1, 0)
                desc = (1, 0, 2) if field == "block_folders" else (0, 1, 2)
                self.assertEqual(rule_view_indices(draft.config, field, order="name_asc"), asc)
                self.assertEqual(rule_view_indices(draft.config, field, order="name_desc"), desc)
                for other in self.FIELDS:
                    if other != field:
                        self.assertEqual(getattr(draft.config, other), getattr(original, other))
                self.assertEqual(draft.config.windows, original.windows)
                self.assertEqual(draft.config.extra, original.extra)
                self.assertTrue(session.dirty)
                self.assertIs(session.snapshot, snapshot)
                self.assertEqual(self.path.read_bytes(), self.original_bytes)

    def test_undo_redo_views_do_not_consume_history_and_save_keeps_registered_json_order(self):
        session = self.session
        draft, baseline = session.draft, session.snapshot
        original = draft.config
        selected = rule_view_indices(draft.config, "block_exes", order="name_desc")[0]
        draft.update_rule("block_exes", selected, "aardvark.exe")
        after_edit = draft.config
        selected = rule_view_indices(draft.config, "block_exes", "alpha", "name_desc")[0]
        draft.remove_rule("block_exes", selected)
        after_remove = draft.config
        self.assertEqual(after_remove.block_exes, ("aardvark.exe", "ALPHA.EXE", "beta.exe"))
        self.assertTrue(draft.undo())
        self.assertTrue(configs_equal(draft.config, after_edit))
        self.assertEqual(rule_view_indices(draft.config, "block_exes", order="name_asc"), (0, 1, 2, 3))
        self.assertTrue(draft.undo())
        self.assertTrue(configs_equal(draft.config, original))
        with patch.object(Path, "read_bytes", side_effect=AssertionError("view read")), \
                patch("core.config_repository._serialize_config", side_effect=AssertionError("view serialize")), \
                patch.object(session, "save", side_effect=AssertionError("view save")):
            self.assertEqual(rule_view_indices(draft.config, "block_exes", order="name_asc"), (1, 2, 3, 0))
            self.assertFalse(session.dirty)
            self.assertFalse(draft.can_undo)
            self.assertTrue(draft.can_redo)
            self.assertIs(session.snapshot, baseline)
        self.assertTrue(draft.redo())
        self.assertTrue(configs_equal(draft.config, after_edit))
        self.assertTrue(draft.redo())
        self.assertTrue(configs_equal(draft.config, after_remove))
        self.assertEqual(rule_view_indices(draft.config, "block_exes", order="name_desc"), (2, 1, 0))
        self.assertEqual(self.path.read_bytes(), self.original_bytes)
        session.save()
        saved_bytes = self.path.read_bytes()
        self.assertEqual(json.loads(saved_bytes)["block_exes"], ["aardvark.exe", "ALPHA.EXE", "beta.exe"])
        self.assertTrue(configs_equal(load_config(self.path), after_remove))
        self.assertEqual(session.snapshot.contents, saved_bytes)
        self.assertFalse(session.dirty)
        self.assertTrue(draft.undo())
        self.assertTrue(session.dirty)
        self.assertTrue(configs_equal(draft.config, after_edit))
        self.assertEqual(rule_view_indices(draft.config, "block_exes", "alpha", "name_desc"), (1, 2))
        self.assertTrue(draft.redo())
        self.assertFalse(session.dirty)
        self.assertEqual(self.path.read_bytes(), saved_bytes)

    def test_view_import_reload_do_not_adopt_external_file_or_bypass_save_conflict(self):
        session = self.session
        baseline = session.snapshot
        session.draft.add_rule("block_exes", "Omega.exe")
        draft = session.draft
        external_data = deepcopy(self.data)
        external_data["block_exes"] = ["External.exe"]
        external_data["future"] = {"external": True}
        external = json.dumps(external_data, ensure_ascii=False).encode("utf-8")
        self.path.write_bytes(external)
        self.assertEqual(rule_view_indices(draft.config, "block_exes", order="name_asc"), (1, 2, 3, 4, 0))
        with self.assertRaises(ConfigConflictError):
            session.save()
        self.assertIs(session.draft, draft)
        self.assertIs(session.snapshot, baseline)
        self.assertTrue(session.dirty)
        self.assertTrue(draft.can_undo)
        self.assertEqual(self.path.read_bytes(), external)
        imported_data = deepcopy(self.data)
        imported_data["block_exes"] = ["Zulu.EXE", "Import.exe", "IMPORT.EXE", "beta.exe"]
        source = self.root / "importação.json"
        source_bytes = json.dumps(imported_data, ensure_ascii=False).encode("utf-8")
        source.write_bytes(source_bytes)
        session.import_config(source)
        self.assertIsNot(session.draft, draft)
        self.assertIs(session.snapshot, baseline)
        self.assertFalse(session.draft.can_undo)
        self.assertFalse(session.draft.can_redo)
        self.assertTrue(session.dirty)
        self.assertEqual(rule_view_indices(session.draft.config, "block_exes", order="name_asc"), (3, 1, 2, 0))
        self.assertEqual(rule_view_indices(session.draft.config, "block_exes", "import", "name_desc"), (1, 2))
        with self.assertRaises(ConfigConflictError):
            session.save()
        self.assertEqual(self.path.read_bytes(), external)
        self.assertEqual(source.read_bytes(), source_bytes)
        session.reload()
        self.assertFalse(session.dirty)
        self.assertFalse(session.draft.can_undo)
        self.assertFalse(session.draft.can_redo)
        self.assertEqual(session.snapshot.contents, external)
        self.assertEqual(rule_view_indices(session.draft.config, "block_exes", order="name_desc"), (0,))
        self.assertEqual(session.draft.config.block_exes, ("External.exe",))


if __name__ == "__main__":
    unittest.main()

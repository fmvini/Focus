"""Remoção em lote com sessão/JSON reais, sem GUI ou efeitos do motor."""

from copy import deepcopy
from dataclasses import replace
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
from ui.rule_list_view import rule_view_indices


class RuleBulkRemoveIntegrationTests(unittest.TestCase):
    FIELDS = ("block_exes", "block_folders", "safelist_exes", "block_cmdline")

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / f".editor-integration-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = self.root / "config.json"
        self.data = {
            "windows": [{"start": "22:00", "end": "02:00", "days": [6, 0]}],
            "block_exes": ["Zulu.exe", "alpha.exe", "beta.exe", "alpha.exe", "Keep.exe", "gamma.exe"],
            "block_folders": [r"C:\Zulu", r"C:\alpha", r"C:\beta", r"C:\alpha", r"C:\Keep", r"C:\gamma"],
            "safelist_exes": ["ZuluSafe.exe", "alphaSafe.exe", "betaSafe.exe", "alphaSafe.exe", "KeepSafe.exe", "gammaSafe.exe"],
            "block_cmdline": [
                {"executable": "Zulu.exe", "contains": " literal Z "},
                {"executable": "alpha.exe", "contains": ' literal.* "ação" '},
                {"executable": "beta.exe", "contains": " literal beta "},
                {"executable": "alpha.exe", "contains": ' literal.* "ação" '},
                {"executable": "Keep.exe", "contains": " literal Keep "},
                {"executable": "gamma.exe", "contains": " literal gamma "},
            ],
            "future": {"ação": [True, 1, 1.0, {"日本語": [False, 0, 0.0]}]},
        }
        self.original_bytes = json.dumps(self.data, ensure_ascii=False).encode("utf-8")
        self.path.write_bytes(self.original_bytes)
        self.session = ConfigSession(self.path)

    def test_filtered_duplicates_in_four_lists_are_one_edit_of_original_positions(self):
        for field in self.FIELDS:
            with self.subTest(field=field):
                session = ConfigSession(self.path)
                draft, baseline = session.draft, session.snapshot
                before = draft.config
                values = getattr(before, field)
                selected = rule_view_indices(before, field, "  ALPHA  ", "name_desc")
                self.assertEqual(selected, (1, 3))  # Dois itens iguais, não posições visuais 0 e 1.
                expected = replace(before, **{field: (values[0], values[2], values[4], values[5])})
                with patch("core.config_session.read_snapshot", side_effect=AssertionError("repository read")), \
                        patch.object(Path, "read_bytes", side_effect=AssertionError("file read")), \
                        patch("core.config_repository._serialize_config", side_effect=AssertionError("serialize")), \
                        patch.object(session, "save", side_effect=AssertionError("implicit save")):
                    self.assertEqual(draft.remove_rules(field, (index for index in selected)), 2)
                    self.assertTrue(configs_equal(draft.config, expected))
                    self.assertTrue(session.dirty)
                    self.assertIs(session.draft, draft)
                    self.assertIs(session.snapshot, baseline)
                    self.assertTrue(configs_equal(baseline.config, before))
                    self.assertEqual(rule_view_indices(draft.config, field, "alpha", "name_desc"), ())
                    self.assertTrue(draft.undo())
                    self.assertTrue(configs_equal(draft.config, before))
                    self.assertFalse(session.dirty)
                    self.assertFalse(draft.can_undo)  # O lote inteiro consumiu só uma edição.
                    self.assertEqual(rule_view_indices(draft.config, field, "alpha", "name_desc"), (1, 3))
                    self.assertTrue(draft.redo())
                    self.assertTrue(configs_equal(draft.config, expected))
                    self.assertTrue(session.dirty)
                    self.assertFalse(draft.can_redo)
                self.assertEqual(self.path.read_bytes(), self.original_bytes)

    def test_noncontiguous_sorted_selection_saves_registered_order_only_on_explicit_save(self):
        session = self.session
        draft, baseline = session.draft, session.snapshot
        before = draft.config
        view = rule_view_indices(before, "block_cmdline", order="name_desc")
        self.assertEqual(view, (0, 4, 5, 2, 1, 3))
        self.assertEqual(draft.remove_rules("block_cmdline", (view[1], view[3], view[1])), 2)
        after = draft.config
        expected = replace(before, block_cmdline=(before.block_cmdline[0], before.block_cmdline[1],
                                                  before.block_cmdline[3], before.block_cmdline[5]))
        self.assertTrue(configs_equal(after, expected))
        self.assertIs(session.snapshot, baseline)
        self.assertTrue(session.dirty)
        self.assertEqual(self.path.read_bytes(), self.original_bytes)
        self.assertEqual(rule_view_indices(after, "block_cmdline", order="name_asc"), (1, 2, 3, 0))
        session.save()
        saved = self.path.read_bytes()
        saved_baseline = session.snapshot
        self.assertEqual(json.loads(saved)["block_cmdline"], [self.data["block_cmdline"][0],
                         self.data["block_cmdline"][1], self.data["block_cmdline"][3], self.data["block_cmdline"][5]])
        self.assertTrue(configs_equal(load_config(self.path), expected))
        self.assertEqual(saved_baseline.contents, saved)
        self.assertFalse(session.dirty)
        self.assertIs(session.draft, draft)
        self.assertTrue(draft.undo())
        self.assertTrue(configs_equal(draft.config, before))
        self.assertTrue(session.dirty)
        self.assertFalse(draft.can_undo)
        self.assertTrue(draft.redo())
        self.assertFalse(session.dirty)
        self.assertIs(session.snapshot, saved_baseline)
        self.assertEqual(self.path.read_bytes(), saved)

    def test_empty_selection_preserves_clean_baseline_and_pending_bulk_redo(self):
        session = self.session
        draft, baseline = session.draft, session.snapshot
        before = draft.config
        second_duplicate = rule_view_indices(before, "block_exes", "alpha", "name_asc")[1]
        self.assertEqual(second_duplicate, 3)
        self.assertEqual(draft.remove_rules("block_exes", (second_duplicate,)), 1)
        after = draft.config
        self.assertEqual(after.block_exes, ("Zulu.exe", "alpha.exe", "beta.exe", "Keep.exe", "gamma.exe"))
        self.assertTrue(draft.undo())
        with patch("core.config_editor.config_to_dict", side_effect=AssertionError("empty validation")), \
                patch.object(Path, "read_bytes", side_effect=AssertionError("file read")), \
                patch.object(session, "save", side_effect=AssertionError("implicit save")):
            self.assertEqual(draft.remove_rules("block_exes", iter(())), 0)
            self.assertTrue(configs_equal(draft.config, before))
            self.assertFalse(session.dirty)
            self.assertFalse(draft.can_undo)
            self.assertTrue(draft.can_redo)
            self.assertIs(session.snapshot, baseline)
        self.assertTrue(draft.redo())
        self.assertTrue(configs_equal(draft.config, after))
        self.assertTrue(session.dirty)
        self.assertEqual(rule_view_indices(draft.config, "block_exes", "alpha"), (1,))
        self.assertEqual(self.path.read_bytes(), self.original_bytes)

    def test_conflict_preserves_bulk_history_import_resets_draft_and_reload_adopts_external(self):
        session = self.session
        draft, baseline = session.draft, session.snapshot
        selected = rule_view_indices(draft.config, "block_exes", "alpha", "name_desc")
        self.assertEqual(draft.remove_rules("block_exes", selected), 2)
        removed = draft.config
        external_data = deepcopy(self.data)
        external_data["block_exes"] = ["External.exe"]
        external_data["future"] = {"external": [1.0, False]}
        external = json.dumps(external_data, ensure_ascii=False).encode("utf-8")
        self.path.write_bytes(external)
        with self.assertRaises(ConfigConflictError):
            session.save()
        self.assertIs(session.draft, draft)
        self.assertIs(session.snapshot, baseline)
        self.assertTrue(configs_equal(draft.config, removed))
        self.assertTrue(session.dirty)
        self.assertTrue(draft.undo())
        self.assertFalse(draft.can_undo)
        self.assertTrue(draft.can_redo)
        self.assertFalse(session.dirty)
        self.assertEqual(self.path.read_bytes(), external)

        imported_data = deepcopy(self.data)
        imported_data["block_exes"][-1] = "Imported.exe"
        imported_data["future"]["ação"][0] = 1  # Tipo JSON também diferencia o import do baseline.
        source = self.root / "importação.json"
        source_bytes = json.dumps(imported_data, ensure_ascii=False).encode("utf-8")
        source.write_bytes(source_bytes)
        session.import_config(source)
        imported_draft = session.draft
        imported = imported_draft.config
        self.assertIsNot(imported_draft, draft)
        self.assertIs(session.snapshot, baseline)
        self.assertTrue(session.dirty)
        self.assertFalse(imported_draft.can_undo)
        self.assertFalse(imported_draft.can_redo)
        self.assertIs(type(imported.extra["future"]["ação"][0]), int)
        self.assertIs(type(baseline.config.extra["future"]["ação"][0]), bool)
        selected = rule_view_indices(imported, "block_exes", "alpha", "name_asc")
        self.assertEqual(selected, (1, 3))
        self.assertEqual(imported_draft.remove_rules("block_exes", selected), 2)
        self.assertTrue(imported_draft.undo())
        self.assertFalse(imported_draft.can_undo)
        self.assertTrue(imported_draft.can_redo)
        with self.assertRaises(ConfigConflictError):
            session.save()
        self.assertIs(session.snapshot, baseline)
        self.assertIs(session.draft, imported_draft)
        self.assertTrue(configs_equal(imported_draft.config, imported))
        self.assertTrue(imported_draft.can_redo)
        self.assertEqual(self.path.read_bytes(), external)
        self.assertEqual(source.read_bytes(), source_bytes)
        session.reload()
        self.assertIsNot(session.draft, imported_draft)
        self.assertFalse(session.dirty)
        self.assertFalse(session.draft.can_undo)
        self.assertFalse(session.draft.can_redo)
        self.assertEqual(session.snapshot.contents, external)
        self.assertEqual(session.draft.config.block_exes, ("External.exe",))
        self.assertTrue(configs_equal(session.draft.config, load_config(self.path)))
        self.assertEqual(rule_view_indices(session.draft.config, "block_exes", order="name_desc"), (0,))
        self.assertEqual(self.path.read_bytes(), external)
        self.assertEqual(source.read_bytes(), source_bytes)


if __name__ == "__main__":
    unittest.main()

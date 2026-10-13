"""Paginação visual com sessão/JSON reais, sem widgets ou efeitos do motor."""

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
from ui.rule_pagination import rule_page, rule_page_for_index


class RulePaginationIntegrationTests(unittest.TestCase):
    FIELDS = ("block_exes", "block_folders", "safelist_exes", "block_cmdline")

    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / f".editor-integration-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = self.root / "config.json"
        names = [f"Match-{59 - index:02}.exe" for index in range(60)]
        for index in (2, 31, 56):
            names[index] = "Match-25.exe"
        self.data = {
            "windows": [{"start": "22:00", "end": "02:00", "days": [6, 0]}],
            "block_exes": names,
            "block_folders": [rf"C:\{name[:-4]}" for name in names],
            "safelist_exes": list(names),
            "block_cmdline": [{"executable": name, "contains": ' literal.* "ação" '}
                              for name in names],
            "future": {"ação": [True, 1, 1.0, {"日本語": [False, 0, 0.0]}]},
        }
        self.original_bytes = json.dumps(self.data, ensure_ascii=False).encode("utf-8")
        self.path.write_bytes(self.original_bytes)
        self.session = ConfigSession(self.path)

    def test_four_lists_sorted_duplicate_boundary_and_filtered_lookup_use_original_indices(self):
        session = self.session
        config, baseline = session.draft.config, session.snapshot
        for field in self.FIELDS:
            with self.subTest(field=field):
                full = rule_view_indices(config, field, "  MATCH  ", "name_asc")
                first, second = rule_page(full), rule_page(full, 1)
                self.assertEqual((first.total, first.page_count, first.start, first.stop), (60, 3, 0, 25))
                self.assertEqual(first.indices[-1], 2)
                self.assertEqual(second.indices[:3], (31, 34, 56))
                self.assertEqual(full[24:28], (2, 31, 34, 56))
                self.assertEqual(rule_page_for_index(full, 56), 1)  # Não 56 // 25.
                self.assertIn(56, rule_page(full, rule_page_for_index(full, 56)).indices)
                filtered = rule_view_indices(config, field, "  25  ", "name_desc")
                self.assertEqual(filtered, (2, 31, 34, 56))
                self.assertEqual(rule_page(filtered).indices, filtered)
                self.assertEqual(rule_page_for_index(filtered, 56), 0)
                self.assertIsNone(rule_page_for_index(filtered, 0))
                registered = rule_view_indices(config, field)
                self.assertEqual(rule_page_for_index(registered, 56), 2)
                self.assertEqual(rule_page(registered, 2).indices, tuple(range(50, 60)))
        self.assertTrue(configs_equal(session.draft.config, config))
        self.assertIs(session.snapshot, baseline)
        self.assertFalse(session.dirty)
        self.assertFalse(session.draft.can_undo)
        self.assertEqual(self.path.read_bytes(), self.original_bytes)

    def test_crosspage_selection_and_all_full_are_single_edits_without_page_limited_removal(self):
        for field, all_full in (("block_exes", False), ("block_cmdline", True)):
            with self.subTest(field=field, all_full=all_full):
                session = ConfigSession(self.path)
                draft, baseline = session.draft, session.snapshot
                before = draft.config
                full = rule_view_indices(before, field, "match", "registered")
                first, second, third = (rule_page(full, page) for page in range(3))
                selected = full if all_full else (first.indices[2], second.indices[6], third.indices[6])
                self.assertEqual(len(first.indices), 25)
                if all_full:
                    self.assertEqual(len(selected), 60)  # Todo o filtro, não só os 25 materializados.
                    survivors = ()
                else:
                    self.assertEqual(selected, (2, 31, 56))
                    values = before.block_exes
                    survivors = values[:2] + values[3:31] + values[32:56] + values[57:]
                expected = replace(before, **{field: survivors})
                self.assertEqual(draft.remove_rules(field, selected), 60 if all_full else 3)
                self.assertTrue(configs_equal(draft.config, expected))
                self.assertIs(session.snapshot, baseline)
                self.assertTrue(session.dirty)
                self.assertEqual(self.path.read_bytes(), self.original_bytes)
                remaining = rule_view_indices(draft.config, field, "match", "registered")
                self.assertEqual(rule_page(remaining).total, 0 if all_full else 57)
                if not all_full:
                    self.assertEqual(rule_view_indices(draft.config, field, "25"), (32,))
                self.assertTrue(draft.undo())
                self.assertFalse(draft.can_undo)
                self.assertFalse(session.dirty)
                self.assertTrue(configs_equal(draft.config, before))
                self.assertEqual(rule_page_for_index(rule_view_indices(draft.config, field), 56), 2)
                self.assertTrue(draft.redo())
                self.assertFalse(draft.can_redo)
                self.assertTrue(configs_equal(draft.config, expected))
                self.assertTrue(session.dirty)
                self.assertEqual(self.path.read_bytes(), self.original_bytes)

    def test_page_navigation_is_view_only_without_io_validation_or_consuming_redo(self):
        session = self.session
        draft, baseline = session.draft, session.snapshot
        draft.add_rule("block_exes", "redo.exe")
        draft.undo()
        before = draft.config
        with patch.object(Path, "read_bytes", side_effect=AssertionError("page read")), \
                patch.object(Path, "open", side_effect=AssertionError("page IO")), \
                patch("core.config_session.read_snapshot", side_effect=AssertionError("page reload")), \
                patch("core.config_editor.config_to_dict", side_effect=AssertionError("page validation")), \
                patch("core.config_editor.parse_config", side_effect=AssertionError("page validation")), \
                patch("core.config_repository._serialize_config", side_effect=AssertionError("page serialize")), \
                patch.object(session, "save", side_effect=AssertionError("page save")):
            for field in self.FIELDS:
                full = rule_view_indices(draft.config, field, "match", "name_asc")
                for page in (0, 1, 2, 1, 0):
                    projection = rule_page(full, page)
                    self.assertEqual(projection.total, 60)
                self.assertEqual(rule_page_for_index(full, 56), 1)
            self.assertIs(session.draft, draft)
            self.assertIs(session.snapshot, baseline)
            self.assertTrue(configs_equal(draft.config, before))
            self.assertFalse(session.dirty)
            self.assertFalse(draft.can_undo)
            self.assertTrue(draft.can_redo)
        self.assertEqual(self.path.read_bytes(), self.original_bytes)
        self.assertTrue(draft.redo())
        self.assertEqual(draft.config.block_exes[-1], "redo.exe")
        self.assertTrue(session.dirty)
        self.assertEqual(self.path.read_bytes(), self.original_bytes)

    def test_explicit_save_order_conflict_import_and_reload_preserve_json_and_session_boundaries(self):
        session = self.session
        draft = session.draft
        before = draft.config
        full = rule_view_indices(before, "block_exes")
        selected = (rule_page(full).indices[2], rule_page(full, 1).indices[6], rule_page(full, 2).indices[6])
        self.assertEqual(draft.remove_rules("block_exes", selected), 3)
        after = draft.config
        self.assertEqual(self.path.read_bytes(), self.original_bytes)
        session.save()
        saved, baseline = self.path.read_bytes(), session.snapshot
        names = self.data["block_exes"]
        self.assertEqual(json.loads(saved)["block_exes"], names[:2] + names[3:31] + names[32:56] + names[57:])
        self.assertTrue(configs_equal(load_config(self.path), after))
        self.assertEqual(baseline.contents, saved)
        self.assertFalse(session.dirty)
        next_full = rule_view_indices(draft.config, "block_exes", order="name_asc")
        offpage = rule_page(next_full, 1).indices[-1]
        self.assertEqual(draft.remove_rules("block_exes", (offpage,)), 1)
        pending = draft.config
        external_data = deepcopy(self.data)
        external_data["block_exes"] = ["External.exe"]
        external_data["future"] = {"external": True}
        external = json.dumps(external_data, ensure_ascii=False).encode("utf-8")
        self.path.write_bytes(external)
        with self.assertRaises(ConfigConflictError):
            session.save()
        self.assertIs(session.draft, draft)
        self.assertIs(session.snapshot, baseline)
        self.assertTrue(configs_equal(draft.config, pending))
        self.assertTrue(draft.undo())
        self.assertTrue(configs_equal(draft.config, after))
        self.assertFalse(session.dirty)
        self.assertTrue(draft.can_redo)
        self.assertEqual(self.path.read_bytes(), external)

        imported_data = deepcopy(self.data)
        imported_data["block_exes"].insert(0, "Import.exe")
        imported_data["future"]["ação"][0] = 1
        source = self.root / "importação.json"
        source_bytes = json.dumps(imported_data, ensure_ascii=False).encode("utf-8")
        source.write_bytes(source_bytes)
        session.import_config(source)
        imported_draft = session.draft
        self.assertIsNot(imported_draft, draft)
        self.assertIs(session.snapshot, baseline)
        self.assertTrue(session.dirty)
        self.assertFalse(imported_draft.can_undo)
        self.assertFalse(imported_draft.can_redo)
        self.assertIs(type(imported_draft.config.extra["future"]["ação"][0]), int)
        self.assertIs(type(baseline.config.extra["future"]["ação"][0]), bool)
        imported_full = rule_view_indices(imported_draft.config, "block_exes", "match")
        self.assertEqual(rule_page(imported_full, 2).indices, tuple(range(51, 61)))
        self.assertEqual(rule_page_for_index(imported_full, 56), 2)
        with self.assertRaises(ConfigConflictError):
            session.save()
        self.assertEqual(self.path.read_bytes(), external)
        self.assertEqual(source.read_bytes(), source_bytes)
        session.reload()
        self.assertIsNot(session.draft, imported_draft)
        self.assertFalse(session.dirty)
        self.assertFalse(session.draft.can_undo)
        self.assertFalse(session.draft.can_redo)
        self.assertEqual(session.snapshot.contents, external)
        self.assertTrue(configs_equal(session.draft.config, load_config(self.path)))
        reloaded = rule_page(rule_view_indices(session.draft.config, "block_exes"))
        self.assertEqual((reloaded.page_count, reloaded.total, reloaded.indices), (1, 1, (0,)))
        self.assertEqual(self.path.read_bytes(), external)
        self.assertEqual(source.read_bytes(), source_bytes)


if __name__ == "__main__":
    unittest.main()

"""Links de revisão com índices originais, prefixo visível e pureza."""

from dataclasses import FrozenInstanceError
from datetime import time
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from core.config_review import ConfigReview, ReviewItem, review_config
from core.models import AppConfig, ScheduleWindow
from ui.review_navigation import ReviewLink, review_links


class ReviewNavigationTests(unittest.TestCase):
    def test_original_ordinals_and_row_indices_are_preserved_after_skipping_none(self):
        report = ConfigReview(0, 2, (
            ReviewItem("no_windows", "windows", None, "sem horários"),
            ReviewItem("duplicate", "block_exes", 7, "detalhe privado"),
            ReviewItem("no_targets", "block_exes", None, "sem alvos"),
            ReviewItem("duplicate", "block_folders", 2, "detalhe"),
        ))
        self.assertEqual(review_links(report), (
            ReviewLink(1, "block_exes", 7, "Apontamento 2 · Executáveis · item 8"),
            ReviewLink(3, "block_folders", 2, "Apontamento 4 · Pastas · item 3"),
        ))

    def test_category_labels_use_only_metadata_and_human_item_numbers(self):
        fields = ("windows", "block_exes", "block_folders", "safelist_exes", "block_cmdline")
        report = ConfigReview(1, 4, tuple(ReviewItem("DO_NOT_EXPOSE_CODE", field, index, "DO_NOT_EXPOSE_REASON.exe") for index, field in enumerate(fields)))
        links = review_links(report)
        self.assertEqual(tuple(link.label for link in links), (
            "Apontamento 1 · Horários · item 1", "Apontamento 2 · Executáveis · item 2",
            "Apontamento 3 · Pastas · item 3", "Apontamento 4 · Proteção adicional · item 4",
            "Apontamento 5 · Linha de comando · item 5",
        ))
        self.assertNotIn("DO_NOT_EXPOSE", repr(links))

    def test_limit_applies_before_filter_and_does_not_fill_links_from_hidden_items(self):
        items = tuple(ReviewItem("no_targets", "block_exes", None, "sem destino") for _ in range(9)) + (
            ReviewItem("duplicate", "block_exes", 4, "visível"),
            ReviewItem("duplicate", "block_exes", 5, "oculto"),
        )
        report = ConfigReview(0, 2, items)
        self.assertEqual(review_links(report), (ReviewLink(9, "block_exes", 4, "Apontamento 10 · Executáveis · item 5"),))
        self.assertEqual(review_links(report, 9), ())
        self.assertEqual(tuple(link.ordinal for link in review_links(report, 11)), (9, 10))
        self.assertEqual(review_links(report, 0), ())
        self.assertEqual(review_links(ConfigReview(0, 0, ())), ())

    def test_invalid_metadata_is_skipped_without_changing_ordinals_or_refilling_prefix(self):
        invalid = (
            ReviewItem("x", "unknown", 0, "skip"),
            ReviewItem("x", "block_exes", -1, "skip"),
            ReviewItem("x", "block_exes", True, "skip"),
            ReviewItem("x", "block_exes", False, "skip"),
            ReviewItem("x", "block_exes", 1.0, "skip"),
            ReviewItem("x", "block_exes", "1", "skip"),
            ReviewItem("x", None, 0, "skip"),
            ReviewItem("x", [], 0, "skip"),
            None,
        )
        report = ConfigReview(0, 1, invalid + (
            ReviewItem("x", "windows", 0, "visível"),
            ReviewItem("x", "block_exes", 0, "oculto"),
        ))
        self.assertEqual(review_links(report), (ReviewLink(9, "windows", 0, "Apontamento 10 · Horários · item 1"),))
        self.assertEqual(review_links(report, 9), ())

    def test_multiple_findings_for_same_original_row_are_not_deduplicated(self):
        window = ScheduleWindow(time(9), time(10), (0,))
        config = AppConfig(windows=(window,), block_exes=("CODE.EXE", "code.exe"))
        report = review_config(config)
        # Proteção no primeiro item, duplicata e proteção no segundo: ordinais
        # diferentes apontam à mesma linha original sem criar identidade nova.
        self.assertEqual(review_links(report), (
            ReviewLink(0, "block_exes", 0, "Apontamento 1 · Executáveis · item 1"),
            ReviewLink(1, "block_exes", 1, "Apontamento 2 · Executáveis · item 2"),
            ReviewLink(2, "block_exes", 1, "Apontamento 3 · Executáveis · item 2"),
        ))

    def test_link_indices_are_candidates_not_range_validation_or_config_access(self):
        report = ConfigReview(0, 0, (ReviewItem("x", "windows", 9999, "destino candidato"),))
        self.assertEqual(review_links(report), (
            ReviewLink(0, "windows", 9999, "Apontamento 1 · Horários · item 10000"),
        ))

    def test_invalid_report_and_strict_limit_types_have_explicit_errors(self):
        report = ConfigReview(0, 0, ())
        for invalid in (None, {}, [], "report", True):
            with self.subTest(report=invalid), self.assertRaises(TypeError):
                review_links(invalid)
        class IntSubclass(int):
            pass
        for invalid in (None, True, False, 1.0, "10", [], IntSubclass(10)):
            with self.subTest(limit=invalid), self.assertRaises(TypeError):
                review_links(report, invalid)
        with self.assertRaises(ValueError):
            review_links(report, -1)
        self.assertEqual(review_links(report, 1000), ())

    def test_links_are_frozen_tuple_and_formatting_preserves_report(self):
        report = ConfigReview(1, 1, (ReviewItem("x", "windows", 0, "literal"),))
        links = review_links(report)
        self.assertIsInstance(links, tuple)
        for field, value in (("ordinal", 2), ("field", "block_exes"), ("index", 2), ("label", "changed")):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError):
                setattr(links[0], field, value)
        self.assertEqual(report, ConfigReview(1, 1, (ReviewItem("x", "windows", 0, "literal"),)))
        self.assertEqual(review_links(report), links)
        self.assertEqual(review_links(ConfigReview(0, 0, ())), ())

    def test_navigation_never_analyzes_config_validates_environment_or_calls_io_runtime(self):
        report = ConfigReview(0, 0, (ReviewItem("x", "block_folders", 0, r"%MISSING%\Games"),))
        with patch.dict(os.environ, {}, clear=True), \
                patch("core.config_review.review_config", side_effect=AssertionError("analysis")), \
                patch("core.config.config_to_dict", side_effect=AssertionError("validation")), \
                patch("core.config.parse_config", side_effect=AssertionError("validation")), \
                patch("json.dumps", side_effect=AssertionError("serialization")), \
                patch.object(Path, "open", side_effect=AssertionError("IO")), \
                patch.object(Path, "resolve", side_effect=AssertionError("discovery")), \
                patch("time.time", side_effect=AssertionError("clock")), \
                patch("subprocess.Popen", side_effect=AssertionError("runtime")):
            links = review_links(report)
        self.assertEqual(links[0].label, "Apontamento 1 · Pastas · item 1")
        self.assertNotIn("MISSING", repr(links))

    def test_fresh_import_and_navigation_do_not_load_gui_or_runtime(self):
        script = '''
import builtins
original = builtins.__import__
def guarded(name,*args,**kwargs):
    if name.startswith(('psutil','tkinter','customtkinter','pystray','PIL')) or name in ('core.proc_blocker','core.process_controller','ui.config_gui'):
        raise AssertionError(name)
    return original(name,*args,**kwargs)
builtins.__import__ = guarded
from ui.review_navigation import review_links
from core.config_review import ConfigReview, ReviewItem
assert review_links(ConfigReview(0,0,(ReviewItem('x','windows',0,'private'),)))[0].index == 0
'''
        result = subprocess.run([sys.executable, "-B", "-c", script], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

"""Presenter do diff: texto limitado e fiel, sem UI, IO ou mutação."""

from copy import deepcopy
from dataclasses import FrozenInstanceError
from datetime import time
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from core.config_diff import ConfigChange, ConfigDiff, diff_config
from core.models import AppConfig, CmdlineRule, ScheduleWindow
from ui.config_diff_presenter import DiffView, format_config_diff


class ConfigDiffPresenterTests(unittest.TestCase):
    def test_empty_existing_report_has_no_changes_and_explicit_baseline_and_limits(self):
        view = format_config_diff(ConfigDiff(False, (), False))
        self.assertEqual(view.title, "Sem alterações")
        self.assertIn("configuração salva/carregada nesta sessão", view.detail)
        self.assertIn("inclusões: 0; remoções: 0; alterações: 0", view.detail)
        self.assertIn("Itens alterados: 0.", view.detail)
        self.assertIn("Extras: sem alterações; valores privados não exibidos", view.detail)
        self.assertIn("100 mudanças e 1000 caracteres por valor", view.detail)
        self.assertIn("O arquivo não é relido", view.detail)
        self.assertIn("Conflitos continuam sendo verificados ao Salvar", view.detail)
        self.assertNotIn("Mais ", view.detail)

    def test_new_empty_file_is_not_presented_as_no_changes_or_existing_file(self):
        view = format_config_diff(diff_config(None, AppConfig()))
        self.assertEqual(view.title, "Nova configuração")
        self.assertIn("ainda não há versão salva/carregada nesta sessão", view.detail)
        self.assertIn("O arquivo ainda será criado ao Salvar.", view.detail)
        self.assertIn("Itens alterados: 0.", view.detail)
        self.assertIn("inclusões: 0; remoções: 0; alterações: 0", view.detail)
        self.assertNotIn("Sem alterações", view.title)

    def test_insert_delete_replace_use_human_original_indices_for_each_side(self):
        report = ConfigDiff(False, (
            ConfigChange("block_exes", "insert", None, 6, None, "included.exe"),
            ConfigChange("block_folders", "delete", 2, None, r"C:\Old", None),
            ConfigChange("safelist_exes", "replace", 4, 1, "old.exe", "new.exe"),
        ), False)
        view = format_config_diff(report)
        self.assertEqual(view.title, "Alterações da configuração")
        self.assertIn("inclusões: 1; remoções: 1; alterações: 1", view.detail)
        self.assertIn("Executáveis — incluído (novo 7)\n  Depois: included.exe", view.detail)
        self.assertIn("Pastas — removido (salvo 3)\n  Antes: C:\\Old", view.detail)
        self.assertIn("Proteção adicional — alterado (salvo 5 → novo 2)\n  Antes: old.exe\n  Depois: new.exe", view.detail)

    def test_actual_diff_field_order_window_and_cmdline_descriptions_are_preserved(self):
        draft = AppConfig(
            windows=(ScheduleWindow(time(22, 30), time(2, 15), (6, 0)),),
            block_exes=("Game.EXE",), block_folders=(r"C:\Games",),
            safelist_exes=("Keep.EXE",),
            block_cmdline=(CmdlineRule("javaw.exe", ' .Minecraft "quoted" \\ literal '),),
        )
        report = diff_config(None, draft)
        view = format_config_diff(report)
        headings = [line for line in view.detail.splitlines() if " — incluído " in line]
        self.assertEqual(headings, [
            "Horários — incluído (novo 1)", "Executáveis — incluído (novo 1)",
            "Pastas — incluído (novo 1)", "Proteção adicional — incluído (novo 1)",
            "Linha de comando — incluído (novo 1)",
        ])
        self.assertIn("22:30–02:15 · dias: dom, seg", view.detail)
        self.assertIn("  Depois: " + report.changes[-1].after, view.detail)

    def test_reorder_duplicate_changes_keep_original_indices_and_counts(self):
        report = diff_config(AppConfig(block_exes=("a.exe", "b.exe")), AppConfig(block_exes=("b.exe", "a.exe")))
        view = format_config_diff(report)
        self.assertIn("incluído (novo 1)", view.detail)
        self.assertIn("removido (salvo 2)", view.detail)
        self.assertIn("inclusões: 1; remoções: 1; alterações: 0", view.detail)
        self.assertEqual(view.detail.count("b.exe"), 2)

    def test_extras_are_only_private_indicator_and_typed_change_is_not_noop(self):
        before = AppConfig(extra={"DO_NOT_EXPOSE_KEY": {"secret": True}})
        after = AppConfig(extra={"DO_NOT_EXPOSE_KEY": {"secret": 1}})
        view = format_config_diff(diff_config(before, after))
        self.assertEqual(view.title, "Alterações da configuração")
        self.assertIn("Extras: alterados; valores privados não exibidos", view.detail)
        self.assertIn("inclusões: 0; remoções: 0; alterações: 0", view.detail)
        self.assertNotIn("DO_NOT_EXPOSE_KEY", view.detail)
        self.assertNotIn("secret", view.detail)
        self.assertNotIn("True", view.detail)

    def test_exactly_one_hundred_changes_are_shown_without_omission_message(self):
        report = ConfigDiff(False, tuple(ConfigChange("block_exes", "insert", None, index, None, f"a{index}.exe") for index in range(100)), False)
        view = format_config_diff(report)
        self.assertEqual(view.detail.count(" — incluído "), 100)
        self.assertIn("novo 100", view.detail)
        self.assertNotIn("Mais ", view.detail)

    def test_over_one_hundred_changes_limit_rows_but_counts_cover_whole_report(self):
        changes = tuple(ConfigChange("block_exes", "insert", None, index, None, f"a{index}.exe") for index in range(100)) + (
            ConfigChange("block_exes", "delete", 101, None, "HIDDEN_DELETE.exe", None),
            ConfigChange("block_exes", "replace", 102, 103, "HIDDEN_OLD.exe", "HIDDEN_NEW.exe"),
        )
        view = format_config_diff(ConfigDiff(False, changes, True))
        self.assertEqual(view.detail.count(" — incluído "), 100)
        self.assertIn("inclusões: 100; remoções: 1; alterações: 1", view.detail)
        self.assertIn("Itens alterados: 102.", view.detail)
        self.assertIn("Mais 2 mudanças não exibidas", view.detail)
        self.assertNotIn("HIDDEN", view.detail)
        self.assertIn("Extras: alterados", view.detail)

    def test_one_omitted_change_uses_singular(self):
        changes = tuple(ConfigChange("block_exes", "insert", None, index, None, "a.exe") for index in range(101))
        self.assertIn("Mais 1 mudança não exibida", format_config_diff(ConfigDiff(False, changes, False)).detail)

    def test_value_at_limit_is_unchanged_but_long_value_includes_bounded_marker_and_count(self):
        report = ConfigDiff(False, (
            ConfigChange("block_folders", "replace", 0, 0, "a" * 1000, "b" * 1001),
            ConfigChange("block_exes", "delete", 1, None, "c" * 2000, None),
        ), False)
        view = format_config_diff(report)
        values = [line.split(": ", 1)[1] for line in view.detail.splitlines() if line.startswith(("  Antes: ", "  Depois: "))]
        self.assertEqual(values[0], "a" * 1000)
        self.assertEqual(len(values[0]), 1000)
        for value in values[1:]:
            self.assertLessEqual(len(value), 1000)
            self.assertTrue(value.endswith("… [valor truncado]"))
        self.assertIn("Valores exibidos truncados: 2", view.detail)

    def test_truncated_count_only_includes_displayed_values(self):
        changes = tuple(ConfigChange("block_exes", "insert", None, index, None, "a.exe") for index in range(99)) + (
            ConfigChange("block_folders", "replace", 0, 99, "a" * 1001, "b" * 1001),
            ConfigChange("block_folders", "insert", None, 100, None, "HIDDEN" * 1000),
        )
        view = format_config_diff(ConfigDiff(False, changes, False))
        self.assertIn("Valores exibidos truncados: 2", view.detail)
        self.assertIn("Mais 1 mudança não exibida", view.detail)
        self.assertNotIn("HIDDEN", view.detail)

    def test_raw_controls_are_escaped_and_cannot_add_fake_heading_or_terminal_command(self):
        value = "prefix\r\nHorários — incluído (novo 999)\t\x1b[2J\x00\x7f\x85\u2028\u2029\u202e\ud800\U000e0001"
        view = format_config_diff(ConfigDiff(False, (ConfigChange("block_folders", "insert", None, 0, None, value),), False))
        rendered = next(line for line in view.detail.splitlines() if line.startswith("  Depois: "))
        self.assertEqual(rendered, "  Depois: prefix\\r\\nHorários — incluído (novo 999)\\t\\x1b[2J\\x00\\x7f\\x85\\u2028\\u2029\\u202e\\ud800\\U000e0001")
        self.assertNotIn("\r", view.detail)
        self.assertNotIn("\t", view.detail)
        self.assertNotIn("\x1b", view.detail)
        self.assertNotIn("\nHorários", view.detail)
        view.detail.encode("utf-8")  # Surrogates crus não escapam para a saída.

    def test_escape_expansion_counts_toward_limit_and_truncation_keeps_whole_tokens(self):
        for value in ("x" * 999 + "\n", "\x00" * 251, "\u202e" * 167):
            with self.subTest(value=value):
                view = format_config_diff(ConfigDiff(False, (ConfigChange("block_exes", "insert", None, 0, None, value),), False))
                displayed = next(line[len("  Depois: "):] for line in view.detail.splitlines() if line.startswith("  Depois: "))
                self.assertLessEqual(len(displayed), 1000)
                self.assertTrue(displayed.endswith("… [valor truncado]"))
                prefix = displayed[:-len("… [valor truncado]")]
                if value.startswith("\x00"):
                    self.assertEqual(prefix, r"\x00" * (len(prefix) // 4))
                elif value.startswith("\u202e"):
                    self.assertEqual(prefix, r"\u202e" * (len(prefix) // 6))
                self.assertIn("Valores exibidos truncados: 1", view.detail)

    def test_spaces_repr_quotes_and_existing_literal_escapes_are_not_trimmed_or_reescaped(self):
        values = ("", "   ", "  literal.*  ", r"C:\Games\new", "javaw.exe + trecho: " + repr(' literal "quoted" \\n '))
        for value in values:
            with self.subTest(value=value):
                view = format_config_diff(ConfigDiff(False, (ConfigChange("block_cmdline", "insert", None, 0, None, value),), False))
                self.assertIn("  Depois: " + value + "\n", view.detail)
                self.assertNotIn("valor truncado", view.detail)

    def test_view_is_frozen_and_report_is_unchanged_after_repeat_formatting(self):
        report = ConfigDiff(False, (ConfigChange("block_exes", "replace", 0, 2, "old.exe", "new.exe"),), True)
        before = deepcopy(report)
        view = format_config_diff(report)
        self.assertIsInstance(view, DiffView)
        for field in ("title", "detail"):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError):
                setattr(view, field, "changed")
        self.assertEqual(report, before)
        self.assertEqual(format_config_diff(report), view)
        self.assertEqual(format_config_diff(ConfigDiff(False, (), False)).title, "Sem alterações")

    def test_formatting_has_no_io_discovery_clock_serialization_or_environment_revalidation(self):
        report = ConfigDiff(False, (ConfigChange("block_folders", "insert", None, 0, None, r"%MISSING%\Games"),), True)
        with patch.dict(os.environ, {}, clear=True), \
                patch.object(Path, "open", side_effect=AssertionError("IO")), \
                patch.object(Path, "resolve", side_effect=AssertionError("discovery")), \
                patch("json.dumps", side_effect=AssertionError("serialization")), \
                patch("time.time", side_effect=AssertionError("clock")), \
                patch("subprocess.Popen", side_effect=AssertionError("runtime")):
            self.assertIn(r"%MISSING%\Games", format_config_diff(report).detail)

    def test_invalid_report_type_raises_type_error(self):
        for report in (None, {}, [], "diff", True):
            with self.subTest(report=report), self.assertRaises(TypeError):
                format_config_diff(report)

    def test_fresh_import_and_formatting_do_not_load_gui_runtime_or_config_validator(self):
        script = '''
import builtins
original = builtins.__import__
def guarded(name,*args,**kwargs):
    if name.startswith(('psutil','tkinter','customtkinter','pystray','PIL')) or name in ('core.config','core.proc_blocker','core.process_controller','ui.config_gui'):
        raise AssertionError(name)
    return original(name,*args,**kwargs)
builtins.__import__ = guarded
from core.config_diff import ConfigDiff
from ui.config_diff_presenter import format_config_diff
assert format_config_diff(ConfigDiff(True,(),False)).title == 'Nova configuração'
'''
        result = subprocess.run([sys.executable, "-B", "-c", script], cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

"""Fluxos da GUI com widgets simulados e configuração/repositório reais.

Não comprova renderização, DPI ou interação nativa do CustomTkinter.
"""

import json
from datetime import date, datetime as real_datetime
from pathlib import Path
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from core.config import load_config
from core.config_session import ConfigSession
from ui.config_gui import _build_app


class Variable:
    def __init__(self, value=None):
        self.value = value
        self.traces = []

    def get(self):
        return self.value

    def set(self, value):
        self.value = value
        for callback in self.traces:
            callback()

    def trace_add(self, mode, callback):
        self.traces.append(callback)


class Widget:
    def __init__(self, parent=None, **options):
        self.options = options
        self.children = []
        self.destroyed = False
        self.value = ""
        self.callbacks = {}
        self.timers = {}
        if parent is not None:
            parent.children.append(self)

    def configure(self, **options):
        self.options.update(options)

    def grid(self, **options):
        pass

    pack = grid
    grid_columnconfigure = lambda *args, **kwargs: None
    grid_rowconfigure = lambda *args, **kwargs: None
    title = lambda *args, **kwargs: None
    geometry = lambda *args, **kwargs: None
    minsize = lambda *args, **kwargs: None
    resizable = lambda *args, **kwargs: None
    transient = lambda *args, **kwargs: None
    grab_set = lambda *args, **kwargs: None
    focus_set = lambda *args, **kwargs: None

    def bind(self, name, callback):
        self.callbacks[name] = callback

    protocol = bind

    def after(self, delay, callback):
        token = f"timer-{len(self.timers)}"
        self.timers[token] = callback
        return token

    def after_cancel(self, token):
        del self.timers[token]

    def winfo_children(self):
        return [child for child in self.children if not child.destroyed]

    def destroy(self):
        self.destroyed = True

    def insert(self, index, value):
        self.value = value

    def delete(self, start, end):
        self.value = ""

    def get(self):
        return self.value

    def invoke(self):
        return self.options["command"]()

    def add(self, text):
        self.options.setdefault("tabs", []).append(text)
        return Widget(self)

    def set(self, text):
        self.options["selected_tab"] = text


def fake_ctk():
    widgets = {name: type(name, (Widget,), {}) for name in (
        "CTk", "CTkFrame", "CTkLabel", "CTkButton", "CTkTabview",
        "CTkScrollableFrame", "CTkOptionMenu", "CTkTextbox", "CTkToplevel",
        "CTkEntry", "CTkCheckBox",
    )}
    return SimpleNamespace(**widgets, CTkFont=lambda **kwargs: kwargs, StringVar=Variable)


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


def button(widget, text):
    matches = [child for child in descendants(widget)
               if child.__class__.__name__ == "CTkButton" and child.options.get("text") == text]
    if len(matches) != 1:
        raise AssertionError(f"Esperado um botão {text!r}; encontrados {len(matches)}")
    return matches[0]


class ConfigGuiFlowTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / f".editor-integration-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = self.root / "config.json"
        self.path.write_text(json.dumps({"windows": [], "future": {"keep": "ação"}}), encoding="utf-8")
        self.session = ConfigSession(self.path)
        self.messages = SimpleNamespace(askyesno=Mock(return_value=True),
                                        askyesnocancel=Mock(return_value=None), showerror=Mock())
        self.filedialog = SimpleNamespace(askdirectory=Mock(return_value="C:\\Games"),
                                          askopenfilename=Mock(return_value=""),
                                          asksaveasfilename=Mock(return_value=""))
        self.app = _build_app(fake_ctk(), SimpleNamespace(IntVar=Variable), self.filedialog,
                              self.messages, self.session)

    def entries(self):
        return [widget for widget in descendants(self.app.modal)
                if widget.__class__.__name__ == "CTkEntry"]

    def add_window(self, start="22:00", end="02:00"):
        button(self.app, "Adicionar horário").invoke()
        first, second = self.entries()
        first.insert(0, start)
        second.insert(0, end)
        button(self.app.modal, "Adicionar").invoke()

    def labels(self, widget):
        return "\n".join(child.options.get("text", "") for child in descendants(widget)
                         if child.__class__.__name__ == "CTkLabel")

    def import_source(self, **config):
        source = self.root / "import.json"
        source.write_text(json.dumps({"windows": [], **config}), encoding="utf-8")
        self.filedialog.askopenfilename.return_value = str(source)
        return source

    def test_overview_is_initial_tab_with_orientation_and_shortcuts(self):
        self.assertEqual(self.app.tabs.options["tabs"][0], "Visão geral")
        self.assertIn("adicione", self.app.orientation.options["text"])
        self.assertIn("0 h 00 min", self.app.preview_summary.options["text"])
        self.assertIn("não uma medição de foco", self.app.preview_note.options["text"])
        button(self.app, "Ir para Horários").invoke()
        self.assertEqual(self.app.tabs.options["selected_tab"], "Horários")
        button(self.app, "Ir para Jogos / Apps").invoke()
        self.assertEqual(self.app.tabs.options["selected_tab"], "Jogos / Apps")

    def test_orientation_distinguishes_disabled_windows_and_protection_only(self):
        self.session.draft.add_window("09:00", "10:00", [])
        self.session.draft.add_rule("safelist_exes", "Code.exe")
        self.app.render()
        self.assertIn("Nenhum horário ativo", self.app.orientation.options["text"])
        self.assertIn("0 h 00 min", self.app.preview_summary.options["text"])
        self.session.draft.update_window(0, "09:00", "10:00", [0])
        self.app.render()
        self.assertIn("Escolha os jogos", self.app.orientation.options["text"])
        self.session.draft.add_rule("block_exes", "game.exe")
        self.app.render()
        self.assertIn("Revise horários", self.app.orientation.options["text"])

    def test_draft_week_merges_overlap_clips_midnight_and_keeps_saved_status(self):
        original = self.path.read_bytes()
        self.app.preview_anchor = date(2026, 10, 14)
        self.session.draft.add_window("22:00", "02:00", [6])
        self.session.draft.add_window("01:00", "03:00", [0])
        self.session.draft.add_window("09:00", "10:00", [])
        self.app.render()
        self.assertIn("12/10/2026 a 18/10/2026", self.app.preview_summary.options["text"])
        self.assertIn("5 h 00 min", self.app.preview_summary.options["text"])
        text = self.labels(self.app.preview_days)
        self.assertIn("Seg 12/10 · 3 h 00 min", text)
        self.assertIn("00:00 → 03:00", text)
        self.assertIn("Dom 18/10 · 2 h 00 min", text)
        self.assertIn("22:00 → 24:00", text)
        self.assertIn("Sem horário planejado", text)
        self.assertIn("não salvas", self.app.preview_note.options["text"])
        with patch("ui.config_gui.datetime") as clock:
            clock.now.return_value = real_datetime(2026, 10, 12, 1, 30)
            self.app.refresh_status(schedule=False)
        self.assertIn("fora da janela", self.app.agenda_label.options["text"])
        self.assertEqual(self.path.read_bytes(), original)
        button(self.app, "Salvar").invoke()
        self.assertIn("Sem alterações pendentes", self.app.preview_note.options["text"])
        with patch("ui.config_gui.datetime") as clock:
            clock.now.return_value = real_datetime(2026, 10, 12, 1, 30)
            self.app.refresh_status(schedule=False)
        self.assertIn("dentro da janela", self.app.agenda_label.options["text"])

    def test_week_navigation_and_return_to_current_week_do_not_edit(self):
        self.app.preview_anchor = date(2026, 10, 14)
        button(self.app, "Semana anterior").invoke()
        self.assertIn("05/10/2026 a 11/10/2026", self.app.preview_summary.options["text"])
        button(self.app, "Próxima semana").invoke()
        self.assertIn("12/10/2026 a 18/10/2026", self.app.preview_summary.options["text"])
        with patch("ui.config_gui.datetime") as clock:
            clock.now.return_value = real_datetime(2026, 10, 20)
            button(self.app, "Esta semana").invoke()
        self.assertIn("19/10/2026 a 25/10/2026", self.app.preview_summary.options["text"])
        self.assertFalse(self.session.dirty)
        self.assertEqual(len(self.app.timers), 1)

    def test_duplicate_appends_draft_copy_and_does_not_double_planned_time(self):
        self.session.draft.add_window("22:00", "02:00", [0])
        self.app.render()
        original = self.path.read_bytes()
        summary = self.app.preview_summary.options["text"]
        with patch.object(self.session.draft, "duplicate_window", wraps=self.session.draft.duplicate_window) as duplicate:
            button(self.app.windows_list, "Duplicar").invoke()
        duplicate.assert_called_once_with(0)
        self.assertEqual(self.session.draft.config.windows[0], self.session.draft.config.windows[1])
        self.assertEqual(self.app.preview_summary.options["text"], summary)
        self.assertTrue(self.session.dirty)
        self.assertEqual(self.path.read_bytes(), original)
        self.app.edit_window(1)
        for child in descendants(self.app.modal):
            if child.__class__.__name__ == "CTkCheckBox":
                child.options["variable"].set(0)
        button(self.app.modal, "Aplicar alteração").invoke()
        self.assertEqual(self.session.draft.config.windows[0].days, (0,))
        self.assertEqual(self.session.draft.config.windows[1].days, ())
        self.app.duplicate_window(1)
        self.assertEqual(self.session.draft.config.windows[2].days, ())

    def test_search_keeps_original_index_for_edit_and_remove(self):
        for name in ("first.exe", "Match.exe", "last.exe"):
            self.session.draft.add_rule("block_exes", name)
        self.app.render()
        self.app.rule_search.set(" MATCH ")
        self.assertNotIn("first.exe", self.labels(self.app.rules_list))
        button(self.app.rules_list, "Editar").invoke()
        self.assertEqual(self.entries()[0].get(), "Match.exe")
        self.entries()[0].insert(0, "match-edited.exe")
        button(self.app.modal, "Aplicar alteração").invoke()
        self.assertEqual(self.session.draft.config.block_exes, ("first.exe", "match-edited.exe", "last.exe"))
        button(self.app.rules_list, "Remover").invoke()
        self.assertEqual(self.session.draft.config.block_exes, ("first.exe", "last.exe"))
        self.assertIn("corresponde à busca", self.labels(self.app.rules_list))
        self.app.rule_search.set("")
        self.assertIn("first.exe", self.labels(self.app.rules_list))
        self.assertIn("last.exe", self.labels(self.app.rules_list))

    def test_search_handles_all_categories_and_both_cmdline_fields(self):
        cases = (("Pastas", "block_folders", "C:\\Games", "games"),
                 ("Proteção adicional", "safelist_exes", "Code.exe", "CODE"),
                 ("Linha de comando", "block_cmdline", {"executable": "javaw.exe", "contains": ".Minecraft"}, "minecraft"))
        for category, field, value, query in cases:
            with self.subTest(category=category):
                self.session.draft.add_rule(field, value)
                self.app.rule_category.set(category)
                self.app.rule_search.set(query)
                self.assertNotIn("corresponde à busca", self.labels(self.app.rules_list))
                button(self.app.rules_list, "Editar").invoke()
                button(self.app.modal, "Cancelar").invoke()
        self.app.rule_search.set("JAVAW")
        self.assertIn("javaw.exe", self.labels(self.app.rules_list))
        self.assertIn(".Minecraft", self.labels(self.app.rules_list))
        self.app.rule_category.set("Executáveis")
        self.app.render_rules()
        self.assertIn("Nenhuma regra nesta lista", self.labels(self.app.rules_list))
        self.session.draft.add_rule("block_exes", "other.exe")
        self.app.render_rules()
        self.assertIn("corresponde à busca", self.labels(self.app.rules_list))
        self.assertIn("Buscar regras nesta categoria", self.labels(self.app))

    def test_import_always_confirms_even_clean_and_waits_for_explicit_save(self):
        self.import_source(windows=[{"start": "09:00", "end": "10:00", "days": [0]}],
                           block_exes=["imported.exe"], future={"imported": True})
        baseline = self.session.snapshot
        draft = self.session.draft
        original = self.path.read_bytes()
        agenda = self.app.agenda_label.options["text"]
        button(self.app, "Importar JSON").invoke()
        self.messages.askyesno.assert_called_once()
        self.assertIsNot(self.session.draft, draft)
        self.assertIs(self.session.snapshot, baseline)
        self.assertEqual(self.session.path, self.path)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.app.agenda_label.options["text"], agenda)
        self.assertTrue(self.session.dirty)
        self.assertIn("09:00 → 10:00", self.labels(self.app.preview_days))
        self.assertIn("imported.exe", self.labels(self.app.rules_list))
        button(self.app, "Salvar").invoke()
        self.assertEqual(load_config(self.path).block_exes, ("imported.exe",))
        self.assertEqual(load_config(self.path).extra, {"future": {"imported": True}})
        self.assertFalse(self.session.dirty)

    def test_import_file_picker_and_confirmation_cancellation_have_no_effect(self):
        with patch.object(self.session, "import_config", wraps=self.session.import_config) as operation:
            button(self.app, "Importar JSON").invoke()
            operation.assert_not_called()
            self.messages.askyesno.assert_not_called()
            self.import_source(block_exes=["imported.exe"])
            self.messages.askyesno.return_value = False
            for dirty in (False, True):
                if dirty:
                    self.session.draft.add_rule("block_exes", "keep.exe")
                    self.app.render()
                draft = self.session.draft
                config = draft.config
                original = self.path.read_bytes()
                feedback = self.app.feedback.options["text"]
                button(self.app, "Importar JSON").invoke()
                operation.assert_not_called()
                self.assertIs(self.session.draft, draft)
                self.assertEqual(self.session.draft.config, config)
                self.assertEqual(self.path.read_bytes(), original)
                self.assertEqual(self.app.feedback.options["text"], feedback)
        self.assertEqual(self.messages.askyesno.call_count, 2)

    def test_invalid_import_preserves_draft_and_external_conflict_after_valid_import(self):
        self.session.draft.add_rule("block_exes", "keep.exe")
        self.app.render()
        source = self.import_source()
        source.write_text('{"windows":broken}', encoding="utf-8")
        draft = self.session.draft
        button(self.app, "Importar JSON").invoke()
        self.assertIs(self.session.draft, draft)
        self.assertIn("Rascunho preservado", self.app.feedback.options["text"])
        self.import_source(block_exes=["imported.exe"])
        external = b'{"windows":[],"external":true}'
        self.path.write_bytes(external)
        button(self.app, "Importar JSON").invoke()
        self.assertFalse(self.app.save_config())
        self.assertEqual(self.path.read_bytes(), external)
        self.assertEqual(self.session.draft.config.block_exes, ("imported.exe",))
        self.assertTrue(self.session.dirty)

    def test_export_writes_draft_to_new_json_without_saving_active(self):
        self.session.draft.add_rule("block_exes", "unsaved.exe")
        self.app.render()
        baseline = self.session.snapshot
        original = self.path.read_bytes()
        destination = self.root / "export.json"
        self.filedialog.asksaveasfilename.return_value = str(destination)
        button(self.app, "Exportar JSON").invoke()
        self.assertEqual(load_config(destination), self.session.draft.config)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertIs(self.session.snapshot, baseline)
        self.assertEqual(self.session.path, self.path)
        self.assertTrue(self.session.dirty)
        self.assertIn("não salva a configuração ativa", self.app.feedback.options["text"])

    def test_export_cancel_has_no_effect_and_existing_or_active_targets_are_rejected(self):
        self.session.draft.add_rule("block_exes", "unsaved.exe")
        self.app.render()
        original = self.path.read_bytes()
        feedback = self.app.feedback.options["text"]
        with patch.object(self.session, "export_config", wraps=self.session.export_config) as operation:
            button(self.app, "Exportar JSON").invoke()
            operation.assert_not_called()
        self.assertEqual(self.app.feedback.options["text"], feedback)
        target = self.root / "existing.json"
        target.write_bytes(b"keep existing file")
        for path in (target, self.path, self.root / "." / "config.json"):
            with self.subTest(path=path):
                baseline = self.session.snapshot
                self.filedialog.asksaveasfilename.return_value = str(path)
                button(self.app, "Exportar JSON").invoke()
                self.assertIn("Não foi possível exportar", self.app.feedback.options["text"])
                self.assertEqual(self.path.read_bytes(), original)
                self.assertEqual(target.read_bytes(), b"keep existing file")
                self.assertIs(self.session.snapshot, baseline)
                self.assertTrue(self.session.dirty)

    def test_portability_and_duplicate_do_not_run_during_modal(self):
        self.session.draft.add_window("09:00", "10:00", [0])
        self.app.render()
        button(self.app, "Adicionar horário").invoke()
        original = self.session.draft.config
        button(self.app, "Importar JSON").invoke()
        button(self.app, "Exportar JSON").invoke()
        button(self.app.windows_list, "Duplicar").invoke()
        self.filedialog.askopenfilename.assert_not_called()
        self.filedialog.asksaveasfilename.assert_not_called()
        self.assertEqual(self.session.draft.config, original)
        button(self.app.modal, "Cancelar").invoke()

    def test_invalid_window_keeps_dialog_open_and_correction_reaches_saved_agenda(self):
        original = self.path.read_bytes()
        self.add_window("08:00", "08:00")
        self.assertIsNotNone(self.app.modal)
        self.assertFalse(self.session.dirty)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertTrue(any(widget.options.get("text") for widget in descendants(self.app.modal)
                            if widget.options.get("text_color") == "#A33232"))
        self.entries()[1].insert(0, "09:00")
        button(self.app.modal, "Adicionar").invoke()
        self.assertIsNone(self.app.modal)
        self.assertTrue(self.session.dirty)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertIn("não salvas", self.app.dirty_label.options["text"])
        button(self.app, "Salvar").invoke()
        self.assertFalse(self.session.dirty)
        self.assertEqual(load_config(self.path).windows[0].days, tuple(range(7)))
        self.assertEqual(load_config(self.path).extra, {"future": {"keep": "ação"}})
        self.assertEqual(len(self.app.timers), 1)

    def test_existing_window_can_be_edited_and_disabled_without_deletion(self):
        self.add_window()
        button(self.app.windows_list, "Editar").invoke()
        self.assertEqual([entry.get() for entry in self.entries()], ["22:00", "02:00"])
        for widget in descendants(self.app.modal):
            if widget.__class__.__name__ == "CTkCheckBox":
                widget.options["variable"].set(0)
        button(self.app.modal, "Aplicar alteração").invoke()
        button(self.app, "Salvar").invoke()
        self.assertEqual(load_config(self.path).windows[0].days, ())

    def test_cancel_dialog_has_no_effect_on_draft_or_file(self):
        original = self.path.read_bytes()
        button(self.app, "Adicionar horário").invoke()
        self.entries()[0].insert(0, "09:00")
        button(self.app.modal, "Cancelar").invoke()
        self.assertIsNone(self.app.modal)
        self.assertFalse(self.session.dirty)
        self.assertEqual(self.path.read_bytes(), original)

    def test_all_rule_categories_can_be_added_and_joint_pattern_is_preserved(self):
        cases = (
            ("Executáveis", "game.exe", None),
            ("Pastas", "C:\\Games", None),
            ("Proteção adicional", "Code.exe", None),
            ("Linha de comando", "javaw.exe", " .minecraft "),
        )
        for category, executable, contains in cases:
            self.app.rule_category.set(category)
            self.app.render_rules()
            button(self.app, "Adicionar regra").invoke()
            self.entries()[0].insert(0, executable)
            if contains is not None:
                self.entries()[1].insert(0, contains)
            button(self.app.modal, "Adicionar").invoke()
            self.assertIsNone(self.app.modal)
        button(self.app, "Salvar").invoke()
        actual = load_config(self.path)
        self.assertEqual(actual.block_exes, ("game.exe",))
        self.assertEqual(actual.block_folders, ("C:\\Games",))
        self.assertEqual(actual.safelist_exes, ("Code.exe",))
        self.assertEqual(actual.block_cmdline[0].executable, "javaw.exe")
        self.assertEqual(actual.block_cmdline[0].contains, " .minecraft ")

    def test_folder_picker_cancel_preserves_entry_then_accepts_absolute_folder(self):
        self.app.rule_category.set("Pastas")
        button(self.app, "Adicionar regra").invoke()
        self.entries()[0].insert(0, "C:\\Old")
        self.filedialog.askdirectory.return_value = ""
        button(self.app.modal, "Escolher pasta…").invoke()
        self.assertEqual(self.entries()[0].get(), "C:\\Old")
        self.filedialog.askdirectory.return_value = "C:\\Games"
        button(self.app.modal, "Escolher pasta…").invoke()
        self.assertEqual(self.entries()[0].get(), "C:\\Games")
        button(self.app.modal, "Adicionar").invoke()
        self.assertEqual(self.session.draft.config.block_folders, ("C:\\Games",))

    def test_rule_edit_and_removal_use_the_selected_category(self):
        self.session.draft.add_rule("block_exes", "old.exe")
        self.session.draft.add_rule("safelist_exes", "Code.exe")
        self.app.render()
        button(self.app.rules_list, "Editar").invoke()
        self.entries()[0].insert(0, "new.exe")
        button(self.app.modal, "Aplicar alteração").invoke()
        self.assertEqual(self.session.draft.config.block_exes, ("new.exe",))
        self.messages.askyesno.return_value = False
        button(self.app.rules_list, "Remover").invoke()
        self.assertEqual(self.session.draft.config.block_exes, ("new.exe",))
        self.messages.askyesno.return_value = True
        button(self.app.rules_list, "Remover").invoke()
        self.assertEqual(self.session.draft.config.block_exes, ())
        self.assertEqual(self.session.draft.config.safelist_exes, ("Code.exe",))

    def test_conflict_shows_error_preserves_draft_and_external_file(self):
        self.add_window()
        external = b'{"windows":[],"external":true}'
        self.path.write_bytes(external)
        self.assertFalse(self.app.save_config())
        self.messages.showerror.assert_called_once()
        self.assertEqual(self.path.read_bytes(), external)
        self.assertTrue(self.session.dirty)
        self.assertIn("Conflito", self.app.feedback.options["text"])

    def test_reload_can_be_cancelled_and_failure_preserves_draft(self):
        self.add_window()
        self.messages.askyesno.return_value = False
        button(self.app, "Recarregar").invoke()
        self.assertTrue(self.session.dirty)
        self.messages.askyesno.return_value = True
        self.path.write_bytes(b'{"windows":broken}')
        button(self.app, "Recarregar").invoke()
        self.assertTrue(self.session.dirty)
        self.assertIn("Rascunho preservado", self.app.feedback.options["text"])
        self.path.write_bytes(b'{"windows":[],"external":true}')
        button(self.app, "Recarregar").invoke()
        self.assertFalse(self.session.dirty)
        self.assertEqual(self.session.draft.config.extra, {"external": True})

    def test_close_allows_cancel_discard_or_save(self):
        self.add_window()
        original = self.path.read_bytes()
        self.messages.askyesnocancel.return_value = None
        self.app.close_editor()
        self.assertFalse(self.app.destroyed)
        self.messages.askyesnocancel.return_value = False
        self.app.close_editor()
        self.assertTrue(self.app.destroyed)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.app.timers, {})

    def test_close_save_failure_keeps_window_open_then_retry_succeeds(self):
        self.add_window()
        self.messages.askyesnocancel.return_value = True
        with patch("core.config.os.replace", side_effect=PermissionError("negado")):
            self.app.close_editor()
        self.assertFalse(self.app.destroyed)
        self.assertTrue(self.session.dirty)
        self.app.close_editor()
        self.assertTrue(self.app.destroyed)
        self.assertFalse(self.session.dirty)
        self.assertEqual(len(load_config(self.path).windows), 1)

    def test_keyboard_save_does_not_publish_while_a_form_is_open(self):
        self.session.draft.add_rule("block_exes", "game.exe")
        original = self.path.read_bytes()
        button(self.app, "Adicionar regra").invoke()
        self.app.callbacks["<Control-s>"](None)
        self.assertEqual(self.path.read_bytes(), original)
        self.app.callbacks["<Control-r>"](None)
        self.messages.askyesno.assert_not_called()
        button(self.app.modal, "Cancelar").invoke()
        self.app.callbacks["<Control-s>"](None)
        self.assertEqual(load_config(self.path).block_exes, ("game.exe",))

    def test_closing_parent_cancels_pending_modal_callbacks(self):
        button(self.app, "Adicionar horário").invoke()
        dialog = self.app.modal
        self.assertEqual(len(dialog.timers), 2)
        self.app.close_editor()
        self.assertTrue(self.app.destroyed)
        self.assertTrue(dialog.destroyed)
        self.assertIsNone(self.app.modal)
        self.assertEqual(dialog.timers, {})


if __name__ == "__main__":
    unittest.main()

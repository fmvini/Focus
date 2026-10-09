"""Fluxos da GUI com widgets simulados e configuração/repositório reais.

Não comprova renderização, DPI ou interação nativa do CustomTkinter.
"""

import json
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

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


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
        return Widget(self)


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
        self.filedialog = SimpleNamespace(askdirectory=Mock(return_value="C:\\Games"))
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

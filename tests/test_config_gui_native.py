"""Smoke tests com widgets reais; exigem dependências gráficas instaladas.

Janelas ficam ocultas. Estes testes não substituem inspeção visual ou DPI.
"""

import importlib.util
import json
from datetime import date
from pathlib import Path
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import Mock
from uuid import uuid4

from core.config import load_config
from core.config_session import ConfigSession
from ui.config_gui import _build_app


@unittest.skipUnless(importlib.util.find_spec("customtkinter"), "CustomTkinter não instalado")
class NativeConfigGuiTests(unittest.TestCase):
    def setUp(self):
        import customtkinter as ctk
        import tkinter as tk

        self.root = Path(__file__).resolve().parents[1] / f".editor-integration-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = self.root / "config.json"
        self.path.write_text(json.dumps({"windows": [], "future": {"keep": True}}), encoding="utf-8")
        self.session = ConfigSession(self.path)

        class HiddenRoot(ctk.CTk):
            def __init__(self):
                super().__init__()
                self.withdraw()

        class Toolkit:
            CTk = HiddenRoot

            def __getattr__(self, name):
                return getattr(ctk, name)

        self.messages = SimpleNamespace(askyesno=Mock(return_value=False),
                                        askyesnocancel=Mock(return_value=False), showerror=Mock())
        self.filedialog = SimpleNamespace(askdirectory=Mock(return_value=""),
                                          askopenfilename=Mock(return_value=""),
                                          asksaveasfilename=Mock(return_value=""))
        self.ctk = ctk
        self.app = _build_app(Toolkit(), tk, self.filedialog, self.messages, self.session)
        self.addCleanup(self.cleanup_app)

    def cleanup_app(self):
        if self.app.modal is not None:
            self.button(self.app.modal, "Cancelar").invoke()
        self.app.close_editor()

    @staticmethod
    def descendants(widget):
        for child in widget.winfo_children():
            yield child
            yield from NativeConfigGuiTests.descendants(child)

    def button(self, widget, text):
        found = [child for child in self.descendants(widget)
                 if isinstance(child, self.ctk.CTkButton) and child.cget("text") == text]
        self.assertEqual(len(found), 1, text)
        return found[0]

    def entries(self):
        return [child for child in self.descendants(self.app.modal) if isinstance(child, self.ctk.CTkEntry)]

    def test_construct_tabs_refresh_status_and_save_with_real_widgets(self):
        self.app.update_idletasks()
        self.assertEqual(self.app.tabs.get(), "Visão geral")
        for tab in ("Visão geral", "Horários", "Jogos / Apps", "Configuração"):
            self.app.tabs.set(tab)
            self.app.update_idletasks()
        self.assertIn("fora da janela", self.app.agenda_label.cget("text"))
        self.session.draft.add_rule("block_exes", "game.exe")
        self.button(self.app, "Salvar").invoke()
        self.assertEqual(load_config(self.path).block_exes, ("game.exe",))
        self.assertEqual(load_config(self.path).extra, {"future": {"keep": True}})

    def test_modal_validation_and_window_edit_roundtrip(self):
        self.button(self.app, "Adicionar horário").invoke()
        self.app.modal.withdraw()
        start, end = self.entries()
        start.insert(0, "22:00")
        end.insert(0, "22:00")
        self.button(self.app.modal, "Adicionar").invoke()
        self.assertIsNotNone(self.app.modal)
        self.assertFalse(self.session.dirty)
        end.delete(0, "end")
        end.insert(0, "02:00")
        self.button(self.app.modal, "Adicionar").invoke()
        self.assertIsNone(self.app.modal)
        self.button(self.app.windows_list, "Editar").invoke()
        self.app.modal.withdraw()
        self.assertEqual([entry.get() for entry in self.entries()], ["22:00", "02:00"])
        self.button(self.app.modal, "Aplicar alteração").invoke()
        self.button(self.app, "Salvar").invoke()
        self.assertEqual(load_config(self.path).windows[0].start.hour, 22)
        self.assertEqual(load_config(self.path).windows[0].end.hour, 2)

    def test_overview_duplicate_and_shortcuts_with_real_widgets(self):
        self.app.preview_anchor = date(2026, 10, 14)
        self.session.draft.add_window("22:00", "02:00", [6])
        self.app.render()
        self.button(self.app.windows_list, "Duplicar").invoke()
        self.app.update_idletasks()
        self.assertEqual(len(self.session.draft.config.windows), 2)
        self.assertIn("4 h 00 min", self.app.preview_summary.cget("text"))
        self.assertIn("não salvas", self.app.preview_note.cget("text"))
        self.button(self.app, "Ir para Horários").invoke()
        self.assertEqual(self.app.tabs.get(), "Horários")
        self.button(self.app, "Ir para Jogos / Apps").invoke()
        self.assertEqual(self.app.tabs.get(), "Jogos / Apps")

    def test_search_trace_keeps_original_index_with_real_widgets(self):
        for name in ("first.exe", "target.exe", "last.exe"):
            self.session.draft.add_rule("block_exes", name)
        self.app.render()
        self.app.rule_search.set("TARGET")
        self.app.update_idletasks()
        self.button(self.app.rules_list, "Editar").invoke()
        self.app.modal.withdraw()
        self.assertEqual(self.entries()[0].get(), "target.exe")
        self.button(self.app.modal, "Cancelar").invoke()
        self.messages.askyesno.return_value = True
        self.button(self.app.rules_list, "Remover").invoke()
        self.assertEqual(self.session.draft.config.block_exes, ("first.exe", "last.exe"))

    def test_import_export_and_settings_scroll_with_real_widgets(self):
        self.app.geometry("880x660")
        settings = self.app.tabs.tab("Configuração")
        self.assertTrue(any(isinstance(child, self.ctk.CTkScrollableFrame)
                            for child in self.descendants(settings)))
        self.app.tabs.set("Configuração")
        self.app.update_idletasks()
        source = self.root / "import.json"
        source.write_text(json.dumps({"windows": [], "block_exes": ["imported.exe"]}), encoding="utf-8")
        destination = self.root / "export.json"
        self.filedialog.askopenfilename.return_value = str(source)
        self.filedialog.asksaveasfilename.return_value = str(destination)
        self.messages.askyesno.return_value = True
        original = self.path.read_bytes()
        self.button(self.app, "Importar JSON").invoke()
        self.messages.askyesno.assert_called_once()
        self.button(self.app, "Exportar JSON").invoke()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(load_config(destination).block_exes, ("imported.exe",))
        self.assertTrue(self.session.dirty)
        self.button(self.app, "Salvar").invoke()
        self.assertFalse(self.session.dirty)


if __name__ == "__main__":
    unittest.main()

"""Smoke tests com widgets reais; exigem dependências gráficas instaladas.

Janelas ficam ocultas. Estes testes não substituem inspeção visual ou DPI.
"""

import importlib.util
import json
from datetime import date, datetime
from pathlib import Path
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from core.config import load_config
from core.config_session import ConfigSession
from ui.config_gui import _build_app
from tests.test_config_gui import FakeController, FakeTray
from ui.tray_commands import TrayMailbox


@unittest.skipUnless(importlib.util.find_spec("customtkinter"), "CustomTkinter não instalado")
class NativeConfigGuiTests(unittest.TestCase):
    def setUp(self):
        import customtkinter as ctk
        import tkinter as tk

        self.root = Path(__file__).resolve().parents[1] / f".editor-integration-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = self.root / "config.json"
        if self._testMethodName.startswith("test_first_setup_"):
            self.session = ConfigSession.for_new(self.path)
        else:
            self.path.write_text(json.dumps({"windows": [], "future": {"keep": True}}), encoding="utf-8")
            self.session = ConfigSession(self.path)

        class HiddenRoot(ctk.CTk):
            def __init__(self):
                super().__init__()
                self.withdraw()

            def deiconify(self):
                # Exercita a intenção de restaurar sem exibir a janela de QA.
                self.restore_requested = True

            def lift(self):
                pass

        class Toolkit:
            CTk = HiddenRoot

            def __getattr__(self, name):
                return getattr(ctk, name)

        self.messages = SimpleNamespace(askyesno=Mock(return_value=False),
                                        askyesnocancel=Mock(return_value=False), showerror=Mock())
        self.filedialog = SimpleNamespace(askdirectory=Mock(return_value=""),
                                          askopenfilename=Mock(return_value=""),
                                          askopenfilenames=Mock(return_value=()),
                                          asksaveasfilename=Mock(return_value=""))
        self.ctk = ctk
        self.controller = FakeController(self.path)
        self.tray = FakeTray()
        self.mailbox = TrayMailbox()
        self.app = _build_app(Toolkit(), tk, self.filedialog, self.messages, self.session,
                              controller=self.controller, tray=self.tray, mailbox=self.mailbox)
        self.background_errors = []
        self.app.tk.createcommand("bgerror", self.background_errors.append)
        self.app.report_callback_exception = lambda *error: self.background_errors.append(str(error))
        self.addCleanup(self.cleanup_app)

    def cleanup_app(self):
        if self.app.modal is not None:
            self.button(self.app.modal, "Cancelar").invoke()
        self.controller.finish()
        self.tray.alive = False
        self.messages.askyesnocancel.return_value = False
        self.app.close_editor()
        self.assertTrue(self.app.closed)
        self.assertEqual(self.app.tk.splitlist(self.app.tk.call("after", "info")), ())
        self.app.tk.call("update")
        self.assertEqual(self.background_errors, [])
        self.controller.wait.assert_not_called()
        self.tray.wait.assert_not_called()

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

    def test_saved_agenda_end_with_real_widgets_and_stopped_motor(self):
        self.app.geometry("880x660")
        self.session.draft.add_window("22:00", "02:00", [6])
        self.session.save()
        with patch("ui.config_gui.datetime", SimpleNamespace(now=lambda: datetime(2026, 10, 12, 1))):
            self.app.refresh_status(schedule=False)
            self.app.update_idletasks()
            self.assertEqual(self.app.end_label.cget("text"), "Fim da janela carregada: 12/10/2026 às 02:00")
            self.assertEqual(self.app.runtime_title.cget("text"), "Motor parado")
        self.assertEqual(self.controller.starts, 0)

    def test_config_review_readonly_scrollable_with_real_widgets(self):
        self.app.geometry("880x660")
        self.session.draft.add_rule("block_exes", "CODE.EXE")
        self.session.draft.add_rule("block_exes", "code.exe")
        self.app.render()
        self.app.update_idletasks()
        text = self.app.review_detail.get("1.0", "end")
        self.assertIn("proteção obrigatória", text)
        self.assertIn("Regra repetida", text)
        self.assertEqual(self.app.review_detail.cget("state"), "disabled")
        self.assertEqual(self.app.review_detail.cget("height"), 150)
        self.assertEqual(self.controller.starts, 0)

    def test_first_setup_selected_suggestions_create_only_on_save_with_real_widgets(self):
        self.app.geometry("880x660")
        self.app.update_idletasks()
        self.assertFalse(self.path.exists())
        self.assertTrue(self.session.is_new)
        self.assertIn("ainda não salva", self.app.agenda_label.cget("text"))
        self.assertEqual(self.app.start_button.cget("state"), "disabled")
        self.assertTrue(all(variable.get() == 0 for variable in self.app.suggestion_vars.values()))
        self.app.tabs.set("Configuração")
        self.app.suggestion_vars["steam"].set(1)
        self.app.suggestion_vars["minecraft_java"].set(1)
        self.button(self.app, "Adicionar selecionadas").invoke()
        self.assertFalse(self.path.exists())
        self.assertEqual(self.session.draft.config.block_exes, ("steam.exe",))
        self.assertEqual(self.session.draft.config.block_cmdline[0].contains, ".minecraft")
        self.assertTrue(all(variable.get() == 0 for variable in self.app.suggestion_vars.values()))
        self.button(self.app, "Salvar").invoke()
        self.assertFalse(self.session.is_new)
        self.assertFalse(self.session.dirty)
        self.assertEqual(load_config(self.path), self.session.draft.config)
        self.assertEqual(self.controller.starts, 0)
        self.assertEqual(self.app.runtime_title.cget("text"), "Motor parado")
        self.assertEqual(self.app.start_button.cget("state"), "normal")

    def test_first_setup_tray_and_cancel_or_discard_close_do_not_create_file(self):
        self.session.draft.add_rule("block_exes", "chosen.exe")
        self.button(self.app, "Enviar à bandeja").invoke()
        self.mailbox.post("ready")
        self.app.refresh_status()
        self.assertTrue(self.app.tray_hidden)
        self.messages.askyesnocancel.return_value = None
        self.mailbox.post("close")
        self.app.refresh_status()
        self.assertFalse(self.app.closing)
        self.assertTrue(self.app.restore_requested)
        self.assertFalse(self.path.exists())
        self.assertTrue(self.session.is_new)
        self.assertTrue(self.tray.alive)
        self.messages.askyesnocancel.return_value = False
        self.app.close_editor()
        self.tray.alive = False
        self.app.poll_close()
        self.assertTrue(self.app.closed)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.app.tk.splitlist(self.app.tk.call("after", "info")), ())
        self.app.tk.call("update")
        self.assertEqual(self.background_errors, [])
        self.controller.wait.assert_not_called()
        self.tray.wait.assert_not_called()

    def test_executable_selection_with_real_widgets_is_draft_only_then_saves(self):
        self.app.geometry("880x660")
        self.app.tabs.set("Jogos / Apps")
        self.app.update_idletasks()
        original = self.path.read_bytes()
        self.filedialog.askopenfilenames.return_value = (r"C:\Games\game.exe", r"D:\Games\GAME.EXE")
        self.button(self.app, "Selecionar .exe…").invoke()
        self.assertEqual(self.session.draft.config.block_exes, ("game.exe",))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.controller.starts, 0)
        self.app.rule_category.set("Linha de comando")
        self.app.render_rules()
        self.assertEqual(self.app.executable_picker.cget("state"), "disabled")
        self.app.rule_category.set("Proteção adicional")
        self.app.render_rules()
        self.filedialog.askopenfilenames.return_value = (r"C:\Tools\Code.exe",)
        self.button(self.app, "Selecionar .exe…").invoke()
        self.button(self.app, "Salvar").invoke()
        self.assertEqual(load_config(self.path).safelist_exes, ("Code.exe",))
        self.assertEqual(load_config(self.path).block_exes, ("game.exe",))

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

    def test_runtime_start_stop_and_close_poll_with_real_widgets(self):
        self.assertEqual(self.controller.starts, 0)
        self.assertEqual(self.app.runtime_title.cget("text"), "Motor parado")
        self.messages.askyesno.return_value = True
        self.button(self.app, "Iniciar").invoke()
        self.assertEqual(self.controller.starts, 1)
        self.assertEqual(self.app.start_button.cget("state"), "disabled")
        self.assertEqual(self.app.stop_button.cget("state"), "normal")
        self.button(self.app, "Parar").invoke()
        self.assertEqual(self.app.runtime_title.cget("text"), "Motor parando")
        self.assertTrue(self.controller.alive)
        self.app.close_editor()
        self.assertFalse(self.app.closed)
        self.app.after(50, self.controller.finish)
        self.app.mainloop()
        self.assertTrue(self.app.closed)
        self.controller.wait.assert_not_called()

    def test_cancel_dirty_close_keeps_fake_worker_and_modal_alive(self):
        self.messages.askyesno.return_value = True
        self.button(self.app, "Iniciar").invoke()
        self.session.draft.add_rule("block_exes", "pending.exe")
        self.button(self.app, "Adicionar horário").invoke()
        modal = self.app.modal
        self.messages.askyesnocancel.return_value = None
        self.app.close_editor()
        self.assertEqual(self.controller.stops, 0)
        self.assertTrue(self.controller.alive)
        self.assertFalse(self.app.closing)
        self.assertIs(self.app.modal, modal)
        self.messages.askyesnocancel.return_value = False
        self.app.close_editor()
        self.assertIsNone(self.app.modal)
        self.assertFalse(self.app.closed)
        self.app.after(50, self.controller.finish)
        self.app.mainloop()
        self.assertTrue(self.app.closed)

    def test_modal_and_filtered_rows_cancel_owned_callbacks_preserving_root_poll(self):
        self.session.draft.add_rule("block_exes", "game.exe")
        self.app.render()
        orphaned_row = Mock()
        self.button(self.app.rules_list, "Editar").after(30, orphaned_row)
        self.app.rule_search.set("no results")
        self.button(self.app, "Adicionar horário").invoke()
        orphaned_modal = Mock()
        self.app.modal.after(30, orphaned_modal)
        self.button(self.app.modal, "Cancelar").invoke()
        root_callback = Mock()
        self.app.after(30, root_callback)
        self.app.after(300, self.app.quit)
        self.app.mainloop()
        root_callback.assert_called_once_with()
        orphaned_row.assert_not_called()
        orphaned_modal.assert_not_called()
        self.assertIsNotNone(self.app.status_timer)
        self.assertEqual(self.background_errors, [])

    def test_tray_ready_show_and_cancel_exit_with_real_widgets(self):
        self.messages.askyesno.return_value = True
        self.button(self.app, "Iniciar").invoke()
        self.session.draft.add_rule("block_exes", "pending.exe")
        self.button(self.app, "Enviar à bandeja").invoke()
        self.assertFalse(self.app.tray_hidden)
        self.mailbox.post("ready")
        self.app.refresh_status()
        self.assertTrue(self.app.tray_hidden)
        self.assertEqual(self.app.state(), "withdrawn")
        self.mailbox.post("show")
        self.app.refresh_status()
        self.assertTrue(self.app.restore_requested)
        self.assertFalse(self.app.tray_hidden)
        self.button(self.app, "Enviar à bandeja").invoke()
        self.messages.askyesnocancel.return_value = None
        self.mailbox.post("close")
        self.app.refresh_status()
        self.assertFalse(self.app.closing)
        self.assertFalse(self.app.tray_hidden)
        self.assertTrue(self.controller.alive)
        self.assertTrue(self.tray.alive)
        self.assertEqual(self.controller.stops, 0)
        self.assertEqual(self.tray.stops, 0)

    def test_close_waits_for_tray_and_motor_and_cancels_all_native_timers(self):
        self.messages.askyesno.return_value = True
        self.button(self.app, "Iniciar").invoke()
        self.button(self.app, "Enviar à bandeja").invoke()
        self.mailbox.post("ready")
        self.app.refresh_status()
        self.app.close_editor()
        self.assertFalse(self.app.closed)
        self.assertTrue(self.app.restore_requested)
        self.controller.finish()
        self.app.poll_close()
        self.assertFalse(self.app.closed)
        self.app.after(50, lambda: setattr(self.tray, "alive", False))
        self.app.mainloop()
        self.assertTrue(self.app.closed)
        self.assertEqual(self.app.tk.splitlist(self.app.tk.call("after", "info")), ())
        self.app.tk.call("update")
        self.assertEqual(self.background_errors, [])
        self.controller.wait.assert_not_called()
        self.tray.wait.assert_not_called()


if __name__ == "__main__":
    unittest.main()

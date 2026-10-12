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
        # Inicializa CTk antes de qualquer teste agendar parada/destruição.
        # Seu primeiro mainloop prepara a barra de título com update interno;
        # uma raiz já inicializada não reentra nessa etapa durante fechamento.
        self.app.update()
        self.assertEqual(self.background_errors, [])

    def cleanup_app(self):
        if self.app.modal is not None:
            self.button(self.app.modal, "Fechar" if self.app.modal.read_only else "Cancelar").invoke()
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

    def native_rule_indices(self, field):
        return [index for row_field, index in self.app.review_rows if row_field == field]

    def test_visual_rule_order_native_compact_layout_stable_ties_and_crud_indices(self):
        self.app.geometry("880x660")
        self.app.tabs.set("Jogos / Apps")
        self.assertEqual(self.app.rule_order.get(), "Cadastro")
        self.assertEqual(self.app.rule_order_picker.master.grid_info()["row"], 3)
        self.assertEqual(self.app.rule_order_picker.master.grid_info()["column"], 1)
        for value in ("z.exe", "a.exe", "A.exe", "b.exe"):
            self.session.draft.add_rule("block_exes", value)
        self.app.render()
        original = self.path.read_bytes()
        self.assertEqual(self.native_rule_indices("block_exes"), [0, 1, 2, 3])
        self.app.change_rule_order("Nome A–Z")
        self.assertEqual(self.native_rule_indices("block_exes"), [1, 2, 3, 0])
        self.app.change_rule_order("Nome Z–A")
        self.assertEqual(self.native_rule_indices("block_exes"), [0, 3, 1, 2])
        self.app.rule_search.set(" A.EXE ")
        self.assertEqual(self.native_rule_indices("block_exes"), [1, 2])
        row = self.app.review_rows[("block_exes", 2)]
        self.button(row, "Editar").invoke()
        self.app.modal.withdraw()
        self.assertEqual(self.entries()[0].get(), "A.exe")
        self.assertEqual(self.app.rule_order_picker.cget("state"), "disabled")
        self.entries()[0].delete(0, "end")
        self.entries()[0].insert(0, "changed.exe")
        self.button(self.app.modal, "Aplicar alteração").invoke()
        self.assertEqual(self.session.draft.config.block_exes, ("z.exe", "a.exe", "changed.exe", "b.exe"))
        self.app.rule_search.set("")
        self.messages.askyesno.return_value = True
        self.button(self.app.review_rows[("block_exes", 3)], "Remover").invoke()
        self.assertEqual(self.session.draft.config.block_exes, ("z.exe", "a.exe", "changed.exe"))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.background_errors, [])

    def test_visual_rule_order_native_all_categories_query_pairs_and_preserved_data(self):
        for field in ("block_exes", "safelist_exes", "block_folders"):
            values = (r"C:\Zed", r"C:\alpha", r"C:\ALPHA") if field == "block_folders" else ("z.exe", "a.exe", "A.exe")
            for value in values:
                self.session.draft.add_rule(field, value)
        for name, contains in (("z.exe", "a"), ("a.exe", "Z"), ("a.exe", "a"), ("A.exe", "A")):
            self.session.draft.add_rule("block_cmdline", {"executable": name, "contains": contains})
        self.app.render()
        draft, snapshot, config = self.session.draft, self.session.snapshot, self.session.draft.config
        original = self.path.read_bytes()
        generation = self.app.review_generation
        self.app.change_rule_order("Nome A–Z")
        for category, field in (("Executáveis", "block_exes"), ("Pastas", "block_folders"),
                                ("Proteção adicional", "safelist_exes")):
            self.app.rule_category.set(category)
            self.app.render_rules()
            self.assertEqual(self.native_rule_indices(field), [1, 2, 0])
        self.app.rule_category.set("Linha de comando")
        self.app.render_rules()
        self.assertEqual(self.native_rule_indices("block_cmdline"), [2, 3, 1, 0])
        self.app.change_rule_order("Nome Z–A")
        self.assertEqual(self.native_rule_indices("block_cmdline"), [0, 1, 2, 3])
        self.app.rule_search.set("z")
        self.assertEqual(self.native_rule_indices("block_cmdline"), [0, 1])
        self.assertIs(self.session.draft, draft)
        self.assertIs(self.session.snapshot, snapshot)
        self.assertEqual(draft.config, config)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.app.review_generation, generation)
        self.assertTrue(draft.can_undo)
        self.assertFalse(draft.can_redo)
        self.assertEqual(self.controller.starts, 0)
        self.assertEqual(self.background_errors, [])

    def test_visual_rule_order_native_navigation_scroll_owned_cancel_and_picker_guard(self):
        for index in range(20):
            self.session.draft.add_rule("block_exes", f"a-{index:02}.exe")
        self.session.draft.add_rule("block_exes", "Code.exe")
        self.app.render()
        link = next(iter(self.app.review_choices.values()))
        self.app.choose_review(link.label, self.app.review_generation)
        token = self.app.review_selected
        self.app.navigate_review_choice(token)
        old_row = self.app.highlighted_row
        timer = old_row.review_scroll_timer
        self.app.change_rule_order("Nome A–Z")
        self.assertIsNone(self.app.highlighted_row)
        self.assertNotIn(timer, self.app.tk.splitlist(self.app.tk.call("after", "info")))
        self.app.rule_search.set("a-00")
        self.assertTrue(self.app.navigate_review_choice(token))
        self.assertEqual(self.app.rule_search.get(), "")
        self.assertEqual(self.app.rule_order.get(), "Nome A–Z")
        self.assertIs(self.app.highlighted_row, self.app.review_rows[("block_exes", 20)])
        self.app.after(100, self.app.quit)
        self.app.mainloop()
        self.assertGreater(self.app.rules_list._parent_canvas.yview()[0], 0)

        def picker(**kwargs):
            self.assertEqual(self.app.rule_order_picker.cget("state"), "disabled")
            self.assertFalse(self.app.change_rule_order("Nome Z–A"))
            self.assertEqual(self.app.rule_order.get(), "Nome A–Z")
            return ()

        self.filedialog.askopenfilenames.side_effect = picker
        self.app.select_executables()
        self.assertEqual(self.app.rule_order_picker.cget("state"), "normal")
        self.app.navigate_review_choice(token)
        self.messages.askyesnocancel.return_value = False
        self.app.close_editor()
        self.assertTrue(self.app.closed)
        self.assertFalse(self.app.change_rule_order("Nome Z–A"))
        self.assertEqual(self.app.tk.splitlist(self.app.tk.call("after", "info")), ())
        self.app.tk.call("update")
        self.assertEqual(self.background_errors, [])

    def test_review_navigation_native_duplicates_all_categories_clear_filter_and_preserve_data(self):
        self.app.geometry("880x660")
        for _ in range(2):
            self.session.draft.add_window("09:00", "10:00", [0])
            self.session.draft.add_rule("block_exes", "same.exe")
            self.session.draft.add_rule("block_folders", r"C:\Games")
            self.session.draft.add_rule("safelist_exes", "keep.exe")
            self.session.draft.add_rule("block_cmdline", {"executable": "javaw.exe", "contains": " profile "})
        self.app.render()
        draft, snapshot, config = self.session.draft, self.session.snapshot, self.session.draft.config
        original = self.path.read_bytes()
        for field in ("windows", "block_exes", "block_folders", "safelist_exes", "block_cmdline"):
            with self.subTest(field=field):
                if field != "windows":
                    self.app.rule_search.set("no results")
                    with patch.object(self.app, "render_rules", wraps=self.app.render_rules) as rendered:
                        self.assertTrue(self.app.navigate_review(field, 1))
                        rendered.assert_called_once_with()
                else:
                    self.assertTrue(self.app.navigate_review(field, 1))
                row = self.app.review_rows[(field, 1)]
                self.assertIs(self.app.highlighted_row, row)
                self.assertIsNot(row, self.app.review_rows[(field, 0)])
                self.assertEqual(row.cget("border_width"), 2)
                self.assertIn("item 2", row.review_detail_label.cget("text"))
                if field != "windows":
                    self.assertEqual(self.app.rule_search.get(), "")
                    self.assertEqual(self.app.tabs.get(), "Jogos / Apps")
        self.assertIs(self.session.draft, draft)
        self.assertIs(self.session.snapshot, snapshot)
        self.assertEqual(draft.config, config)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertTrue(draft.can_undo)
        self.assertFalse(draft.can_redo)
        self.assertEqual(self.controller.starts, 0)
        self.assertIsNone(self.app.modal)
        self.assertEqual(self.background_errors, [])

    def test_review_navigation_native_explicit_selection_and_real_canvas_scroll_to_original_row(self):
        self.app.geometry("880x660")
        for index in range(24):
            self.session.draft.add_rule("block_exes", f"game-{index}.exe")
        self.session.draft.add_rule("block_exes", "Code.exe")
        self.app.render()
        link = next(link for link in self.app.review_choices.values() if link.index == 24)
        self.assertIn(f"{link.ordinal + 1}. ", self.app.review_detail.get("1.0", "end"))
        self.assertTrue(self.app.choose_review(link.label, self.app.review_generation))
        self.assertEqual(self.app.tabs.get(), "Visão geral")
        self.assertIsNone(self.app.highlighted_row)
        self.button(self.app, "Ir para item").invoke()
        row = self.app.review_rows[("block_exes", 24)]
        self.app.after(100, self.app.quit)
        self.app.mainloop()
        canvas = self.app.rules_list._parent_canvas
        self.assertIs(self.app.highlighted_row, row)
        self.assertGreater(canvas.yview()[0], 0)
        self.assertIn("item 25", row.review_detail_label.cget("text"))
        self.messages.askyesno.return_value = True
        self.button(row, "Editar").invoke()
        self.app.modal.withdraw()
        self.assertEqual(self.entries()[0].get(), "Code.exe")
        self.button(self.app.modal, "Cancelar").invoke()
        self.assertEqual(self.background_errors, [])

    def test_review_navigation_native_stale_same_label_import_and_picker_modal_guards(self):
        source = self.root / "import.json"
        source.write_text(json.dumps({"windows": [], "block_exes": ["old.exe", "old.exe"]}), encoding="utf-8")
        self.filedialog.askopenfilename.return_value = str(source)
        self.messages.askyesno.return_value = True
        self.app.import_config()
        label = next(iter(self.app.review_choices))
        self.app.choose_review(label, self.app.review_generation)
        old_token = self.app.review_selected
        source.write_text(json.dumps({"windows": [], "block_exes": ["new.exe", "new.exe"]}), encoding="utf-8")
        self.app.import_config()
        self.assertIn(label, self.app.review_choices)
        self.assertFalse(self.app.navigate_review_choice(old_token))
        self.app.edit_rule()
        self.app.modal.withdraw()
        self.assertFalse(self.app.navigate_review("block_exes", 1))
        self.assertEqual(self.app.review_go.cget("state"), "disabled")
        self.button(self.app.modal, "Cancelar").invoke()

        def picker(**kwargs):
            self.assertFalse(self.app.navigate_review("block_exes", 1))
            self.assertEqual(self.app.review_picker.cget("state"), "disabled")
            return ()

        self.filedialog.askopenfilenames.side_effect = picker
        self.app.select_executables()
        for index in (True, -1, 2, 0.0, None):
            self.assertFalse(self.app.navigate_review("block_exes", index))
        self.assertIsNone(self.app.highlighted_row)
        self.assertEqual(self.controller.starts, 0)
        self.assertEqual(self.background_errors, [])

    def test_review_navigation_native_owned_scroll_cancelled_on_rerender_and_exit(self):
        self.session.draft.add_rule("block_exes", "Code.exe")
        self.app.render()
        self.assertTrue(self.app.navigate_review("block_exes", 0))
        row = self.app.highlighted_row
        timer = row.review_scroll_timer
        self.app.rule_search.set("no results")
        self.assertIsNone(self.app.highlighted_row)
        self.assertNotIn(timer, self.app.tk.splitlist(self.app.tk.call("after", "info")))
        self.app.rule_search.set("")
        self.app.navigate_review("block_exes", 0)
        self.app.after(100, self.app.quit)
        self.app.mainloop()
        self.assertEqual(self.background_errors, [])
        self.app.navigate_review("block_exes", 0)
        self.messages.askyesnocancel.return_value = False
        self.app.close_editor()
        self.assertTrue(self.app.closed)
        self.assertEqual(self.app.tk.splitlist(self.app.tk.call("after", "info")), ())
        self.app.tk.call("update")
        self.assertEqual(self.background_errors, [])
        self.controller.wait.assert_not_called()
        self.tray.wait.assert_not_called()

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

    def test_history_buttons_and_text_focus_with_real_widgets(self):
        self.app.geometry("880x660")
        original = self.path.read_bytes()
        self.session.draft.add_rule("block_exes", "game.exe")
        self.app.render()
        self.assertEqual(self.app.undo_button.cget("state"), "normal")
        entry = next(child for child in self.descendants(self.app) if child.winfo_class() == "Entry")
        self.assertIsNone(self.app.history_shortcut(SimpleNamespace(widget=entry), redo=False))
        self.assertEqual(self.session.draft.config.block_exes, ("game.exe",))
        self.button(self.app, "Desfazer").invoke()
        self.assertFalse(self.session.dirty)
        self.assertIn("Nenhuma regra de bloqueio", self.app.review_detail.get("1.0", "end"))
        self.button(self.app, "Refazer").invoke()
        self.assertTrue(self.session.dirty)
        self.assertEqual(self.path.read_bytes(), original)
        self.button(self.app, "Salvar").invoke()
        saved = self.path.read_bytes()
        self.button(self.app, "Desfazer").invoke()
        self.assertTrue(self.session.dirty)
        self.assertEqual(self.path.read_bytes(), saved)
        self.assertEqual(self.controller.starts, 0)

    def test_changes_modal_readonly_resizable_and_history_preview_in_880_window(self):
        self.app.geometry("880x660")
        self.app.tabs.set("Configuração")
        self.session.draft.add_rule("block_exes", "game.exe")
        self.session.draft.add_rule("block_cmdline", {"executable": "javaw.exe", "contains": " value  line "})
        self.app.render()
        original = self.path.read_bytes()
        snapshot = self.session.snapshot
        draft = self.session.draft
        changes = self.button(self.app, "Ver alterações")
        self.assertIsInstance(changes.master, self.ctk.CTkScrollableFrame)
        self.assertEqual(changes.grid_info()["row"], 2)
        changes.invoke()
        dialog = self.app.modal
        dialog.withdraw()
        self.app.update_idletasks()
        self.assertEqual(dialog.resizable(), (1, 1))
        minimum = dialog.tk.call("wm", "minsize", dialog._w)
        self.assertGreaterEqual(minimum[0], 620)
        self.assertGreaterEqual(minimum[1], 420)
        self.assertEqual(dialog.diff_text.cget("state"), "disabled")
        self.assertEqual(dialog.diff_text.cget("wrap"), "none")
        self.assertEqual(self.entries(), [])
        text = dialog.diff_text.get("1.0", "end")
        self.assertIn("game.exe", text)
        self.assertIn("' value  line '", text)
        self.assertEqual(self.app.undo_button.cget("state"), "disabled")
        self.assertFalse(self.app.undo_draft())
        self.assertEqual(dialog.diff_text.get("1.0", "end"), text)
        self.button(dialog, "Fechar").invoke()
        self.assertIsNone(self.app.modal)
        self.assertIs(self.session.snapshot, snapshot)
        self.assertIs(self.session.draft, draft)
        self.assertEqual(self.path.read_bytes(), original)
        self.app.undo_draft()
        self.app.show_changes()
        self.app.modal.withdraw()
        self.assertNotIn("javaw.exe", self.app.modal.diff_text.get("1.0", "end"))
        self.button(self.app.modal, "Fechar").invoke()
        self.button(self.app, "Salvar").invoke()
        self.app.show_changes()
        self.app.modal.withdraw()
        self.assertEqual(self.app.modal.title(), "Sem alterações")
        self.button(self.app.modal, "Fechar").invoke()
        self.assertEqual(self.controller.starts, 0)
        self.assertEqual(self.background_errors, [])

    def test_first_setup_changes_empty_modal_and_private_extras_stay_unsaved(self):
        self.app.geometry("880x660")
        self.app.show_changes()
        self.app.modal.withdraw()
        self.assertEqual(self.app.modal.title(), "Nova configuração")
        self.assertIn("0", self.app.modal.diff_text.get("1.0", "end"))
        self.assertIn("criad", self.app.modal.diff_text.get("1.0", "end"))
        self.button(self.app.modal, "Fechar").invoke()
        source = self.root / "import.json"
        source.write_text(json.dumps({"windows": [], "PRIVATE_KEY": "SECRET_DO_NOT_SHOW"}), encoding="utf-8")
        self.filedialog.askopenfilename.return_value = str(source)
        self.messages.askyesno.return_value = True
        self.app.import_config()
        self.app.show_changes()
        self.app.modal.withdraw()
        text = self.app.modal.diff_text.get("1.0", "end")
        self.assertNotIn("PRIVATE_KEY", text)
        self.assertNotIn("SECRET_DO_NOT_SHOW", text)
        self.button(self.app.modal, "Fechar").invoke()
        self.assertTrue(self.session.is_new)
        self.assertTrue(self.session.dirty)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.controller.starts, 0)

    def test_changes_modal_picker_guard_conflict_and_owned_timers_preserve_root_poll(self):
        self.session.draft.add_rule("block_exes", "draft.exe")
        self.path.write_text('{"windows":[],"block_exes":["external.exe"]}', encoding="utf-8")
        external = self.path.read_bytes()

        def picker(**kwargs):
            self.app.show_changes()
            self.assertIsNone(self.app.modal)
            return ()

        self.filedialog.askopenfilenames.side_effect = picker
        self.app.select_executables()
        self.app.show_changes()
        dialog = self.app.modal
        dialog.withdraw()
        self.assertNotIn("external.exe", dialog.diff_text.get("1.0", "end"))
        orphaned = Mock()
        dialog.diff_text.after(30, orphaned)
        self.button(dialog, "Fechar").invoke()
        root_callback = Mock()
        self.app.after(30, root_callback)
        self.app.after(150, self.app.quit)
        self.app.mainloop()
        root_callback.assert_called_once_with()
        orphaned.assert_not_called()
        self.assertIsNotNone(self.app.status_timer)
        self.assertFalse(self.app.save_config())
        self.assertEqual(self.path.read_bytes(), external)
        self.assertTrue(self.session.dirty)
        self.assertEqual(self.background_errors, [])

    def test_changes_modal_close_cancel_discard_teardown_and_explicit_limits(self):
        for index in range(105):
            self.session.draft.add_rule("block_exes", f"game-{index}.exe")
        self.session.draft.update_rule("block_exes", 0, "x" * 1200 + ".exe")
        self.app.show_changes()
        dialog = self.app.modal
        dialog.withdraw()
        text = dialog.diff_text.get("1.0", "end")
        self.assertIn("Mais 5", text)
        self.assertIn("truncad", text)
        self.messages.askyesnocancel.return_value = None
        self.app.close_editor()
        self.assertIs(self.app.modal, dialog)
        self.assertFalse(self.app.closing)
        self.app.modal.withdraw()
        self.messages.askyesnocancel.return_value = False
        self.app.close_editor()
        self.assertTrue(self.app.closed)
        self.assertEqual(self.app.tk.splitlist(self.app.tk.call("after", "info")), ())
        self.app.tk.call("update")
        self.assertEqual(self.background_errors, [])
        self.controller.wait.assert_not_called()
        self.tray.wait.assert_not_called()

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

    def test_folder_picker_cancel_error_and_late_modal_return_with_real_widgets(self):
        import tkinter as tk

        self.app.rule_category.set("Pastas")
        self.app.edit_rule()
        dialog = self.app.modal
        dialog.withdraw()
        entry = self.entries()[0]
        entry.insert(0, r"C:\Keep")
        choose = self.button(dialog, "Escolher pasta…")
        original = self.session.draft.config
        choose.invoke()
        self.assertEqual(entry.get(), r"C:\Keep")
        self.filedialog.askdirectory.side_effect = tk.TclError("dialog indisponível")
        choose.invoke()
        self.assertEqual(entry.get(), r"C:\Keep")
        self.assertTrue(any("Não foi possível abrir o seletor de pasta" in widget.cget("text")
                            for widget in self.descendants(dialog) if isinstance(widget, self.ctk.CTkLabel)))

        def replace_modal(**kwargs):
            self.button(dialog, "Cancelar").invoke()
            self.app.edit_rule()
            self.app.modal.withdraw()
            return r"C:\Late"

        self.filedialog.askdirectory.side_effect = replace_modal
        choose.invoke()
        self.assertIsNot(self.app.modal, dialog)
        self.assertEqual(self.entries()[0].get(), "")
        self.assertFalse(self.app.picker_active)
        self.assertEqual(self.session.draft.config, original)
        self.assertEqual(self.background_errors, [])

    def test_folder_picker_late_return_after_close_has_no_tcl_error(self):
        self.app.rule_category.set("Pastas")
        self.app.edit_rule()
        self.app.modal.withdraw()
        choose = self.button(self.app.modal, "Escolher pasta…")

        def close_during_picker(**kwargs):
            self.assertTrue(self.app.picker_active)
            self.app.close_editor()
            return r"C:\Late"

        self.filedialog.askdirectory.side_effect = close_during_picker
        choose.invoke()
        self.assertTrue(self.app.closed)
        self.assertFalse(self.app.picker_active)
        self.assertEqual(self.session.draft.config.block_folders, ())
        self.assertEqual(self.background_errors, [])

    def test_import_bool_to_int_extra_prompts_on_close_and_saves_integer_with_real_widgets(self):
        original = self.path.read_bytes()
        source = self.root / "import.json"
        source.write_text(json.dumps({"windows": [], "future": {"keep": 1}}), encoding="utf-8")
        self.filedialog.askopenfilename.return_value = str(source)
        self.messages.askyesno.return_value = True
        self.button(self.app, "Importar JSON").invoke()
        self.assertTrue(self.session.dirty)
        self.assertIs(type(self.session.draft.config.extra["future"]["keep"]), int)
        self.assertIn("Alterações não salvas", self.app.dirty_label.cget("text"))
        self.messages.askyesnocancel.return_value = None
        self.app.close_editor()
        self.messages.askyesnocancel.assert_called_once()
        self.assertFalse(self.app.closed)
        self.assertEqual(self.path.read_bytes(), original)
        self.button(self.app, "Salvar").invoke()
        self.assertFalse(self.session.dirty)
        self.assertIs(type(load_config(self.path).extra["future"]["keep"]), int)
        self.assertEqual(self.controller.starts, 0)
        self.assertEqual(self.background_errors, [])

    def test_pending_tray_ready_during_file_pickers_keeps_native_root_visible_intent(self):
        self.app.geometry("880x660")
        original = self.path.read_bytes()
        for kind in ("exe", "import", "export", "folder"):
            with self.subTest(kind=kind):
                self.app.tray_ready = False
                self.tray.alive = False
                self.app.send_to_tray()
                self.assertTrue(self.app.tray_pending)

                def nested_picker(**kwargs):
                    self.assertTrue(self.app.picker_active)
                    self.mailbox.post("ready")
                    self.app.refresh_status(schedule=False)
                    self.app.send_to_tray()
                    self.assertFalse(self.app.tray_hidden)
                    self.assertFalse(self.app.tray_pending)
                    self.assertTrue(self.app.restore_requested)
                    self.assertIn("Termine a seleção", self.app.feedback.cget("text"))
                    self.assertEqual(self.app.start_button.cget("state"), "disabled")
                    self.assertEqual(self.app.undo_button.cget("state"), "disabled")
                    return () if kind == "exe" else ""

                if kind == "exe":
                    self.filedialog.askopenfilenames.side_effect = nested_picker
                    self.app.select_executables()
                elif kind == "import":
                    self.filedialog.askopenfilename.side_effect = nested_picker
                    self.app.import_config()
                elif kind == "export":
                    self.filedialog.asksaveasfilename.side_effect = nested_picker
                    self.app.export_config()
                else:
                    self.app.rule_category.set("Pastas")
                    self.app.edit_rule()
                    self.app.modal.withdraw()
                    self.filedialog.askdirectory.side_effect = nested_picker
                    self.button(self.app.modal, "Escolher pasta…").invoke()
                    self.button(self.app.modal, "Cancelar").invoke()
                self.assertFalse(self.app.picker_active)
                self.mailbox.post("ready")
                self.app.refresh_status(schedule=False)
                self.assertFalse(self.app.tray_hidden)
                self.assertEqual(self.path.read_bytes(), original)
                self.assertEqual(self.controller.starts, 0)
        self.assertEqual(self.background_errors, [])

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

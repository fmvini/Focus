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
from core.process_controller import RuntimeSnapshot
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

    def set_rule_query(self, value):
        """Conclui a busca quando o fluxo legado exige a lista atualizada."""
        self.app.rule_search.set(value)
        self.app.flush_rule_search()

    def native_pagination_fixture(self, *, duplicates=False):
        values = [f"game-{index:03}.exe" for index in range(60)]
        if duplicates:
            values[31] = values[56] = values[2]
        self.path.write_text(json.dumps({"windows": [],
            "block_exes": values,
            "typed": [True, 1, 1.0, "ação"]}), encoding="utf-8")
        self.session.reload()
        self.app.render()
        self.app.geometry("880x660")
        self.app.tabs.set("Jogos / Apps")

    def test_rule_search_debounce_native_trailing_timer_old_callbacks_and_full_selection_reset(self):
        self.native_pagination_fixture()
        self.session.draft.add_rule("safelist_exes", "redo.exe")
        self.session.draft.undo()
        self.app.render()
        self.set_rule_query("game-")
        self.app.begin_rule_selection()
        self.app.selection_select_all(self.app.rule_selection_context)
        row, variable, checkbox = self.app.rule_selection_boxes[2]
        old_commands = [checkbox.cget("command"), self.button(row, "Editar").cget("command"),
                        self.button(row, "Remover").cget("command"), self.app.rule_page_next.cget("command")]
        draft, snapshot, config = self.session.draft, self.session.snapshot, self.session.draft.config
        original = self.path.read_bytes()
        with patch.object(self.app, "after", wraps=self.app.after) as scheduled, \
                patch.object(self.app, "render_rule_projection", wraps=self.app.render_rule_projection) as projected:
            self.app.rule_search.set("game-")
            old_timer, old_complete = self.app.rule_search_timer, scheduled.call_args.args[1]
            self.app.rule_search.set("missing")
            self.app.rule_search.set("game-")
            current_timer = self.app.rule_search_timer
            self.assertEqual(sum(call.args[0] == 200 for call in scheduled.call_args_list), 3)
            self.assertNotIn(old_timer, self.app.tk.splitlist(self.app.tk.call("after", "info")))
            self.assertIn(current_timer, self.app.tk.splitlist(self.app.tk.call("after", "info")))
            self.assertIsNone(self.app.rule_view_context)
            self.assertEqual(self.app.rule_selection_indices, set())
            self.assertEqual(self.button(row, "Editar").cget("state"), "disabled")
            self.assertEqual(checkbox.cget("state"), "disabled")
            self.assertIn("Atualizando busca", self.app.rule_selection_count.cget("text"))
            self.assertEqual(self.app.rule_page_next.cget("state"), "disabled")
            with patch.object(variable, "get", side_effect=AssertionError("old native variable")):
                for command in old_commands:
                    self.assertFalse(command())
            old_complete()
            self.assertEqual(self.app.rule_search_timer, current_timer)
            projected.assert_not_called()
            self.app.after(350, self.app.quit)
            self.app.mainloop()
            projected.assert_called_once_with(0)
        self.assertFalse(self.app.rule_search_pending)
        self.assertIsNone(self.app.rule_search_timer)
        self.assertEqual(self.app.rule_page_result.total, 60)
        self.assertEqual(len(self.app.rule_selection_boxes), 25)
        self.assertTrue(all(box.cget("state") == "normal" for _, _, box in self.app.rule_selection_boxes.values()))
        self.assertIs(self.session.snapshot, snapshot)
        self.assertEqual(draft.config, config)
        self.assertFalse(self.session.dirty)
        self.assertFalse(draft.can_undo)
        self.assertTrue(draft.can_redo)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual((self.controller.starts, self.controller.stops), (0, 0))
        self.assertEqual(self.background_errors, [])

    def test_rule_search_debounce_native_review_modal_picker_exit_cancel_and_teardown(self):
        import tkinter as tk
        self.native_pagination_fixture()
        self.app.change_rule_order("Nome Z–A")
        original = self.path.read_bytes()
        for query, expected in (("game-", "game-"), ("game-059", "")):
            with self.subTest(query=query), patch.object(self.app, "render_rule_projection", wraps=self.app.render_rule_projection) as projected:
                self.app.rule_search.set(query)
                self.assertTrue(self.app.navigate_review("block_exes", 2))
                projected.assert_called_once_with(2)
                self.assertEqual(self.app.rule_search.get(), expected)
                self.assertIs(self.app.highlighted_row, self.app.review_rows[("block_exes", 2)])
        self.app.edit_rule()
        self.app.modal.withdraw()
        self.entries()[0].insert(0, "game-added.exe")
        with patch.object(self.app, "render_rule_projection", wraps=self.app.render_rule_projection) as projected:
            self.app.rule_search.set("game-")
            self.assertIsNone(self.app.rule_search_timer)
            projected.assert_not_called()
            self.button(self.app.modal, "Adicionar").invoke()
            projected.assert_called_once_with(0)
        self.assertTrue(self.app.undo_draft())
        self.assertFalse(self.session.dirty)
        self.app.edit_rule()
        self.app.modal.withdraw()
        with patch.object(self.app, "render_rule_projection", wraps=self.app.render_rule_projection) as projected:
            self.app.rule_search.set("game-00")
            self.button(self.app.modal, "Cancelar").invoke()
            projected.assert_called_once_with(0)
        def failed_picker(**options):
            self.app.rule_search.set("game-")
            self.assertIsNone(self.app.rule_search_timer)
            raise tk.TclError("picker failed")
        with patch.object(self.app, "render_rule_projection", wraps=self.app.render_rule_projection) as projected:
            with self.assertRaisesRegex(tk.TclError, "picker failed"):
                self.app.open_picker(failed_picker)
            projected.assert_called_once_with(0)
        self.session.draft.add_rule("safelist_exes", "unsaved.exe")
        self.app.render()
        self.messages.askyesnocancel.return_value = None
        with patch.object(self.app, "after", wraps=self.app.after) as scheduled, \
                patch.object(self.app, "render_rule_projection", wraps=self.app.render_rule_projection) as projected:
            self.app.rule_search.set("game-")
            old_complete = scheduled.call_args.args[1]
            self.app.close_editor()
            projected.assert_called_once_with(0)
            old_complete()
            self.assertEqual(projected.call_count, 1)
        self.assertFalse(self.app.closing)
        self.assertFalse(self.app.closed)
        self.assertFalse(self.app.rule_search_pending)
        self.assertEqual(self.app.rule_search.get(), "game-")
        self.assertEqual((self.controller.starts, self.controller.stops), (0, 0))
        self.messages.askyesnocancel.return_value = False
        with patch.object(self.app, "after", wraps=self.app.after) as scheduled:
            self.app.rule_search.set("game-00")
            old_complete = scheduled.call_args.args[1]
        self.app.close_editor()
        self.assertTrue(self.app.closed)
        self.assertIsNone(self.app.rule_search_timer)
        with patch.object(self.app.rule_search, "get", side_effect=AssertionError("Tk after destroy")):
            old_complete()
            self.assertFalse(self.app.flush_rule_search())
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.app.tk.splitlist(self.app.tk.call("after", "info")), ())
        self.app.tk.call("update")
        self.assertEqual(self.background_errors, [])
        self.controller.wait.assert_not_called()
        self.tray.wait.assert_not_called()

    def test_rule_pagination_native_layout_crosspage_old_callbacks_and_one_undo(self):
        self.native_pagination_fixture(duplicates=True)
        draft, snapshot, config = self.session.draft, self.session.snapshot, self.session.draft.config
        original = self.path.read_bytes()
        self.assertEqual(len(self.native_rule_indices("block_exes")), 25)
        self.assertEqual(self.app.rules_list._parent_frame.grid_info()["row"], 4)
        self.assertEqual(self.app.rule_pager.grid_info()["row"], 5)
        self.assertEqual(self.app.rule_page_previous.cget("state"), "disabled")
        self.app.begin_rule_selection()
        self.assertEqual(self.app.rules_list._parent_frame.grid_info()["row"], 5)
        self.assertEqual(self.app.rule_pager.grid_info()["row"], 6)
        self.assertEqual(self.app.rule_area.grid_rowconfigure(5)["weight"], 1)
        context, generation = self.app.rule_selection_context, self.app.rule_selection_generation
        old_row, old_var, old_box = self.app.rule_selection_boxes[2]
        old_commands = [old_box.cget("command"), self.button(old_row, "Editar").cget("command"),
                        self.button(old_row, "Remover").cget("command"), self.app.rule_page_next.cget("command")]
        for page, index in ((0, 2), (1, 31), (2, 56)):
            if page:
                self.assertTrue(self.app.change_rule_page(page))
            self.app.rule_selection_boxes[index][2].toggle()
            self.assertIs(self.app.rule_selection_context, context)
            self.assertEqual(self.app.rule_selection_generation, generation)
        self.assertEqual(self.app.rule_selection_indices, {2, 31, 56})
        self.assertEqual(len(self.app.rule_selection_boxes), 10)
        self.assertIn("Página 3 de 3 · itens 51–60 de 60", self.app.rule_page_label.cget("text"))
        self.assertTrue(self.app.change_rule_page(0))
        self.assertEqual(self.app.rule_selection_boxes[2][1].get(), 1)
        with patch.object(old_var, "get", side_effect=AssertionError("old native Tk")):
            for command in old_commands:
                self.assertFalse(command())
        self.messages.askyesno.assert_not_called()
        self.messages.askyesno.return_value = True
        with patch.object(draft, "remove_rules", wraps=draft.remove_rules) as remove:
            self.assertTrue(self.app.selection_remove(context))
            remove.assert_called_once_with("block_exes", (2, 31, 56))
        self.assertIs(self.session.snapshot, snapshot)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertTrue(self.app.undo_draft())
        self.assertEqual(draft.config, config)
        self.assertFalse(draft.can_undo)
        self.assertTrue(draft.can_redo)
        self.set_rule_query("missing")
        self.assertFalse(self.app.rule_pager.grid_info())
        self.assertEqual(self.app.rule_page_result.total, 0)
        self.app.update()
        self.assertEqual(self.background_errors, [])
        self.assertEqual((self.controller.starts, self.controller.stops), (0, 0))

    def test_rule_pagination_native_review_sorted_target_preserves_selection_and_owned_scroll(self):
        self.native_pagination_fixture()
        self.app.change_rule_order("Nome Z–A")
        self.app.begin_rule_selection()
        context, config, original = self.app.rule_selection_context, self.session.draft.config, self.path.read_bytes()
        self.app.selection_select_all(context)
        with patch.object(self.app, "render_rule_projection", wraps=self.app.render_rule_projection) as projected:
            self.assertTrue(self.app.navigate_review("block_exes", 2))
            projected.assert_called_once_with(2)
        self.assertEqual(self.app.rule_page_result.page, 2)
        self.assertIs(self.app.rule_selection_context, context)
        self.assertEqual(self.app.rule_selection_indices, set(range(60)))
        self.assertTrue(all(var.get() == 1 for _, var, _ in self.app.rule_selection_boxes.values()))
        row, timer = self.app.highlighted_row, self.app.highlighted_row.review_scroll_timer
        self.assertTrue(self.app.change_rule_page(0))
        self.assertNotIn(timer, self.app.tk.splitlist(self.app.tk.call("after", "info")))
        self.assertIsNone(self.app.highlighted_row)
        self.set_rule_query("game-059")
        with patch.object(self.app, "render_rule_projection", wraps=self.app.render_rule_projection) as projected:
            self.assertTrue(self.app.navigate_review("block_exes", 2))
            projected.assert_called_once_with(2)
        self.assertEqual(self.app.rule_selection_indices, set())
        self.assertEqual(self.app.rule_search.get(), "")
        self.assertEqual(self.app.visual_rule_order, "name_desc")
        row = self.app.highlighted_row
        self.assertIs(row, self.app.review_rows[("block_exes", 2)])
        self.assertEqual(row.cget("border_width"), 2)
        self.app.after(100, self.app.quit)
        self.app.mainloop()
        self.assertIsNone(row.review_scroll_timer)
        self.assertEqual(self.session.draft.config, config)
        self.assertFalse(self.session.dirty)
        self.assertFalse(self.session.draft.can_undo)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.background_errors, [])

    def test_rule_pagination_native_review_included_filter_keeps_selection_owner_and_redo(self):
        self.native_pagination_fixture()
        self.session.draft.add_rule("safelist_exes", "redo.exe")
        self.session.draft.undo()
        self.app.render()
        self.set_rule_query("game-")
        self.app.change_rule_order("Nome Z–A")
        self.app.begin_rule_selection()
        context, generation = self.app.rule_selection_context, self.app.rule_selection_generation
        self.app.selection_select_all(context)
        draft, snapshot, config = self.session.draft, self.session.snapshot, self.session.draft.config
        original = self.path.read_bytes()
        with patch.object(self.app, "render_rules", side_effect=AssertionError("unneeded logical reset")), \
                patch.object(self.app, "render_rule_projection", wraps=self.app.render_rule_projection) as projected, \
                patch.object(Path, "read_bytes", side_effect=AssertionError("navigation IO")):
            self.assertTrue(self.app.navigate_review("block_exes", 2))
            projected.assert_called_once_with(2)
        self.assertEqual(self.app.rule_search.get(), "game-")
        self.assertEqual(self.app.visual_rule_order, "name_desc")
        self.assertEqual(self.app.rule_page_result.page, 2)
        self.assertIs(self.app.rule_selection_context, context)
        self.assertIs(self.app.rule_view_context, context)
        self.assertEqual(self.app.rule_selection_generation, generation)
        self.assertEqual(self.app.rule_selection_indices, set(range(60)))
        self.assertEqual(len(self.app.rule_selection_boxes), 10)
        self.assertTrue(all(variable.get() for _, variable, _ in self.app.rule_selection_boxes.values()))
        self.assertIs(self.app.highlighted_row, self.app.review_rows[("block_exes", 2)])
        self.app.after(100, self.app.quit)
        self.app.mainloop()
        self.assertIs(self.session.draft, draft)
        self.assertIs(self.session.snapshot, snapshot)
        self.assertEqual(draft.config, config)
        self.assertFalse(self.session.dirty)
        self.assertFalse(draft.can_undo)
        self.assertTrue(draft.can_redo)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual((self.controller.starts, self.controller.stops), (0, 0))
        self.assertEqual(self.background_errors, [])

    def watch_idle_configures(self):
        widgets = [self.app, *self.descendants(self.app)]
        for widget in widgets:
            widget.configure = Mock(wraps=widget.configure)
        return widgets

    def assert_idle_polls(self, widgets):
        for widget in widgets:
            widget.configure.reset_mock()
        for _ in range(3):
            self.app.refresh_status(schedule=False)
        for widget in widgets:
            widget.configure.assert_not_called()

    def test_idle_updates_native_stable_idle_active_toolbar_and_picker_state_changes(self):
        self.app.refresh_status(schedule=False)
        for name in ("one.exe", "two.exe"):
            self.session.draft.add_rule("block_exes", name)
        self.app.render()
        self.app.begin_rule_selection()
        original, snapshot, config = self.path.read_bytes(), self.session.snapshot, self.session.draft.config
        generation, context = self.app.rule_selection_generation, self.app.rule_selection_context
        widgets = self.watch_idle_configures()
        self.assert_idle_polls(widgets)
        self.app.selection_select_all(context)
        self.assertIn("2 selecionadas / 2 resultados", self.app.rule_selection_count.cget("text"))
        self.assertEqual(self.app.rule_selection_actions["remove"].cget("state"), "normal")
        self.assert_idle_polls(widgets)
        self.app.picker_active = True
        self.app.refresh_status(schedule=False)
        self.assertEqual(self.app.rule_order_picker.cget("state"), "disabled")
        self.assertTrue(all(control.cget("state") == "disabled" for control in self.app.rule_selection_actions.values()))
        self.assert_idle_polls(widgets)
        self.app.picker_active = False
        self.app.refresh_status(schedule=False)
        self.assertEqual(self.app.rule_order_picker.cget("state"), "normal")
        self.assertEqual(self.app.rule_selection_actions["remove"].cget("state"), "normal")
        self.app.selection_clear(context)
        self.assertIn("0 selecionadas / 2 resultados", self.app.rule_selection_count.cget("text"))
        self.assertEqual(self.app.rule_selection_actions["remove"].cget("state"), "disabled")
        self.assert_idle_polls(widgets)
        self.assertIs(self.app.rule_selection_context, context)
        self.assertEqual(self.app.rule_selection_generation, generation)
        self.assertEqual(self.app.rule_selection_indices, set())
        self.assertEqual(self.session.draft.config, config)
        self.assertIs(self.session.snapshot, snapshot)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.controller.starts, 0)
        self.assertEqual(self.background_errors, [])

    def test_idle_updates_native_runtime_error_modal_and_alive_closing_keep_transitions(self):
        self.session.draft.add_rule("block_exes", "game.exe")
        self.app.render()
        original = self.path.read_bytes()
        self.app.edit_rule()
        self.app.modal.withdraw()
        self.assertEqual(self.app.undo_button.cget("state"), "disabled")
        widgets = self.watch_idle_configures()
        self.assert_idle_polls(widgets)
        self.button(self.app.modal, "Cancelar").invoke()
        self.assertEqual(self.app.undo_button.cget("state"), "normal")
        for state, alive, title, start, stop in (
            ("running", True, "Motor em execução", "disabled", "normal"),
            ("stopping", True, "Motor parando", "disabled", "disabled"),
            ("error", False, "Motor com erro", "normal", "disabled"),
        ):
            self.controller.value = RuntimeSnapshot(state=state, error="falha" if state == "error" else None)
            self.controller.alive = alive
            self.app.refresh_status(schedule=False)
            self.assertEqual(self.app.runtime_title.cget("text"), title)
            self.assertEqual(self.app.start_button.cget("state"), start)
            self.assertEqual(self.app.stop_button.cget("state"), stop)
            self.assert_idle_polls(widgets)
        self.controller.value, self.controller.alive = RuntimeSnapshot(state="running"), True
        self.app.close_editor()
        self.assertTrue(self.app.closing)
        self.assertFalse(self.app.closed)
        self.assertEqual(self.app.runtime_title.cget("text"), "Motor parando")
        self.assertEqual(self.app.start_button.cget("state"), "disabled")
        self.assertEqual(self.app.stop_button.cget("state"), "disabled")
        for widget in widgets:
            widget.configure.reset_mock()
        for _ in range(3):
            self.app.update_runtime()
        for widget in widgets:
            widget.configure.assert_not_called()
        self.controller.finish()
        self.app.poll_close()
        self.assertTrue(self.app.closed)
        with patch.object(self.app.agenda_label, "cget", side_effect=AssertionError("Tk after close")):
            self.app.refresh_status()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.app.tk.splitlist(self.app.tk.call("after", "info")), ())
        self.app.tk.call("update")
        self.assertEqual(self.background_errors, [])

    def native_day_variables(self):
        return [widget.cget("variable") for widget in self.descendants(self.app.modal)
                if isinstance(widget, self.ctk.CTkCheckBox)]

    def load_native_window_days(self):
        self.path.write_text(json.dumps({"windows": [{"start": "22:00", "end": "02:00", "days": [6, 0]}],
                                        "typed": [True, 1, 1.0]}), encoding="utf-8")
        self.session.reload()
        self.app.render()

    def test_window_days_native_shortcuts_local_cancel_and_new_disabled_apply_in_880_window(self):
        self.app.geometry("880x660")
        original = self.path.read_bytes()
        self.app.edit_window()
        dialog = self.app.modal
        dialog.withdraw()
        variables = self.native_day_variables()
        for title, expected in (("Nenhum", ()), ("Fim de semana", (5, 6)), ("Seg–Sex", tuple(range(5))),
                                ("Todos", tuple(range(7)))):
            self.button(dialog, title).invoke()
            self.assertEqual(tuple(day for day, variable in enumerate(variables) if variable.get()), expected)
            self.assertFalse(self.session.dirty)
            self.assertFalse(self.session.draft.can_undo)
        self.button(dialog, "Cancelar").invoke()
        self.assertEqual(self.path.read_bytes(), original)
        self.app.edit_window()
        self.app.modal.withdraw()
        start, end = self.entries()
        start.insert(0, "09:00")
        end.insert(0, "09:00")
        self.button(self.app.modal, "Nenhum").invoke()
        self.button(self.app.modal, "Adicionar").invoke()
        self.assertIsNotNone(self.app.modal)
        self.assertFalse(self.session.dirty)
        end.delete(0, "end")
        end.insert(0, "10:00")
        self.button(self.app.modal, "Adicionar").invoke()
        self.assertEqual(self.session.draft.config.windows[0].days, ())
        self.assertEqual(self.path.read_bytes(), original)
        self.app.undo_draft()
        self.assertFalse(self.session.dirty)
        self.assertFalse(self.session.draft.can_undo)
        self.assertEqual(self.controller.starts, 0)
        self.assertEqual(self.background_errors, [])

    def test_window_days_native_noncanonical_noop_redo_then_retained_and_added_days(self):
        self.load_native_window_days()
        self.session.draft.add_rule("block_exes", "redo.exe")
        self.app.undo_draft()
        snapshot, original = self.session.snapshot, self.path.read_bytes()
        for toggle in (False, True):
            self.app.edit_window(0)
            dialog = self.app.modal
            dialog.withdraw()
            variables = self.native_day_variables()
            if toggle:
                self.button(dialog, "Todos").invoke()
                self.button(dialog, "Nenhum").invoke()
                variables[6].set(1)
                variables[0].set(1)
            self.button(dialog, "Aplicar alteração").invoke()
            self.assertEqual(self.session.draft.config.windows[0].days, (6, 0))
            self.assertFalse(self.session.dirty)
            self.assertFalse(self.session.draft.can_undo)
            self.assertTrue(self.session.draft.can_redo)
        self.assertIs(self.session.snapshot, snapshot)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual([type(value) for value in self.session.draft.config.extra["typed"]], [bool, int, float])
        self.app.edit_window(0)
        self.app.modal.withdraw()
        self.native_day_variables()[2].set(1)
        self.button(self.app.modal, "Aplicar alteração").invoke()
        self.assertEqual(self.session.draft.config.windows[0].days, (6, 0, 2))
        self.app.undo_draft()
        self.assertEqual(self.session.draft.config.windows[0].days, (6, 0))
        self.assertFalse(self.session.draft.can_undo)
        self.app.redo_draft()
        self.assertEqual(self.session.draft.config.windows[0].days, (6, 0, 2))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.background_errors, [])

    def test_window_days_native_old_apply_and_presets_do_not_touch_replacement_or_closed_tk(self):
        self.load_native_window_days()
        self.app.edit_window(0)
        dialog = self.app.modal
        dialog.withdraw()
        preset = self.button(dialog, "Todos").cget("command")
        apply = self.button(dialog, "Aplicar alteração").cget("command")
        self.button(dialog, "Cancelar").invoke()
        self.app.edit_window()
        replacement = self.app.modal
        replacement.withdraw()
        original = self.session.draft.config
        self.assertFalse(preset())
        self.assertFalse(apply())
        self.assertIs(self.app.modal, replacement)
        self.assertEqual(self.session.draft.config, original)
        active_preset = self.button(replacement, "Nenhum").cget("command")
        active_apply = self.button(replacement, "Adicionar").cget("command")
        self.messages.askyesnocancel.return_value = False
        self.app.close_editor()
        self.assertFalse(active_preset())
        self.assertFalse(active_apply())
        self.assertEqual(self.session.draft.config, original)
        self.assertEqual(self.app.tk.splitlist(self.app.tk.call("after", "info")), ())
        self.app.tk.call("update")
        self.assertEqual(self.background_errors, [])

    def native_rule_indices(self, field):
        return [index for row_field, index in self.app.review_rows if row_field == field]

    def native_action_fixture(self):
        self.load_native_window_days()
        self.session.draft.add_rule("block_exes", "same.exe")
        self.session.draft.add_rule("block_exes", "same.exe")
        self.app.save_config()
        self.session.reload()
        self.app.render()

    def test_editor_action_native_old_apply_and_changed_forms_never_access_destroyed_entries(self):
        self.native_action_fixture()
        original, snapshot = self.path.read_bytes(), self.session.snapshot
        for kind in ("rule", "window"):
            self.app.edit_rule(0, "block_exes") if kind == "rule" else self.app.edit_window(0)
            dialog = self.app.modal
            dialog.withdraw()
            old_apply = self.button(dialog, "Aplicar alteração").cget("command")
            self.button(dialog, "Cancelar").invoke()
            self.app.edit_rule()
            replacement = self.app.modal
            replacement.withdraw()
            self.assertFalse(old_apply())  # real Entry from old form is already destroyed
            self.assertIs(self.app.modal, replacement)
            self.button(replacement, "Cancelar").invoke()
            self.app.edit_rule(0, "block_exes") if kind == "rule" else self.app.edit_window(0)
            dialog = self.app.modal
            dialog.withdraw()
            current_apply = self.button(dialog, "Aplicar alteração").cget("command")
            changed = self.session.draft.config
            changed.extra["typed"][0] = 1 if type(changed.extra["typed"][0]) is bool else True
            self.session.draft.replace_config(changed)
            before = self.session.draft.config
            with patch.object(self.app, "finish_edit", side_effect=AssertionError("stale finish")):
                self.assertFalse(current_apply())
            text = "\n".join(child.cget("text") for child in self.descendants(dialog)
                             if isinstance(child, self.ctk.CTkLabel))
            self.assertIn("rascunho mudou", text)
            self.assertEqual(self.session.draft.config, before)
            self.assertIs(self.app.modal, dialog)
            with patch.object(self.session, "reload", side_effect=AssertionError("IO under form")):
                self.assertFalse(self.app.reload_config())
            self.button(dialog, "Cancelar").invoke()
        self.assertIs(self.session.snapshot, snapshot)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.controller.starts, 0)
        self.assertEqual(self.background_errors, [])

    def test_editor_action_native_row_generations_remove_postprompt_and_closed_callbacks(self):
        self.native_action_fixture()
        commands = [self.button(self.app.review_rows[(field, 0)], title).cget("command")
                    for field, title in (("windows", "Editar"), ("windows", "Remover"),
                                         ("windows", "Duplicar"), ("block_exes", "Editar"),
                                         ("block_exes", "Remover"))]
        self.app.render()  # equal content is still a different row generation
        with patch.object(self.app, "new_dialog", side_effect=AssertionError("stale dialog")), \
                patch.object(self.messages, "askyesno", side_effect=AssertionError("stale prompt")):
            for command in commands:
                self.assertFalse(command())
        original = self.path.read_bytes()
        def changed_prompt(*args, **kwargs):
            self.assertFalse(self.app.remove_item("windows", 0))
            self.assertFalse(self.app.reload_config())
            self.session.draft.update_rule("block_exes", 0, "replacement.exe")
            return True
        self.messages.askyesno.side_effect = changed_prompt
        with patch.object(self.session.draft, "remove_rule", side_effect=AssertionError("wrong target")):
            self.assertFalse(self.button(self.app.review_rows[("block_exes", 0)], "Remover").invoke())
        self.assertFalse(self.app.confirming_rule_removal)
        self.assertEqual(self.session.draft.config.block_exes, ("replacement.exe", "same.exe"))
        self.assertEqual(self.path.read_bytes(), original)
        self.app.render()
        self.messages.askyesno.side_effect = None
        self.messages.askyesno.return_value = True
        self.assertTrue(self.button(self.app.review_rows[("block_exes", 1)], "Remover").invoke())
        self.assertTrue(self.app.undo_draft())
        self.assertEqual(self.session.draft.config.block_exes, ("replacement.exe", "same.exe"))
        commands = [self.button(self.app.review_rows[(field, 0)], title).cget("command")
                    for field, title in (("windows", "Editar"), ("windows", "Remover"),
                                         ("windows", "Duplicar"), ("block_exes", "Editar"),
                                         ("block_exes", "Remover"))]
        self.app.close_editor()
        for command in commands:
            self.assertFalse(command())
        self.assertEqual(self.app.tk.splitlist(self.app.tk.call("after", "info")), ())
        self.app.tk.call("update")
        self.assertEqual(self.background_errors, [])

    def test_editor_action_native_active_selection_row_edit_cancel_remove_one_undo(self):
        self.native_action_fixture()
        config, snapshot, original = self.session.draft.config, self.session.snapshot, self.path.read_bytes()
        self.app.begin_rule_selection()
        self.app.selection_select_all(self.app.rule_selection_context)
        row = self.app.review_rows[("block_exes", 1)]
        self.assertEqual(len(row.action_context), 8)
        self.assertEqual(len(self.app.rule_selection_context), 7)
        self.button(row, "Editar").invoke()
        self.app.modal.withdraw()
        self.assertEqual(self.entries()[0].get(), "same.exe")
        self.button(self.app.modal, "Cancelar").invoke()
        self.assertEqual(self.session.draft.config, config)
        self.messages.askyesno.return_value = True
        self.assertTrue(self.button(row, "Remover").invoke())
        self.assertEqual(self.session.draft.config.block_exes, ("same.exe",))
        self.assertTrue(self.app.undo_draft())
        self.assertEqual(self.session.draft.config, config)
        self.assertFalse(self.session.draft.can_undo)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertIs(self.session.snapshot, snapshot)
        self.assertTrue(self.app.rule_selection_mode)
        self.assertEqual(self.background_errors, [])

    def test_rule_bulk_selection_native_compact_mode_offviewport_all_and_close_view_only(self):
        self.app.geometry("880x660")
        self.app.tabs.set("Jogos / Apps")
        for index in range(30):
            self.session.draft.add_rule("block_exes", f"match-{index:02}.exe")
        self.session.draft.add_rule("block_exes", "hidden.exe")
        self.app.render()
        self.app.change_rule_order("Nome Z–A")
        self.set_rule_query("match")
        draft, snapshot, config = self.session.draft, self.session.snapshot, self.session.draft.config
        original = self.path.read_bytes()
        history = self.session.dirty, draft.can_undo, draft.can_redo
        self.assertEqual(self.app.rules_list._parent_frame.grid_info()["row"], 4)
        self.assertFalse(self.app.rule_selection_bar.grid_info())
        self.assertEqual(self.app.rule_selection_begin.grid_info()["row"], 2)
        self.assertEqual(self.app.rule_selection_begin.grid_info()["column"], 1)
        self.assertFalse(any(isinstance(child, self.ctk.CTkCheckBox) for child in self.descendants(self.app.rules_list)))
        self.button(self.app, "Selecionar regras").invoke()
        self.assertEqual(self.app.rules_list._parent_frame.grid_info()["row"], 5)
        self.assertEqual(self.app.rule_selection_bar.grid_info()["row"], 4)
        self.assertEqual(self.app.rule_area.grid_rowconfigure(5)["weight"], 1)
        self.assertEqual(self.app.rule_order_picker.master.grid_info()["row"], 3)
        self.assertEqual(len(self.app.rule_selection_boxes), 25)
        self.assertEqual(self.app.rule_selection_context[2], tuple(reversed(range(30))))
        with patch.object(self.app, "render_rules", side_effect=AssertionError("selection render")), \
                patch.object(Path, "read_bytes", side_effect=AssertionError("IO")), \
                patch.object(self.controller, "start", side_effect=AssertionError("motor")), \
                patch.object(self.controller, "stop", side_effect=AssertionError("motor")):
            self.button(self.app, "Selecionar exibidas").invoke()
            self.assertEqual(self.app.rule_selection_indices, set(range(30)))
            self.assertIn("30 selecionadas / 30 resultados", self.app.rule_selection_count.cget("text"))
            self.assertNotIn(30, self.app.rule_selection_indices)
            self.assertTrue(self.app.change_rule_page(1))
            self.assertEqual(set(self.app.rule_selection_boxes), set(range(5)))
            self.assertTrue(all(var.get() for _, var, _ in self.app.rule_selection_boxes.values()))
            self.button(self.app, "Limpar seleção").invoke()
            self.app.rule_selection_boxes[0][2].toggle()
            self.assertTrue(self.app.change_rule_page(0))
            self.app.rule_selection_boxes[29][2].toggle()
            self.assertEqual(self.app.rule_selection_indices, {0, 29})
        self.button(self.app, "Fechar seleção").invoke()
        self.assertEqual(self.app.rules_list._parent_frame.grid_info()["row"], 4)
        self.assertEqual(self.app.rule_area.grid_rowconfigure(4)["weight"], 1)
        self.assertEqual(self.app.rule_area.grid_rowconfigure(5)["weight"], 0)
        self.assertFalse(self.app.rule_selection_bar.grid_info())
        self.assertIs(self.session.draft, draft)
        self.assertIs(self.session.snapshot, snapshot)
        self.assertEqual(draft.config, config)
        self.assertEqual((self.session.dirty, draft.can_undo, draft.can_redo), history)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.background_errors, [])

    def test_rule_bulk_selection_native_cancel_reset_old_commands_and_one_undo_original_duplicates(self):
        self.path.write_text(json.dumps({"windows": [], "block_exes": ["z.exe", "dup.exe", "hidden.exe", "DUP.exe"],
                                         "typed": [True, 1, 1.0]}), encoding="utf-8")
        self.session.reload()
        self.app.render()
        original, config, snapshot = self.path.read_bytes(), self.session.draft.config, self.session.snapshot
        self.set_rule_query("dup")
        self.app.change_rule_order("Nome Z–A")
        self.app.begin_rule_selection()
        self.button(self.app, "Selecionar exibidas").invoke()
        self.assertEqual(self.app.rule_selection_indices, {1, 3})
        commands = [control.cget("command") for control in self.app.rule_selection_actions.values()]
        old_checkbox = self.app.rule_selection_boxes[3][2].cget("command")
        self.assertFalse(self.app.selection_remove(self.app.rule_selection_context))
        self.assertEqual(self.app.rule_selection_indices, {1, 3})
        self.app.change_rule_order("Nome A–Z")
        self.assertEqual(self.app.rule_selection_indices, set())
        for command in commands + [old_checkbox]:
            self.assertFalse(command())
        old_close = self.app.rule_selection_actions["close"].cget("command")
        self.assertTrue(old_close())
        self.app.begin_rule_selection()
        self.assertFalse(old_close())
        self.button(self.app, "Selecionar exibidas").invoke()
        self.messages.askyesno.return_value = True
        with patch.object(self.session.draft, "remove_rules", wraps=self.session.draft.remove_rules) as remove:
            self.assertTrue(self.app.selection_remove(self.app.rule_selection_context))
            remove.assert_called_once_with("block_exes", (1, 3))
        self.assertEqual(self.session.draft.config.block_exes, ("z.exe", "hidden.exe"))
        self.assertIs(self.session.snapshot, snapshot)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.app.rule_selection_indices, set())
        self.assertTrue(self.app.undo_draft())
        self.assertEqual(self.session.draft.config, config)
        self.assertFalse(self.session.draft.can_undo)
        self.assertTrue(self.app.redo_draft())
        self.assertEqual(self.session.draft.config.block_exes, ("z.exe", "hidden.exe"))
        self.assertEqual(self.background_errors, [])

    def test_rule_bulk_selection_native_prompt_change_reentry_picker_and_close_no_tk_after_teardown(self):
        self.path.write_text(json.dumps({"windows": [], "block_exes": ["one.exe", "two.exe"]}), encoding="utf-8")
        self.session.reload()
        self.app.render()
        self.app.begin_rule_selection()
        context = self.app.rule_selection_context
        self.app.selection_select_all(context)
        def changed_prompt(*args, **kwargs):
            self.assertTrue(self.app.confirming_rule_removal)
            self.assertFalse(self.app.selection_remove(context))
            self.assertFalse(self.app.selection_clear(context))
            self.set_rule_query("two")
            return True
        self.messages.askyesno.side_effect = changed_prompt
        with patch.object(self.session.draft, "remove_rules", side_effect=AssertionError("stale remove")):
            self.assertFalse(self.app.selection_remove(context))
        self.assertFalse(self.app.confirming_rule_removal)
        self.assertEqual(self.session.draft.config.block_exes, ("one.exe", "two.exe"))
        self.app.selection_select_all(self.app.rule_selection_context)
        context = self.app.rule_selection_context
        self.messages.askyesno.side_effect = lambda *a, **k: (setattr(self.app, "picker_active", True) or True)
        with patch.object(self.session.draft, "remove_rules", side_effect=AssertionError("picker remove")):
            self.assertFalse(self.app.selection_remove(context))
        self.app.picker_active = False
        self.app.update_runtime()
        commands = [control.cget("command") for control in self.app.rule_selection_actions.values()]
        commands.append(next(iter(self.app.rule_selection_boxes.values()))[2].cget("command"))
        self.messages.askyesno.side_effect = lambda *a, **k: (self.app.close_editor() or True)
        with patch.object(self.session.draft, "remove_rules", side_effect=AssertionError("closed remove")):
            self.assertFalse(self.app.selection_remove(context))
        self.assertTrue(self.app.closed)
        self.assertFalse(self.app.confirming_rule_removal)
        for command in commands:
            self.assertFalse(command())
        self.assertEqual(self.app.tk.splitlist(self.app.tk.call("after", "info")), ())
        self.app.tk.call("update")
        self.assertEqual(self.background_errors, [])

    def test_rule_search_keyboard_native_focus_selection_categories_and_compact_layout(self):
        self.app.geometry("880x660")
        entry = self.app.rule_search_entry
        self.app.change_rule_order("Nome Z–A")
        self.set_rule_query(" Existing query ")
        self.assertEqual(entry.master.grid_info()["row"], 3)
        self.assertEqual(entry.master.grid_info()["column"], 0)
        self.assertIs(self.button(self.app, "Limpar").master, entry.master)
        self.assertEqual(self.app.rule_order_picker.master.grid_info()["row"], 3)
        self.assertEqual(self.app.rule_order_picker.master.grid_info()["column"], 1)
        self.assertEqual(self.app.rules_list._parent_frame.grid_info()["row"], 4)
        self.assertTrue(self.app.bind("<Control-f>"))
        self.assertIn("clear_rule_search", self.app.tk.call("bind", str(entry._entry), "<Escape>"))
        self.assertFalse(self.app.bind("<Escape>"))
        for category in ("Executáveis", "Pastas", "Proteção adicional", "Linha de comando"):
            self.app.rule_category.set(category)
            self.app.tabs.set("Horários")
            with patch.object(self.app, "render_rules", side_effect=AssertionError("render")), \
                    patch.object(entry, "focus_set", wraps=entry.focus_set) as focus:
                self.assertEqual(self.app.focus_rule_search(), "break")
                focus.assert_called_once_with()
            self.assertEqual(self.app.tabs.get(), "Jogos / Apps")
            self.assertEqual(self.app.rule_category.get(), category)
            self.assertEqual(self.app.rule_search.get(), " Existing query ")
            self.assertEqual(self.app.rule_order.get(), "Nome Z–A")
            self.assertTrue(entry.select_present())
            self.assertEqual(entry.index("sel.first"), 0)
            self.assertEqual(entry.index("sel.last"), len(" Existing query "))
            self.assertEqual(entry.index("insert"), len(" Existing query "))
        self.assertEqual(self.background_errors, [])

    def test_rule_search_keyboard_native_clear_once_original_indices_history_and_no_io(self):
        for value in ("z.exe", "a.exe", "A.exe", "redo.exe"):
            self.session.draft.add_rule("block_exes", value)
        self.session.draft.undo()
        self.app.render()
        draft, snapshot, config = self.session.draft, self.session.snapshot, self.session.draft.config
        original = self.path.read_bytes()
        state = self.session.dirty, draft.can_undo, draft.can_redo
        generation = self.app.review_generation
        self.app.change_rule_order("Nome Z–A")
        self.set_rule_query("a.exe")
        self.assertEqual(self.native_rule_indices("block_exes"), [1, 2])
        with patch.object(self.app, "render_rules", wraps=self.app.render_rules) as render, \
                patch.object(Path, "read_bytes", side_effect=AssertionError("IO")), \
                patch.object(self.session, "save", side_effect=AssertionError("Save")), \
                patch.object(self.controller, "start", side_effect=AssertionError("motor")), \
                patch.object(self.controller, "stop", side_effect=AssertionError("motor")):
            self.assertEqual(self.app.clear_rule_search(SimpleNamespace()), "break")
            render.assert_called_once_with()
            render.reset_mock()
            self.button(self.app, "Limpar").invoke()
            render.assert_not_called()
            self.set_rule_query("missing")
            render.reset_mock()
            self.button(self.app, "Limpar").invoke()
            render.assert_called_once_with()
        self.assertEqual(self.native_rule_indices("block_exes"), [0, 1, 2])
        self.assertEqual(self.app.rule_order.get(), "Nome Z–A")
        self.assertIs(self.session.draft, draft)
        self.assertIs(self.session.snapshot, snapshot)
        self.assertEqual(draft.config, config)
        self.assertEqual((self.session.dirty, draft.can_undo, draft.can_redo), state)
        self.assertEqual(self.app.review_generation, generation)
        self.assertEqual(self.path.read_bytes(), original)
        self.button(self.app.review_rows[("block_exes", 2)], "Editar").invoke()
        self.app.modal.withdraw()
        self.assertEqual(self.entries()[0].get(), "A.exe")
        self.button(self.app.modal, "Cancelar").invoke()
        self.assertEqual(self.background_errors, [])

    def test_rule_search_keyboard_native_modal_picker_and_captured_callbacks_after_teardown(self):
        focus, clear = self.app.focus_rule_search, self.app.clear_rule_search
        button_command = self.button(self.app, "Limpar").cget("command")
        self.set_rule_query("keep")
        config = self.session.draft.config
        self.app.edit_window()
        self.app.modal.withdraw()
        dialog = self.app.modal
        for action in (focus, clear):
            self.assertIsNone(action(SimpleNamespace()))
        self.assertFalse(button_command())
        self.assertIs(self.app.modal, dialog)
        # Escape continua registrado no formulário; só a Entry busca limpa query.
        self.assertTrue(dialog.bind("<Escape>"))
        self.button(dialog, "Cancelar").invoke()
        for flag in ("picker_active", "selecting_executables", "closing", "closed"):
            setattr(self.app, flag, True)
            with patch.object(self.app.tabs, "set", side_effect=AssertionError("Tk")), \
                    patch.object(self.app.rule_search, "get", side_effect=AssertionError("Tk")):
                self.assertIsNone(focus(SimpleNamespace()))
                self.assertIsNone(clear(SimpleNamespace()))
                self.assertFalse(button_command())
            setattr(self.app, flag, False)
        self.assertEqual(self.app.rule_search.get(), "keep")
        self.app.close_editor()
        self.assertTrue(self.app.closed)
        self.assertIsNone(focus(SimpleNamespace()))
        self.assertIsNone(clear(SimpleNamespace()))
        self.assertFalse(button_command())
        self.assertEqual(self.session.draft.config, config)
        self.assertEqual(self.app.tk.splitlist(self.app.tk.call("after", "info")), ())
        self.app.tk.call("update")
        self.assertEqual(self.background_errors, [])

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
        self.set_rule_query(" A.EXE ")
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
        self.set_rule_query("")
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
        self.set_rule_query("z")
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
        self.set_rule_query("a-00")
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
                    self.set_rule_query("no results")
                    with patch.object(self.app, "render_rules", wraps=self.app.render_rules) as rendered:
                        self.assertTrue(self.app.navigate_review(field, 1))
                        rendered.assert_called_once_with(target_index=1)
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
        self.set_rule_query("no results")
        self.assertIsNone(self.app.highlighted_row)
        self.assertNotIn(timer, self.app.tk.splitlist(self.app.tk.call("after", "info")))
        self.set_rule_query("")
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
            self.assertFalse(self.app.edit_rule())  # picker ativo recusa ação normal
            replacement, form, *_ = self.app.new_dialog("Modal substituto externo")
            replacement.withdraw()
            self.ctk.CTkEntry(form).grid(row=0, column=0, sticky="ew")
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
        self.set_rule_query("TARGET")
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
        self.set_rule_query("no results")
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

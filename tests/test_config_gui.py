"""Fluxos da GUI com widgets simulados e configuração/repositório reais.

Não comprova renderização, DPI ou interação nativa do CustomTkinter.
"""

import json
from dataclasses import replace
from datetime import date, datetime as real_datetime
from pathlib import Path
import shutil
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from core.config import load_config
from core.config import ConfigError
from core.config_session import ConfigSession
from core.process_controller import RuntimeSnapshot
from ui.tray_commands import TrayMailbox
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
        if self.__class__.__name__ in {"CTkButton", "CTkOptionMenu", "CTkCheckBox"}:
            self.options.setdefault("state", "normal")
        self.children = []
        self.destroyed = False
        self.value = ""
        self.callbacks = {}
        self.timers = {}
        self.grid_options = {}
        self.grid_visible = False
        if parent is not None:
            parent.children.append(self)

    def configure(self, **options):
        self.options.update(options)

    def cget(self, name):
        return self.options.get(name, "normal" if name == "state" else None)

    def grid(self, **options):
        self.grid_options.update(options)
        self.grid_visible = True

    pack = grid
    def grid_remove(self):
        self.grid_visible = False
    grid_columnconfigure = lambda *args, **kwargs: None
    grid_rowconfigure = lambda *args, **kwargs: None
    def title(self, value):
        self.options["title"] = value

    def geometry(self, value):
        self.options["geometry"] = value

    def minsize(self, width, height):
        self.options["minsize"] = (width, height)

    def resizable(self, width, height):
        self.options["resizable"] = (width, height)
    transient = lambda *args, **kwargs: None
    grab_set = lambda *args, **kwargs: None
    focus_set = lambda *args, **kwargs: None
    lift = lambda *args, **kwargs: None

    def withdraw(self):
        self.options["hidden"] = True

    def deiconify(self):
        self.options["hidden"] = False

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


class FakeController:
    """Worker controlado pelo teste; nunca cria thread ou bloqueador."""

    def __init__(self, path=None):
        self.path = path
        self.value = RuntimeSnapshot()
        self.alive = False
        self.starts = 0
        self.stops = 0
        self.started_config = None
        self.wait = Mock(side_effect=AssertionError("wait em callback Tk"))

    def start(self):
        self.starts += 1
        if self.alive:
            return False
        self.started_config = load_config(self.path) if self.path is not None else None
        self.alive = True
        self.value = RuntimeSnapshot(state="running")
        return True

    def stop(self):
        self.stops += 1
        if self.alive and self.value.state != "error":
            self.value = replace(self.value, state="stopping")

    def snapshot(self):
        return self.value

    def is_alive(self):
        return self.alive

    def finish(self, **values):
        self.alive = False
        self.value = replace(self.value, state="idle", **values)


class FakeTray:
    def __init__(self):
        self.alive = False
        self.starts = self.stops = 0
        self.wait = Mock(side_effect=AssertionError("wait bandeja em callback Tk"))

    def start(self):
        self.starts += 1
        self.alive = True

    def stop(self):
        self.stops += 1

    def is_alive(self):
        return self.alive


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
                                          askopenfilenames=Mock(return_value=()),
                                          asksaveasfilename=Mock(return_value=""))
        self.controller = FakeController(self.path)
        self.mailbox = TrayMailbox()
        self.tray = FakeTray()
        self.tk = SimpleNamespace(IntVar=Variable, TclError=type("DialogError", (Exception,), {}))
        self.app = _build_app(fake_ctk(), self.tk, self.filedialog,
                              self.messages, self.session, controller=self.controller,
                              tray=self.tray, mailbox=self.mailbox)

    def entries(self):
        return [widget for widget in descendants(self.app.modal)
                if widget.__class__.__name__ == "CTkEntry"]

    def pagination_fixture(self, count=60, *, duplicates=False):
        values = [f"game-{index:03}.exe" for index in range(count)]
        if duplicates:
            values[31] = values[56] = values[2]
        self.path.write_text(json.dumps({
            "windows": [], "block_exes": values,
            "safelist_exes": ["keep.exe"], "typed": [True, 1, 1.0, "ação"],
        }), encoding="utf-8")
        self.session.reload()
        self.app.render()

    def test_rule_pagination_bounds_materializes_only_page_and_keeps_model_history(self):
        for count in (0, 25, 26, 50, 51, 1000):
            with self.subTest(count=count):
                self.pagination_fixture(count)
                self.session.draft.add_rule("safelist_exes", "redo.exe")
                self.session.draft.undo()
                self.app.render()
                draft, snapshot, config = self.session.draft, self.session.snapshot, self.session.draft.config
                original = self.path.read_bytes()
                context = self.app.rule_view_context
                self.assertEqual(self.displayed_rule_indices("block_exes"), list(range(min(count, 25))))
                self.assertEqual(self.app.rule_page_result.total, count)
                self.assertEqual(self.app.rule_pager.grid_visible, count > 25)
                self.assertEqual(self.app.rule_page_previous.cget("state"), "disabled")
                with patch.object(Path, "read_bytes", side_effect=AssertionError("page IO")), \
                        patch.object(draft, "_accept", side_effect=AssertionError("page edit")), \
                        patch.object(self.app, "render_rules", side_effect=AssertionError("logical reset")):
                    for page in range(1, (count + 24) // 25):
                        self.assertTrue(self.app.change_rule_page(page))
                        self.assertEqual(self.displayed_rule_indices("block_exes"),
                                         list(range(page * 25, min(count, (page + 1) * 25))))
                        self.assertIs(self.app.rule_view_context, context)
                    self.assertFalse(self.app.change_rule_page(self.app.rule_page_result.page_count))
                    self.assertFalse(self.app.change_rule_page(True))
                    self.assertEqual(self.app.rule_page_next.cget("state"), "disabled")
                self.assertIs(self.session.draft, draft)
                self.assertIs(self.session.snapshot, snapshot)
                self.assertEqual(draft.config, config)
                self.assertFalse(self.session.dirty)
                self.assertFalse(draft.can_undo)
                self.assertTrue(draft.can_redo)
                self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual((self.controller.starts, self.controller.stops), (0, 0))

    def test_rule_pagination_crosspage_selection_old_rows_pager_and_atomic_remove(self):
        self.pagination_fixture(duplicates=True)
        config, snapshot, original = self.session.draft.config, self.session.snapshot, self.path.read_bytes()
        self.app.begin_rule_selection()
        context = self.app.rule_selection_context
        old_row, old_var, old_box = self.app.rule_selection_boxes[2]
        callbacks = [old_box.options["command"], button(old_row, "Editar").options["command"],
                     button(old_row, "Remover").options["command"], self.app.rule_page_next.options["command"]]
        for page, index in ((0, 2), (1, 31), (2, 56)):
            if page:
                self.assertTrue(self.app.change_rule_page(page))
            _, variable, checkbox = self.app.rule_selection_boxes[index]
            variable.set(1)
            self.assertTrue(checkbox.invoke())
            self.assertIs(self.app.rule_selection_context, context)
        self.assertEqual(self.app.rule_selection_indices, {2, 31, 56})
        self.assertTrue(self.app.change_rule_page(0))
        self.assertEqual(self.app.rule_selection_boxes[2][1].get(), 1)
        with patch.object(old_var, "get", side_effect=AssertionError("destroyed variable")):
            for callback in callbacks:
                self.assertFalse(callback())
        self.messages.askyesno.assert_not_called()
        self.assertIn("3 selecionadas / 60 resultados", self.app.rule_selection_count.cget("text"))
        with patch.object(self.session.draft, "remove_rules", wraps=self.session.draft.remove_rules) as remove:
            self.assertTrue(self.app.selection_remove(context))
            remove.assert_called_once_with("block_exes", (2, 31, 56))
        self.assertEqual(self.session.draft.config.block_exes,
                         tuple(value for index, value in enumerate(config.block_exes) if index not in (2, 31, 56)))
        self.assertIs(self.session.snapshot, snapshot)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertTrue(self.app.undo_draft())
        self.assertEqual(self.session.draft.config, config)
        self.assertFalse(self.session.draft.can_undo)
        self.assertTrue(self.app.redo_draft())
        self.app.save_config()
        self.assertEqual(load_config(self.path), self.session.draft.config)
        self.assertFalse(self.session.dirty)

    def test_rule_pagination_all_full_filtered_categories_and_logical_reset(self):
        self.pagination_fixture(51)
        config = self.session.draft.config
        # Populate the other categories once, keeping separate hidden rules.
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data.update(block_folders=[f"C:\\Games\\game-{i:03}" for i in range(51)] + ["C:\\Other"],
                    safelist_exes=[f"game-{i:03}.exe" for i in range(51)] + ["keep.exe"],
                    block_cmdline=[{"executable": "javaw.exe", "contains": f"game-{i:03}"} for i in range(51)]
                                  + [{"executable": "other.exe", "contains": "hidden"}])
        self.path.write_text(json.dumps(data), encoding="utf-8")
        self.session.reload()
        self.app.render()
        config, snapshot, original = self.session.draft.config, self.session.snapshot, self.path.read_bytes()
        for category, field in (("Executáveis", "block_exes"), ("Pastas", "block_folders"),
                                ("Proteção adicional", "safelist_exes"), ("Linha de comando", "block_cmdline")):
            with self.subTest(field=field):
                self.app.rule_category.set(category)
                self.app.rule_search.set("game-")
                if not self.app.rule_selection_mode:
                    self.app.begin_rule_selection()
                context = self.app.rule_selection_context
                self.assertEqual(len(self.app.rule_selection_boxes), 25)
                self.assertTrue(self.app.selection_select_all(context))
                self.assertEqual(self.app.rule_selection_indices, set(range(51)))
                self.assertTrue(self.app.change_rule_page(2))
                self.assertEqual(set(self.app.rule_selection_boxes), {50})
                self.assertEqual(self.app.rule_selection_boxes[50][1].get(), 1)
                self.assertTrue(self.app.selection_remove(context))
                self.assertEqual(getattr(self.session.draft.config, field), getattr(config, field)[51:])
                self.assertTrue(self.app.undo_draft())
                self.assertEqual(self.session.draft.config, config)
                self.assertFalse(self.session.draft.can_undo)
                self.assertTrue(self.session.draft.can_redo)
                self.assertEqual(self.path.read_bytes(), original)
                self.assertIs(self.session.snapshot, snapshot)
        for change in (lambda: self.app.rule_search.set("game-0"),
                       lambda: self.app.change_rule_order("Nome Z–A"),
                       lambda: (self.app.rule_category.set("Executáveis"), self.app.render_rules()),
                       lambda: self.app.render(), lambda: self.app.redo_draft(), lambda: self.app.undo_draft()):
            self.app.selection_select_all(self.app.rule_selection_context)
            old = self.app.rule_selection_context
            self.app.change_rule_page(1)
            change()
            self.assertIsNot(self.app.rule_selection_context, old)
            self.assertEqual(self.app.rule_selection_indices, set())
            self.assertEqual(self.app.rule_page_result.page, 0)
            self.assertFalse(self.app.selection_select_all(old))

    def test_rule_pagination_prompt_projection_guards_and_closed_callbacks_before_tk(self):
        self.pagination_fixture()
        self.app.begin_rule_selection()
        context = self.app.rule_selection_context
        self.app.selection_select_all(context)
        config, original = self.session.draft.config, self.path.read_bytes()

        def cancel_prompt(*args, **kwargs):
            self.assertFalse(self.app.change_rule_page(1))
            self.assertFalse(self.app.selection_remove(context))
            self.assertFalse(self.app.navigate_review("block_exes", 31))
            self.assertEqual(self.app.rule_page_next.cget("state"), "disabled")
            return False

        self.messages.askyesno.side_effect = cancel_prompt
        self.assertFalse(self.app.selection_remove(context))
        self.assertEqual(self.app.rule_selection_indices, set(range(60)))
        self.assertEqual(self.app.rule_page_next.cget("state"), "normal")

        def replace_projection(*args, **kwargs):
            self.app.render_rule_projection(1)  # External reentrant UI refresh invalidates epoch.
            return True

        self.messages.askyesno.side_effect = replace_projection
        with patch.object(self.session.draft, "remove_rules", side_effect=AssertionError("stale prompt edit")):
            self.assertFalse(self.app.selection_remove(context))
        self.assertFalse(self.app.confirming_rule_removal)
        self.assertEqual(self.session.draft.config, config)
        self.assertEqual(self.path.read_bytes(), original)
        row, variable, checkbox = self.app.rule_selection_boxes[31]
        commands = [checkbox.options["command"], self.app.rule_page_previous.options["command"],
                    button(row, "Editar").options["command"], button(row, "Remover").options["command"]]
        for flag in ("picker_active", "selecting_executables", "closing", "closed"):
            setattr(self.app, flag, True)
            with patch.object(variable, "get", side_effect=AssertionError("guard before Tk")), \
                    patch.object(self.app.rule_category, "get", side_effect=AssertionError("guard before Tk")):
                for command in commands:
                    self.assertFalse(command())
            setattr(self.app, flag, False)
        self.app.edit_rule()
        for command in commands:
            self.assertFalse(command())
        button(self.app.modal, "Cancelar").invoke()

    def test_rule_pagination_review_sorted_original_target_one_projection_selection_and_scroll(self):
        self.pagination_fixture()
        self.app.change_rule_order("Nome Z–A")
        self.app.begin_rule_selection()
        context, config = self.app.rule_selection_context, self.session.draft.config
        self.app.selection_select_all(context)
        original, generation = self.path.read_bytes(), self.app.rule_selection_generation
        # Original 2 is at sorted offset57, page2, not 2//25.
        with patch.object(self.app, "render_rule_projection", wraps=self.app.render_rule_projection) as projected:
            self.assertTrue(self.app.navigate_review("block_exes", 2))
            projected.assert_called_once_with(2)
        row = self.app.highlighted_row
        timer, callback = row.review_scroll_timer, row.timers[row.review_scroll_timer]
        self.assertEqual(self.app.rule_page_result.page, 2)
        self.assertIs(self.app.rule_selection_context, context)
        self.assertEqual(self.app.rule_selection_generation, generation)
        self.assertEqual(self.app.rule_selection_indices, set(range(60)))
        self.assertTrue(self.app.change_rule_page(0))
        self.assertNotIn(timer, row.timers)
        with patch.object(row, "winfo_y", create=True, side_effect=AssertionError("old scroll Tk")):
            callback()
        self.app.rule_search.set("game-059")
        with patch.object(self.app, "render_rule_projection", wraps=self.app.render_rule_projection) as projected:
            self.assertTrue(self.app.navigate_review("block_exes", 2))
            projected.assert_called_once_with(2)
        self.assertEqual(self.app.rule_search.get(), "")
        self.assertEqual(self.app.rule_selection_indices, set())
        self.assertEqual(self.app.visual_rule_order, "name_desc")
        self.assertEqual(self.session.draft.config, config)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertFalse(self.session.dirty)
        self.assertFalse(self.session.draft.can_undo)
        self.assertEqual((self.controller.starts, self.controller.stops), (0, 0))

    def test_rule_pagination_review_included_filter_preserves_owner_selection_and_redo(self):
        self.pagination_fixture()
        self.session.draft.add_rule("safelist_exes", "redo.exe")
        self.session.draft.undo()
        self.app.render()
        self.app.rule_search.set("game-")
        self.app.change_rule_order("Nome Z–A")
        self.app.begin_rule_selection()
        context, generation = self.app.rule_selection_context, self.app.rule_selection_generation
        self.app.selection_select_all(context)
        draft, snapshot, config = self.session.draft, self.session.snapshot, self.session.draft.config
        original = self.path.read_bytes()
        with patch.object(self.app, "render_rules", side_effect=AssertionError("unneeded logical reset")), \
                patch.object(self.app, "render_rule_projection", wraps=self.app.render_rule_projection) as projected, \
                patch.object(Path, "read_bytes", side_effect=AssertionError("navigation IO")), \
                patch.object(draft, "_accept", side_effect=AssertionError("navigation edit")):
            self.assertTrue(self.app.navigate_review("block_exes", 2))
            projected.assert_called_once_with(2)
        self.assertEqual(self.app.rule_search.get(), "game-")
        self.assertEqual(self.app.visual_rule_order, "name_desc")
        self.assertEqual(self.app.rule_page_result.total, 60)
        self.assertEqual(self.app.rule_page_result.page, 2)
        self.assertIs(self.app.rule_view_context, context)
        self.assertIs(self.app.rule_selection_context, context)
        self.assertEqual(self.app.rule_selection_generation, generation)
        self.assertEqual(self.app.rule_selection_indices, set(range(60)))
        self.assertTrue(all(variable.get() for _, variable, _ in self.app.rule_selection_boxes.values()))
        self.assertIs(self.app.highlighted_row, self.app.review_rows[("block_exes", 2)])
        self.assertIs(self.session.draft, draft)
        self.assertIs(self.session.snapshot, snapshot)
        self.assertEqual(draft.config, config)
        self.assertFalse(self.session.dirty)
        self.assertFalse(draft.can_undo)
        self.assertTrue(draft.can_redo)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual((self.controller.starts, self.controller.stops), (0, 0))

    def watch_idle_configures(self):
        widgets = [self.app, *descendants(self.app)]
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

    def test_idle_updates_stable_poll_no_configure_and_changed_agenda_text_no_effects(self):
        self.app.refresh_status(schedule=False)
        snapshot, draft, config = self.session.snapshot, self.session.draft, self.session.draft.config
        original, timer = self.path.read_bytes(), self.app.status_timer
        widgets = self.watch_idle_configures()
        with patch.object(self.controller, "snapshot", wraps=self.controller.snapshot) as runtime, \
                patch.object(self.session, "agenda_status", wraps=self.session.agenda_status) as agenda, \
                patch.object(self.mailbox, "drain", wraps=self.mailbox.drain) as drain:
            self.assert_idle_polls(widgets)
            self.assertEqual((runtime.call_count, agenda.call_count, drain.call_count), (3, 3, 3))
        active = SimpleNamespace(active=True, next_start=real_datetime(2026, 10, 19, 9),
                                 current_end=real_datetime(2026, 10, 19, 10))
        with patch.object(self.session, "agenda_status", return_value=active):
            self.app.refresh_status(schedule=False)
            self.assertEqual(self.app.agenda_label.cget("text"), "Agenda carregada: dentro da janela")
            self.assertIn("19/10/2026 às 09:00", self.app.next_label.cget("text"))
            self.assertIn("19/10/2026 às 10:00", self.app.end_label.cget("text"))
            for control in (self.app.agenda_label, self.app.next_label, self.app.end_label):
                self.assertEqual(control.configure.call_count, 1)
            self.app.agenda_hint.configure.assert_not_called()
            self.assert_idle_polls(widgets)
        self.assertIs(self.session.snapshot, snapshot)
        self.assertIs(self.session.draft, draft)
        self.assertEqual(draft.config, config)
        self.assertFalse(self.session.dirty)
        self.assertFalse(draft.can_undo)
        self.assertFalse(draft.can_redo)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.app.status_timer, timer)
        self.assertEqual((self.controller.starts, self.controller.stops), (0, 0))

    def test_idle_updates_history_review_modal_picker_runtime_and_closing_transitions(self):
        for _ in range(2):
            self.session.draft.add_rule("block_exes", "game.exe")
        self.app.render()
        config, original = self.session.draft.config, self.path.read_bytes()
        self.app.undo_draft()
        self.app.undo_draft()
        self.assertFalse(self.session.dirty)
        self.assertEqual(self.app.undo_button.cget("state"), "disabled")
        self.assertEqual(self.app.redo_button.cget("state"), "normal")
        self.app.redo_draft()
        self.app.redo_draft()
        self.assertTrue(self.session.dirty)
        self.assertIn("não salvas", self.app.dirty_label.cget("text"))
        self.assertEqual(self.app.undo_button.cget("state"), "normal")
        self.assertEqual(self.app.redo_button.cget("state"), "disabled")
        self.assertEqual(self.app.review_picker.cget("state"), "normal")
        self.assertEqual(self.app.review_go.cget("state"), "disabled")
        self.app.choose_review(next(iter(self.app.review_choices)), self.app.review_generation)
        self.assertEqual(self.app.review_go.cget("state"), "normal")
        widgets = self.watch_idle_configures()
        self.assert_idle_polls(widgets)
        self.app.edit_rule()
        self.assertEqual(self.app.undo_button.cget("state"), "disabled")
        self.assertEqual(self.app.review_go.cget("state"), "disabled")
        self.assert_idle_polls(widgets)
        button(self.app.modal, "Cancelar").invoke()
        self.assertEqual(self.app.undo_button.cget("state"), "normal")
        self.assertEqual(self.app.review_go.cget("state"), "normal")
        for flag in ("picker_active", "selecting_executables"):
            setattr(self.app, flag, True)
            self.app.refresh_status(schedule=False)
            self.assertEqual(self.app.start_button.cget("state"), "disabled")
            self.assertEqual(self.app.rule_order_picker.cget("state"), "disabled")
            self.assert_idle_polls(widgets)
            setattr(self.app, flag, False)
            self.app.refresh_status(schedule=False)
            self.assertEqual(self.app.rule_order_picker.cget("state"), "normal")
        for state, alive, title, start, stop in (
            ("running", True, "Motor em execução", "disabled", "normal"),
            ("stopping", True, "Motor parando", "disabled", "disabled"),
            ("error", True, "Motor com erro", "disabled", "disabled"),
            ("error", False, "Motor com erro", "normal", "disabled"),
            ("idle", False, "Motor parado", "normal", "disabled"),
        ):
            self.controller.value = RuntimeSnapshot(state=state, error="falha" if state == "error" else None)
            self.controller.alive = alive
            self.app.refresh_status(schedule=False)
            self.assertEqual(self.app.runtime_title.cget("text"), title)
            self.assertEqual(self.app.start_button.cget("state"), start)
            self.assertEqual(self.app.stop_button.cget("state"), stop)
            self.assert_idle_polls(widgets)
        self.controller.value, self.controller.alive = RuntimeSnapshot(state="running"), True
        self.app.closing = self.app.stop_requested = True
        self.app.update_runtime()
        self.assertEqual(self.app.runtime_title.cget("text"), "Motor parando")
        for control in (self.app.start_button, self.app.stop_button, self.app.undo_button,
                        self.app.redo_button, self.app.review_go, self.app.rule_selection_begin):
            self.assertEqual(control.cget("state"), "disabled")
        for widget in widgets:
            widget.configure.reset_mock()
        for _ in range(3):
            self.app.update_runtime()
        for widget in widgets:
            widget.configure.assert_not_called()
        self.app.closing = False
        self.controller.finish()
        self.assertEqual(self.session.draft.config, config)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual((self.controller.starts, self.controller.stops), (0, 0))

    def test_idle_updates_active_selection_toolbar_changes_only_real_values(self):
        self.bulk_fixture()
        self.app.begin_rule_selection()
        context, generation = self.app.rule_selection_context, self.app.rule_selection_generation
        draft, snapshot, config = self.session.draft, self.session.snapshot, self.session.draft.config
        original = self.path.read_bytes()
        widgets = self.watch_idle_configures()
        self.assert_idle_polls(widgets)
        self.app.selection_select_all(context)
        self.app.rule_selection_count.configure.assert_called_once()
        self.app.rule_selection_actions["clear"].configure.assert_called_once_with(state="normal")
        self.app.rule_selection_actions["remove"].configure.assert_called_once_with(state="normal")
        self.app.rule_selection_actions["all"].configure.assert_not_called()
        self.app.rule_selection_actions["close"].configure.assert_not_called()
        self.assertIn("4 selecionadas / 4 resultados", self.app.rule_selection_count.cget("text"))
        self.assertIn("Todas as páginas. Busca/ordem/categoria limpam seleção.",
                      self.app.rule_selection_count.cget("text"))
        self.assert_idle_polls(widgets)
        self.app.selection_clear(context)
        self.app.rule_selection_actions["clear"].configure.assert_called_once_with(state="disabled")
        self.app.rule_selection_actions["remove"].configure.assert_called_once_with(state="disabled")
        self.assertIn("0 selecionadas / 4 resultados", self.app.rule_selection_count.cget("text"))
        self.assert_idle_polls(widgets)
        for flag in ("picker_active", "confirming_rule_removal"):
            setattr(self.app, flag, True)
            self.app.refresh_status(schedule=False)
            self.assertTrue(all(control.cget("state") == "disabled" for control in self.app.rule_selection_actions.values()))
            self.assert_idle_polls(widgets)
            setattr(self.app, flag, False)
            self.app.refresh_status(schedule=False)
            self.assertEqual(self.app.rule_selection_actions["all"].cget("state"), "normal")
            self.assertEqual(self.app.rule_selection_actions["close"].cget("state"), "normal")
        self.assertIs(self.app.rule_selection_context, context)
        self.assertEqual(self.app.rule_selection_generation, generation)
        self.assertIs(self.session.draft, draft)
        self.assertIs(self.session.snapshot, snapshot)
        self.assertEqual(draft.config, config)
        self.assertEqual(self.path.read_bytes(), original)

    def window_day_variables(self):
        return [widget.options["variable"] for widget in descendants(self.app.modal)
                if widget.__class__.__name__ == "CTkCheckBox"]

    def load_window_days(self, days=(6, 0)):
        self.path.write_text(json.dumps({"windows": [{"start": "22:00", "end": "02:00", "days": days}],
                                        "typed": [True, 1, 1.0]}), encoding="utf-8")
        self.session.reload()
        self.app.render()

    def test_window_day_presets_are_local_and_cancel_escape_leave_all_state_intact(self):
        snapshot, draft, config = self.session.snapshot, self.session.draft, self.session.draft.config
        original = self.path.read_bytes()
        self.app.edit_window()
        variables = self.window_day_variables()
        for title, expected in (("Nenhum", ()), ("Fim de semana", (5, 6)), ("Seg–Sex", tuple(range(5))),
                                ("Todos", tuple(range(7)))):
            with self.subTest(title=title):
                button(self.app.modal, title).invoke()
                self.assertEqual(tuple(day for day, variable in enumerate(variables) if variable.get()), expected)
                self.assertEqual(draft.config, config)
                self.assertFalse(draft.can_undo)
                self.assertFalse(self.session.dirty)
        self.app.modal.callbacks["<Escape>"](None)
        self.assertIsNone(self.app.modal)
        self.app.edit_window()
        button(self.app.modal, "Nenhum").invoke()
        button(self.app.modal, "Cancelar").invoke()
        self.assertIs(self.session.snapshot, snapshot)
        self.assertIs(self.session.draft, draft)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.controller.starts, 0)

    def test_window_days_noncanonical_noop_toggles_and_presets_preserve_redo_and_typed_extras(self):
        self.load_window_days()
        self.session.draft.add_rule("block_exes", "redo.exe")
        self.app.undo_draft()
        snapshot, config, original = self.session.snapshot, self.session.draft.config, self.path.read_bytes()
        self.assertTrue(self.session.draft.can_redo)
        self.assertFalse(self.session.dirty)
        for mode in ("unchanged", "toggle", "presets"):
            with self.subTest(mode=mode):
                self.app.edit_window(0)
                variables = self.window_day_variables()
                if mode == "toggle":
                    variables[6].set(0)
                    variables[6].set(1)
                elif mode == "presets":
                    button(self.app.modal, "Todos").invoke()
                    button(self.app.modal, "Nenhum").invoke()
                    variables[0].set(1)
                    variables[6].set(1)
                button(self.app.modal, "Aplicar alteração").invoke()
                self.assertEqual(self.session.draft.config.windows[0].days, (6, 0))
                self.assertEqual(self.session.draft.config, config)
                self.assertFalse(self.session.draft.can_undo)
                self.assertTrue(self.session.draft.can_redo)
                self.assertFalse(self.session.dirty)
        self.assertIs(self.session.snapshot, snapshot)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual([type(value) for value in self.session.draft.config.extra["typed"]], [bool, int, float])
        self.app.redo_draft()
        self.assertEqual(self.session.draft.config.block_exes, ("redo.exe",))

    def test_window_days_retained_removed_new_and_all_use_original_order(self):
        expected_modes = (("remove", (0,)), ("add", (6, 0, 2)), ("Todos", (6, 0, 1, 2, 3, 4, 5)),
                          ("Seg–Sex", (0, 1, 2, 3, 4)), ("Fim de semana", (6, 5)), ("Nenhum", ()))
        for mode, expected in expected_modes:
            with self.subTest(mode=mode):
                self.load_window_days()
                original = self.path.read_bytes()
                self.app.edit_window(0)
                variables = self.window_day_variables()
                if mode == "remove":
                    variables[6].set(0)
                elif mode == "add":
                    variables[2].set(1)
                else:
                    button(self.app.modal, mode).invoke()
                button(self.app.modal, "Aplicar alteração").invoke()
                self.assertEqual(self.session.draft.config.windows[0].days, expected)
                self.assertTrue(self.session.dirty)
                self.assertEqual(self.path.read_bytes(), original)
                self.app.undo_draft()
                self.assertEqual(self.session.draft.config.windows[0].days, (6, 0))
                self.assertFalse(self.session.draft.can_undo)
                self.app.redo_draft()
                self.assertEqual(self.session.draft.config.windows[0].days, expected)

    def test_window_days_new_presets_weekly_disabled_and_invalid_apply_remains_local(self):
        for title, expected in (("Todos", tuple(range(7))), ("Seg–Sex", tuple(range(5))),
                                ("Fim de semana", (5, 6)), ("Nenhum", ())):
            with self.subTest(title=title):
                self.app.edit_window()
                start, end = self.entries()
                start.insert(0, "09:00")
                end.insert(0, "09:00")
                button(self.app.modal, title).invoke()
                before = self.session.draft.config
                button(self.app.modal, "Adicionar").invoke()
                self.assertIsNotNone(self.app.modal)
                self.assertEqual(self.session.draft.config, before)
                end.insert(0, "10:00")
                button(self.app.modal, "Adicionar").invoke()
                self.assertEqual(self.session.draft.config.windows[-1].days, expected)
                self.app.undo_draft()
                self.assertEqual(self.session.draft.config, before)

    def test_window_days_time_edit_preserves_order_and_save_remains_conflict_checked(self):
        self.load_window_days()
        self.app.edit_window(0)
        start, _ = self.entries()
        start.insert(0, "21:00")
        button(self.app.modal, "Aplicar alteração").invoke()
        self.assertEqual(self.session.draft.config.windows[0].days, (6, 0))
        self.assertEqual(self.session.draft.config.windows[0].start.hour, 21)
        self.path.write_bytes(b'{"windows":[],"writer":"external"}')
        external = self.path.read_bytes()
        self.assertFalse(self.app.save_config())
        self.assertEqual(self.path.read_bytes(), external)
        self.assertTrue(self.session.dirty)

    def test_window_day_old_callbacks_guard_before_any_variable_or_finish_edit_access(self):
        self.load_window_days()
        self.app.edit_window(0)
        dialog = self.app.modal
        preset = button(dialog, "Todos").options["command"]
        apply = button(dialog, "Aplicar alteração").options["command"]
        variables = self.window_day_variables()
        button(dialog, "Cancelar").invoke()
        self.app.edit_window()
        replacement = self.app.modal
        before = self.session.draft.config
        with patch.object(variables[0], "set", side_effect=AssertionError("oldTk")), \
                patch.object(variables[0], "get", side_effect=AssertionError("oldTk")), \
                patch.object(self.app, "finish_edit", side_effect=AssertionError("oldfinish")):
            self.assertFalse(preset())
            self.assertFalse(apply())
        self.assertIs(self.app.modal, replacement)
        self.assertEqual(self.session.draft.config, before)
        active_preset = button(replacement, "Nenhum").options["command"]
        active_apply = button(replacement, "Adicionar").options["command"]
        for flag in ("picker_active", "selecting_executables", "closing", "closed"):
            setattr(self.app, flag, True)
            self.assertFalse(active_preset())
            self.assertFalse(active_apply())
            setattr(self.app, flag, False)
        self.assertIs(self.app.modal, replacement)
        self.messages.askyesnocancel.return_value = False
        self.app.close_editor()
        self.assertFalse(active_preset())
        self.assertFalse(active_apply())
        self.assertEqual(self.session.draft.config, before)

    def displayed_rule_indices(self, field):
        return [index for row_field, index in self.app.review_rows if row_field == field]

    def bulk_fixture(self):
        self.path.write_text(json.dumps({"windows": [], "typed": [True, 1, 1.0],
            "block_exes": ["z.exe", "dup.exe", "hidden.exe", "DUP.exe"],
            "safelist_exes": ["z.exe", "dup.exe", "hidden.exe", "DUP.exe"],
            "block_folders": ["C:\\z", "C:\\dup", "C:\\hidden", "C:\\DUP"],
            "block_cmdline": [{"executable": name, "contains": "literal "}
                              for name in ("z.exe", "dup.exe", "hidden.exe", "DUP.exe")]}), encoding="utf-8")
        self.session.reload()
        self.app.render()

    def action_fixture(self):
        self.bulk_fixture()
        self.session.draft.add_window("22:00", "02:00", (6, 0))
        self.app.save_config()
        self.session.reload()
        self.app.render()

    def test_editor_action_render_shared_snapshots_and_old_rows_never_operate_again(self):
        self.action_fixture()
        draft = self.session.draft
        getter = type(draft).config.fget
        calls = []
        def counted(owner):
            calls.append(owner)
            return getter(owner)
        with patch.object(type(draft), "config", new=property(counted)):
            self.app.render_windows()
            self.app.render_rules()
        self.assertEqual(calls, [draft, draft])
        rows = [row for (field, _), row in self.app.review_rows.items() if field == "block_exes"]
        self.assertTrue(all(row.action_context[6] is rows[0].action_context[6] for row in rows))
        for change in ("render", "import_equal", "reload", "undo_redo_equal", "view_roundtrip", "typed_extra"):
            with self.subTest(change=change):
                self.action_fixture()
                commands = [button(self.app.review_rows[(field, 0)], title).options["command"]
                            for field, title in (("windows", "Editar"), ("windows", "Remover"),
                                                 ("windows", "Duplicar"), ("block_exes", "Editar"),
                                                 ("block_exes", "Remover"))]
                if change == "render": self.app.render()
                elif change == "import_equal": self.session.import_config(self.path)
                elif change == "reload": self.app.reload_config()
                elif change == "undo_redo_equal":
                    self.session.draft.add_rule("block_exes", "temporary.exe")
                    self.app.undo_draft()
                    self.app.redo_draft()
                    self.app.undo_draft()
                elif change == "view_roundtrip":
                    self.app.render_windows()  # invalidate schedules too, with equal data
                    self.app.rule_search.set("dup")
                    self.app.rule_search.set("")
                else:
                    config = self.session.draft.config
                    config.extra["typed"][0] = 1
                    self.session.draft.replace_config(config)
                before = self.session.draft.config
                state = self.session.dirty, self.session.draft.can_undo, self.session.draft.can_redo
                with patch.object(self.app, "new_dialog", side_effect=AssertionError("stale dialog")), \
                        patch.object(self.messages, "askyesno", side_effect=AssertionError("stale prompt")):
                    for command in commands:
                        self.assertFalse(command())
                self.assertEqual(self.session.draft.config, before)
                self.assertEqual((self.session.dirty, self.session.draft.can_undo, self.session.draft.can_redo), state)

    def test_editor_action_remove_postprompt_replacement_view_same_data_and_reentrancy(self):
        for change in ("identity", "model", "typed", "render_equal", "row", "query", "picker", "closed", "reentrant"):
            with self.subTest(change=change):
                self.app.closed = self.app.picker_active = False
                self.app.rule_search.set("")
                self.action_fixture()
                command = button(self.app.review_rows[("block_exes", 0)], "Remover").options["command"]
                def confirm(*args, **kwargs):
                    if change == "identity": self.session.import_config(self.path)
                    elif change == "model": self.session.draft.update_rule("block_exes", 0, "replacement.exe")
                    elif change == "typed":
                        config = self.session.draft.config
                        config.extra["typed"][0] = 1
                        self.session.draft.replace_config(config)
                    elif change == "render_equal": self.app.render_rules()
                    elif change == "row": self.app.review_rows[("block_exes", 0)] = Widget()
                    elif change == "query": self.app.rule_search.set("z")
                    elif change == "picker": self.app.picker_active = True
                    elif change == "closed": self.app.closed = True
                    else:
                        self.assertFalse(command())
                        self.assertFalse(self.app.reload_config())
                        self.assertFalse(self.app.begin_rule_selection())
                        self.assertFalse(self.app.edit_window())
                    return change != "reentrant"
                self.messages.askyesno.side_effect = confirm
                with patch.object(self.session.draft, "remove_rule", side_effect=AssertionError("wrong target")):
                    self.assertFalse(command())
                self.assertFalse(self.app.confirming_rule_removal)
                self.app.closed = self.app.picker_active = False
                self.messages.askyesno.side_effect = None
        self.action_fixture()
        config, original = self.session.draft.config, self.path.read_bytes()
        with patch.object(self.session.draft, "remove_window", side_effect=ConfigError("invalid")):
            self.assertFalse(button(self.app.review_rows[("windows", 0)], "Remover").invoke())
        self.assertIn("Rascunho preservado", self.labels(self.app))
        self.assertEqual(self.session.draft.config, config)
        self.assertEqual(self.path.read_bytes(), original)
        self.messages.askyesno.side_effect = RuntimeError("dialog failure")
        with self.assertRaisesRegex(RuntimeError, "dialog failure"):
            self.app.remove_item("windows", 0)
        self.assertFalse(self.app.confirming_rule_removal)

    def test_editor_action_forms_stale_model_or_draft_rejected_before_getters_and_finish(self):
        for kind in ("window", "rule"):
            for change in ("identity_equal", "model", "typed_extra"):
                with self.subTest(kind=kind, change=change):
                    self.action_fixture()
                    self.app.edit_window(0) if kind == "window" else self.app.edit_rule(0, "block_exes")
                    dialog = self.app.modal
                    command = button(dialog, "Aplicar alteração").options["command"]
                    entries = self.entries()
                    if change == "identity_equal": self.session.import_config(self.path)
                    elif change == "model": self.session.draft.update_rule("block_exes", 0, "new.exe")
                    else:
                        config = self.session.draft.config
                        config.extra["typed"][0] = 1
                        self.session.draft.replace_config(config)
                    before, snapshot, original = self.session.draft.config, self.session.snapshot, self.path.read_bytes()
                    for entry in entries:
                        entry.get = Mock(side_effect=AssertionError("stale getter"))
                    with patch.object(self.app, "finish_edit", side_effect=AssertionError("finish")):
                        self.assertFalse(command())
                    self.assertIs(self.app.modal, dialog)
                    self.assertIn("rascunho mudou", self.labels(dialog))
                    self.assertEqual(self.session.draft.config, before)
                    self.assertIs(self.session.snapshot, snapshot)
                    self.assertEqual(self.path.read_bytes(), original)
                    button(dialog, "Cancelar").invoke()

    def test_editor_action_old_rule_apply_and_dialog_creation_change_never_touch_old_tk(self):
        self.action_fixture()
        for kind in ("rule", "window"):
            self.app.edit_rule() if kind == "rule" else self.app.edit_window()
            old = self.app.modal
            apply = button(old, "Adicionar").options["command"]
            old_entries = self.entries()
            button(old, "Cancelar").invoke()
            self.app.edit_rule()
            replacement = self.app.modal
            for entry in old_entries:
                entry.get = Mock(side_effect=AssertionError("destroyed Tk"))
            with patch.object(self.app, "finish_edit", side_effect=AssertionError("finish")):
                self.assertFalse(apply())
            self.assertIs(self.app.modal, replacement)
            button(replacement, "Cancelar").invoke()
        create = self.app.new_dialog
        for kind in ("rule", "window"):
            def replaced(*args, **kwargs):
                dialog = create(*args, **kwargs)
                self.session.import_config(self.path)
                return dialog
            with patch.object(self.app, "new_dialog", side_effect=replaced):
                self.assertFalse(self.app.edit_rule(0, "block_exes") if kind == "rule" else self.app.edit_window(0))
            self.assertEqual(self.entries(), [])
            self.assertIn("rascunho mudou", self.labels(self.app.modal))
            button(self.app.modal, "Cancelar").invoke()

    def test_editor_action_invalid_indices_fields_and_guards_before_dialog_or_prompt(self):
        self.action_fixture()
        with patch.object(self.app, "new_dialog", side_effect=AssertionError("dialog")), \
                patch.object(self.messages, "askyesno", side_effect=AssertionError("prompt")):
            for index in (True, False, -1, 200, "0", 1.0):
                self.assertFalse(self.app.edit_window(index))
                self.assertFalse(self.app.edit_rule(index, "block_exes"))
                self.assertFalse(self.app.remove_item("windows", index))
                self.assertFalse(self.app.duplicate_window(index))
            self.assertFalse(self.app.edit_rule(0, "unknown"))
            self.assertFalse(self.app.remove_item("unknown", 0))
            for flag in ("picker_active", "selecting_executables", "closing", "closed", "confirming_rule_removal"):
                setattr(self.app, flag, True)
                self.assertFalse(self.app.edit_rule())
                self.assertFalse(self.app.edit_window())
                self.assertFalse(self.app.remove_item("windows", 0))
                self.assertFalse(self.app.duplicate_window(0))
                setattr(self.app, flag, False)

    def test_editor_action_active_selection_row_edit_cancel_remove_one_undo(self):
        self.action_fixture()
        config, snapshot, original = self.session.draft.config, self.session.snapshot, self.path.read_bytes()
        self.app.begin_rule_selection()
        self.app.selection_select_all(self.app.rule_selection_context)
        row = self.app.review_rows[("block_exes", 1)]
        self.assertEqual(len(row.action_context), 8)
        self.assertEqual(len(self.app.rule_selection_context), 7)
        button(row, "Editar").invoke()
        self.assertEqual(self.entries()[0].get(), "dup.exe")
        button(self.app.modal, "Cancelar").invoke()
        self.assertEqual(self.session.draft.config, config)
        self.assertFalse(self.session.draft.can_undo)
        self.assertTrue(button(row, "Remover").invoke())
        self.assertEqual(self.session.draft.config.block_exes, ("z.exe", "hidden.exe", "DUP.exe"))
        self.assertTrue(self.app.undo_draft())
        self.assertEqual(self.session.draft.config, config)
        self.assertFalse(self.session.draft.can_undo)
        self.assertTrue(self.app.rule_selection_mode)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertIs(self.session.snapshot, snapshot)

    def test_editor_action_reload_guards_and_memory_change_preserve_new_draft_without_io(self):
        self.action_fixture()
        self.app.edit_rule()
        with patch.object(self.session, "reload", side_effect=AssertionError("IO")), \
                patch.object(self.messages, "askyesno", side_effect=AssertionError("prompt")):
            self.assertFalse(self.app.reload_config())
        button(self.app.modal, "Cancelar").invoke()
        for flag in ("picker_active", "selecting_executables", "closing", "closed", "confirming_rule_removal"):
            setattr(self.app, flag, True)
            with patch.object(self.session, "reload", side_effect=AssertionError("IO")), \
                    patch.object(self.messages, "askyesno", side_effect=AssertionError("prompt")):
                self.assertFalse(self.app.reload_config())
            setattr(self.app, flag, False)
        for change in ("identity", "typed", "history_equal", "picker"):
            self.action_fixture()
            self.session.draft.add_rule("block_exes", "dirty.exe")
            self.app.render()
            snapshot, original = self.session.snapshot, self.path.read_bytes()
            def confirm(*args, **kwargs):
                self.assertFalse(self.app.reload_config())
                if change == "identity": self.session.import_config(self.path)
                elif change == "typed":
                    config = self.session.draft.config
                    config.extra["typed"][0] = 1
                    self.session.draft.replace_config(config)
                elif change == "history_equal":
                    self.session.draft.add_rule("block_exes", "temporary.exe")
                    self.app.undo_draft()
                else: self.app.picker_active = True
                return True
            self.messages.askyesno.side_effect = confirm
            with patch.object(self.session, "reload", side_effect=AssertionError("new draft lost")):
                self.assertFalse(self.app.reload_config())
            self.assertFalse(self.app.confirming_rule_removal)
            self.assertIs(self.session.snapshot, snapshot)
            self.assertEqual(self.path.read_bytes(), original)
            self.app.picker_active = False
            self.messages.askyesno.side_effect = None
        self.action_fixture()
        self.session.draft.add_rule("block_exes", "dirty.exe")
        def external(*args, **kwargs):
            self.path.write_text(json.dumps({"windows": [], "block_exes": ["external.exe"]}), encoding="utf-8")
            return True
        self.messages.askyesno.side_effect = external
        self.assertTrue(self.app.reload_config())
        self.assertEqual(self.session.draft.config.block_exes, ("external.exe",))
        self.assertFalse(self.session.dirty)

    def test_rule_bulk_selection_view_only_all_visible_indices_all_categories_and_one_undo(self):
        self.bulk_fixture()
        original, snapshot = self.path.read_bytes(), self.session.snapshot
        for category, field in (("Executáveis", "block_exes"), ("Pastas", "block_folders"),
                                ("Proteção adicional", "safelist_exes"), ("Linha de comando", "block_cmdline")):
            with self.subTest(field=field):
                self.app.rule_category.set(category)
                self.app.rule_search.set("dup")
                self.app.change_rule_order("Nome Z–A")
                self.assertTrue(button(self.app, "Selecionar regras").invoke())
                context = self.app.rule_selection_context
                self.assertEqual(context[2], (1, 3))
                config = self.session.draft.config
                with patch.object(self.app, "render_rules", side_effect=AssertionError("render selection")), \
                        patch.object(Path, "read_bytes", side_effect=AssertionError("IO")), \
                        patch.object(self.controller, "start", side_effect=AssertionError("motor")), \
                        patch.object(self.controller, "stop", side_effect=AssertionError("motor")):
                    self.assertTrue(button(self.app, "Selecionar exibidas").invoke())
                    self.assertEqual(self.app.rule_selection_indices, {1, 3})
                    self.assertEqual(self.session.draft.config, config)
                    self.assertFalse(self.session.dirty)
                    self.assertFalse(self.session.draft.can_undo)
                    self.assertIn("2 selecionadas / 2 resultados", self.app.rule_selection_count.options["text"])
                with patch.object(self.session.draft, "remove_rules", wraps=self.session.draft.remove_rules) as remove:
                    self.assertTrue(button(self.app, "Remover selecionadas").invoke())
                    remove.assert_called_once_with(field, (1, 3))
                prompt = self.messages.askyesno.call_args.args[1]
                self.assertIn(category, prompt)
                self.assertIn("2 regra(s)", prompt)
                self.assertIn("rascunho", prompt)
                self.assertEqual(getattr(self.session.draft.config, field),
                                 tuple(value for index, value in enumerate(getattr(config, field)) if index not in (1, 3)))
                self.assertEqual(self.app.rule_selection_indices, set())
                self.assertEqual(self.path.read_bytes(), original)
                self.assertIs(self.session.snapshot, snapshot)
                self.assertTrue(self.app.undo_draft())
                self.assertEqual(self.session.draft.config, config)
                self.assertFalse(self.session.draft.can_undo)
                self.assertTrue(self.app.redo_draft())
                self.assertTrue(self.app.undo_draft())
                self.assertTrue(button(self.app, "Fechar seleção").invoke())

    def test_rule_bulk_selection_unchanged_runtime_poll_does_not_reconfigure_checkboxes(self):
        self.bulk_fixture()
        self.app.begin_rule_selection()
        generation, config = self.app.rule_selection_generation, self.session.draft.config
        self.app.selection_select_all(self.app.rule_selection_context)
        controls = [checkbox for _, _, checkbox in self.app.rule_selection_boxes.values()]
        for control in controls:
            control.configure = Mock(wraps=control.configure)
        for _ in range(3):
            self.app.update_runtime()
        for control in controls:
            control.configure.assert_not_called()
        self.app.picker_active = True
        self.app.update_runtime()
        self.app.update_runtime()
        for control in controls:
            control.configure.assert_called_once_with(state="disabled")
            self.assertEqual(control.cget("state"), "disabled")
            control.configure.reset_mock()
        self.app.picker_active = False
        self.app.update_runtime()
        self.app.update_runtime()
        for control in controls:
            control.configure.assert_called_once_with(state="normal")
        self.assertEqual(self.app.rule_selection_generation, generation)
        self.assertEqual(self.app.rule_selection_indices, {0, 1, 2, 3})
        self.assertEqual(self.session.draft.config, config)

    def test_rule_bulk_selection_checkbox_clear_cancel_empty_and_mode_preserve_redo(self):
        self.bulk_fixture()
        self.session.draft.add_rule("block_exes", "redo.exe")
        self.session.draft.undo()
        self.app.render()
        original, draft, snapshot = self.path.read_bytes(), self.session.draft, self.session.snapshot
        config = draft.config
        self.app.begin_rule_selection()
        self.assertEqual(self.app.rule_selection_actions["remove"].options["state"], "disabled")
        row, variable, checkbox = self.app.rule_selection_boxes[3]
        context = self.app.rule_selection_context
        with patch.object(self.app, "render_rules", side_effect=AssertionError("render")):
            variable.set(1)
            self.assertTrue(checkbox.invoke())
            self.assertEqual(self.app.rule_selection_indices, {3})
            self.messages.askyesno.return_value = False
            self.assertFalse(button(self.app, "Remover selecionadas").invoke())
            self.assertEqual(self.app.rule_selection_indices, {3})
            self.assertFalse(self.app.confirming_rule_removal)
            self.assertTrue(button(self.app, "Limpar seleção").invoke())
            self.assertEqual(variable.get(), 0)
            self.messages.askyesno.reset_mock()
            self.assertFalse(self.app.selection_remove(context))
            self.messages.askyesno.assert_not_called()
        button(self.app, "Fechar seleção").invoke()
        self.assertIs(self.session.draft, draft)
        self.assertIs(self.session.snapshot, snapshot)
        self.assertEqual(draft.config, config)
        self.assertFalse(self.session.dirty)
        self.assertFalse(draft.can_undo)
        self.assertTrue(draft.can_redo)
        self.assertEqual(self.path.read_bytes(), original)
        self.app.rule_search.set("missing")
        self.app.begin_rule_selection()
        self.assertEqual(self.app.rule_selection_actions["all"].options["state"], "disabled")
        self.assertEqual(self.app.rule_selection_actions["remove"].options["state"], "disabled")
        self.assertIn("0 selecionadas / 0 resultados", self.app.rule_selection_count.options["text"])

    def test_rule_bulk_selection_every_render_resets_and_all_old_commands_are_stale(self):
        self.bulk_fixture()
        self.app.begin_rule_selection()
        for change in (lambda: self.app.render_rules(), lambda: self.app.rule_search.set("dup"),
                       lambda: self.app.change_rule_order("Nome A–Z"),
                       lambda: (self.app.rule_category.set("Proteção adicional"), self.app.render_rules()),
                       lambda: self.app.render(), lambda: self.app.undo_draft(),
                       lambda: (self.session.draft.add_rule("block_exes", "redo-history.exe"),
                                self.session.draft.undo(), self.app.redo_draft())):
            # History operations have real edits so they must render.
            if not self.session.draft.can_undo:
                self.session.draft.add_rule("block_exes", "history.exe")
                self.app.render()
            self.app.selection_select_all(self.app.rule_selection_context)
            old = self.app.rule_selection_context
            commands = [control.options["command"] for control in self.app.rule_selection_actions.values()]
            row, variable, checkbox = next(iter(self.app.rule_selection_boxes.values()))
            callback = checkbox.options["command"]
            change()
            self.assertGreater(self.app.rule_selection_generation, old[0])
            self.assertEqual(self.app.rule_selection_indices, set())
            with patch.object(variable, "get", side_effect=AssertionError("old Tk")):
                self.assertFalse(callback())
                for command in commands:
                    self.assertFalse(command())
        old_close = self.app.rule_selection_actions["close"].options["command"]
        self.assertTrue(old_close())
        self.app.begin_rule_selection()
        self.assertFalse(old_close())
        self.assertTrue(self.app.rule_selection_mode)

    def test_rule_bulk_selection_prompt_reentrancy_cancel_and_failure_release_flag(self):
        self.bulk_fixture()
        self.app.begin_rule_selection()
        context = self.app.rule_selection_context
        self.app.selection_select_all(context)
        config = self.session.draft.config
        def confirm(*args, **kwargs):
            self.assertTrue(self.app.confirming_rule_removal)
            self.assertFalse(self.app.selection_remove(context))
            self.assertFalse(self.app.selection_clear(context))
            self.assertFalse(self.app.selection_select_all(context))
            self.assertFalse(self.app.selection_close(context))
            return False
        self.messages.askyesno.side_effect = confirm
        self.assertFalse(self.app.selection_remove(context))
        self.messages.askyesno.assert_called_once()
        self.assertEqual(self.app.rule_selection_indices, {0, 1, 2, 3})
        self.assertEqual(self.session.draft.config, config)
        self.messages.askyesno.side_effect = RuntimeError("dialog error")
        with self.assertRaisesRegex(RuntimeError, "dialog error"):
            self.app.selection_remove(context)
        self.assertFalse(self.app.confirming_rule_removal)
        self.messages.askyesno.side_effect = None
        self.messages.askyesno.return_value = True
        with patch.object(self.session.draft, "remove_rules", side_effect=ConfigError("invalid")):
            self.assertFalse(self.app.selection_remove(context))
        self.assertEqual(self.session.draft.config, config)
        self.assertFalse(self.app.confirming_rule_removal)

    def test_rule_bulk_selection_changes_during_prompt_never_remove_new_or_old_target(self):
        mutations = ("query", "order", "category", "render", "model", "typed_extra", "identity", "undo_redo",
                     "row", "picker", "selecting", "modal", "closing", "closed")
        for mutation in mutations:
            with self.subTest(mutation=mutation):
                self.app.rule_selection_mode = False
                self.app.rule_category.set("Executáveis")
                self.app.rule_search.set("")
                self.bulk_fixture()
                self.app.begin_rule_selection()
                context = self.app.rule_selection_context
                self.app.selection_select_all(context)
                draft = self.session.draft
                def confirm(*args, **kwargs):
                    if mutation == "query": self.app.rule_search.set("dup")
                    elif mutation == "order": self.app.change_rule_order("Nome A–Z")
                    elif mutation == "category":
                        self.app.rule_category.set("Proteção adicional")
                        self.app.render_rules()
                    elif mutation == "render": self.app.render_rules()
                    elif mutation == "model": draft.update_rule("block_exes", 0, "changed.exe")
                    elif mutation == "typed_extra":
                        changed = draft.config
                        changed.extra["typed"][0] = 1
                        draft.replace_config(changed)
                    elif mutation == "identity": self.session.import_config(self.path)
                    elif mutation == "undo_redo":
                        draft.add_rule("block_exes", "temporary.exe")
                        self.app.undo_draft()
                        self.app.redo_draft()
                        self.app.undo_draft()
                    elif mutation == "row": self.app.review_rows[("block_exes", 0)] = Widget()
                    elif mutation == "picker": self.app.picker_active = True
                    elif mutation == "selecting": self.app.selecting_executables = True
                    elif mutation == "modal": self.app.new_dialog("Interrompido")
                    else: setattr(self.app, mutation, True)
                    return True
                self.messages.askyesno.side_effect = confirm
                with patch.object(draft, "remove_rules", side_effect=AssertionError("stale removal")):
                    self.assertFalse(self.app.selection_remove(context))
                self.assertFalse(self.app.confirming_rule_removal)
                self.app.closing = self.app.closed = self.app.picker_active = self.app.selecting_executables = False
                if self.app.modal is not None:
                    button(self.app.modal, "Cancelar").invoke()
                self.messages.askyesno.side_effect = None

    def test_rule_bulk_selection_guards_old_checkbox_and_toolbar_before_tk_even_after_close(self):
        self.bulk_fixture()
        self.app.begin_rule_selection()
        context = self.app.rule_selection_context
        row, variable, checkbox = self.app.rule_selection_boxes[0]
        commands = [control.options["command"] for control in self.app.rule_selection_actions.values()]
        commands.append(checkbox.options["command"])
        for flag in ("picker_active", "selecting_executables", "closing", "closed"):
            setattr(self.app, flag, True)
            with patch.object(variable, "get", side_effect=AssertionError("Tk")), \
                    patch.object(self.app.rule_category, "get", side_effect=AssertionError("Tk")):
                for command in commands:
                    self.assertFalse(command())
                self.assertFalse(self.app.begin_rule_selection())
            setattr(self.app, flag, False)
        self.app.edit_window()
        for command in commands:
            self.assertFalse(command())
        button(self.app.modal, "Cancelar").invoke()
        self.app.close_editor()
        with patch.object(variable, "get", side_effect=AssertionError("destroyed Tk")):
            for command in commands:
                self.assertFalse(command())

    def test_rule_bulk_selection_only_save_changes_bytes_and_external_conflict_is_preserved(self):
        self.bulk_fixture()
        baseline, snapshot = self.path.read_bytes(), self.session.snapshot
        self.app.begin_rule_selection()
        self.app.selection_select_all(self.app.rule_selection_context)
        self.app.selection_remove(self.app.rule_selection_context)
        self.assertEqual(self.path.read_bytes(), baseline)
        self.path.write_text(json.dumps({"windows": [], "block_exes": ["external.exe"]}), encoding="utf-8")
        external = self.path.read_bytes()
        self.assertFalse(self.app.save_config())
        self.assertEqual(self.path.read_bytes(), external)
        self.assertIs(self.session.snapshot, snapshot)
        self.assertTrue(self.session.dirty)
        self.assertTrue(self.session.draft.can_undo)
        self.assertTrue(self.app.undo_draft())
        self.assertEqual(self.session.draft.config.block_exes, ("z.exe", "dup.exe", "hidden.exe", "DUP.exe"))
        self.app.reload_config()
        self.assertEqual(self.session.draft.config.block_exes, ("external.exe",))
        self.assertEqual(self.app.rule_selection_indices, set())

    def test_rule_search_keyboard_focus_preserves_each_category_query_order_without_render(self):
        entry = self.app.rule_search_entry
        entry.focus_set, entry.select_range, entry.icursor = Mock(), Mock(), Mock()
        self.app.change_rule_order("Nome Z–A")
        self.app.rule_search.set(" Existing query ")
        for category in ("Executáveis", "Pastas", "Proteção adicional", "Linha de comando"):
            self.app.rule_category.set(category)
            self.app.tabs.set("Horários")
            with patch.object(self.app, "render_rules", side_effect=AssertionError("render")), \
                    patch.object(self.app, "after", side_effect=AssertionError("timer")):
                self.assertEqual(self.app.callbacks["<Control-f>"](SimpleNamespace()), "break")
            self.assertEqual(self.app.tabs.options["selected_tab"], "Jogos / Apps")
            self.assertEqual(self.app.rule_category.get(), category)
            self.assertEqual(self.app.rule_search.get(), " Existing query ")
            self.assertEqual(self.app.rule_order.get(), "Nome Z–A")
        self.assertEqual(entry.focus_set.call_count, 4)
        self.assertEqual(entry.select_range.call_args_list, [unittest.mock.call(0, "end")] * 4)
        self.assertEqual(entry.icursor.call_args_list, [unittest.mock.call("end")] * 4)

    def test_rule_search_keyboard_clear_once_original_indices_and_empty_noop(self):
        for value in ("z.exe", "a.exe", "A.exe", "b.exe"):
            self.session.draft.add_rule("block_exes", value)
        self.app.render()
        self.app.change_rule_order("Nome Z–A")
        self.app.rule_search.set("a.exe")
        self.assertEqual(self.displayed_rule_indices("block_exes"), [1, 2])
        escape = self.app.rule_search_entry.callbacks["<Escape>"]
        self.assertNotIn("<Escape>", self.app.callbacks)
        with patch.object(self.app, "render_rules", wraps=self.app.render_rules) as render:
            self.assertEqual(escape(SimpleNamespace()), "break")
            render.assert_called_once_with()
            render.reset_mock()
            self.assertFalse(button(self.app, "Limpar").invoke())
            self.assertEqual(escape(SimpleNamespace()), "break")
            render.assert_not_called()
            self.app.rule_search.set("missing")
            render.reset_mock()
            self.assertTrue(button(self.app, "Limpar").invoke())
            render.assert_called_once_with()
        self.assertEqual(self.displayed_rule_indices("block_exes"), [0, 3, 1, 2])
        button(self.app.review_rows[("block_exes", 2)], "Editar").invoke()
        self.assertEqual(self.entries()[0].get(), "A.exe")
        self.app.modal.callbacks["<Escape>"](None)
        self.assertIsNone(self.app.modal)
        self.assertEqual(self.session.draft.config.block_exes, ("z.exe", "a.exe", "A.exe", "b.exe"))

    def test_rule_search_keyboard_view_only_preserves_history_baseline_bytes_and_motor(self):
        for value in ("z.exe", "Code.exe", "Code.exe"):
            self.session.draft.add_rule("block_exes", value)
        self.app.save_config()
        self.app.undo_draft()
        draft, snapshot, config = self.session.draft, self.session.snapshot, self.session.draft.config
        original = self.path.read_bytes()
        state = self.session.dirty, draft.can_undo, draft.can_redo
        generation, review_snapshot = self.app.review_generation, self.app.review_snapshot
        entry = self.app.rule_search_entry
        entry.focus_set, entry.select_range, entry.icursor = Mock(), Mock(), Mock()
        self.app.change_rule_order("Nome A–Z")
        self.app.rule_search.set("code")
        with patch.object(Path, "read_bytes", side_effect=AssertionError("IO")), \
                patch.object(self.session, "save", side_effect=AssertionError("Save")), \
                patch.object(self.controller, "start", side_effect=AssertionError("motor")), \
                patch.object(self.controller, "stop", side_effect=AssertionError("motor")):
            self.app.focus_rule_search()
            button(self.app, "Limpar").invoke()
        self.assertIs(self.session.draft, draft)
        self.assertIs(self.session.snapshot, snapshot)
        self.assertEqual(draft.config, config)
        self.assertEqual((self.session.dirty, draft.can_undo, draft.can_redo), state)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.app.review_generation, generation)
        self.assertIs(self.app.review_snapshot, review_snapshot)
        self.assertEqual(self.app.rule_order.get(), "Nome A–Z")

    def test_rule_search_keyboard_guards_captured_callbacks_before_tk_and_preserves_form_escape(self):
        focus = self.app.callbacks["<Control-f>"]
        escape = self.app.rule_search_entry.callbacks["<Escape>"]
        clear = button(self.app, "Limpar").options["command"]
        event = SimpleNamespace()
        self.app.rule_search.set("keep")
        draft = self.session.draft.config
        self.app.edit_window()
        dialog = self.app.modal
        with patch.object(self.app.tabs, "set", side_effect=AssertionError("Tk")), \
                patch.object(self.app.rule_search, "get", side_effect=AssertionError("Tk")):
            self.assertIsNone(focus(event))
            self.assertIsNone(escape(event))
            self.assertFalse(clear())
        self.assertIs(self.app.modal, dialog)
        dialog.callbacks["<Escape>"](None)
        self.assertIsNone(self.app.modal)
        for flag in ("picker_active", "selecting_executables", "closing", "closed"):
            setattr(self.app, flag, True)
            with patch.object(self.app.tabs, "set", side_effect=AssertionError("Tk")), \
                    patch.object(self.app.rule_search, "get", side_effect=AssertionError("Tk")):
                self.assertIsNone(focus(event))
                self.assertIsNone(escape(event))
                self.assertFalse(clear())
            setattr(self.app, flag, False)
        self.assertEqual(self.app.rule_search.get(), "keep")
        self.app.close_editor()
        with patch.object(self.app.tabs, "set", side_effect=AssertionError("destroyed Tk")), \
                patch.object(self.app.rule_search, "get", side_effect=AssertionError("destroyed Tk")):
            self.assertIsNone(focus(event))
            self.assertIsNone(escape(event))
            self.assertFalse(clear())
        self.assertEqual(self.session.draft.config, draft)

    def test_visual_rule_order_default_stable_ties_search_and_original_crud_indices(self):
        for value in ("z.exe", "a.exe", "A.exe", "b.exe"):
            self.session.draft.add_rule("block_exes", value)
        self.app.render()
        self.assertEqual(self.app.rule_order.get(), "Cadastro")
        self.assertEqual(self.displayed_rule_indices("block_exes"), [0, 1, 2, 3])
        self.app.change_rule_order("Nome A–Z")
        self.assertEqual(self.displayed_rule_indices("block_exes"), [1, 2, 3, 0])
        self.app.change_rule_order("Nome Z–A")
        self.assertEqual(self.displayed_rule_indices("block_exes"), [0, 3, 1, 2])
        self.app.rule_search.set(" A.EXE ")
        self.assertEqual(self.displayed_rule_indices("block_exes"), [1, 2])
        button(self.app.review_rows[("block_exes", 2)], "Editar").invoke()
        self.assertEqual(self.entries()[0].get(), "A.exe")
        self.entries()[0].insert(0, "changed.exe")
        button(self.app.modal, "Aplicar alteração").invoke()
        self.assertEqual(self.session.draft.config.block_exes, ("z.exe", "a.exe", "changed.exe", "b.exe"))
        self.app.rule_search.set("")
        button(self.app.review_rows[("block_exes", 3)], "Remover").invoke()
        self.assertEqual(self.session.draft.config.block_exes, ("z.exe", "a.exe", "changed.exe"))

    def test_visual_rule_order_all_categories_cmdline_pair_and_two_field_search(self):
        for field in ("block_exes", "block_folders", "safelist_exes"):
            values = (r"C:\Zed", r"C:\alpha", r"C:\ALPHA") if field == "block_folders" else ("z.exe", "a.exe", "A.exe")
            for value in values:
                self.session.draft.add_rule(field, value)
        for executable, contains in (("z.exe", "a"), ("a.exe", "Z"), ("a.exe", "a"), ("A.exe", "A")):
            self.session.draft.add_rule("block_cmdline", {"executable": executable, "contains": contains})
        self.app.render()
        self.app.change_rule_order("Nome A–Z")
        for category, field in (("Executáveis", "block_exes"), ("Pastas", "block_folders"),
                                ("Proteção adicional", "safelist_exes")):
            self.app.rule_category.set(category)
            self.app.render_rules()
            self.assertEqual(self.displayed_rule_indices(field), [1, 2, 0])
            self.assertEqual(self.app.rule_order.get(), "Nome A–Z")
        self.app.rule_category.set("Linha de comando")
        self.app.render_rules()
        self.assertEqual(self.displayed_rule_indices("block_cmdline"), [2, 3, 1, 0])
        self.app.change_rule_order("Nome Z–A")
        self.assertEqual(self.displayed_rule_indices("block_cmdline"), [0, 1, 2, 3])
        self.app.rule_search.set("z")
        self.assertEqual(self.displayed_rule_indices("block_cmdline"), [0, 1])

    def test_visual_rule_order_only_changes_view_no_io_dirty_history_review_or_motor(self):
        for value in ("z.exe", "Code.exe", "Code.exe", "a.exe"):
            self.session.draft.add_rule("block_exes", value)
        self.app.save_config()
        self.app.undo_draft()
        self.app.redo_draft()
        self.app.undo_draft()
        snapshot, draft, config = self.session.snapshot, self.session.draft, self.session.draft.config
        original = self.path.read_bytes()
        generation, review_snapshot = self.app.review_generation, self.app.review_snapshot
        dirty, undo, redo = self.session.dirty, draft.can_undo, draft.can_redo
        self.controller.alive = True
        self.controller.value = RuntimeSnapshot(state="running")
        label = next(iter(self.app.review_choices))
        self.app.choose_review(label, generation)
        old_go = self.app.review_go.options["command"]
        with patch.object(Path, "read_bytes", side_effect=AssertionError("IO")), \
                patch.object(self.session, "save", side_effect=AssertionError("Save")), \
                patch.object(self.controller, "start", side_effect=AssertionError("motor")), \
                patch.object(self.controller, "stop", side_effect=AssertionError("motor")):
            for title in ("Nome A–Z", "Nome Z–A", "Cadastro"):
                self.app.change_rule_order(title)
                self.assertEqual(self.app.review_generation, generation)
                self.assertIs(self.app.review_snapshot, review_snapshot)
            self.assertTrue(old_go())
        self.assertIs(self.session.draft, draft)
        self.assertIs(self.session.snapshot, snapshot)
        self.assertEqual(draft.config, config)
        self.assertEqual((self.session.dirty, draft.can_undo, draft.can_redo), (dirty, undo, redo))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.controller.value.state, "running")

    def test_visual_rule_order_navigation_cancels_rows_but_retains_choice_and_order(self):
        for value in ("z.exe", "Code.exe", "a.exe"):
            self.session.draft.add_rule("block_exes", value)
        self.app.render()
        label = next(iter(self.app.review_choices))
        self.app.choose_review(label, self.app.review_generation)
        navigate = self.app.review_go.options["command"]
        self.assertTrue(navigate())
        old_row = self.app.highlighted_row
        old_scroll = old_row.timers[old_row.review_scroll_timer]
        self.app.change_rule_order("Nome A–Z")
        self.assertIsNone(self.app.highlighted_row)
        self.assertTrue(old_row.destroyed)
        self.assertEqual(old_row.timers, {})
        old_scroll()
        self.app.rule_search.set("z")
        self.assertTrue(navigate())
        self.assertEqual(self.app.rule_search.get(), "")
        self.assertEqual(self.app.rule_order.get(), "Nome A–Z")
        self.assertEqual(self.displayed_rule_indices("block_exes"), [2, 1, 0])
        self.assertIs(self.app.highlighted_row, self.app.review_rows[("block_exes", 1)])

    def test_visual_rule_order_guards_and_recalculates_after_history_import_reload(self):
        for value in ("z.exe", "a.exe"):
            self.session.draft.add_rule("block_exes", value)
        self.app.render()
        self.app.change_rule_order("Nome A–Z")
        self.app.edit_rule()
        self.assertEqual(self.app.rule_order_picker.options["state"], "disabled")
        self.app.rule_order.set("Nome Z–A")
        self.assertFalse(self.app.change_rule_order("Nome Z–A"))
        self.assertEqual(self.app.rule_order.get(), "Nome A–Z")
        button(self.app.modal, "Cancelar").invoke()
        for flag in ("picker_active", "selecting_executables", "closing", "closed"):
            setattr(self.app, flag, True)
            self.assertFalse(self.app.change_rule_order("Nome Z–A"))
            setattr(self.app, flag, False)
        self.assertFalse(self.app.change_rule_order("unknown"))
        self.app.undo_draft()
        self.assertEqual(self.displayed_rule_indices("block_exes"), [0])
        self.app.redo_draft()
        self.assertEqual(self.displayed_rule_indices("block_exes"), [1, 0])
        self.import_source(block_exes=["b.exe", "a.exe"])
        self.app.import_config()
        self.assertEqual(self.displayed_rule_indices("block_exes"), [1, 0])
        self.assertEqual(self.app.rule_order.get(), "Nome A–Z")
        self.app.reload_config()
        self.assertEqual(self.displayed_rule_indices("block_exes"), [])
        self.assertEqual(self.app.rule_order.get(), "Nome A–Z")

    def test_review_navigation_disabled_without_link_then_explicit_choice_matches_number(self):
        self.assertEqual(self.app.review_picker.options["state"], "disabled")
        self.assertEqual(self.app.review_go.options["state"], "disabled")
        self.session.draft.add_rule("block_exes", "Code.exe")
        self.session.draft.add_rule("block_exes", "code.exe")
        self.app.render()
        self.assertEqual(len(self.app.review_choices), 3)
        for label, link in self.app.review_choices.items():
            self.assertIn(f"{link.ordinal + 1}. ", self.app.review_detail.get())
            self.assertIn(f"Apontamento {link.ordinal + 1}", label)
        link = next(link for link in self.app.review_choices.values() if link.index == 1)
        self.app.review_picker.options["command"](link.label)
        self.assertIsNone(self.app.highlighted_row)
        self.assertEqual(self.app.tabs.options.get("selected_tab", "Visão geral"), "Visão geral")
        self.assertEqual(self.controller.starts, 0)
        self.assertEqual(self.app.review_go.options["state"], "normal")
        button(self.app, "Ir para item").invoke()
        self.assertIs(self.app.highlighted_row, self.app.review_rows[("block_exes", 1)])
        self.assertIn("item 2", self.app.highlighted_row.review_detail_label.options["text"])
        for _ in range(8):
            self.session.draft.add_rule("block_exes", "Code.exe")
        self.app.render()
        self.assertIsNone(self.app.highlighted_row)
        self.assertEqual(len(self.app.review_choices), 9)  # prefixo10 inclui no_windows sem índice
        self.assertTrue(all(link.ordinal < 10 for link in self.app.review_choices.values()))
        self.assertIn("Mais", self.app.review_detail.get())

    def test_review_navigation_all_fields_uses_original_duplicate_indices_without_io_or_edits(self):
        for _ in range(2):
            self.session.draft.add_window("09:00", "10:00", [0])
            self.session.draft.add_rule("block_exes", "game.exe")
            self.session.draft.add_rule("block_folders", r"C:\Games")
            self.session.draft.add_rule("safelist_exes", "keep.exe")
            self.session.draft.add_rule("block_cmdline", {"executable": "javaw.exe", "contains": " profile "})
        self.app.render()
        snapshot, draft, config = self.session.snapshot, self.session.draft, self.session.draft.config
        original = self.path.read_bytes()
        self.controller.alive = True
        self.controller.value = RuntimeSnapshot(state="running")
        with patch.object(Path, "read_bytes", side_effect=AssertionError("IO")), \
                patch.object(self.session, "save", side_effect=AssertionError("save")), \
                patch.object(self.controller, "start", side_effect=AssertionError("motor")), \
                patch.object(self.controller, "stop", side_effect=AssertionError("motor")):
            for field, category in (("windows", None), ("block_exes", "Executáveis"),
                                    ("block_folders", "Pastas"), ("safelist_exes", "Proteção adicional"),
                                    ("block_cmdline", "Linha de comando")):
                with self.subTest(field=field):
                    if category:
                        self.app.rule_search.set("no results")
                    self.assertTrue(self.app.navigate_review(field, 1))
                    self.assertIs(self.app.highlighted_row, self.app.review_rows[(field, 1)])
                    self.assertIsNot(self.app.highlighted_row, self.app.review_rows[(field, 0)])
                    self.assertEqual(self.app.highlighted_row.options["border_width"], 2)
                    self.assertIsNone(self.app.modal)
                    if category:
                        self.assertEqual(self.app.rule_category.get(), category)
                        self.assertEqual(self.app.rule_search.get(), "")
                        self.assertEqual(self.app.tabs.options["selected_tab"], "Jogos / Apps")
                    else:
                        self.assertEqual(self.app.tabs.options["selected_tab"], "Horários")
        self.assertIs(self.session.snapshot, snapshot)
        self.assertIs(self.session.draft, draft)
        self.assertEqual(draft.config, config)
        self.assertTrue(draft.can_undo)
        self.assertFalse(draft.can_redo)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.controller.value.state, "running")

    def test_review_navigation_filtered_target_retains_crud_original_index(self):
        for value in ("first.exe", "target.exe", "TARGET.EXE", "last.exe"):
            self.session.draft.add_rule("block_exes", value)
        self.app.render()
        self.app.rule_search.set("last")
        with patch.object(self.app, "render_rules", wraps=self.app.render_rules) as rendered:
            self.assertTrue(self.app.navigate_review("block_exes", 2))
            rendered.assert_called_once_with(target_index=2)
        row = self.app.review_rows[("block_exes", 2)]
        button(row, "Editar").invoke()
        self.assertEqual(self.entries()[0].get(), "TARGET.EXE")
        self.entries()[0].insert(0, "changed.exe")
        button(self.app.modal, "Aplicar alteração").invoke()
        self.assertIsNone(self.app.highlighted_row)
        self.assertEqual(self.session.draft.config.block_exes, ("first.exe", "target.exe", "changed.exe", "last.exe"))
        with patch.object(self.app, "render_rule_projection", wraps=self.app.render_rule_projection) as rendered:
            self.assertTrue(self.app.navigate_review("block_exes", 2))
            rendered.assert_called_once_with(0)
        button(self.app.highlighted_row, "Remover").invoke()
        self.assertEqual(self.session.draft.config.block_exes, ("first.exe", "target.exe", "last.exe"))
        self.assertIsNone(self.app.highlighted_row)

    def test_review_navigation_strict_invalid_inputs_modal_picker_closing_guards(self):
        self.session.draft.add_rule("block_exes", "Code.exe")
        self.app.render()
        for field, index in (("unknown", 0), ([], 0), ("block_exes", True), ("block_exes", -1),
                             ("block_exes", 1), ("block_exes", 0.0), ("windows", None)):
            self.assertFalse(self.app.navigate_review(field, index))
        self.app.edit_rule()
        self.assertFalse(self.app.navigate_review("block_exes", 0))
        self.assertEqual(self.app.review_go.options["state"], "disabled")
        button(self.app.modal, "Cancelar").invoke()
        for flag in ("picker_active", "selecting_executables", "closing", "closed"):
            with self.subTest(flag=flag):
                setattr(self.app, flag, True)
                self.assertFalse(self.app.navigate_review("block_exes", 0))
                setattr(self.app, flag, False)
        self.assertIsNone(self.app.highlighted_row)

    def test_review_navigation_stale_same_label_import_undo_redo_reload_and_unrendered_change(self):
        self.import_source(block_exes=["old.exe", "old.exe"])
        self.app.import_config()
        label = next(iter(self.app.review_choices))
        old_select = self.app.review_picker.options["command"]
        old_select(label)
        old_go = self.app.review_go.options["command"]
        self.import_source(block_exes=["new.exe", "new.exe"])
        self.app.import_config()
        self.assertIn(label, self.app.review_choices)
        self.assertFalse(old_select(label))
        self.assertFalse(old_go())
        self.assertIsNone(self.app.highlighted_row)
        self.app.review_picker.options["command"](label)
        old_go = self.app.review_go.options["command"]
        self.session.draft.update_rule("block_exes", 0, "changed.exe")
        self.app.render()
        self.app.undo_draft()
        self.app.redo_draft()
        self.assertFalse(old_go())
        self.assertIsNone(self.app.highlighted_row)
        self.app.undo_draft()
        self.app.review_picker.options["command"](label)
        old_go = self.app.review_go.options["command"]
        self.app.reload_config()
        self.assertFalse(old_go())
        self.assertIsNone(self.app.highlighted_row)
        self.session.draft.add_rule("block_exes", "unrendered.exe")
        self.assertFalse(self.app.navigate_review("block_exes", 0))

    def test_review_navigation_identical_rows_rerender_invalidates_old_callbacks(self):
        for _ in range(3):
            self.session.draft.add_rule("block_exes", "same.exe")
        self.app.render()
        label = next(label for label, link in self.app.review_choices.items() if link.index == 2)
        self.app.review_picker.options["command"](label)
        callback = self.app.review_go.options["command"]
        self.assertTrue(callback())
        self.app.render()
        self.assertIsNone(self.app.highlighted_row)
        self.assertFalse(callback())
        self.assertFalse(self.session.draft.can_redo)

    def test_review_navigation_row_owned_scroll_is_cancelled_and_never_reaches_stale_canvas(self):
        self.session.draft.add_rule("block_exes", "Code.exe")
        self.app.render()
        canvas = SimpleNamespace(bbox=Mock(return_value=(0, 0, 700, 1600)), yview_moveto=Mock())
        self.app.rules_list._parent_canvas = canvas
        root_timers = set(self.app.timers)
        self.assertTrue(self.app.navigate_review("block_exes", 0))
        row = self.app.highlighted_row
        row.winfo_y = Mock(return_value=800)
        callback = row.timers.pop(row.review_scroll_timer)
        callback()
        canvas.yview_moveto.assert_called_once_with(0.5)
        self.assertEqual(set(self.app.timers), root_timers)
        self.assertTrue(self.app.navigate_review("block_exes", 0))
        row = self.app.highlighted_row
        callback = row.timers[row.review_scroll_timer]
        self.app.rule_search.set("no results")
        self.assertEqual(row.timers, {})
        self.assertTrue(row.destroyed)
        callback()
        self.assertEqual(canvas.yview_moveto.call_count, 1)
        self.app.rule_search.set("")
        self.assertTrue(self.app.navigate_review("block_exes", 0))
        row = self.app.highlighted_row
        callback = row.timers[row.review_scroll_timer]
        self.messages.askyesnocancel.return_value = False
        self.app.close_editor()
        callback()
        self.assertEqual(canvas.yview_moveto.call_count, 1)
        self.assertTrue(self.app.closed)

    def test_changes_modal_uses_loaded_baseline_and_preserves_editing_and_motor_without_io(self):
        self.path.write_text(json.dumps({
            "windows": [{"start": "09:00", "end": "10:00", "days": [0]},
                        {"start": "11:00", "end": "12:00", "days": [1]}],
            "block_exes": ["keep.exe", "old.exe"], "block_folders": [r"C:\Games"],
            "safelist_exes": ["keep-safe.exe"],
            "block_cmdline": [{"executable": "javaw.exe", "contains": " old  value "}],
            "private-key": "PRIVATE_VALUE_DO_NOT_SHOW",
        }), encoding="utf-8")
        self.session.reload()
        self.session.draft.update_window(0, "09:00", "11:00", [0])
        self.session.draft.remove_window(1)
        self.session.draft.update_rule("block_exes", 1, "new.exe")
        self.session.draft.add_rule("block_exes", "last.exe")
        self.session.draft.update_rule("block_folders", 0, r"D:\Games")
        self.session.draft.remove_rule("safelist_exes", 0)
        self.session.draft.update_rule("block_cmdline", 0, {"executable": "javaw.exe", "contains": " new  value "})
        self.app.render()
        draft, snapshot = self.session.draft, self.session.snapshot
        state = draft.config
        original = self.path.read_bytes()
        self.controller.alive = True
        self.controller.value = RuntimeSnapshot(state="running")
        with patch.object(Path, "read_bytes", side_effect=AssertionError("releitura")), \
                patch.object(self.session, "save", side_effect=AssertionError("gravação")), \
                patch.object(self.controller, "start", side_effect=AssertionError("motor")), \
                patch.object(self.controller, "stop", side_effect=AssertionError("motor")):
            button(self.app, "Ver alterações").invoke()
            dialog = self.app.modal
            text = dialog.diff_text.get()
            self.assertTrue(dialog.read_only)
            self.assertEqual(dialog.diff_text.options["state"], "disabled")
            self.assertEqual(dialog.diff_text.options["wrap"], "none")
            self.assertEqual(dialog.options["resizable"], (True, True))
            self.assertEqual(dialog.options["minsize"], (620, 420))
            for value in ("Horários", "Executáveis", "Pastas", "Proteção adicional", "Linha de comando",
                          "old.exe", "new.exe", "last.exe", "09:00", "11:00", "' old  value '", "' new  value '"):
                self.assertIn(value, text)
            self.assertNotIn("PRIVATE_VALUE_DO_NOT_SHOW", text)
            self.assertNotIn("private-key", text)
            self.assertIn("salvo 2", text)
            self.assertIn("novo 3", text)
            self.assertIn("Antes", text)
            self.assertIn("Depois", text)
            button(dialog, "Fechar").invoke()
        self.assertIsNone(self.app.modal)
        self.assertTrue(dialog.destroyed)
        self.assertEqual(dialog.timers, {})
        self.assertEqual(self.path.read_bytes(), original)
        self.assertIs(self.session.draft, draft)
        self.assertIs(self.session.snapshot, snapshot)
        self.assertEqual(draft.config, state)
        self.assertTrue(draft.can_undo)
        self.assertTrue(self.session.dirty)
        self.assertTrue(self.controller.alive)
        self.assertEqual(self.controller.value.state, "running")
        self.assertIsNotNone(self.app.status_timer)

    def test_changes_modal_distinguishes_noop_new_empty_and_private_extra_changes(self):
        self.app.show_changes()
        self.assertEqual(self.app.modal.options["title"], "Sem alterações")
        button(self.app.modal, "Fechar").invoke()
        self.path.write_text(json.dumps({"windows": [], "private-key": True}), encoding="utf-8")
        self.session.reload()
        self.import_source(**{"private-key": 1})
        self.app.import_config()
        self.assertTrue(self.session.dirty)
        self.app.show_changes()
        self.assertEqual(self.app.modal.options["title"], "Alterações da configuração")
        self.assertIn("Extras: alterados", self.app.modal.diff_text.get())
        self.assertNotIn("private-key", self.app.modal.diff_text.get())
        button(self.app.modal, "Fechar").invoke()
        self.messages.askyesnocancel.return_value = False
        self.make_new()
        self.app.show_changes()
        self.assertEqual(self.app.modal.options["title"], "Nova configuração")
        self.assertIn("0", self.app.modal.diff_text.get())
        self.assertIn("criad", self.app.modal.diff_text.get())
        button(self.app.modal, "Fechar").invoke()
        self.assertTrue(self.session.is_new)
        self.assertTrue(self.session.dirty)
        self.assertFalse(self.path.exists())

    def test_changes_modal_is_captured_and_reopens_after_history_save_import_reload(self):
        self.session.draft.add_rule("block_exes", "draft.exe")
        self.app.render()
        self.app.show_changes()
        dialog = self.app.modal
        text = dialog.diff_text.get()
        original = self.path.read_bytes()
        self.app.callbacks["<Control-s>"](None)
        self.app.callbacks["<Control-r>"](None)
        self.app.undo_draft()
        self.app.import_config()
        self.assertEqual(dialog.diff_text.get(), text)
        self.assertEqual(self.path.read_bytes(), original)
        self.filedialog.askopenfilename.assert_not_called()
        button(dialog, "Fechar").invoke()
        self.app.undo_draft()
        self.app.show_changes()
        self.assertEqual(self.app.modal.options["title"], "Sem alterações")
        button(self.app.modal, "Fechar").invoke()
        self.app.redo_draft()
        self.app.save_config()
        self.app.show_changes()
        self.assertEqual(self.app.modal.options["title"], "Sem alterações")
        button(self.app.modal, "Fechar").invoke()
        self.app.undo_draft()
        self.app.show_changes()
        self.assertIn("draft.exe", self.app.modal.diff_text.get())
        self.assertIn("removido", self.app.modal.diff_text.get())
        button(self.app.modal, "Fechar").invoke()
        self.import_source(block_exes=["imported.exe"])
        self.app.import_config()
        self.app.show_changes()
        self.assertIn("imported.exe", self.app.modal.diff_text.get())
        button(self.app.modal, "Fechar").invoke()
        self.app.reload_config()
        self.app.show_changes()
        self.assertEqual(self.app.modal.options["title"], "Sem alterações")
        button(self.app.modal, "Fechar").invoke()

    def test_changes_preview_does_not_adopt_external_file_or_bypass_save_conflicts(self):
        self.session.draft.add_rule("block_exes", "draft.exe")
        self.path.write_bytes(b'{"windows":[],"block_exes":["external.exe"]}')
        external = self.path.read_bytes()
        self.app.show_changes()
        text = self.app.modal.diff_text.get()
        self.assertIn("draft.exe", text)
        self.assertNotIn("external.exe", text)
        button(self.app.modal, "Fechar").invoke()
        self.assertFalse(self.app.save_config())
        self.assertEqual(self.path.read_bytes(), external)
        self.assertTrue(self.session.dirty)
        self.app.show_changes()
        self.assertEqual(self.app.modal.diff_text.get(), text)
        button(self.app.modal, "Fechar").invoke()

    def test_changes_modal_guards_existing_form_picker_closing_and_simple_escape(self):
        self.app.edit_rule()
        form = self.app.modal
        self.app.show_changes()
        self.assertIs(self.app.modal, form)
        button(form, "Cancelar").invoke()
        for flag in ("picker_active", "selecting_executables", "closing"):
            setattr(self.app, flag, True)
            self.app.show_changes()
            self.assertIsNone(self.app.modal)
            setattr(self.app, flag, False)
        self.app.show_changes()
        dialog = self.app.modal
        self.assertEqual(self.app.start_button.options["state"], "disabled")
        self.assertEqual(self.app.undo_button.options["state"], "disabled")
        self.assertEqual(self.entries(), [])
        dialog.callbacks["<Escape>"](None)
        self.assertIsNone(self.app.modal)
        self.assertFalse(self.session.dirty)
        self.app.close_editor()
        self.app.show_changes()
        self.assertIsNone(self.app.modal)

    def test_changes_modal_parent_close_preserves_cancel_then_resolves_dirty_and_workers(self):
        self.session.draft.add_rule("block_exes", "draft.exe")
        self.app.show_changes()
        dialog = self.app.modal
        self.messages.askyesnocancel.return_value = None
        self.app.close_editor()
        self.assertIs(self.app.modal, dialog)
        self.assertFalse(self.app.closing)
        self.assertEqual(self.controller.stops, 0)
        self.messages.askyesnocancel.return_value = False
        self.app.close_editor()
        self.assertTrue(self.app.closed)
        self.assertTrue(dialog.destroyed)
        self.assertEqual(dialog.timers, {})
        self.assertEqual(self.app.timers, {})
        self.controller.wait.assert_not_called()
        self.tray.wait.assert_not_called()

    def test_changes_modal_long_values_and_lists_have_explicit_presenter_limits(self):
        for index in range(105):
            self.session.draft.add_rule("block_exes", f"game-{index}.exe")
        self.session.draft.update_rule("block_exes", 0, "very-" + "x" * 1200 + ".exe")
        self.session.draft.add_rule("block_cmdline", {"executable": "javaw.exe", "contains": " value  line "})
        self.app.show_changes()
        text = self.app.modal.diff_text.get()
        self.assertIn("Mais 6", text)
        self.assertIn("truncad", text)
        self.assertIn("game-99.exe", text)
        self.assertNotIn("game-100.exe", text)
        button(self.app.modal, "Fechar").invoke()
        for _ in range(105):
            self.session.draft.remove_rule("block_exes", 0)
        self.session.draft.add_rule("block_exes", "look\u202e.exe")
        self.app.show_changes()
        self.assertIn("' value  line '", self.app.modal.diff_text.get())
        self.assertIn("look\\u202e.exe", self.app.modal.diff_text.get())
        self.assertNotIn("\u202e", self.app.modal.diff_text.get())
        button(self.app.modal, "Fechar").invoke()

    def test_executable_picker_batch_draft_only_dedup_and_save(self):
        original = self.path.read_bytes()
        self.filedialog.askopenfilenames.return_value = (
            r"C:\Games\Game.exe", r"D:\Another\GAME.EXE", r"C:\Games\Second.exe",
        )
        button(self.app, "Selecionar .exe…").invoke()
        self.assertEqual(self.session.draft.config.block_exes, ("Game.exe", "Second.exe"))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertTrue(self.session.dirty)
        self.assertIn("2 executáveis adicionados", self.app.feedback.options["text"])
        self.assertIn("qualquer pasta", self.app.rule_description.options["text"])
        self.assertEqual(self.session.draft.config.extra, {"future": {"keep": "ação"}})
        self.assertEqual(self.controller.starts, 0)
        button(self.app, "Salvar").invoke()
        self.assertEqual(load_config(self.path).block_exes, ("Game.exe", "Second.exe"))

    def test_executable_picker_category_cancel_and_existing_names(self):
        self.app.notify("previous feedback")
        before = self.session.draft.config
        self.app.select_executables()
        self.assertEqual(self.session.draft.config, before)
        self.assertEqual(self.app.feedback.options["text"], "previous feedback")
        self.app.rule_category.set("Proteção adicional")
        self.app.render_rules()
        self.filedialog.askopenfilenames.return_value = (r"C:\Tools\Code.exe",)
        self.app.select_executables()
        self.assertEqual(self.session.draft.config.safelist_exes, ("Code.exe",))
        self.assertEqual(self.session.draft.config.block_exes, ())
        self.assertIn("proteção adicional", self.app.feedback.options["text"])
        self.filedialog.askopenfilenames.return_value = (r"D:\Tools\CODE.EXE",)
        self.app.select_executables()
        self.assertEqual(self.session.draft.config.safelist_exes, ("Code.exe",))
        self.assertIn("já estão", self.app.feedback.options["text"])
        for category in ("Pastas", "Linha de comando"):
            self.app.rule_category.set(category)
            self.app.render_rules()
            self.assertEqual(self.app.executable_picker.options["state"], "disabled")
            self.filedialog.askopenfilenames.reset_mock()
            self.app.select_executables()
            self.filedialog.askopenfilenames.assert_not_called()

    def test_executable_picker_invalid_batch_and_dialog_failure_preserve_draft(self):
        self.session.draft.add_rule("block_exes", "keep.exe")
        before = self.session.draft.config
        self.filedialog.askopenfilenames.return_value = (r"C:\Games\valid.exe", r"C:\Games\invalid.txt")
        self.app.select_executables()
        self.assertEqual(self.session.draft.config, before)
        self.assertIn("Rascunho preservado", self.app.feedback.options["text"])
        self.filedialog.askopenfilenames.side_effect = self.tk.TclError("dialog unavailable")
        self.app.select_executables()
        self.assertEqual(self.session.draft.config, before)
        self.assertFalse(self.app.selecting_executables)
        self.assertEqual(self.app.executable_picker.options["state"], "normal")
        self.assertIn("Não foi possível abrir o seletor", self.app.feedback.options["text"])

    def test_executable_picker_modal_reentrancy_and_close_guards(self):
        button(self.app, "Adicionar regra").invoke()
        self.app.select_executables()
        self.filedialog.askopenfilenames.assert_not_called()
        button(self.app.modal, "Cancelar").invoke()
        def nested_dialog(**kwargs):
            self.assertTrue(self.app.selecting_executables)
            self.assertEqual(self.app.start_button.options["state"], "disabled")
            self.app.start_runtime()
            self.app.select_executables()
            self.assertEqual(self.controller.starts, 0)
            self.messages.askyesnocancel.return_value = False
            self.app.close_editor()
            return (r"C:\Games\late.exe",)
        self.filedialog.askopenfilenames.side_effect = nested_dialog
        self.app.select_executables()
        self.assertEqual(self.filedialog.askopenfilenames.call_count, 1)
        self.assertTrue(self.app.closed)
        self.assertFalse(self.app.selecting_executables)
        self.assertEqual(self.session.draft.config.block_exes, ())

    def test_executable_picker_keeps_category_captured_before_nested_events(self):
        def nested_dialog(**kwargs):
            self.app.rule_category.set("Proteção adicional")
            return (r"C:\Games\chosen.exe",)
        self.filedialog.askopenfilenames.side_effect = nested_dialog
        self.app.select_executables()
        self.assertEqual(self.session.draft.config.block_exes, ("chosen.exe",))
        self.assertEqual(self.session.draft.config.safelist_exes, ())
        self.assertIn("rascunho de bloqueio", self.app.feedback.options["text"])

    def test_pending_tray_ready_during_any_picker_and_after_return_never_hides_root(self):
        original = self.path.read_bytes()
        for kind in ("exe", "import", "export", "folder"):
            with self.subTest(kind=kind):
                self.app.tray_ready = False
                self.tray.alive = False
                self.app.send_to_tray()

                def nested_picker(**kwargs):
                    self.assertTrue(self.app.picker_active)
                    self.mailbox.post("ready")
                    self.fire_timer(self.app.status_timer)
                    self.app.send_to_tray()
                    self.assertFalse(self.app.options["hidden"])
                    self.assertFalse(self.app.tray_pending)
                    self.assertIn("Termine a seleção", self.app.feedback.options["text"])
                    self.assertEqual(self.app.start_button.options["state"], "disabled")
                    self.assertEqual(self.app.undo_button.options["state"], "disabled")
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
                    self.filedialog.askdirectory.side_effect = nested_picker
                    button(self.app.modal, "Escolher pasta…").invoke()
                    button(self.app.modal, "Cancelar").invoke()
                self.assertFalse(self.app.picker_active)
                self.mailbox.post("ready")
                self.fire_timer(self.app.status_timer)
                self.assertFalse(self.app.options["hidden"])
                self.assertEqual(self.path.read_bytes(), original)
                self.assertEqual(self.controller.starts, 0)
        self.app.send_to_tray()
        self.assertTrue(self.app.tray_hidden)

    def test_folder_picker_error_preserves_entry_and_draft_then_retry_succeeds(self):
        self.app.rule_category.set("Pastas")
        self.app.edit_rule()
        entry = self.entries()[0]
        entry.insert(0, r"C:\Keep")
        before = self.session.draft.config
        self.filedialog.askdirectory.side_effect = self.tk.TclError("dialog unavailable")
        button(self.app.modal, "Escolher pasta…").invoke()
        self.assertEqual(entry.get(), r"C:\Keep")
        self.assertEqual(self.session.draft.config, before)
        self.assertIn("Não foi possível abrir o seletor de pasta", self.labels(self.app.modal))
        self.assertFalse(self.app.picker_active)
        self.filedialog.askdirectory.side_effect = None
        button(self.app.modal, "Escolher pasta…").invoke()
        self.assertEqual(entry.get(), r"C:\Games")
        self.assertEqual(self.session.draft.config, before)

    def test_folder_picker_discards_return_when_modal_was_closed_or_replaced(self):
        self.app.rule_category.set("Pastas")
        for replace in (False, True):
            with self.subTest(replace=replace):
                self.app.edit_rule()
                dialog = self.app.modal
                entry = self.entries()[0]
                entry.insert(0, r"C:\Keep")

                def close_modal(**kwargs):
                    button(dialog, "Cancelar").invoke()
                    if replace:
                        self.assertFalse(self.app.edit_rule())  # picker ativo recusa ação normal
                        _, form, *_ = self.app.new_dialog("Modal substituto externo")
                        type(entry)(form).grid(row=0, column=0, sticky="ew")
                    return r"C:\Late"

                self.filedialog.askdirectory.side_effect = close_modal
                button(dialog, "Escolher pasta…").invoke()
                self.assertEqual(entry.get(), r"C:\Keep")
                self.assertFalse(self.app.picker_active)
                self.assertEqual(self.session.draft.config.block_folders, ())
                if replace:
                    self.assertIsNot(self.app.modal, dialog)
                    self.assertEqual(self.entries()[0].get(), "")
                    button(self.app.modal, "Cancelar").invoke()

    def test_folder_picker_late_return_after_close_never_touches_entry(self):
        self.app.rule_category.set("Pastas")
        self.app.edit_rule()
        dialog = self.app.modal
        entry = self.entries()[0]
        entry.insert(0, r"C:\Keep")

        def close_app(**kwargs):
            self.app.close_editor()
            return r"C:\Late"

        self.filedialog.askdirectory.side_effect = close_app
        button(dialog, "Escolher pasta…").invoke()
        self.assertTrue(self.app.closed)
        self.assertEqual(entry.get(), r"C:\Keep")
        self.assertFalse(self.app.picker_active)
        self.assertEqual(self.session.draft.config.block_folders, ())

    def test_import_export_picker_errors_preserve_draft_feedback_and_busy_state(self):
        before = self.session.draft.config
        for choose, action in ((self.filedialog.askopenfilename, self.app.import_config),
                               (self.filedialog.asksaveasfilename, self.app.export_config)):
            with self.subTest(action=action.__name__):
                choose.side_effect = self.tk.TclError("dialog unavailable")
                action()
                self.assertIn("Não foi possível abrir o seletor", self.app.feedback.options["text"])
                self.assertEqual(self.session.draft.config, before)
                self.assertFalse(self.app.picker_active)

    def test_import_extra_bool_to_int_is_dirty_and_prompts_before_close_then_saves_type(self):
        self.path.write_text(json.dumps({"windows": [], "future": {"keep": True}}), encoding="utf-8")
        self.session.reload()
        self.app.render()
        original = self.path.read_bytes()
        self.import_source(future={"keep": 1})
        self.app.import_config()
        self.assertTrue(self.session.dirty)
        self.assertIs(type(self.session.draft.config.extra["future"]["keep"]), int)
        self.assertIn("Alterações não salvas", self.app.dirty_label.options["text"])
        self.messages.askyesnocancel.return_value = None
        self.app.close_editor()
        self.messages.askyesnocancel.assert_called_once()
        self.assertFalse(self.app.closed)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.controller.starts, 0)
        self.assertTrue(self.app.save_config())
        self.assertFalse(self.session.dirty)
        self.assertIs(type(load_config(self.path).extra["future"]["keep"]), int)
        self.messages.askyesnocancel.reset_mock()
        self.app.close_editor()
        self.messages.askyesnocancel.assert_not_called()
        self.assertTrue(self.app.closed)

    def test_current_agenda_end_uses_saved_union_not_draft_and_updates_after_save(self):
        now = real_datetime(2026, 10, 12, 10)
        self.session.draft.add_window("09:00", "11:00", [0])
        self.session.draft.add_window("11:00", "12:00", [0])
        self.session.save()
        with patch("ui.config_gui.datetime", SimpleNamespace(now=lambda: now)):
            self.app.refresh_status(schedule=False)
            self.assertIn("12/10/2026 às 12:00", self.app.end_label.options["text"])
            self.session.draft.update_window(1, "11:00", "13:00", [0])
            self.app.refresh_status(schedule=False)
            self.assertIn("às 12:00", self.app.end_label.options["text"])
            self.app.save_config()
            self.assertIn("às 13:00", self.app.end_label.options["text"])
        self.assertEqual(self.controller.starts, 0)

    def test_current_agenda_end_distinguishes_inactive_continuous_and_new(self):
        self.assertIn("Nenhuma janela carregada", self.app.end_label.options["text"])
        self.session.draft.add_window("00:00", "12:00")
        self.session.draft.add_window("12:00", "00:00")
        self.session.save()
        self.app.refresh_status(schedule=False)
        self.assertIn("cobertura semanal contínua", self.app.end_label.options["text"])
        self.make_new()
        self.assertIn("Nenhuma janela salva", self.app.end_label.options["text"])

    def test_config_review_follows_draft_without_writing_or_blocking_save_start(self):
        original = self.path.read_bytes()
        self.session.draft.add_window("09:00", "12:00", [0])
        self.session.draft.add_rule("block_exes", "code.exe")
        self.session.draft.add_rule("safelist_exes", "game.exe")
        self.session.draft.add_rule("block_exes", "GAME.EXE")
        self.app.render()
        detail = self.app.review_detail.get()
        self.assertIn("proteção obrigatória", detail)
        self.assertIn("Proteção adicional preserva", detail)
        self.assertIn("sem verificar processos", detail)
        self.assertEqual(self.app.review_detail.options["state"], "disabled")
        self.assertEqual(self.path.read_bytes(), original)
        self.assertIn("2 regras cadastradas", self.app.review_title.options["text"])
        self.app.save_config()
        self.app.start_runtime()
        self.assertEqual(self.controller.starts, 1)

    def test_config_review_bounds_long_lists_and_updates_after_removal(self):
        for _ in range(18):
            self.session.draft.add_rule("block_exes", "game.exe")
        self.app.render()
        self.assertIn("Mais", self.app.review_detail.get())
        self.assertLessEqual(len(self.app.review_detail.get().splitlines()), 12)
        for index in range(17, 0, -1):
            self.session.draft.remove_rule("block_exes", index)
        self.app.render()
        self.assertNotIn("Regra repetida", self.app.review_detail.get())
        self.assertNotIn("Mais", self.app.review_detail.get())

    def test_undo_redo_buttons_shortcuts_and_save_keep_file_explicit(self):
        original = self.path.read_bytes()
        self.assertEqual(self.app.undo_button.options["state"], "disabled")
        self.filedialog.askopenfilenames.return_value = (r"C:\Games\one.exe", r"C:\Games\two.exe")
        self.app.select_executables()
        self.assertEqual(self.app.undo_button.options["state"], "normal")
        self.assertEqual(self.app.callbacks["<Control-z>"](None), "break")
        self.assertFalse(self.session.dirty)
        self.assertEqual(self.session.draft.config.block_exes, ())
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.app.redo_button.options["state"], "normal")
        self.assertEqual(self.app.callbacks["<Control-y>"](None), "break")
        self.app.save_config()
        saved = self.path.read_bytes()
        button(self.app, "Desfazer").invoke()
        self.assertTrue(self.session.dirty)
        self.assertEqual(self.path.read_bytes(), saved)
        self.assertEqual(self.controller.starts, 0)

    def test_suggestions_preserve_previous_history_and_undo_as_one_edit(self):
        self.session.draft.add_rule("block_exes", "existing.exe")
        self.app.suggestion_vars["steam"].set(1)
        self.app.suggestion_vars["minecraft_java"].set(1)
        self.app.add_suggestions()
        self.app.undo_draft()
        self.assertEqual(self.session.draft.config.block_exes, ("existing.exe",))
        self.assertEqual(self.session.draft.config.block_cmdline, ())
        self.app.undo_draft()
        self.assertFalse(self.session.dirty)
        self.app.redo_draft()
        self.app.redo_draft()
        self.assertEqual(self.session.draft.config.block_exes, ("existing.exe", "steam.exe"))

    def test_history_guards_modal_picker_text_focus_and_late_close(self):
        self.session.draft.add_rule("block_exes", "game.exe")
        self.app.render()
        before = self.session.draft.config
        button(self.app, "Adicionar regra").invoke()
        self.assertEqual(self.app.undo_button.options["state"], "disabled")
        self.assertFalse(self.app.undo_draft())
        button(self.app.modal, "Cancelar").invoke()
        event = SimpleNamespace(widget=SimpleNamespace(winfo_class=lambda: "Entry"))
        self.assertIsNone(self.app.callbacks["<Control-z>"](event))
        self.assertEqual(self.session.draft.config, before)
        def picker(**kwargs):
            self.assertEqual(self.app.undo_button.options["state"], "disabled")
            self.assertFalse(self.app.undo_draft())
            return ()
        self.filedialog.askopenfilenames.side_effect = picker
        self.app.select_executables()
        self.assertEqual(self.session.draft.config, before)
        self.messages.askyesnocancel.return_value = False
        self.app.close_editor()
        self.assertFalse(self.app.undo_draft())
        self.assertIsNone(self.app.callbacks["<Control-z>"](event))

    def test_history_restore_failure_is_visible_and_keeps_draft(self):
        self.session.draft.add_rule("block_exes", "game.exe")
        before = self.session.draft.config
        with patch.object(self.session.draft, "undo", side_effect=ConfigError("validation")):
            self.assertFalse(self.app.undo_draft())
        self.assertEqual(self.session.draft.config, before)
        self.assertIn("Rascunho preservado", self.app.feedback.options["text"])

    def test_import_reload_reset_history_but_save_preserves_it(self):
        self.session.draft.add_rule("block_exes", "original.exe")
        self.app.save_config()
        self.assertEqual(self.app.undo_button.options["state"], "normal")
        self.import_source(block_exes=["imported.exe"])
        self.app.import_config()
        self.assertEqual(self.app.undo_button.options["state"], "disabled")
        self.assertEqual(self.app.redo_button.options["state"], "disabled")
        self.session.draft.add_rule("block_exes", "next.exe")
        self.app.reload_config()
        self.assertEqual(self.app.undo_button.options["state"], "disabled")
        self.assertEqual(self.session.draft.config.block_exes, ("original.exe",))

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

    def fire_timer(self, token):
        callback = self.app.timers.pop(token)
        callback()

    def make_new(self):
        self.app.close_editor()
        self.path.unlink()
        self.session = ConfigSession.for_new(self.path)
        self.controller = FakeController(self.path)
        self.mailbox = TrayMailbox()
        self.tray = FakeTray()
        self.app = _build_app(fake_ctk(), SimpleNamespace(IntVar=Variable), self.filedialog,
                              self.messages, self.session, controller=self.controller,
                              tray=self.tray, mailbox=self.mailbox)

    def test_first_configuration_empty_unsaved_and_start_impossible_before_explicit_save(self):
        self.make_new()
        self.assertTrue(self.session.is_new)
        self.assertTrue(self.session.dirty)
        self.assertEqual(self.session.draft.config.windows, ())
        self.assertEqual(self.session.draft.config.block_exes, ())
        self.assertTrue(all(variable.get() == 0 for variable in self.app.suggestion_vars.values()))
        self.assertIn(str(self.path.absolute()), self.app.setup_note.options["text"])
        self.assertEqual(self.app.agenda_label.options["text"], "Agenda ainda não salva")
        self.assertEqual(self.app.start_button.options["state"], "disabled")
        self.app.start_runtime()
        self.assertEqual(self.controller.starts, 0)
        self.messages.askyesno.assert_not_called()
        self.assertIn("Salvar", self.app.feedback.options["text"])
        self.assertFalse(self.path.exists())
        self.add_window("09:00", "11:00")
        self.assertEqual(self.app.agenda_label.options["text"], "Agenda ainda não salva")
        self.assertIn("14 h 00 min", self.app.preview_summary.options["text"])
        self.app.callbacks["<Control-s>"](None)
        self.assertFalse(self.session.is_new)
        self.assertFalse(self.session.dirty)
        self.assertEqual(self.controller.starts, 0)
        self.assertEqual(len(load_config(self.path).windows), 1)
        self.assertNotIn("ainda não", self.app.setup_note.options["text"])
        self.assertEqual(self.app.start_button.options["state"], "normal")
        self.messages.askyesno.return_value = False
        self.app.start_runtime()
        self.assertEqual(self.controller.starts, 0)
        self.messages.askyesno.return_value = True
        self.app.start_runtime()
        self.assertEqual(self.controller.starts, 1)

    def test_first_configuration_suggestions_are_opt_in_draft_only_and_editable(self):
        self.make_new()
        before = self.session.draft
        button(self.app, "Adicionar selecionadas").invoke()
        self.assertIs(self.session.draft, before)
        self.app.suggestion_vars["steam"].set(1)
        self.app.suggestion_vars["minecraft_java"].set(1)
        button(self.app, "Adicionar selecionadas").invoke()
        config = self.session.draft.config
        self.assertEqual(config.block_exes, ("steam.exe",))
        self.assertEqual([(rule.executable, rule.contains) for rule in config.block_cmdline],
                         [("javaw.exe", ".minecraft")])
        self.assertEqual(config.windows, ())
        self.assertTrue(all(variable.get() == 0 for variable in self.app.suggestion_vars.values()))
        self.assertFalse(self.path.exists())
        self.assertEqual(self.controller.starts, 0)
        self.app.rule_category.set("Linha de comando")
        self.app.render_rules()
        button(self.app.rules_list, "Editar").invoke()
        executable, contains = self.entries()
        self.assertEqual(executable.get(), "javaw.exe")
        self.assertEqual(contains.get(), ".minecraft")
        contains.insert(0, "custom-profile")
        button(self.app.modal, "Aplicar alteração").invoke()
        self.assertEqual(self.session.draft.config.block_cmdline[0].contains, "custom-profile")
        button(self.app.rules_list, "Remover").invoke()
        self.assertEqual(self.session.draft.config.block_cmdline, ())

    def test_suggestions_preserve_existing_rules_extras_and_are_blocked_during_modal_or_close(self):
        original = self.path.read_bytes()
        self.session.draft.add_rule("block_exes", "STEAM.EXE")
        self.app.suggestion_vars["steam"].set(1)
        button(self.app, "Adicionar regra").invoke()
        button(self.app, "Adicionar selecionadas").invoke()
        self.assertEqual(self.app.suggestion_vars["steam"].get(), 1)
        button(self.app.modal, "Cancelar").invoke()
        button(self.app, "Adicionar selecionadas").invoke()
        self.assertEqual(self.session.draft.config.block_exes, ("STEAM.EXE",))
        self.assertEqual(self.session.draft.config.extra, {"future": {"keep": "ação"}})
        self.assertEqual(self.path.read_bytes(), original)
        self.app.suggestion_vars["valorant"].set(1)
        self.messages.askyesnocancel.return_value = False
        self.app.close_editor()
        self.app.add_suggestions()
        self.assertEqual(self.session.draft.config.block_exes, ("STEAM.EXE",))

    def test_suggestions_validation_failure_preserves_draft_and_selection(self):
        self.app.suggestion_vars["steam"].set(1)
        before = self.session.draft
        with patch("ui.config_gui.with_process_suggestions", side_effect=ConfigError("catálogo inválido")):
            self.app.add_suggestions()
        self.assertIs(self.session.draft, before)
        self.assertEqual(self.app.suggestion_vars["steam"].get(), 1)
        self.assertIn("Rascunho preservado", self.app.feedback.options["text"])

    def test_first_configuration_import_export_reload_and_external_creation(self):
        self.make_new()
        self.import_source(block_exes=["imported.exe"], future={"preserved": True})
        button(self.app, "Importar JSON").invoke()
        self.assertTrue(self.session.is_new)
        self.assertEqual(self.app.agenda_label.options["text"], "Agenda ainda não salva")
        destination = self.root / "export.json"
        self.filedialog.asksaveasfilename.return_value = str(destination)
        button(self.app, "Exportar JSON").invoke()
        self.assertEqual(load_config(destination).block_exes, ("imported.exe",))
        self.assertFalse(self.path.exists())
        self.assertTrue(self.session.is_new)
        draft = self.session.draft
        self.messages.askyesno.return_value = False
        button(self.app, "Recarregar").invoke()
        self.assertIs(self.session.draft, draft)
        self.messages.askyesno.return_value = True
        button(self.app, "Recarregar").invoke()
        self.assertIs(self.session.draft, draft)
        self.assertTrue(self.session.is_new)
        self.assertIn("Rascunho preservado", self.app.feedback.options["text"])
        self.path.write_text('{"windows":[],"block_exes":["external.exe"]}', encoding="utf-8")
        self.assertFalse(self.app.save_config())
        self.assertIs(self.session.draft, draft)
        self.assertTrue(self.session.is_new)
        self.assertEqual(load_config(self.path).block_exes, ("external.exe",))
        button(self.app, "Recarregar").invoke()
        self.assertFalse(self.session.is_new)
        self.assertEqual(self.session.draft.config.block_exes, ("external.exe",))
        self.assertEqual(self.controller.starts, 0)
        self.assertIn("Agenda carregada", self.app.agenda_label.options["text"])

    def test_first_configuration_save_failure_retry_and_close_save_create_explicitly(self):
        self.make_new()
        self.app.suggestion_vars["steam"].set(1)
        self.app.add_suggestions()
        self.messages.askyesnocancel.return_value = True
        with patch.object(self.session, "save", side_effect=ConfigError("permissão negada")):
            self.app.close_editor()
        self.assertFalse(self.app.closed)
        self.assertTrue(self.session.is_new)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.controller.stops, 0)
        self.app.close_editor()
        self.assertTrue(self.app.closed)
        self.assertFalse(self.session.is_new)
        self.assertEqual(load_config(self.path).block_exes, ("steam.exe",))
        self.assertEqual(self.controller.starts, 0)

    def test_first_configuration_tray_cancel_then_discard_exit_never_creates_json(self):
        self.make_new()
        button(self.app, "Enviar à bandeja").invoke()
        self.mailbox.post("ready")
        self.fire_timer(self.app.status_timer)
        self.assertTrue(self.app.tray_hidden)
        self.mailbox.post("close")
        self.fire_timer(self.app.status_timer)
        self.assertFalse(self.app.tray_hidden)
        self.assertFalse(self.app.closing)
        self.assertEqual(self.tray.stops, 0)
        self.assertFalse(self.path.exists())
        self.messages.askyesnocancel.return_value = False
        self.app.close_editor()
        self.assertFalse(self.app.closed)
        self.tray.alive = False
        self.fire_timer(self.app.close_timer)
        self.assertTrue(self.app.closed)
        self.assertFalse(self.path.exists())
        self.assertEqual(self.controller.starts, 0)
        self.controller.wait.assert_not_called()
        self.tray.wait.assert_not_called()

    def test_tray_hides_only_after_ready_and_keeps_draft_and_motor(self):
        button(self.app, "Iniciar").invoke()
        self.session.draft.add_rule("block_exes", "pending.exe")
        draft = self.session.draft.config
        button(self.app, "Enviar à bandeja").invoke()
        self.assertEqual(self.tray.starts, 1)
        self.assertTrue(self.app.tray_pending)
        self.assertFalse(self.app.options.get("hidden", False))
        button(self.app, "Enviar à bandeja").invoke()
        self.assertEqual(self.tray.starts, 1)
        self.mailbox.post("ready")
        self.fire_timer(self.app.status_timer)
        self.assertTrue(self.app.tray_hidden)
        self.assertTrue(self.app.options["hidden"])
        self.assertTrue(self.controller.alive)
        self.assertEqual(self.session.draft.config, draft)
        self.controller.wait.assert_not_called()
        self.tray.wait.assert_not_called()
        self.mailbox.post("show")
        self.fire_timer(self.app.status_timer)
        self.assertFalse(self.app.options["hidden"])
        button(self.app, "Enviar à bandeja").invoke()
        self.assertTrue(self.app.options["hidden"])
        self.assertEqual(self.tray.starts, 1)

    def test_tray_error_timeout_and_unexpected_exit_keep_or_restore_visibility(self):
        button(self.app, "Enviar à bandeja").invoke()
        self.mailbox.post("error", "startup falhou")
        self.fire_timer(self.app.status_timer)
        self.assertFalse(self.app.options["hidden"])
        self.assertFalse(self.app.tray_pending)
        self.assertIn("startup falhou", self.app.feedback.options["text"])
        self.mailbox.post("ready")
        self.fire_timer(self.app.status_timer)
        self.assertFalse(self.app.options["hidden"])
        self.tray.alive = False
        button(self.app, "Enviar à bandeja").invoke()
        self.app.tray_deadline = 0
        self.fire_timer(self.app.status_timer)
        self.assertIn("10 segundos", self.app.feedback.options["text"])
        self.assertFalse(self.app.options["hidden"])
        self.tray.alive = False
        button(self.app, "Enviar à bandeja").invoke()
        self.mailbox.post("ready")
        self.fire_timer(self.app.status_timer)
        self.assertTrue(self.app.options["hidden"])
        self.tray.alive = False
        self.fire_timer(self.app.status_timer)
        self.assertFalse(self.app.options["hidden"])
        self.assertIn("inesperadamente", self.app.feedback.options["text"])

    def test_tray_menu_commands_execute_only_on_tk_poll_and_close_cancel_restores(self):
        button(self.app, "Iniciar").invoke()
        button(self.app, "Enviar à bandeja").invoke()
        self.mailbox.post("ready")
        self.fire_timer(self.app.status_timer)
        self.session.draft.add_rule("block_exes", "pending.exe")
        self.messages.askyesnocancel.side_effect = lambda *args, **kwargs: (
            self.assertFalse(self.app.options["hidden"]) or None
        )
        self.mailbox.post("close")
        self.assertEqual(self.controller.stops, 0)
        self.assertTrue(self.app.options["hidden"])
        self.fire_timer(self.app.status_timer)
        self.assertFalse(self.app.options["hidden"])
        self.assertTrue(self.controller.alive)
        self.assertTrue(self.tray.alive)
        self.assertFalse(self.app.closing)
        self.mailbox.post("stop")
        self.assertEqual(self.controller.stops, 0)
        self.fire_timer(self.app.status_timer)
        self.assertEqual(self.controller.stops, 1)
        self.assertFalse(self.app.closing)

    def test_late_native_add_error_restores_hidden_window_while_tray_worker_is_alive(self):
        button(self.app, "Iniciar").invoke()
        button(self.app, "Enviar à bandeja").invoke()
        self.mailbox.post("ready")
        self.fire_timer(self.app.status_timer)
        self.assertTrue(self.app.options["hidden"])
        self.mailbox.post("error", "O Windows recusou criar o ícone da bandeja (NIM_ADD)")
        self.assertTrue(self.app.options["hidden"])
        self.fire_timer(self.app.status_timer)
        self.assertFalse(self.app.options["hidden"])
        self.assertTrue(self.tray.alive)
        self.assertEqual(self.tray.stops, 1)
        self.assertTrue(self.controller.alive)
        self.assertEqual(self.controller.stops, 0)
        self.assertIn("NIM_ADD", self.app.feedback.options["text"])

    def test_ready_during_modal_does_not_hide_or_discard_form(self):
        button(self.app, "Enviar à bandeja").invoke()
        button(self.app, "Adicionar horário").invoke()
        modal = self.app.modal
        self.entries()[0].insert(0, "09:00")
        self.mailbox.post("ready")
        self.mailbox.post("show")
        self.fire_timer(self.app.status_timer)
        self.assertFalse(self.app.options["hidden"])
        self.assertIs(self.app.modal, modal)
        self.assertEqual(self.entries()[0].get(), "09:00")
        self.assertFalse(self.app.tray_pending)
        button(modal, "Cancelar").invoke()

    def test_close_waits_for_both_workers_and_late_mailbox_posts_have_no_effect(self):
        button(self.app, "Iniciar").invoke()
        button(self.app, "Enviar à bandeja").invoke()
        self.mailbox.post("ready")
        self.fire_timer(self.app.status_timer)
        self.app.callbacks["WM_DELETE_WINDOW"]()
        self.assertTrue(self.app.closing)
        self.assertFalse(self.app.options["hidden"])
        self.assertEqual(self.tray.stops, 1)
        self.controller.finish()
        self.fire_timer(self.app.close_timer)
        self.assertFalse(self.app.destroyed)
        self.mailbox.post("ready")
        self.mailbox.post("show")
        self.assertEqual(self.mailbox.drain(), ())
        self.tray.alive = False
        self.fire_timer(self.app.close_timer)
        self.assertTrue(self.app.destroyed)
        self.controller.wait.assert_not_called()
        self.tray.wait.assert_not_called()

    def test_default_controller_is_constructed_for_saved_path_without_start(self):
        controller = FakeController()
        with patch("ui.config_gui.ProcessController", return_value=controller) as constructor:
            app = _build_app(fake_ctk(), SimpleNamespace(IntVar=Variable), self.filedialog,
                             self.messages, self.session)
        constructor.assert_called_once_with(self.path)
        self.assertIs(app.controller, controller)
        self.assertEqual(controller.starts, 0)
        self.assertEqual(controller.stops, 0)
        controller.wait.assert_not_called()
        self.assertIn("Motor parado", app.runtime_title.options["text"])

    def test_runtime_requires_clean_draft_and_explicit_risk_confirmation(self):
        self.session.draft.add_rule("block_exes", "pending.exe")
        self.app.render()
        button(self.app, "Iniciar").invoke()
        self.assertEqual(self.controller.starts, 0)
        self.messages.askyesno.assert_not_called()
        self.assertIn("Salve", self.app.feedback.options["text"])
        self.assertIn("Recarregar", self.app.feedback.options["text"])
        self.app.save_config()
        self.messages.askyesno.return_value = False
        button(self.app, "Iniciar").invoke()
        self.assertEqual(self.controller.starts, 0)
        prompt = self.messages.askyesno.call_args.args[1]
        self.assertIn("sem salvar seu estado", prompt)
        self.assertIn("JSON salvo", prompt)
        self.messages.askyesno.return_value = True
        button(self.app, "Iniciar").invoke()
        self.assertEqual(self.controller.starts, 1)
        self.assertEqual(self.controller.started_config.block_exes, ("pending.exe",))
        self.assertIn("Motor em execução", self.app.runtime_title.options["text"])
        self.assertEqual(self.app.start_button.options["state"], "disabled")
        self.assertEqual(self.app.stop_button.options["state"], "normal")
        button(self.app, "Iniciar").invoke()
        self.assertEqual(self.controller.starts, 1)
        self.controller.wait.assert_not_called()

    def test_runtime_uses_persisted_external_json_not_session_baseline_or_import(self):
        self.path.write_text(json.dumps({"windows": [], "block_exes": ["external.exe"]}), encoding="utf-8")
        button(self.app, "Iniciar").invoke()
        self.assertEqual(self.controller.started_config.block_exes, ("external.exe",))
        self.assertEqual(self.session.snapshot.config.block_exes, ())
        self.controller.stop()
        self.controller.finish()
        self.import_source(block_exes=["draft-only.exe"])
        button(self.app, "Importar JSON").invoke()
        button(self.app, "Iniciar").invoke()
        self.assertEqual(self.controller.starts, 1)
        self.assertEqual(load_config(self.path).block_exes, ("external.exe",))

    def test_stop_polling_preserves_last_agenda_and_is_nonblocking(self):
        button(self.app, "Iniciar").invoke()
        self.controller.value = RuntimeSnapshot(state="running", active=True,
                                                last_scan=real_datetime(2026, 10, 11, 9))
        agenda = self.app.agenda_label.options["text"]
        preview = self.app.preview_summary.options["text"]
        button(self.app, "Parar").invoke()
        self.assertTrue(self.controller.is_alive())
        self.assertIn("Motor parando", self.app.runtime_title.options["text"])
        self.assertIn("dentro da janela", self.app.runtime_detail.get())
        self.assertEqual(self.app.agenda_label.options["text"], agenda)
        self.assertEqual(self.app.preview_summary.options["text"], preview)
        self.assertEqual(self.app.start_button.options["state"], "disabled")
        self.assertEqual(self.app.stop_button.options["state"], "disabled")
        self.controller.wait.assert_not_called()
        # O snapshot pode ser publicado no finally antes do retorno da thread.
        self.controller.value = replace(self.controller.value, state="idle")
        self.app.refresh_status(schedule=False)
        self.assertIn("Motor parando", self.app.runtime_title.options["text"])
        self.controller.finish()
        self.fire_timer(self.app.status_timer)
        self.assertIn("Motor parado", self.app.runtime_title.options["text"])
        self.assertIn("dentro da janela", self.app.runtime_detail.get())
        self.assertEqual(self.app.start_button.options["state"], "normal")
        self.assertEqual(len(self.app.timers), 1)
        self.app.refresh_status(schedule=False)
        self.assertEqual(len(self.app.timers), 1)

    def test_error_retry_waits_for_worker_exit_and_requires_new_confirmation(self):
        button(self.app, "Iniciar").invoke()
        self.controller.value = RuntimeSnapshot(state="error", error="JSON inválido", active=True)
        self.fire_timer(self.app.status_timer)
        self.assertIn("Motor com erro", self.app.runtime_title.options["text"])
        self.assertIn("JSON inválido", self.app.runtime_detail.get())
        self.assertIn("dentro da janela", self.app.runtime_detail.get())
        self.assertEqual(self.app.start_button.options["state"], "disabled")
        button(self.app, "Iniciar").invoke()
        self.assertEqual(self.controller.starts, 1)
        self.controller.alive = False
        self.fire_timer(self.app.status_timer)
        self.assertEqual(self.app.start_button.options["state"], "normal")
        self.messages.askyesno.reset_mock()
        button(self.app, "Iniciar").invoke()
        self.messages.askyesno.assert_called_once()
        self.assertEqual(self.controller.starts, 2)
        self.controller.wait.assert_not_called()

    def test_runtime_presenter_detail_stays_readonly_and_scrollable(self):
        detail = "diagnóstico longo\n" * 20
        view = SimpleNamespace(title="Motor com erro", detail=detail, start_enabled=True, stop_enabled=False)
        with patch("ui.config_gui.format_runtime", return_value=view) as presenter:
            self.app.refresh_status(schedule=False)
        presenter.assert_called_once_with(self.controller.snapshot())
        self.assertEqual(self.app.runtime_detail.get(), detail)
        self.assertEqual(self.app.runtime_detail.options["state"], "disabled")
        self.assertEqual(self.app.runtime_detail.options["height"], 62)

    def test_modal_blocks_start_but_stop_does_not_discard_form(self):
        button(self.app, "Iniciar").invoke()
        button(self.app, "Adicionar horário").invoke()
        dialog = self.app.modal
        self.entries()[0].insert(0, "09:00")
        self.app.start_runtime()
        self.assertEqual(self.controller.starts, 1)
        self.app.stop_runtime()
        self.assertIs(self.app.modal, dialog)
        self.assertEqual(self.entries()[0].get(), "09:00")
        self.assertIn("Motor parando", self.app.runtime_title.options["text"])
        button(dialog, "Cancelar").invoke()
        self.assertFalse(self.session.dirty)

    def test_cancel_close_keeps_worker_modal_and_timers_running(self):
        button(self.app, "Iniciar").invoke()
        self.session.draft.add_rule("block_exes", "pending.exe")
        button(self.app, "Adicionar horário").invoke()
        modal = self.app.modal
        timer = self.app.status_timer
        self.messages.askyesnocancel.return_value = None
        self.app.close_editor()
        self.assertEqual(self.controller.stops, 0)
        self.assertTrue(self.controller.alive)
        self.assertFalse(self.app.closing)
        self.assertFalse(self.app.destroyed)
        self.assertIs(self.app.modal, modal)
        self.assertEqual(self.app.status_timer, timer)
        self.controller.wait.assert_not_called()

    def test_save_conflict_on_close_keeps_worker_then_success_stops_before_destroy(self):
        button(self.app, "Iniciar").invoke()
        baseline = self.path.read_bytes()
        self.session.draft.add_rule("block_exes", "pending.exe")
        self.path.write_bytes(b'{"windows":[],"external":true}')
        self.messages.askyesnocancel.return_value = True
        self.app.close_editor()
        self.assertEqual(self.controller.stops, 0)
        self.assertFalse(self.app.closing)
        self.assertTrue(self.controller.alive)
        self.path.write_bytes(baseline)
        self.app.close_editor()
        self.assertEqual(self.controller.stops, 1)
        self.assertFalse(self.session.dirty)
        self.assertEqual(load_config(self.path).block_exes, ("pending.exe",))
        self.assertFalse(self.app.destroyed)
        self.assertIsNone(self.app.status_timer)
        self.assertIsNotNone(self.app.close_timer)
        self.controller.finish()
        self.fire_timer(self.app.close_timer)
        self.assertTrue(self.app.destroyed)
        self.assertEqual(self.app.timers, {})
        self.controller.wait.assert_not_called()

    def test_discard_close_waits_and_prevents_all_new_actions_and_stale_form_apply(self):
        button(self.app, "Iniciar").invoke()
        self.session.draft.add_window("09:00", "10:00", [0])
        self.app.render()
        original = self.path.read_bytes()
        draft = self.session.draft.config
        button(self.app, "Adicionar regra").invoke()
        dialog = self.app.modal
        apply = button(dialog, "Adicionar").options["command"]
        self.messages.askyesnocancel.return_value = False
        self.app.close_editor()
        self.assertTrue(self.app.closing)
        self.assertFalse(self.app.destroyed)
        self.assertTrue(dialog.destroyed)
        self.assertEqual(dialog.timers, {})
        for child in descendants(self.app):
            if child.__class__.__name__ in ("CTkButton", "CTkEntry", "CTkCheckBox", "CTkOptionMenu"):
                self.assertEqual(child.options["state"], "disabled")
        self.messages.askyesno.reset_mock()
        self.app.start_runtime()
        self.app.stop_runtime()
        self.app.close_editor()
        self.app.edit_window()
        self.app.edit_rule()
        self.app.duplicate_window(0)
        self.app.remove_item("windows", 0)
        self.app.import_config()
        self.app.export_config()
        self.app.change_week(7)
        self.app.callbacks["<Control-s>"](None)
        self.app.callbacks["<Control-r>"](None)
        apply()
        self.assertIsNone(self.app.modal)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(self.session.draft.config, draft)
        self.assertEqual(self.controller.starts, 1)
        self.assertEqual(self.controller.stops, 1)
        self.messages.askyesno.assert_not_called()
        self.filedialog.askopenfilename.assert_not_called()
        self.filedialog.asksaveasfilename.assert_not_called()
        self.fire_timer(self.app.close_timer)
        self.assertFalse(self.app.destroyed)
        self.assertEqual(len(self.app.timers), 1)
        self.controller.finish()
        self.fire_timer(self.app.close_timer)
        self.assertTrue(self.app.destroyed)
        self.assertEqual(self.app.timers, {})
        self.controller.wait.assert_not_called()

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
        self.assertIn("Buscar regras · Ctrl+F · Esc limpa", self.labels(self.app))

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

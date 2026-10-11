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
                                          asksaveasfilename=Mock(return_value=""))
        self.controller = FakeController(self.path)
        self.mailbox = TrayMailbox()
        self.tray = FakeTray()
        self.app = _build_app(fake_ctk(), SimpleNamespace(IntVar=Variable), self.filedialog,
                              self.messages, self.session, controller=self.controller,
                              tray=self.tray, mailbox=self.mailbox)

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

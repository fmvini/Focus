"""Dispatch gráfico, isolamento dos modos e erros sem dependência gráfica."""

import builtins
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from core.config import ConfigError, default_config
from core.instance_guard import InstanceGuardError
import main
from ui.config_gui import run_config_gui


class ConfigGuiMainTests(unittest.TestCase):
    def setUp(self):
        self.guard = Mock()
        self.guard.acquire.return_value = True
        guard_patch = patch("ui.config_gui.InstanceGuard", return_value=self.guard)
        guard_patch.start()
        self.addCleanup(guard_patch.stop)

    def test_second_instance_or_guard_failure_prevents_session_tk_and_workers(self):
        for outcome in (False, InstanceGuardError("mutex indisponível")):
            with self.subTest(outcome=outcome):
                self.guard.reset_mock()
                self.guard.acquire.side_effect = outcome if isinstance(outcome, Exception) else None
                self.guard.acquire.return_value = outcome
                with patch("ui.config_gui._run_guarded_config_gui", side_effect=AssertionError("sessão/Tk")):
                    with patch("ui.config_gui.ProcessController", side_effect=AssertionError("motor")):
                        with redirect_stderr(io.StringIO()) as output:
                            self.assertEqual(run_config_gui("isolated.json"), 1)
                self.assertIn("Erro", output.getvalue())
                self.guard.release.assert_called_once_with()

    def test_guard_acquired_before_session_and_released_after_both_workers_and_window(self):
        import tkinter as tk

        for failure in (None, tk.TclError("erro Tk"), KeyboardInterrupt(), RuntimeError("loop")):
            with self.subTest(failure=type(failure).__name__):
                order = []
                self.guard.acquire.side_effect = lambda: order.append("acquire") or True
                self.guard.release.side_effect = lambda: order.append("release")
                controller, tray, mailbox = Mock(), Mock(), Mock()
                for resource, name in ((controller, "motor"), (tray, "tray")):
                    resource.stop.side_effect = lambda label=name: order.append(label + ".stop")
                    resource.wait.side_effect = lambda label=name: order.append(label + ".wait")
                mailbox.close.side_effect = lambda: order.append("mailbox.close")

                def loop():
                    order.append("mainloop")
                    if failure is not None:
                        raise failure

                app = SimpleNamespace(mainloop=loop, finish_close=lambda: order.append("destroy"))
                ctk = SimpleNamespace(set_appearance_mode=Mock(), set_default_color_theme=Mock())
                with patch.dict(sys.modules, {"customtkinter": ctk}):
                    with patch("ui.config_gui.ConfigSession", side_effect=lambda path: (
                        order.append("session") or SimpleNamespace(path=Path(path))
                    )):
                        with patch("ui.config_gui.ProcessController", return_value=controller):
                            with patch("ui.config_gui.WindowsTray", return_value=tray):
                                with patch("ui.config_gui.TrayMailbox", return_value=mailbox):
                                    with patch("ui.config_gui._build_app", return_value=app):
                                        if isinstance(failure, (KeyboardInterrupt, RuntimeError)):
                                            with self.assertRaises(type(failure)):
                                                run_config_gui("isolated.json")
                                        else:
                                            with redirect_stderr(io.StringIO()):
                                                self.assertEqual(run_config_gui("isolated.json"), 1 if failure else 0)
                self.assertEqual(order, ["acquire", "session", "mainloop", "mailbox.close", "motor.stop",
                                         "tray.stop", "motor.wait", "tray.wait", "destroy", "release"])
                controller.start.assert_not_called()
                tray.start.assert_not_called()

    def test_guard_release_failure_is_reported_and_dependency_error_releases_guard(self):
        self.guard.release.side_effect = InstanceGuardError("close handle")
        with patch("ui.config_gui._run_guarded_config_gui", return_value=0):
            with redirect_stderr(io.StringIO()) as output:
                self.assertEqual(run_config_gui("isolated.json"), 1)
        self.assertIn("close handle", output.getvalue())
        self.guard.release.side_effect = None
        self.guard.reset_mock()
        with patch.dict(sys.modules, {"customtkinter": None}):
            with redirect_stderr(io.StringIO()):
                self.assertEqual(run_config_gui("isolated.json"), 1)
        self.guard.release.assert_called_once_with()

    def test_dispatch_passes_path_and_propagates_result_without_process_loading(self):
        for result in (0, 1):
            with self.subTest(result=result):
                module = ModuleType("ui.config_gui")
                calls = []
                module.run_config_gui = lambda path: calls.append(path) or result
                with patch.dict(sys.modules, {"ui.config_gui": module}):
                    with patch("main.load_config", side_effect=AssertionError("carga na CLI")):
                        with patch("main._create_process_blocker", side_effect=AssertionError("bloqueador")):
                            self.assertEqual(main.main(["--config", "custom.json", "--gui"]), result)
                self.assertEqual(calls, [Path("custom.json")])

    def test_default_path_is_forwarded(self):
        calls = []
        module = ModuleType("ui.config_gui")
        module.run_config_gui = lambda path: calls.append(path) or 0
        with patch.dict(sys.modules, {"ui.config_gui": module}):
            with patch("main.default_config_path", return_value=Path("isolated/config.json")):
                self.assertEqual(main.main(["--gui"]), 0)
        self.assertEqual(calls, [Path("isolated/config.json")])

    def test_conflicting_flags_reject_before_file_access_or_import(self):
        modes = (["--init-config"], ["--check"], ["--status"], ["--watch"],
                 ["--apply-processes"], ["--edit-config"], ["--at", "2026-10-09T09:00:00"])
        for mode in modes:
            for args in (["--gui", *mode], [*mode, "--gui"]):
                with self.subTest(args=args):
                    with patch("main.default_config_path", side_effect=AssertionError("IO")):
                        with patch.dict(sys.modules, {"ui.config_gui": None}):
                            with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                                main.main(args)
                    self.assertEqual(error.exception.code, 2)

    def test_gui_module_import_does_not_require_graphics_or_process_libraries(self):
        original_import = builtins.__import__

        def guarded(name, *args, **kwargs):
            if name.startswith(("customtkinter", "tkinter", "psutil", "pystray", "PIL")) or name == "core.proc_blocker":
                raise AssertionError(f"importação antecipada: {name}")
            return original_import(name, *args, **kwargs)

        path = Path(main.__file__).resolve().parent / "ui/config_gui.py"
        with patch("builtins.__import__", side_effect=guarded):
            spec = importlib.util.spec_from_file_location("_gui_lazy_test", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        self.assertTrue(callable(module.run_config_gui))

    def test_diagnostics_and_help_do_not_import_graphical_dependencies(self):
        original_import = builtins.__import__

        def guarded(name, *args, **kwargs):
            if name.startswith(("customtkinter", "tkinter")) or name == "ui.config_gui":
                raise AssertionError(f"GUI importada no diagnóstico: {name}")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=guarded):
            with patch("main.load_config", return_value=default_config()):
                with patch("main.time.sleep", side_effect=KeyboardInterrupt):
                    for args in (["--status"], ["--check"], ["--watch"]):
                        with redirect_stdout(io.StringIO()):
                            self.assertEqual(main.main(["--config", "unused.json", *args]), 0)
            with redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as error:
                main.main(["--help"])
            self.assertEqual(error.exception.code, 0)

    def test_missing_graphical_dependency_is_actionable_without_io(self):
        with patch.dict(sys.modules, {"customtkinter": None}):
            with patch("ui.config_gui.ConfigSession", side_effect=AssertionError("IO")):
                with redirect_stderr(io.StringIO()) as output:
                    self.assertEqual(run_config_gui("unused.json"), 1)
        self.assertIn("pip install -r requirements.txt", output.getvalue())

    def test_invalid_config_does_not_create_a_window_or_replace_file(self):
        ctk = SimpleNamespace()
        with patch.dict(sys.modules, {"customtkinter": ctk}):
            with patch("ui.config_gui.ConfigSession", side_effect=ConfigError("JSON inválido")):
                with patch("ui.config_gui._build_app", side_effect=AssertionError("janela")):
                    with redirect_stderr(io.StringIO()) as output:
                        self.assertEqual(run_config_gui("unused.json"), 1)
        self.assertIn("JSON inválido", output.getvalue())

    def test_gui_ctrl_c_is_reported_as_editor_exit(self):
        with patch("main.default_config_path", side_effect=KeyboardInterrupt):
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main.main(["--gui"]), 0)
        self.assertIn("Editor encerrado", output.getvalue())

    def test_gui_finally_stops_and_waits_outside_mainloop_on_every_exit(self):
        import tkinter as tk

        for failure in (None, tk.TclError("Tk indisponível"), KeyboardInterrupt(), RuntimeError("mainloop falhou")):
            with self.subTest(failure=type(failure).__name__):
                order = []
                controller = Mock()
                controller.stop.side_effect = lambda: order.append("stop")
                controller.wait.side_effect = lambda: order.append("wait")

                def mainloop():
                    order.append("mainloop")
                    if failure is not None:
                        raise failure

                app = SimpleNamespace(mainloop=mainloop,
                                      finish_close=lambda: order.append("destroy"))
                ctk = SimpleNamespace(set_appearance_mode=Mock(), set_default_color_theme=Mock())
                session = SimpleNamespace(path=Path("saved.json"))
                with patch.dict(sys.modules, {"customtkinter": ctk}):
                    with patch("ui.config_gui.ConfigSession", return_value=session):
                        with patch("ui.config_gui.ProcessController", return_value=controller) as constructor:
                            with patch("ui.config_gui._build_app", return_value=app) as build:
                                if isinstance(failure, (KeyboardInterrupt, RuntimeError)):
                                    with self.assertRaises(type(failure)):
                                        run_config_gui("saved.json")
                                else:
                                    with redirect_stderr(io.StringIO()):
                                        self.assertEqual(run_config_gui("saved.json"), 1 if failure else 0)
                constructor.assert_called_once_with(session.path)
                self.assertIs(build.call_args.kwargs["controller"], controller)
                controller.start.assert_not_called()
                controller.stop.assert_called_once_with()
                controller.wait.assert_called_once_with()
                self.assertEqual(order, ["mainloop", "stop", "wait", "destroy"])

    def test_gui_construction_error_still_signals_stop_and_waits(self):
        import tkinter as tk

        controller = Mock()
        ctk = SimpleNamespace(set_appearance_mode=Mock(), set_default_color_theme=Mock())
        with patch.dict(sys.modules, {"customtkinter": ctk}):
            with patch("ui.config_gui.ConfigSession", return_value=SimpleNamespace(path=Path("saved.json"))):
                with patch("ui.config_gui.ProcessController", return_value=controller):
                    with patch("ui.config_gui._build_app", side_effect=tk.TclError("falha de criação")):
                        with redirect_stderr(io.StringIO()):
                            self.assertEqual(run_config_gui("saved.json"), 1)
        controller.start.assert_not_called()
        controller.stop.assert_called_once_with()
        controller.wait.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()

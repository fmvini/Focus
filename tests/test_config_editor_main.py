"""Flags e importações da CLI, sem bloqueadores ou perfil reais."""

import builtins
from contextlib import redirect_stderr, redirect_stdout
import importlib.util
import io
from pathlib import Path
import sys
import unittest
from types import ModuleType
from unittest.mock import patch

from core.config import default_config
import main


class ConfigEditorMainTests(unittest.TestCase):
    def test_editor_dispatch_is_lazy_and_passes_explicit_path(self):
        module = ModuleType("ui.config_cli")
        calls = []
        module.run_config_editor = lambda path: calls.append(path) or 0
        with patch.dict(sys.modules, {"ui.config_cli": module}):
            with patch("main.load_config", side_effect=AssertionError("carga fora do editor")):
                with patch("main._create_process_blocker", side_effect=AssertionError("bloqueador")):
                    code = main.main(["--config", "custom.json", "--edit-config"])
        self.assertEqual(code, 0)
        self.assertEqual(len(calls), 1)
        self.assertEqual(str(calls[0]), "custom.json")

    def test_editor_uses_default_path_and_propagates_return_code(self):
        module = ModuleType("ui.config_cli")
        for result in (0, 1):
            with self.subTest(result=result):
                calls = []
                module.run_config_editor = lambda path: calls.append(path) or result
                with patch.dict(sys.modules, {"ui.config_cli": module}):
                    with patch("main.default_config_path", return_value=Path("isolated/config.json")) as default:
                        code = main.main(["--edit-config"])
                self.assertEqual(code, result)
                default.assert_called_once_with()
                self.assertEqual(calls, [Path("isolated/config.json")])

    def test_editor_ctrl_c_before_dispatch_has_editor_message(self):
        output = io.StringIO()
        with patch("main.default_config_path", side_effect=KeyboardInterrupt):
            with redirect_stdout(output):
                code = main.main(["--edit-config"])
        self.assertEqual(code, 0)
        self.assertIn("Editor encerrado", output.getvalue())
        self.assertIn("não salvas descartadas", output.getvalue())

    def test_import_main_and_ui_package_does_not_import_editor_dependencies(self):
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name in ("ui.config_cli", "core.config_editor", "core.config_repository",
                        "core.proc_blocker") or name.startswith("psutil"):
                raise AssertionError(f"importação antecipada: {name}")
            return original_import(name, *args, **kwargs)

        project = Path(main.__file__).resolve().parent
        with patch("builtins.__import__", side_effect=guarded_import):
            for path in (project / "main.py", project / "ui" / "__init__.py"):
                with self.subTest(path=path):
                    spec = importlib.util.spec_from_file_location("_lazy_import_test", path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)

    def test_diagnostics_and_help_do_not_import_editor(self):
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name == "ui" or name.startswith("ui.") or name in (
                "core.config_editor", "core.config_repository", "core.proc_blocker",
            ) or name.startswith("psutil"):
                raise AssertionError(f"importação proibida no diagnóstico: {name}")
            return original_import(name, *args, **kwargs)

        cases = ([], ["--status"], ["--check"],
                 ["--at", "2026-10-05T09:00:00"], ["--watch"])
        with patch("builtins.__import__", side_effect=guarded_import):
            with patch("main.load_config", return_value=default_config()):
                with patch("main.time.sleep", side_effect=KeyboardInterrupt):
                    for args in cases:
                        with self.subTest(args=args), redirect_stdout(io.StringIO()):
                            self.assertEqual(main.main(["--config", "unused.json", *args]), 0)
            with patch("main.default_config_path", side_effect=AssertionError("IO")):
                with redirect_stdout(io.StringIO()) as output, self.assertRaises(SystemExit) as raised:
                    main.main(["--help"])
            self.assertEqual(raised.exception.code, 0)
            self.assertIn("--edit-config", output.getvalue())
            self.assertIn("rascunho", output.getvalue())

    def test_importing_editor_does_not_import_process_blockers(self):
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name == "core.proc_blocker" or name.startswith("psutil"):
                raise AssertionError(f"bloqueador importado pelo editor: {name}")
            return original_import(name, *args, **kwargs)

        path = Path(main.__file__).resolve().parent / "ui" / "config_cli.py"
        with patch("builtins.__import__", side_effect=guarded_import):
            spec = importlib.util.spec_from_file_location("_editor_import_test", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        self.assertTrue(callable(module.run_config_editor))

    def test_editor_flag_combinations_are_rejected_before_io_or_import(self):
        invalid_options = (
            "--init-config", "--check", "--status", "--at", "--watch",
            "--apply-processes",
        )
        cases = []
        for option in invalid_options:
            mode = [option, "2026-10-05T09:00:00"] if option == "--at" else [option]
            cases.extend([["--edit-config", *mode], [*mode, "--edit-config"]])
        cases.extend([
            ["--edit-config", "--watch", "--apply-processes"],
            ["--edit-config", "--unknown"],
        ])
        for argv in cases:
            with self.subTest(argv=argv):
                output = io.StringIO()
                with patch("main.default_config_path", side_effect=AssertionError("IO")):
                    with patch.dict(sys.modules, {"ui.config_cli": None}):
                        with redirect_stderr(output), self.assertRaises(SystemExit) as raised:
                            main.main(argv)
                self.assertEqual(raised.exception.code, 2)
                self.assertIn("--edit-config", output.getvalue())


if __name__ == "__main__":
    unittest.main()

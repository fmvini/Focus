"""Review CLI real, somente leitura, com importações e modos isolados."""

from contextlib import redirect_stdout, redirect_stderr
import io
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

from core.config import _serialize_config
from core.models import AppConfig, ScheduleWindow
from datetime import time
import main


class ConfigReviewCliTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / f".editor-integration-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = self.root / "config.json"
        self.path.write_bytes(_serialize_config(AppConfig(
            windows=(ScheduleWindow(time(9), time(12), (0,)),), block_exes=("game.exe",),
        )))

    def run_review(self, *args):
        stdout, stderr = io.StringIO(), io.StringIO()
        with redirect_stdout(stdout), redirect_stderr(stderr):
            result = main.main(["--config", str(self.path), "--review", *args])
        return result, stdout.getvalue(), stderr.getvalue()

    def test_valid_configuration_readonly_counts_and_no_process_clock_or_watch(self):
        original = self.path.read_bytes()
        with patch("main.datetime") as clock, patch("main.time.sleep", side_effect=AssertionError("watch")), \
                patch("main._create_process_blocker", side_effect=AssertionError("motor")):
            code, stdout, stderr = self.run_review()
            clock.now.assert_not_called()
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Horários ativos: 1", stdout)
        self.assertIn("Nenhum apontamento estático", stdout)
        self.assertNotIn("Consulta local:", stdout)
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.root.iterdir()), [self.path])

    def test_informative_findings_return_zero_with_original_indices_without_writing(self):
        self.path.write_bytes(_serialize_config(AppConfig(block_exes=("CODE.EXE", "code.exe"))))
        original = self.path.read_bytes()
        code, stdout, stderr = self.run_review()
        self.assertEqual((code, stderr), (0, ""))
        self.assertIn("Executáveis, item 2: Regra repetida do item 1", stdout)
        self.assertIn("proteção obrigatória", stdout)
        self.assertIn("Apontamentos informativos:", stdout)
        self.assertEqual(self.path.read_bytes(), original)

    def test_invalid_and_missing_configuration_return_one_and_do_not_recover_file(self):
        self.path.write_bytes(b"invalid")
        code, stdout, stderr = self.run_review()
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("Erro:", stderr)
        self.assertEqual(self.path.read_bytes(), b"invalid")
        self.path.unlink()
        code, _, stderr = self.run_review()
        self.assertEqual(code, 1)
        self.assertIn("Erro:", stderr)
        self.assertFalse(self.path.exists())

    def test_conflicting_modes_reject_before_path_io_or_review_import(self):
        for mode in (["--gui"], ["--edit-config"], ["--init-config"], ["--check"], ["--status"],
                     ["--watch"], ["--apply-processes"], ["--at", "2026-10-12T09:00:00"]):
            for args in (["--review", *mode], [*mode, "--review"]):
                with self.subTest(args=args), patch("main.default_config_path", side_effect=AssertionError("IO")), \
                        patch.dict(sys.modules, {"ui.config_review_cli": None}), \
                        redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
                    main.main(args)
                self.assertEqual(caught.exception.code, 2)

    def test_default_config_path_forwarded_and_output_callback_supported(self):
        with patch("main.default_config_path", return_value=self.path):
            with redirect_stdout(io.StringIO()) as output:
                self.assertEqual(main.main(["--review"]), 0)
        self.assertIn(str(self.path), output.getvalue())
        from ui.config_review_cli import run_config_review
        lines = []
        self.assertEqual(run_config_review(self.path, output_fn=lines.append), 0)
        self.assertIn("Revisão da configuração salva", lines[0])

    def test_fresh_process_review_and_help_do_not_import_graphics_or_process_libraries(self):
        script = '''
import builtins,sys
original = builtins.__import__
def guarded(name,*args,**kwargs):
    if name.startswith(('psutil','tkinter','customtkinter','pystray','PIL')) or name in ('core.proc_blocker','core.process_controller','ui.config_gui'):
        raise AssertionError(name)
    return original(name,*args,**kwargs)
builtins.__import__ = guarded
import main
assert main.main(['--config',sys.argv[1],'--review']) == 0
try:
    main.main(['--help'])
except SystemExit as exc:
    assert exc.code == 0
'''
        result = subprocess.run([sys.executable, "-B", "-c", script, str(self.path)],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--review", result.stdout)

    def test_interrupt_during_read_exits_cleanly_without_starting_anything(self):
        with patch("ui.config_review_cli.load_config", side_effect=KeyboardInterrupt):
            code, stdout, stderr = self.run_review()
        self.assertEqual(code, 0)
        self.assertEqual(stderr, "")
        self.assertIn("Diagnóstico encerrado por Ctrl+C", stdout)

    def test_restricted_stdout_encoding_returns_one_and_preserves_unicode_configuration(self):
        unicode_path = self.root / "日本語.json"
        original = self.path.read_bytes()
        unicode_path.write_bytes(original)
        encoded = io.BytesIO()
        stderr = io.StringIO()
        with io.TextIOWrapper(encoded, encoding="cp1252", write_through=True) as stdout:
            with redirect_stdout(stdout), redirect_stderr(stderr):
                result = main.main(["--config", str(unicode_path), "--review"])
        self.assertEqual(result, 1)
        self.assertIn("Erro:", stderr.getvalue())
        self.assertNotIn("Traceback", stderr.getvalue())
        self.assertEqual(unicode_path.read_bytes(), original)
        self.assertEqual(set(self.root.iterdir()), {self.path, unicode_path})


if __name__ == "__main__":
    unittest.main()

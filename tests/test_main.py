"""Testes da CLI, sempre com configuração/perfil em diretório temporário."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
import io
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from uuid import uuid4

import main as cli


class MainTests(unittest.TestCase):
    def setUp(self):
        # mkdir com permissões herdadas: mode 0700 de TemporaryDirectory no
        # Python 3.14/Windows impede acesso pelo token restrito do sandbox.
        self.root = Path(__file__).resolve().parents[1] / f".phase1-cli-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = self.root / "config.json"
        self.env = patch.dict(os.environ, {"APPDATA": str(self.root / "profile")})
        self.env.start()
        self.addCleanup(self.env.stop)

    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--config", str(self.path), *args])
        return code, out.getvalue(), err.getvalue()

    def write_config(self, windows=None):
        self.path.write_text(json.dumps({"windows": windows or []}), encoding="utf-8")

    def test_init_creates_empty_config_only_on_explicit_request(self):
        code, out, err = self.invoke("--init-config")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), {"windows": []})
        self.assertIn("sem janelas ativas", out)

    def test_init_refuses_existing_valid_and_corrupt_files(self):
        for payload in (b'{"windows": []}', b'{"windows": broken'):
            with self.subTest(payload=payload):
                self.path.write_bytes(payload)
                code, _, err = self.invoke("--init-config", "--check")
                self.assertEqual(code, 1)
                self.assertIn("não será sobrescrita", err)
                self.assertEqual(self.path.read_bytes(), payload)

    def test_init_refuses_existing_directory(self):
        self.path.mkdir()
        code, _, err = self.invoke("--init-config")
        self.assertEqual(code, 1)
        self.assertTrue(self.path.is_dir())
        self.assertIn("Erro:", err)

    def test_init_exclusive_creation_preserves_concurrent_file(self):
        original_open = Path.open
        payload = b'{"windows": [], "other": "concurrent"}'

        def race_open(path, mode="r", *args, **kwargs):
            if path == self.path and mode == "x":
                with original_open(path, "wb") as stream:
                    stream.write(payload)
            return original_open(path, mode, *args, **kwargs)

        with patch.object(Path, "open", race_open):
            code, _, err = self.invoke("--init-config")
        self.assertEqual(code, 1)
        self.assertIn("não será sobrescrita", err)
        self.assertEqual(self.path.read_bytes(), payload)

    def test_init_write_failure_describes_partial_creation_limit(self):
        class BrokenWriter(io.StringIO):
            def write(self, value):
                raise OSError("disco cheio simulado")

        with patch.object(Path, "open", return_value=BrokenWriter()):
            code, _, err = self.invoke("--init-config")
        self.assertEqual(code, 1)
        self.assertIn("pode estar incompleto", err)
        self.assertIn("disco cheio simulado", err)

    def test_missing_config_is_error_without_creation(self):
        code, _, err = self.invoke("--check")
        self.assertEqual(code, 1)
        self.assertIn("Erro:", err)
        self.assertFalse(self.path.exists())

    def test_invalid_json_and_schema_are_preserved(self):
        for payload in (b'{bad', b'{"windows":[{"start":"09:00","end":"09:00"}]}'):
            with self.subTest(payload=payload):
                self.path.write_bytes(payload)
                code, _, err = self.invoke("--check", "--status")
                self.assertEqual(code, 1)
                self.assertIn("Erro:", err)
                self.assertEqual(self.path.read_bytes(), payload)

    def test_check_does_not_compute_status_or_change_config(self):
        self.write_config()
        original = self.path.read_bytes()
        with patch.object(cli, "is_blocking") as state:
            code, out, err = self.invoke("--check")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Configuração válida para a fase 1", out)
        state.assert_not_called()
        self.assertEqual(self.path.read_bytes(), original)

    def test_status_is_default_and_claims_only_calculated_state(self):
        self.write_config()
        with patch.object(cli, "datetime") as clock:
            clock.now.return_value = datetime(2026, 10, 5, 12)
            code, out, err = self.invoke()
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Estado calculado da agenda: fora da janela", out)
        self.assertIn("não aplica bloqueios ao Windows", out)
        self.assertIn("Próximo início efetivo: nenhum", out)

    def test_at_uses_explicit_datetime_without_reading_clock(self):
        self.write_config([{"start": "09:00", "end": "10:00", "days": [0]}])
        with patch.object(cli, "datetime", wraps=datetime) as clock:
            code, out, err = self.invoke("--at", "2026-10-05T09:00:00")
        self.assertEqual((code, err), (0, ""))
        clock.now.assert_not_called()
        self.assertIn("Estado calculado da agenda: dentro da janela", out)

    def test_argument_errors_precede_io_and_writes(self):
        cases = [
            ["--at", "invalid"], ["--at", "2026-10-05"],
            ["--at", "2026-10-05T09:00:00Z"],
            ["--at", "2026-10-05T09:00:00-03:00"],
            ["--at", "2026-10-05T09:00:00", "--watch"],
            ["--unknown"],
        ]
        for args in cases:
            with self.subTest(args=args):
                with self.assertRaises(SystemExit) as raised:
                    self.invoke("--init-config", *args)
                self.assertEqual(raised.exception.code, 2)
                self.assertFalse(self.path.exists())

    def test_init_check_status_can_be_combined(self):
        code, out, err = self.invoke("--init-config", "--check", "--status")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("Configuração criada", out)
        self.assertIn("Configuração válida", out)
        self.assertIn("Estado calculado", out)

    def test_watch_reloads_and_stops_on_keyboard_interrupt_without_wait(self):
        self.write_config()
        with patch.object(cli.time, "sleep", side_effect=[None, KeyboardInterrupt]) as sleep:
            with patch.object(cli, "load_config", wraps=cli.load_config) as load:
                code, out, err = self.invoke("--watch")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(sleep.call_args_list, [unittest.mock.call(5), unittest.mock.call(5)])
        self.assertEqual(load.call_count, 2)
        self.assertEqual(out.count("Estado calculado da agenda:"), 2)
        self.assertIn("encerrado por Ctrl+C", out)

    def test_watch_stops_on_corrupt_reload_without_replacing_file(self):
        self.write_config()

        def corrupt(_):
            self.path.write_bytes(b'{broken')

        with patch.object(cli.time, "sleep", side_effect=corrupt):
            code, out, err = self.invoke("--watch")
        self.assertEqual(code, 1)
        self.assertEqual(out.count("Estado calculado da agenda:"), 1)
        self.assertIn("Erro:", err)
        self.assertEqual(self.path.read_bytes(), b'{broken')

    def test_default_path_uses_only_temporary_appdata(self):
        out = io.StringIO()
        with redirect_stdout(out):
            code = cli.main(["--init-config"])
        self.assertEqual(code, 0)
        target = self.root / "profile" / "FocusBlocker" / "config.json"
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"windows": []})

    def test_missing_appdata_has_no_fallback_or_write(self):
        with patch.dict(os.environ, {}, clear=True):
            with redirect_stderr(io.StringIO()) as err:
                code = cli.main(["--init-config"])
        self.assertEqual(code, 1)
        self.assertIn("APPDATA", err.getvalue())
        self.assertEqual(list(self.root.iterdir()), [])


if __name__ == "__main__":
    unittest.main()

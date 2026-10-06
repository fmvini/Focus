"""Contrato config -> agenda -> CLI por subprocess, sem perfil/hosts reais."""

import json
import os
from pathlib import Path
import subprocess
import sys
import shutil
import unittest
from uuid import uuid4


PROJECT = Path(__file__).resolve().parents[1]
ENTRY = PROJECT / "main.py"


class Phase1IntegrationTests(unittest.TestCase):
    def setUp(self):
        # Herdar ACLs do workspace evita a ACL 0700 do tempfile no Python 3.14.
        self.root = PROJECT / f".phase1-cli-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.config = self.root / "config.json"
        self.env = os.environ.copy()
        self.env.update({
            "APPDATA": str(self.root / "appdata"),
            "PYTHONIOENCODING": "utf-8",
            "PYTHONDONTWRITEBYTECODE": "1",
        })

    def write_config(self, windows, **extra):
        self.config.write_text(json.dumps({**extra, "windows": windows}), encoding="utf-8")

    def run_python(self, *args, env=None):
        return subprocess.run(
            [sys.executable, "-B", *args], cwd=self.root,
            env=self.env if env is None else env, stdin=subprocess.DEVNULL,
            capture_output=True, text=True, encoding="utf-8", timeout=10,
        )

    def run_cli(self, *args):
        return self.run_python(str(ENTRY), "--config", str(self.config), *args)

    def assert_state(self, at, active, next_start=None):
        result = self.run_cli("--check", "--status", "--at", at)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        state = "dentro da janela" if active else "fora da janela"
        self.assertIn(f"Estado calculado da agenda: {state}", result.stdout)
        self.assertIn("não aplica bloqueios ao Windows", result.stdout)
        if next_start is not None:
            self.assertIn(f"Próximo início efetivo: {next_start}", result.stdout)

    def test_initial_config_stays_inactive_until_user_chooses_windows(self):
        result = self.run_cli("--init-config", "--at", "2026-10-05T22:00:00")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(self.config.read_text(encoding="utf-8")), {
            "windows": [], "block_exes": [], "block_folders": [],
            "safelist_exes": [], "block_cmdline": [],
        })
        self.assertIn("Estado calculado da agenda: fora da janela", result.stdout)
        self.assertIn("Próximo início efetivo: nenhum", result.stdout)
        self.write_config([{"start": "22:00", "end": "02:00", "days": [0]}])
        self.assert_state("2026-10-05T22:00:00", True)

    def test_monday_overnight_boundaries_and_tuesday_continuation(self):
        self.write_config([{"start": "22:00", "end": "02:00", "days": [0]}])
        cases = [
            ("2026-10-05T21:59:59", False, "2026-10-05T22:00:00"),
            ("2026-10-05T22:00:00", True, "2026-10-12T22:00:00"),
            ("2026-10-06T00:00:00", True, "2026-10-12T22:00:00"),
            ("2026-10-06T01:59:59", True, "2026-10-12T22:00:00"),
            ("2026-10-06T02:00:00", False, "2026-10-12T22:00:00"),
            ("2026-10-06T22:00:00", False, "2026-10-12T22:00:00"),
        ]
        for at, active, next_start in cases:
            with self.subTest(at=at):
                self.assert_state(at, active, next_start)

    def test_sunday_window_crosses_week_into_monday(self):
        self.write_config([{"start": "23:00", "end": "01:00", "days": [6]}])
        self.assert_state("2026-10-05T00:30:00", True, "2026-10-11T23:00:00")
        self.assert_state("2026-10-05T01:00:00", False, "2026-10-11T23:00:00")

    def test_adjacent_and_overlapping_windows_have_no_internal_start(self):
        self.write_config([
            {"start": "09:00", "end": "10:00", "days": [0]},
            {"start": "10:00", "end": "11:00", "days": [0]},
            {"start": "10:30", "end": "12:00", "days": [0]},
        ])
        self.assert_state("2026-10-05T09:30:00", True, "2026-10-12T09:00:00")
        self.assert_state("2026-10-05T10:00:00", True, "2026-10-12T09:00:00")
        self.assert_state("2026-10-05T12:00:00", False, "2026-10-12T09:00:00")

    def test_empty_days_disabled_and_missing_days_means_every_day(self):
        self.write_config([{"start": "09:00", "end": "10:00", "days": []}])
        self.assert_state("2026-10-05T09:00:00", False, "nenhum")
        self.write_config([{"start": "09:00", "end": "10:00"}])
        self.assert_state("2026-10-06T09:00:00", True, "2026-10-07T09:00:00")

    def test_continuous_schedule_has_no_next_effective_start(self):
        self.write_config([
            {"start": "00:00", "end": "12:00"},
            {"start": "12:00", "end": "00:00"},
        ])
        self.assert_state("2026-10-05T00:00:00", True, "nenhum")
        self.assert_state("2026-10-11T23:59:59", True, "nenhum")

    def test_corrupt_config_check_and_init_preserve_exact_bytes(self):
        original = b'{"windows": invalid json'
        self.config.write_bytes(original)
        for args in (("--check",), ("--status",), ("--init-config",)):
            with self.subTest(args=args):
                result = self.run_cli(*args)
                self.assertEqual(result.returncode, 1)
                self.assertIn("Erro:", result.stderr)
                self.assertNotIn("Estado calculado", result.stdout)
                self.assertEqual(self.config.read_bytes(), original)

    def test_extra_fields_remain_untouched_by_diagnostics(self):
        self.write_config([], sites=["example.invalid"], future={"unknown": [1, True]})
        original = self.config.read_bytes()
        self.assert_state("2026-10-05T09:00:00", False, "nenhum")
        self.assertEqual(self.config.read_bytes(), original)

    def test_invalid_arguments_return_two_without_initializing(self):
        result = self.run_cli("--init-config", "--at", "2026-10-05T09:00:00Z")
        self.assertEqual(result.returncode, 2)
        self.assertIn("sem fuso", result.stderr)
        self.assertFalse(self.config.exists())

    def test_help_and_missing_file_never_create_configuration(self):
        help_result = self.run_cli("--help")
        self.assertEqual(help_result.returncode, 0, help_result.stderr)
        self.assertIn("Códigos:", help_result.stdout)
        result = self.run_cli("--status")
        self.assertEqual(result.returncode, 1)
        self.assertFalse(self.config.exists())
        self.assertFalse((self.root / "appdata").exists())

    def test_default_appdata_and_missing_appdata_are_isolated(self):
        result = self.run_python(str(ENTRY), "--init-config", "--check")
        self.assertEqual(result.returncode, 0, result.stderr)
        target = self.root / "appdata" / "FocusBlocker" / "config.json"
        self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {
            "windows": [], "block_exes": [], "block_folders": [],
            "safelist_exes": [], "block_cmdline": [],
        })
        env = self.env.copy()
        env.pop("APPDATA", None)
        result = self.run_python(str(ENTRY), "--init-config", env=env)
        self.assertEqual(result.returncode, 1)
        self.assertIn("APPDATA", result.stderr)

    def test_watch_cycles_reload_and_stop_via_sigint_without_real_sleep(self):
        self.write_config([])
        # Executa o entrypoint real. Apenas a espera é substituída, permitindo
        # dois ciclos, edição entre ciclos e SIGINT real no processo de teste.
        script = """
import json, pathlib, runpy, signal, sys, time
entry, config = sys.argv[1:3]
sys.path.insert(0, str(pathlib.Path(entry).parent))
sys.argv = [entry, '--config', config, '--watch']
calls = 0
def controlled_sleep(seconds):
    global calls
    assert seconds == 5, seconds
    calls += 1
    if calls == 1:
        pathlib.Path(config).write_text(json.dumps({'windows': [
            {'start': '00:00', 'end': '12:00'},
            {'start': '12:00', 'end': '00:00'},
        ]}), encoding='utf-8')
    else:
        signal.raise_signal(signal.SIGINT)
time.sleep = controlled_sleep
runpy.run_path(entry, run_name='__main__')
"""
        result = self.run_python("-c", script, str(ENTRY), str(self.config))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertEqual(result.stdout.count("Estado calculado da agenda:"), 2)
        self.assertIn("Estado calculado da agenda: fora da janela", result.stdout)
        self.assertIn("Estado calculado da agenda: dentro da janela", result.stdout)
        self.assertIn("encerrado por Ctrl+C", result.stdout)
        self.assertNotIn("Traceback", result.stdout)


if __name__ == "__main__":
    unittest.main()

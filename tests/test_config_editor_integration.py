"""Sessões reais da CLI, com JSON e agenda, em diretório isolado."""

from datetime import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

from core.config import load_config
from core.scheduler import is_blocking
from ui.config_cli import run_config_editor


class ConfigEditorIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.project = Path(__file__).resolve().parents[1]
        self.root = self.project / f".editor-integration-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = self.root / "config.json"
        self.path.write_text(json.dumps({
            "windows": [], "future": {"keep": ["ação", 12]},
            "sites": {"personal": ["example.org"]},
        }, ensure_ascii=False), encoding="utf-8")

    def run_editor(self, lines):
        environment = dict(os.environ, PYTHONUTF8="1")
        return subprocess.run(
            [sys.executable, "-B", str(self.project / "main.py"),
             "--config", str(self.path), "--edit-config"],
            input="\n".join(lines) + "\n", capture_output=True,
            text=True, encoding="utf-8", env=environment,
            cwd=self.project, timeout=20,
        )

    def test_saved_night_window_and_joint_rule_reach_scheduler(self):
        result = self.run_editor([
            "1", "2", "22:00", "02:00", "0",
            "2", "4", "2", "javaw.exe", ".minecraft",
            "2", "3", "2", "Code.exe", "3", "5",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stderr, "")
        self.assertIn("Configuração salva.", result.stdout)
        config = load_config(self.path)
        self.assertEqual(config.windows[0].days, (0,))
        self.assertTrue(is_blocking(config.windows, datetime(2026, 10, 6, 1)))
        self.assertFalse(is_blocking(config.windows, datetime(2026, 10, 6, 2)))
        self.assertEqual(config.block_cmdline[0].contains, ".minecraft")
        self.assertEqual(config.safelist_exes, ("Code.exe",))
        self.assertEqual(config.extra, {
            "future": {"keep": ["ação", 12]},
            "sites": {"personal": ["example.org"]},
        })
        self.assertEqual(set(self.root.iterdir()), {self.path})

    def test_eof_after_edits_preserves_original_bytes(self):
        original = self.path.read_bytes()
        result = self.run_editor(["1", "2", "08:00", "12:00", ""])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("não salvas descartadas", result.stdout)
        self.assertEqual(self.path.read_bytes(), original)

    def test_invalid_entry_then_disabled_window_can_be_saved(self):
        result = self.run_editor([
            "1", "2", "08:00", "08:00", "",
            "1", "2", "09:00", "10:00", "nenhum", "3", "5",
        ])
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("Erro:", result.stdout)
        config = load_config(self.path)
        self.assertEqual(len(config.windows), 1)
        self.assertEqual(config.windows[0].days, ())
        self.assertFalse(is_blocking(config.windows, datetime(2026, 10, 5, 9, 30)))

    def test_real_repository_conflict_then_reload_preserves_external_revision(self):
        original = self.path.read_bytes()
        external = b'{"windows":[],"future":{"external":true}}'
        answers = iter(["1", "2", "09:00", "10:00", "", "3", "4", "3", "5"])
        output = []
        menus = 0

        def read(prompt):
            nonlocal menus
            if prompt == "Editor > ":
                menus += 1
                if menus == 2:
                    self.path.write_bytes(external)
                elif menus == 3:
                    # A gravação recusada manteve exatamente os bytes externos.
                    self.assertEqual(self.path.read_bytes(), external)
            return next(answers)

        self.assertEqual(run_config_editor(self.path, input_fn=read, output_fn=output.append), 0)
        config = load_config(self.path)
        self.assertEqual(config.windows, ())
        self.assertEqual(config.extra, {"future": {"external": True}})
        self.assertNotEqual(self.path.read_bytes(), original)
        self.assertIn("recarregue", "\n".join(output))
        self.assertIn("Rascunho descartado", "\n".join(output))
        self.assertEqual(output.count("Configuração salva."), 1)
        self.assertEqual(set(self.root.iterdir()), {self.path})

    def test_failed_publication_keeps_draft_for_retry_and_original_bytes(self):
        original = self.path.read_bytes()
        answers = iter(["1", "2", "22:00", "02:00", "0", "3", "3", "5"])
        output = []
        menus = 0
        real_replace = os.replace
        attempts = 0

        def publish(source, destination):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise PermissionError("publicação negada")
            return real_replace(source, destination)

        def read(prompt):
            nonlocal menus
            if prompt == "Editor > ":
                menus += 1
                if menus == 3:
                    self.assertEqual(self.path.read_bytes(), original)
                    self.assertEqual(set(self.root.iterdir()), {self.path})
            return next(answers)

        with patch("core.config.os.replace", side_effect=publish):
            self.assertEqual(run_config_editor(self.path, input_fn=read, output_fn=output.append), 0)
        config = load_config(self.path)
        self.assertEqual(len(config.windows), 1)
        self.assertEqual(config.windows[0].days, (0,))
        self.assertEqual(config.extra["future"], {"keep": ["ação", 12]})
        self.assertTrue(is_blocking(config.windows, datetime(2026, 10, 6, 1)))
        self.assertEqual(attempts, 2)
        self.assertIn("publicação negada", "\n".join(output))
        self.assertEqual(output.count("Configuração salva."), 1)
        self.assertEqual(set(self.root.iterdir()), {self.path})


if __name__ == "__main__":
    unittest.main()

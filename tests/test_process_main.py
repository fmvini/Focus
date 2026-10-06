"""Integração CLI com bloqueador falso, sem processos/hosts/perfil reais."""

import builtins
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import main as cli


class FakeBlockerError(Exception):
    def __init__(self, message, partial_report=None):
        super().__init__(message)
        self.partial_report = partial_report


def report(*results, events=()):
    return SimpleNamespace(results=results, events=events)


def result(pid, status, reason="regra simulada"):
    return SimpleNamespace(pid=pid, name=f"fake-{pid}.exe", status=status, reason=reason)


class ProcessMainTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / f".phase2-cli-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = self.root / "config.json"
        self.write_config()
        self.tick = 0
        self.blocker = SimpleNamespace(scan=Mock(return_value=report()))
        self.fake_module = ModuleType("core.proc_blocker")
        self.fake_module.ProcessBlockerError = FakeBlockerError
        self.fake_module.ProcessBlocker = Mock(side_effect=AssertionError("adaptador real proibido"))
        self.enterContext(patch.dict(sys.modules, {"core.proc_blocker": self.fake_module}))
        self.factory = self.enterContext(patch.object(cli, "_create_process_blocker", return_value=self.blocker))
        self.clock = self.enterContext(patch.object(cli, "datetime", wraps=datetime))
        self.clock.now.return_value = datetime(2026, 10, 5, 9, 30)
        self.enterContext(patch.object(cli.time, "monotonic", side_effect=lambda: self.tick))
        self.sleep = self.enterContext(patch.object(cli.time, "sleep", side_effect=KeyboardInterrupt))
        self.enterContext(patch.dict(os.environ, {
            "APPDATA": str(self.root / "profile"),
            "LOCALAPPDATA": str(self.root / "local-profile"),
        }))

    def write_config(self, windows=None, **extra):
        if windows is None:
            windows = [{"start": "09:00", "end": "10:00", "days": [0]}]
        self.path.write_text(json.dumps({"windows": windows, **extra}), encoding="utf-8")

    def invoke(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = cli.main(["--config", str(self.path), *args])
        return code, out.getvalue(), err.getvalue()

    def apply(self, *args):
        return self.invoke("--watch", "--apply-processes", *args)

    def test_default_and_current_diagnostic_flags_do_not_create_or_import_blocker(self):
        original_import = builtins.__import__

        def guarded_import(name, *args, **kwargs):
            if name in ("psutil", "core.proc_blocker"):
                raise AssertionError(f"importação proibida no diagnóstico: {name}")
            return original_import(name, *args, **kwargs)

        cases = [(), ("--status",), ("--check",),
                 ("--at", "2026-10-05T09:00:00"), ("--watch",)]
        with patch("builtins.__import__", side_effect=guarded_import):
            for args in cases:
                with self.subTest(args=args):
                    code, _, err = self.invoke(*args)
                    self.assertEqual((code, err), (0, ""))
        self.factory.assert_not_called()
        self.blocker.scan.assert_not_called()

    def test_invalid_apply_combinations_precede_io_and_initialization(self):
        cases = [
            ("--apply-processes",),
            ("--apply-processes", "--watch", "--at", "2026-10-05T09:00:00"),
            ("--apply-processes", "--watch", "--init-config"),
            ("--apply-processes", "--watch", "--check"),
        ]
        self.path.unlink()
        with patch.object(cli, "load_config", side_effect=AssertionError("IO proibido")):
            for args in cases:
                with self.subTest(args=args):
                    with self.assertRaises(SystemExit) as raised:
                        self.invoke(*args)
                    self.assertEqual(raised.exception.code, 2)
                    self.assertFalse(self.path.exists())
        self.factory.assert_not_called()

    def test_initial_invalid_configuration_prevents_factory(self):
        self.path.write_bytes(b"{broken")
        code, _, err = self.apply()
        self.assertEqual(code, 1)
        self.assertIn("novas ações interrompidas", err)
        self.assertEqual(self.path.read_bytes(), b"{broken")
        self.factory.assert_not_called()

    def test_check_validates_process_lists_and_keeps_unknown_extras_opaque(self):
        self.write_config(
            block_exes=["game.exe"], block_folders=[r"%LOCALAPPDATA%\Games"],
            safelist_exes=["study.exe"],
            block_cmdline=[{"executable": "javaw.exe", "contains": ".Minecraft"}],
            future={"unknown": True},
        )
        # Usar variável fictícia absoluta Windows, sem consultar perfil real.
        with patch.dict(os.environ, {"LOCALAPPDATA": r"C:\FakeUser\Local"}):
            original = self.path.read_bytes()
            code, out, err = self.invoke("--check")
        self.assertEqual((code, err), (0, ""))
        self.assertIn("agenda e regras de processos", out)
        self.assertEqual(self.path.read_bytes(), original)
        self.factory.assert_not_called()

    def test_check_rejects_each_invalid_process_list_without_effects(self):
        for field, value in (
            ("block_exes", ["game"]), ("block_folders", ["relative"]),
            ("safelist_exes", ["*"]), ("block_cmdline", [".minecraft"]),
        ):
            with self.subTest(field=field):
                self.write_config(**{field: value})
                original = self.path.read_bytes()
                code, _, err = self.invoke("--check")
                self.assertEqual(code, 1)
                self.assertIn(field, err)
                self.assertEqual(self.path.read_bytes(), original)
        self.factory.assert_not_called()

    def test_immediate_scan_and_per_effect_callback_rechecks_real_clock(self):
        effects, checks = [], []
        self.clock.now.side_effect = [
            datetime(2026, 10, 5, 9, 59, 58),
            datetime(2026, 10, 5, 9, 59, 59),
            datetime(2026, 10, 5, 10),
        ]

        def scan(config, may_act):
            for pid in (10, 11):
                allowed = may_act()
                checks.append(allowed)
                if allowed:
                    effects.append(pid)
            return report(result(10, "terminated"), result(11, "inactive"), events=(object(),))

        self.blocker.scan.side_effect = scan
        code, out, err = self.apply("--status")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(checks, [True, False])
        self.assertEqual(effects, [10])
        self.assertIn("1 encerramentos confirmados", out)
        self.assertIn("encerramento confirmado", out)
        self.assertIn("sites/hosts não são alterados", out)
        self.assertNotIn("não aplica bloqueios ao Windows", out)
        self.assertNotIn("sites bloqueados", out.lower())

    def test_inactive_schedule_calls_scan_with_false_gate_and_no_effects(self):
        self.clock.now.return_value = datetime(2026, 10, 5, 10)
        effects, enumerations = [], []

        def scan(config, may_act):
            if may_act():
                enumerations.append("new targets")
                effects.append(10)
            return report()

        self.blocker.scan.side_effect = scan
        code, out, err = self.apply()
        self.assertEqual((code, err), (0, ""))
        self.assertIn("somente reconciliação de pedidos anteriores", out)
        self.blocker.scan.assert_called_once()
        self.assertEqual((effects, enumerations), ([], []))

    def test_pending_confirmation_outside_window_without_new_targets_or_effects(self):
        effects, enumerations, reconciliations = [], [], []

        def scan(config, may_act):
            if self.blocker.scan.call_count == 1:
                self.assertTrue(may_act())
                enumerations.append("initial targets")
                effects.append(10)
                return report(result(10, "pending"))
            reconciliations.append(10)
            self.assertFalse(may_act())
            return report(result(10, "terminated"), events=(object(),))

        def sleep(seconds):
            self.tick += seconds
            if self.sleep.call_count == 1:
                self.clock.now.return_value = datetime(2026, 10, 5, 10)
            else:
                raise KeyboardInterrupt

        self.blocker.scan.side_effect = scan
        self.sleep.side_effect = sleep
        code, out, err = self.apply()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual((effects, enumerations, reconciliations),
                         ([10], ["initial targets"], [10]))
        self.assertIn("0 encerramentos confirmados; 1 pendentes", out)
        self.assertIn("1 encerramentos confirmados; 0 pendentes", out)
        self.assertIn("somente reconciliação de pedidos anteriores", out)

    def test_reload_updates_rules_and_agenda_before_next_scan(self):
        self.write_config(block_exes=["first.exe"])

        def sleep(seconds):
            self.tick += seconds
            if self.sleep.call_count == 1:
                self.write_config(block_exes=["second.exe"])
            elif self.sleep.call_count == 2:
                self.write_config(windows=[])
            else:
                raise KeyboardInterrupt

        self.sleep.side_effect = sleep
        with patch.object(cli, "load_config", wraps=cli.load_config) as load:
            code, out, err = self.apply()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(load.call_count, 3)
        self.assertEqual(self.blocker.scan.call_count, 3)
        snapshots = [call.args[0] for call in self.blocker.scan.call_args_list]
        self.assertEqual([item.block_exes for item in snapshots], [("first.exe",), ("second.exe",), ()])
        self.assertEqual(snapshots[-1].windows, ())
        self.assertIn("somente reconciliação de pedidos anteriores", out)

    def test_corrupt_reload_stops_without_stale_configuration(self):
        def corrupt(seconds):
            self.tick += seconds
            self.path.write_bytes(b"{broken reload")

        self.sleep.side_effect = corrupt
        code, out, err = self.apply()
        self.assertEqual(code, 1)
        self.assertIn("novas ações interrompidas", err)
        self.assertEqual(self.blocker.scan.call_count, 1)
        self.assertEqual(self.path.read_bytes(), b"{broken reload")
        self.assertNotIn("encerrado por Ctrl+C", out)

    def test_invalid_process_rules_on_reload_stop_before_next_scan(self):
        def invalid_rules(seconds):
            self.tick += seconds
            self.write_config(block_cmdline=[".minecraft"])

        self.sleep.side_effect = invalid_rules
        code, _, err = self.apply()
        self.assertEqual(code, 1)
        self.assertIn("block_cmdline", err)
        self.assertEqual(self.blocker.scan.call_count, 1)

    def test_monotonic_deadline_discounts_scan_duration(self):
        def scan(config, may_act):
            self.tick += 2
            return report()

        self.blocker.scan.side_effect = scan
        self.assertEqual(self.apply()[0], 0)
        self.sleep.assert_called_once_with(3)

    def test_slow_scan_skips_missed_deadlines_without_catchup_burst(self):
        def scan(config, may_act):
            self.tick += 12
            return report()

        self.blocker.scan.side_effect = scan
        code, _, err = self.apply()
        self.assertEqual(code, 0)
        self.assertIn("ciclo atrasado", err)
        self.sleep.assert_called_once_with(3)
        self.blocker.scan.assert_called_once()

    def test_target_failures_are_visible_without_stopping_safe_targets(self):
        effects = []

        def scan(config, may_act):
            if may_act():
                effects.append(14)
            return report(
                result(10, "protected"), result(11, "unmatched"),
                result(12, "unavailable", "AccessDenied simulado"),
                result(13, "failed", "confirmação falhou"),
                result(14, "terminated"), result(15, "gone"), events=(object(),),
            )

        self.blocker.scan.side_effect = scan
        code, out, err = self.apply()
        self.assertEqual(code, 0)
        self.assertEqual(effects, [14])
        self.assertIn("AccessDenied simulado", err)
        self.assertIn("alvo preservado", err)
        self.assertIn("encerramento não confirmado", err)
        self.assertIn("1 indisponíveis; 1 falhas", out)
        self.assertIn("1 encerramentos confirmados", out)
        self.assertNotIn("fake-10.exe", out)
        self.assertNotIn("fake-11.exe", out)

    def test_only_confirmed_events_are_counted(self):
        self.blocker.scan.return_value = report(
            result(10, "failed"), result(11, "gone"), result(12, "pending"),
        )
        code, out, err = self.apply()
        self.assertEqual(code, 0)
        self.assertIn("0 encerramentos confirmados", out)
        self.assertIn("1 falhas", out)
        self.assertIn("1 pendentes", out)
        self.assertIn("solicitado; ainda sem saída confirmada", out)
        self.assertIn("não confirmado", err)

    def test_global_errors_stop_scans_with_exit_one(self):
        for stage in ("factory", "scan"):
            with self.subTest(stage=stage):
                self.factory.reset_mock(side_effect=True)
                self.blocker.scan.reset_mock(side_effect=True)
                target = self.factory if stage == "factory" else self.blocker.scan
                target.side_effect = FakeBlockerError("falha global simulada")
                code, out, err = self.apply()
                self.assertEqual(code, 1)
                self.assertIn("falha global simulada", err)
                self.assertIn("novas ações interrompidas", err)
                self.assertNotIn("encerrado por Ctrl+C", out)
                self.sleep.assert_not_called()

    def test_missing_dependency_is_global_error(self):
        self.factory.side_effect = ImportError("dependência simulada ausente")
        code, _, err = self.apply()
        self.assertEqual(code, 1)
        self.assertIn("dependência simulada ausente", err)
        self.blocker.scan.assert_not_called()

    def test_global_error_displays_partial_results_before_error_and_stops(self):
        callbacks = []
        partial = report(
            result(10, "terminated"), result(11, "pending"),
            result(12, "unavailable", "dados inseguros simulados"),
            events=(object(),),
        )

        def scan(config, may_act):
            callbacks.append(may_act)
            self.assertTrue(may_act())
            raise FakeBlockerError("contexto falhou após efeitos", partial)

        self.blocker.scan.side_effect = scan
        combined = io.StringIO()
        with patch.object(cli, "load_config", wraps=cli.load_config) as load:
            with redirect_stdout(combined), redirect_stderr(combined):
                code = cli.main(["--config", str(self.path), "--watch", "--apply-processes"])
        output = combined.getvalue()
        self.assertEqual(code, 1)
        self.assertIn("Relatório parcial", output)
        self.assertIn("fake-10.exe", output)
        self.assertIn("solicitado; ainda sem saída confirmada", output)
        self.assertIn("dados inseguros simulados", output)
        self.assertEqual(output.count("1 encerramentos confirmados; 1 pendentes"), 1)
        self.assertLess(output.index("Resumo de processos:"), output.index("Erro global de processos:"))
        self.assertIn("novas ações interrompidas", output)
        self.assertFalse(callbacks[0]())
        self.assertEqual(load.call_count, 1)
        self.blocker.scan.assert_called_once()
        self.sleep.assert_not_called()

    def test_pending_reconciliation_partial_confirmation_on_later_global_error(self):
        def scan(config, may_act):
            if self.blocker.scan.call_count == 1:
                return report(result(10, "pending"))
            raise FakeBlockerError(
                "enumeração falhou após reconciliação",
                report(result(10, "terminated"), events=(object(),)),
            )

        def sleep(seconds):
            self.tick += seconds

        self.blocker.scan.side_effect = scan
        self.sleep.side_effect = sleep
        code, out, err = self.apply()
        self.assertEqual(code, 1)
        self.assertIn("0 encerramentos confirmados; 1 pendentes", out)
        self.assertEqual(out.count("1 encerramentos confirmados; 0 pendentes"), 1)
        self.assertEqual(out.count("fake-10.exe): encerramento confirmado"), 1)
        self.assertIn("enumeração falhou após reconciliação", err)
        self.assertEqual(self.blocker.scan.call_count, 2)
        self.sleep.assert_called_once_with(5)

    def test_empty_partial_report_is_shown_without_claiming_success(self):
        self.blocker.scan.side_effect = FakeBlockerError("falha global", report())
        code, out, err = self.apply()
        self.assertEqual(code, 1)
        self.assertIn("Relatório parcial", out)
        self.assertIn("0 encerramentos confirmados; 0 pendentes", out)
        self.assertIn("Erro global", err)
        self.sleep.assert_not_called()

    def test_ctrl_c_during_scan_stops_and_revokes_callback(self):
        callbacks, effects = [], []

        def scan(config, may_act):
            callbacks.append(may_act)
            if may_act():
                effects.append(10)
            raise KeyboardInterrupt

        self.blocker.scan.side_effect = scan
        code, out, err = self.apply()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(effects, [10])
        self.assertFalse(callbacks[0]())
        self.assertIn("Varredura de processos encerrada por Ctrl+C", out)
        self.assertIn("não são reabertos", out)
        self.blocker.scan.assert_called_once()
        self.sleep.assert_not_called()

    def test_ctrl_c_during_sleep_stops_before_reload(self):
        with patch.object(cli, "load_config", wraps=cli.load_config) as load:
            code, out, err = self.apply()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(load.call_count, 1)
        self.blocker.scan.assert_called_once()
        self.assertIn("Varredura de processos encerrada por Ctrl+C", out)

    def test_lazy_factory_uses_module_only_when_called(self):
        # Exercitar a fábrica original com um módulo integralmente falso.
        from importlib import util
        spec = util.spec_from_file_location("fake_factory_cli", Path(cli.__file__))
        fresh_cli = util.module_from_spec(spec)
        spec.loader.exec_module(fresh_cli)
        self.fake_module.ProcessBlocker.assert_not_called()
        self.fake_module.ProcessBlocker.side_effect = None
        self.fake_module.ProcessBlocker.return_value = self.blocker
        self.assertIs(fresh_cli._create_process_blocker(), self.blocker)
        self.fake_module.ProcessBlocker.assert_called_once_with()

    def test_help_in_fresh_subprocess_blocks_process_imports_and_creates_no_profile(self):
        script = """
import builtins, pathlib, runpy, sys
entry = sys.argv[1]
sys.path.insert(0, str(pathlib.Path(entry).parent))
original = builtins.__import__
def guarded(name, *args, **kwargs):
    if name == 'core.proc_blocker' or name.startswith('psutil'):
        raise AssertionError('process import forbidden')
    return original(name, *args, **kwargs)
builtins.__import__ = guarded
sys.argv = [entry, '--help']
runpy.run_path(entry, run_name='__main__')
"""
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        completed = subprocess.run(
            [sys.executable, "-B", "-c", script, str(Path(cli.__file__).resolve())],
            cwd=self.root, env=env, capture_output=True, text=True, encoding="utf-8", timeout=10,
        )
        self.assertEqual((completed.returncode, completed.stderr), (0, ""))
        for text in ("--apply-processes", "exige --watch", "relógio local real",
                     "Sites/hosts não são alterados", "não reabre", "Códigos:"):
            self.assertIn(text, completed.stdout)
        self.assertFalse((self.root / "profile").exists())
        self.assertFalse((self.root / "local-profile").exists())


if __name__ == "__main__":
    unittest.main()

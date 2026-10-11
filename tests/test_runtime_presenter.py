"""Tradução de snapshots reais sem widgets, processos ou histórico acumulado."""

from dataclasses import FrozenInstanceError, replace
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import sys
import unittest

from core.process_controller import RuntimeSnapshot
from core.proc_blocker import ProcessIdentity, ProcessResult, ScanReport, TerminationEvent
from ui.runtime_presenter import RuntimeView, format_runtime


class RuntimePresenterTests(unittest.TestCase):
    NOW = datetime(2026, 10, 11, 15, 4, 9)

    def report(self):
        statuses = (
            "pending", "pending", "unavailable", "failed", "failed", "failed",
            "protected", "unmatched", "unmatched", "terminated", "terminated", "gone",
        )
        return ScanReport(
            tuple(ProcessResult(100 + index, "fake.exe", status, "test") for index, status in enumerate(statuses)),
            (TerminationEvent(ProcessIdentity(99, 10.0), self.NOW.replace(tzinfo=timezone.utc)),),
        )

    def test_initial_view_is_stopped_without_scan_or_report(self):
        self.assertEqual(format_runtime(RuntimeSnapshot()), RuntimeView(
            "Motor parado",
            "Iniciar usa a configuração salva.\nNenhum ciclo registrado.\n"
            "Última avaliação da agenda: não determinada.\nNenhum relatório disponível.",
            True, False,
        ))

    def test_runtime_view_is_frozen(self):
        view = format_runtime(RuntimeSnapshot())
        for field, value in (
            ("title", "changed"), ("detail", "changed"),
            ("start_enabled", False), ("stop_enabled", True),
        ):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError):
                setattr(view, field, value)

    def test_running_before_first_scan_does_not_claim_confirmed_termination(self):
        view = format_runtime(RuntimeSnapshot(state="running"))
        self.assertEqual(view.title, "Motor em execução")
        self.assertFalse(view.start_enabled)
        self.assertTrue(view.stop_enabled)
        self.assertIn("isso não confirma encerramentos", view.detail)
        self.assertIn("Nenhum ciclo registrado", view.detail)
        self.assertNotIn("encerramentos confirmados:", view.detail)

    def test_last_cycle_timestamp_and_agenda_are_explicit_and_separate_from_motor(self):
        for active, message in ((True, "dentro da janela"), (False, "fora da janela"), (None, "não determinada")):
            with self.subTest(active=active):
                view = format_runtime(RuntimeSnapshot(state="running", active=active, last_scan=self.NOW))
                self.assertEqual(view.title, "Motor em execução")
                self.assertIn("Último ciclo: 11/10/2026 15:04:09", view.detail)
                self.assertIn(f"Última avaliação da agenda: {message}", view.detail)
                self.assertIn("Nenhum relatório disponível", view.detail)

    def test_report_counts_confirmations_from_events_and_other_statuses_from_results(self):
        view = format_runtime(RuntimeSnapshot(state="running", active=True, last_scan=self.NOW, report=self.report()))
        self.assertIn(
            "Resumo do último ciclo: encerramentos confirmados: 1; pendentes de confirmação: 2; "
            "indisponíveis: 1; falhas: 3; protegidos: 1; sem correspondência: 2.", view.detail,
        )
        self.assertNotIn("possivelmente parcial", view.detail)

    def test_empty_report_is_distinct_from_missing_report(self):
        view = format_runtime(RuntimeSnapshot(state="running", active=False, last_scan=self.NOW, report=ScanReport((), ())))
        self.assertIn("encerramentos confirmados: 0", view.detail)
        self.assertIn("pendentes de confirmação: 0", view.detail)
        self.assertIn("fora da janela", view.detail)
        self.assertNotIn("Nenhum relatório disponível", view.detail)

    def test_stopping_disables_buttons_and_does_not_claim_worker_already_stopped(self):
        view = format_runtime(RuntimeSnapshot(state="stopping", active=True, last_scan=self.NOW, report=self.report()))
        self.assertEqual(view.title, "Motor parando")
        self.assertFalse(view.start_enabled)
        self.assertFalse(view.stop_enabled)
        self.assertIn("aguardando o motor terminar", view.detail)
        self.assertIn("não são reabertos", view.detail)
        self.assertIn("encerramentos confirmados: 1", view.detail)

    def test_error_preserves_diagnostic_and_partial_report(self):
        diagnostic = "Falha de enumeração: acesso negado à ação 日本語"
        view = format_runtime(RuntimeSnapshot(
            state="error", active=True, last_scan=self.NOW,
            report=self.report(), error=diagnostic,
        ))
        self.assertEqual(view.title, "Motor com erro")
        self.assertTrue(view.start_enabled)
        self.assertFalse(view.stop_enabled)
        self.assertIn("Novas ações interrompidas", view.detail)
        self.assertIn(f"Erro: {diagnostic}", view.detail)
        self.assertIn("Resumo do último ciclo (possivelmente parcial)", view.detail)
        self.assertIn("falhas: 3", view.detail)
        self.assertIn("encerramentos confirmados: 1", view.detail)

    def test_error_without_report_or_known_agenda_does_not_invent_result(self):
        view = format_runtime(RuntimeSnapshot(state="error", last_scan=self.NOW, error="JSON inválido"))
        self.assertIn("Erro: JSON inválido", view.detail)
        self.assertIn("não determinada", view.detail)
        self.assertIn("Nenhum relatório disponível", view.detail)
        self.assertNotIn("encerramentos confirmados:", view.detail)

    def test_idle_after_stop_preserves_last_cycle_but_not_running_claim(self):
        view = format_runtime(RuntimeSnapshot(state="idle", active=True, last_scan=self.NOW, report=self.report()))
        self.assertEqual(view.title, "Motor parado")
        self.assertTrue(view.start_enabled)
        self.assertFalse(view.stop_enabled)
        self.assertIn("Última avaliação da agenda: dentro da janela", view.detail)
        self.assertIn("encerramentos confirmados: 1", view.detail)
        self.assertNotIn("Monitoramento em execução", view.detail)

    def test_formatting_is_repeatable_preserves_snapshot_and_does_not_accumulate(self):
        snapshot = RuntimeSnapshot(state="running", active=True, last_scan=self.NOW, report=self.report())
        before = replace(snapshot)
        first = format_runtime(snapshot)
        empty = format_runtime(replace(snapshot, report=ScanReport((), ())))
        again = format_runtime(snapshot)
        self.assertEqual(snapshot, before)
        self.assertEqual(first, again)
        self.assertIn("encerramentos confirmados: 0", empty.detail)
        self.assertIn("falhas: 0", empty.detail)

    def test_target_diagnostics_show_at_most_three_names_pids_and_reasons(self):
        report = ScanReport(tuple(
            ProcessResult(index, f"app-{index}.exe", "failed" if index % 2 else "unavailable", f"reason-{index}")
            for index in range(300)
        ), ())
        view = format_runtime(RuntimeSnapshot(state="running", last_scan=self.NOW, report=report))
        diagnostic_lines = [line for line in view.detail.splitlines() if line.startswith(("Falha:", "Indisponível:"))]
        self.assertEqual(len(diagnostic_lines), 3)
        self.assertEqual(diagnostic_lines[0], "Indisponível: app-0.exe (PID 0) — reason-0")
        self.assertEqual(diagnostic_lines[1], "Falha: app-1.exe (PID 1) — reason-1")
        self.assertEqual(diagnostic_lines[2], "Indisponível: app-2.exe (PID 2) — reason-2")
        self.assertIn("Mais 297 diagnósticos", view.detail)
        self.assertNotIn("app-3.exe", view.detail)
        self.assertIn("indisponíveis: 150; falhas: 150", view.detail)

    def test_target_diagnostics_use_fallbacks_for_missing_names_pid_and_reason(self):
        report = ScanReport((
            ProcessResult(None, None, "unavailable", None),
            ProcessResult(100, "", "failed", "  "),
        ), ())
        view = format_runtime(RuntimeSnapshot(state="error", error="falha global", report=report))
        self.assertIn("Indisponível: nome desconhecido (PID desconhecido) — motivo indisponível", view.detail)
        self.assertIn("Falha: nome desconhecido (PID 100) — motivo indisponível", view.detail)
        self.assertNotIn("Mais ", view.detail)
        self.assertNotIn("None", view.detail)

    def test_target_diagnostics_bound_long_fields_and_keep_one_line_per_target(self):
        name = "jogo.exe\n" + "x" * 1000
        reason = "ação negada\r\n" + "y" * 1000
        report = ScanReport((ProcessResult(123, name, "failed", reason),), ())
        view = format_runtime(RuntimeSnapshot(state="error", report=report))
        diagnostics = [line for line in view.detail.splitlines() if line.startswith("Falha:")]
        self.assertEqual(len(diagnostics), 1)
        self.assertIn("jogo.exe ", diagnostics[0])
        self.assertIn("ação negada ", diagnostics[0])
        self.assertEqual(diagnostics[0].count("…"), 2)
        self.assertLess(len(diagnostics[0]), 280)

    def test_only_failed_and_unavailable_targets_appear_in_diagnostics(self):
        view = format_runtime(RuntimeSnapshot(state="running", report=self.report()))
        diagnostics = [line for line in view.detail.splitlines() if line.startswith(("Falha:", "Indisponível:"))]
        self.assertEqual(len(diagnostics), 3)
        self.assertIn("Indisponível: fake.exe (PID 102) — test", diagnostics[0])
        self.assertIn("Mais 1 diagnóstico de", view.detail)
        self.assertNotIn("(PID 100)", view.detail)  # Pending não é falha confirmada.
        cleared = format_runtime(RuntimeSnapshot(state="running", report=ScanReport((), ())))
        self.assertNotIn("fake.exe", cleared.detail)
        self.assertNotIn("Mais ", cleared.detail)

    def test_presenter_import_alone_does_not_import_controller_psutil_or_gui(self):
        result = subprocess.run(
            [sys.executable, "-B", "-c", "import sys; import ui.runtime_presenter; "
             "assert not {'core.process_controller', 'psutil', 'customtkinter', 'tkinter'} & sys.modules.keys()"],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

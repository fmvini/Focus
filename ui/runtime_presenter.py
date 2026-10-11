"""Apresentação pura do estado do motor e do último ciclo, sem widgets ou IO."""

from collections import Counter
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.process_controller import RuntimeSnapshot


@dataclass(frozen=True)
class RuntimeView:
    title: str
    detail: str
    start_enabled: bool
    stop_enabled: bool


def _compact_text(value, fallback: str, limit: int) -> str:
    text = " ".join(str(value).split()) if value is not None else ""
    text = text or fallback
    return text if len(text) <= limit else text[:limit - 1] + "…"


def format_runtime(snapshot: "RuntimeSnapshot") -> RuntimeView:
    """Traduz um snapshot sem confundir monitoramento com encerramento confirmado."""
    states = {
        "idle": ("Motor parado", "Iniciar usa a configuração salva.", True, False),
        "running": (
            "Motor em execução",
            "Monitoramento em execução; isso não confirma encerramentos.",
            False, True,
        ),
        "stopping": (
            "Motor parando",
            "Parada solicitada; aguardando o motor terminar. "
            "Aplicativos encerrados não são reabertos.",
            False, False,
        ),
        "error": (
            "Motor com erro",
            "Novas ações interrompidas. Inicie novamente para tentar.",
            True, False,
        ),
    }
    title, message, start_enabled, stop_enabled = states[snapshot.state]
    lines = [message]
    if snapshot.error is not None:
        lines.append(f"Erro: {snapshot.error}")
    if snapshot.last_scan is None:
        lines.append("Nenhum ciclo registrado.")
    else:
        lines.append(f"Último ciclo: {snapshot.last_scan:%d/%m/%Y %H:%M:%S}.")
    agenda = {
        None: "não determinada",
        True: "dentro da janela",
        False: "fora da janela",
    }[snapshot.active]
    lines.append(f"Última avaliação da agenda: {agenda}.")
    if snapshot.report is not None:
        counts = Counter(result.status for result in snapshot.report.results)
        label = "Resumo do último ciclo"
        if snapshot.state == "error":
            label += " (possivelmente parcial)"
        lines.append(
            f"{label}: encerramentos confirmados: {len(snapshot.report.events)}; "
            f"pendentes de confirmação: {counts['pending']}; "
            f"indisponíveis: {counts['unavailable']}; falhas: {counts['failed']}; "
            f"protegidos: {counts['protected']}; sem correspondência: {counts['unmatched']}."
        )
        diagnostics = [
            result for result in snapshot.report.results
            if result.status in {"unavailable", "failed"}
        ]
        for result in diagnostics[:3]:
            status = "Indisponível" if result.status == "unavailable" else "Falha"
            name = _compact_text(result.name, "nome desconhecido", 80)
            pid = _compact_text(result.pid, "desconhecido", 20)
            reason = _compact_text(result.reason, "motivo indisponível", 160)
            lines.append(f"{status}: {name} (PID {pid}) — {reason}")
        if len(diagnostics) > 3:
            additional = len(diagnostics) - 3
            noun = "diagnóstico" if additional == 1 else "diagnósticos"
            lines.append(f"Mais {additional} {noun} de falha/indisponibilidade neste ciclo.")
    else:
        lines.append("Nenhum relatório disponível.")
    return RuntimeView(title, "\n".join(lines), start_enabled, stop_enabled)

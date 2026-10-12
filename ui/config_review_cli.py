"""Diagnóstico estático do JSON salvo, sem abrir GUI ou iniciar motor."""

from pathlib import Path

from core.config import load_config
from core.config_review import review_config


def run_config_review(path: str | Path, *, output_fn=None) -> int:
    """Apontamentos são informativos: configuração válida retorna zero."""
    report = review_config(load_config(path))
    output_fn = print if output_fn is None else output_fn
    output_fn(f"Revisão da configuração salva: {path}")
    output_fn(f"Horários ativos: {report.active_windows}; regras cadastradas de bloqueio: {report.target_rules}.")
    output_fn("Análise estática, sem verificar processos ou instalações. O arquivo não é alterado.")
    labels = {"windows": "Horários", "block_exes": "Executáveis", "block_folders": "Pastas",
              "safelist_exes": "Proteção adicional", "block_cmdline": "Linha de comando"}
    for item in report.items:
        position = f", item {item.index + 1}" if item.index is not None else ""
        output_fn(f"{labels[item.field]}{position}: {' '.join(item.detail.split())}")
    if not report.items:
        output_fn("Nenhum apontamento estático. Proteções adicionais do motor continuam valendo.")
    else:
        output_fn(f"Apontamentos informativos: {len(report.items)}; revise o que desejar no editor.")
    return 0

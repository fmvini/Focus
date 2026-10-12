"""Destinos candidatos dos apontamentos visíveis, sem acessar o rascunho."""

from dataclasses import dataclass

from core.config_review import ConfigReview, ReviewItem


_FIELDS = {
    "windows": "Horários",
    "block_exes": "Executáveis",
    "block_folders": "Pastas",
    "safelist_exes": "Proteção adicional",
    "block_cmdline": "Linha de comando",
}


@dataclass(frozen=True)
class ReviewLink:
    ordinal: int
    field: str
    index: int
    label: str


def review_links(report: ConfigReview, limit: int = 10) -> tuple[ReviewLink, ...]:
    """Mantém posições originais dentro do prefixo exibido, sem deduplicar.

    Apontamentos sem índice ou com metadados não linkáveis são omitidos para
    não oferecer destinos inválidos. Isso não valida a configuração ou a faixa
    atual: ConfigReview não contém as listas. Quem navega deve conferir faixa
    e geração do rascunho para recusar callbacks de uma revisão obsoleta.
    """
    if not isinstance(report, ConfigReview):
        raise TypeError("navegação da revisão: esperado ConfigReview")
    if type(limit) is not int:
        raise TypeError("limite da revisão: esperado int")
    if limit < 0:
        raise ValueError("limite da revisão: esperado inteiro não negativo")
    links = []
    for ordinal, item in enumerate(report.items[:limit]):
        if not isinstance(item, ReviewItem):
            continue
        if not isinstance(item.field, str) or item.field not in _FIELDS:
            continue
        if type(item.index) is not int or item.index < 0:
            continue
        label = f"Apontamento {ordinal + 1} · {_FIELDS[item.field]} · item {item.index + 1}"
        links.append(ReviewLink(ordinal, item.field, item.index, label))
    return tuple(links)

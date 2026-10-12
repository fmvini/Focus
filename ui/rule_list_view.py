"""Filtragem e ordenação visual das regras por seus índices de cadastro."""

from core.models import AppConfig


_FIELDS = frozenset(("block_exes", "block_folders", "safelist_exes", "block_cmdline"))
_ORDERS = frozenset(("registered", "name_asc", "name_desc"))


def rule_view_indices(
    config: AppConfig, field: str, query: str = "", order: str = "registered"
) -> tuple[int, ...]:
    """Retorna índices originais sem alterar ou validar o modelo recebido.

    Busca e nomes usam casefold, mantendo espaços/literais das regras. A
    ordenação é estável nos dois sentidos: empates seguem o cadastro original.
    Pastas não são expandidas nem resolvidas; cmdline ordena pelo par completo.
    """
    if not isinstance(config, AppConfig):
        raise TypeError("lista de regras: esperado AppConfig")
    for label, value in (("campo", field), ("busca", query), ("ordem", order)):
        if not isinstance(value, str):
            raise TypeError(f"{label} da lista de regras: esperado str")
    if field not in _FIELDS:
        raise ValueError("campo da lista de regras desconhecido")
    if order not in _ORDERS:
        raise ValueError("ordem da lista de regras desconhecida")

    values = getattr(config, field)
    needle = query.strip().casefold()
    cmdline = field == "block_cmdline"
    indices = [
        index for index, value in enumerate(values)
        if needle in (
            f"{value.executable}\n{value.contains}" if cmdline else value
        ).casefold()
    ]
    if order != "registered":
        def name_key(index):
            value = values[index]
            if cmdline:
                return value.executable.casefold(), value.contains.casefold()
            return value.casefold()

        indices.sort(key=name_key, reverse=order == "name_desc")
    return tuple(indices)

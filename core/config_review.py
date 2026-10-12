"""Revisão estática do rascunho, sem consultar processos ou instalações."""

from dataclasses import dataclass

from core.config import config_to_dict, parse_config
from core.models import AppConfig
from core.process_catalog import MANDATORY_NAMES


@dataclass(frozen=True)
class ReviewItem:
    code: str
    field: str
    index: int | None
    detail: str


@dataclass(frozen=True)
class ConfigReview:
    active_windows: int
    target_rules: int
    items: tuple[ReviewItem, ...]


def review_config(config: AppConfig) -> ConfigReview:
    """Apontamentos informativos; não corrige regras ou impede salvar/iniciar.

    Índices referem-se às listas originais. Duplicatas de nomes/pares ignoram
    caixa como o matcher; pastas comparam somente o texto, sem resolver aliases.
    Proteções de runtime adicionais não podem ser inferidas desta análise.
    """
    config = parse_config(config_to_dict(config))
    items = []
    active_windows = sum(bool(window.days) for window in config.windows)
    target_rules = len(config.block_exes) + len(config.block_folders) + len(config.block_cmdline)
    if not active_windows:
        items.append(ReviewItem("no_windows", "windows", None, "Nenhum horário ativo cadastrado."))
    if not target_rules:
        items.append(ReviewItem("no_targets", "block_exes", None, "Nenhuma regra de bloqueio cadastrada."))

    seen = {}
    for index, window in enumerate(config.windows):
        key = (window.start, window.end, tuple(sorted(window.days)))
        if key in seen:
            items.append(ReviewItem("duplicate", "windows", index,
                                    f"Horário repetido do item {seen[key] + 1}; a agenda une sobreposições."))
        else:
            seen[key] = index
    safelist = {name.casefold() for name in config.safelist_exes}
    for field in ("block_exes", "block_folders", "safelist_exes", "block_cmdline"):
        seen = {}
        for index, value in enumerate(getattr(config, field)):
            key = ((value.executable.casefold(), value.contains.casefold())
                   if field == "block_cmdline" else value.casefold())
            if key in seen:
                items.append(ReviewItem("duplicate", field, index,
                                        f"Regra repetida do item {seen[key] + 1}, ignorando caixa."))
            else:
                seen[key] = index
            if field not in {"block_exes", "block_cmdline"}:
                continue
            executable = value.executable if field == "block_cmdline" else value
            if executable.casefold() in MANDATORY_NAMES:
                items.append(ReviewItem("mandatory_protection", field, index,
                                        f"{executable}: o catálogo de proteção obrigatória prevalece sobre esta regra."))
            elif executable.casefold() in safelist:
                items.append(ReviewItem("user_protection", field, index,
                                        f"{executable}: Proteção adicional preserva esse nome antes das regras de bloqueio."))
            if field == "block_exes" and executable.casefold() == "javaw.exe":
                items.append(ReviewItem("java_name", field, index,
                                        "javaw.exe por nome abrange aplicativos Java além do Minecraft. "
                                        "Uma regra de linha de comando permite escolher um trecho específico."))
    return ConfigReview(active_windows, target_rules, tuple(items))

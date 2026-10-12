"""Diferenças legíveis do rascunho, sem gravar ou revalidar o ambiente."""

from dataclasses import dataclass
from difflib import SequenceMatcher

from core.config_comparison import configs_equal
from core.models import AppConfig


_FIELDS = ("windows", "block_exes", "block_folders", "safelist_exes", "block_cmdline")
_DAYS = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")


@dataclass(frozen=True)
class ConfigChange:
    field: str
    kind: str
    before_index: int | None
    after_index: int | None
    before: str | None
    after: str | None


@dataclass(frozen=True)
class ConfigDiff:
    is_new: bool
    changes: tuple[ConfigChange, ...]
    extras_changed: bool


def _describe(field, value) -> str:
    if field == "windows":
        start = f"{value.start.hour:02d}:{value.start.minute:02d}"
        end = f"{value.end.hour:02d}:{value.end.minute:02d}"
        days = ("dias: " + ", ".join(_DAYS[day] for day in value.days)
                if value.days else "desativado (sem dias)")
        return f"{start}–{end} · {days}"
    if field == "block_cmdline":
        return f"{value.executable} + trecho: {value.contains!r}"
    return value


def _list_changes(field, before, after):
    if before == after:
        return
    prefix = 0
    limit = min(len(before), len(after))
    while prefix < limit and before[prefix] == after[prefix]:
        prefix += 1
    before_limit, after_limit = len(before), len(after)
    while (before_limit > prefix and after_limit > prefix
           and before[before_limit - 1] == after[after_limit - 1]):
        before_limit -= 1
        after_limit -= 1
    # Preservar bordas iguais evita alinhamento quadrático de duplicatas quando
    # somente o centro mudou. O miolo conserva o matcher exato, sem fallback.
    matcher = SequenceMatcher(a=before[prefix:before_limit],
                              b=after[prefix:after_limit], autojunk=False)
    for kind, before_start, before_end, after_start, after_end in matcher.get_opcodes():
        before_start += prefix
        before_end += prefix
        after_start += prefix
        after_end += prefix
        if kind == "equal":
            continue
        paired = min(before_end - before_start, after_end - after_start) if kind == "replace" else 0
        for offset in range(paired):
            old_index, new_index = before_start + offset, after_start + offset
            yield ConfigChange(field, "replace", old_index, new_index,
                               _describe(field, before[old_index]), _describe(field, after[new_index]))
        for old_index in range(before_start + paired, before_end):
            yield ConfigChange(field, "delete", old_index, None,
                               _describe(field, before[old_index]), None)
        for new_index in range(after_start + paired, after_end):
            yield ConfigChange(field, "insert", None, new_index,
                               None, _describe(field, after[new_index]))


def diff_config(baseline: AppConfig | None, draft: AppConfig) -> ConfigDiff:
    """Compara modelos tipados, sem normalizar valores nem alterar entradas.

    Índices são originais e zero-based; kinds são insert/delete/replace. Cada
    bloco replace pareia posições e mantém as sobras como exclusões/inclusões.
    Campos seguem a ordem windows e das quatro listas de processos. Ordem,
    duplicatas, caixa, dias e trechos literais não são normalizados.
    Bordas exatamente iguais são preservadas antes de alinhar o miolo; índices
    continuam globais. Não promete script mínimo ou identidade de duplicatas.

    Baseline None significa primeiro arquivo e compara contra listas/extras
    vazios. Extras JSON acíclicos usam igualdade estrutural tipada, com somente
    um indicador no resultado. A função espera modelos de configuração, não
    iterables; não valida caminhos/variáveis, serializa ou consulta runtime.
    """
    if baseline is not None and not isinstance(baseline, AppConfig):
        raise TypeError("diff: baseline deve ser AppConfig ou None")
    if not isinstance(draft, AppConfig):
        raise TypeError("diff: draft deve ser AppConfig")
    before = AppConfig() if baseline is None else baseline
    changes = tuple(
        change
        for field in _FIELDS
        for change in _list_changes(field, getattr(before, field), getattr(draft, field))
    )
    extras_changed = not configs_equal(AppConfig(extra=before.extra), AppConfig(extra=draft.extra))
    return ConfigDiff(baseline is None, changes, extras_changed)

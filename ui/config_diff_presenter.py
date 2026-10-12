"""Texto compartilhado do diff, sem UI, IO ou valores privados dos extras."""

from collections import Counter
from dataclasses import dataclass
import unicodedata

from core.config_diff import ConfigDiff


_CHANGE_LIMIT = 100
_VALUE_LIMIT = 1000
_TRUNCATED = "… [valor truncado]"
_FIELDS = {
    "windows": "Horários",
    "block_exes": "Executáveis",
    "block_folders": "Pastas",
    "safelist_exes": "Proteção adicional",
    "block_cmdline": "Linha de comando",
}


@dataclass(frozen=True)
class DiffView:
    title: str
    detail: str


def _escaped_char(char: str) -> str:
    escapes = {"\r": r"\r", "\n": r"\n", "\t": r"\t"}
    if char in escapes:
        return escapes[char]
    if unicodedata.category(char) in {"Cc", "Cf", "Cs", "Zl", "Zp"}:
        code = ord(char)
        if code <= 0xff:
            return f"\\x{code:02x}"
        if code <= 0xffff:
            return f"\\u{code:04x}"
        return f"\\U{code:08x}"
    return char


def _display_value(value: str) -> tuple[str, bool]:
    # Contar caracteres já escapados e nunca cortar um escape pela metade.
    parts = []
    length = 0
    for char in value:
        part = _escaped_char(char)
        if length + len(part) > _VALUE_LIMIT:
            while length > _VALUE_LIMIT - len(_TRUNCATED):
                length -= len(parts.pop())
            return "".join(parts) + _TRUNCATED, True
        parts.append(part)
        length += len(part)
    return "".join(parts), False


def format_config_diff(report: ConfigDiff) -> DiffView:
    """Formata até 100 mudanças, com no máximo 1000 caracteres por valor.

    O limite do valor inclui escapes e marcador de truncamento. Espaços e repr
    já presentes são preservados. O relatório é informativo e não lê arquivo,
    decide conflitos, solicita confirmação ou altera o rascunho.
    """
    if not isinstance(report, ConfigDiff):
        raise TypeError("apresentação do diff: esperado ConfigDiff")
    if report.is_new:
        title = "Nova configuração"
    elif not report.changes and not report.extras_changed:
        title = "Sem alterações"
    else:
        title = "Alterações da configuração"

    counts = Counter(change.kind for change in report.changes)
    lines = [
        "Comparação do rascunho com a configuração salva/carregada nesta sessão.",
    ]
    if report.is_new:
        lines.append("Nova configuração: ainda não há versão salva/carregada nesta sessão.")
        lines.append("O arquivo ainda será criado ao Salvar.")
    lines.extend((
        f"Itens alterados: {len(report.changes)}.",
        f"Resumo: inclusões: {counts['insert']}; remoções: {counts['delete']}; alterações: {counts['replace']}.",
        "Extras: " + ("alterados" if report.extras_changed else "sem alterações")
        + "; valores privados não exibidos.",
        "Limites de exibição: 100 mudanças e 1000 caracteres por valor, incluindo escapes e aviso de truncamento.",
    ))
    truncated_values = 0
    for change in report.changes[:_CHANGE_LIMIT]:
        if change.kind == "insert":
            action = f"incluído (novo {change.after_index + 1})"
        elif change.kind == "delete":
            action = f"removido (salvo {change.before_index + 1})"
        else:
            action = f"alterado (salvo {change.before_index + 1} → novo {change.after_index + 1})"
        lines.extend(("", f"{_FIELDS[change.field]} — {action}"))
        for label, value in (("Antes", change.before), ("Depois", change.after)):
            if value is not None:
                displayed, truncated = _display_value(value)
                truncated_values += truncated
                lines.append(f"  {label}: {displayed}")
    if len(report.changes) > _CHANGE_LIMIT:
        omitted = len(report.changes) - _CHANGE_LIMIT
        noun = "mudança não exibida" if omitted == 1 else "mudanças não exibidas"
        lines.extend(("", f"Mais {omitted} {noun}."))
    if truncated_values:
        lines.append(f"Valores exibidos truncados: {truncated_values}.")
    lines.extend(("", "O arquivo não é relido nesta comparação. Conflitos continuam sendo verificados ao Salvar."))
    return DiffView(title, "\n".join(lines))

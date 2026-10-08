"""Editor interativo de horários e regras já tipadas da configuração."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from pathlib import Path

from core.config import ConfigError
from core.config_editor import ConfigDraft
from core.config_repository import ConfigConflictError, read_snapshot, save_snapshot


_RULE_FIELDS = (
    ("1", "block_exes", "Executáveis bloqueados"),
    ("2", "block_folders", "Pastas bloqueadas"),
    ("3", "safelist_exes", "Executáveis adicionais protegidos"),
    ("4", "block_cmdline", "Regras de linha de comando"),
)


def _parse_days(value: str) -> list[int]:
    """Lê dias 0–6; vazio significa todos e 'nenhum' desativa a janela."""
    value = value.strip()
    if not value:
        return list(range(7))
    if value.casefold() == "nenhum":
        return []
    try:
        days = [int(part.strip()) for part in value.split(",")]
    except ValueError:
        raise ConfigError("dias: informe números de 0 a 6, vazio ou 'nenhum'") from None
    if any(not 0 <= day <= 6 for day in days):
        raise ConfigError("dias: cada número deve estar entre 0 e 6")
    if len(set(days)) != len(days):
        raise ConfigError("dias: não repita o mesmo número")
    return days


def _read_index(value: str, length: int) -> int:
    try:
        index = int(value.strip()) - 1
    except ValueError:
        raise ConfigError("informe o número da linha") from None
    if index < 0 or index >= length:
        raise ConfigError("número fora da lista")
    return index


def _format_days(days: Iterable[int]) -> str:
    values = tuple(days)
    return "nenhum (desativada)" if not values else ",".join(map(str, values))


def _show_config(draft: ConfigDraft, output_fn: Callable[[str], object]) -> None:
    config = draft.config
    output_fn("\nHorários:")
    if not config.windows:
        output_fn("  (nenhum)")
    for index, window in enumerate(config.windows, 1):
        output_fn(
            f"  {index}. {window.start.strftime('%H:%M')}–"
            f"{window.end.strftime('%H:%M')}; dias {_format_days(window.days)}"
        )
    for number, field, label in _RULE_FIELDS:
        output_fn(f"\n{label}:")
        values = getattr(config, field)
        if not values:
            output_fn("  (nenhum)")
        for index, value in enumerate(values, 1):
            if field == "block_cmdline":
                rendered = f"{value.executable} contém {value.contains!r}"
            else:
                rendered = str(value)
            output_fn(f"  {index}. {rendered}")


def _edit_windows(draft: ConfigDraft, input_fn, output_fn) -> None:
    output_fn("Janelas: 1 listar, 2 adicionar, 3 alterar, 4 remover, 0 voltar")
    action = input_fn("Horários > ").strip()
    if action == "1":
        _show_config(draft, output_fn)
    elif action == "2":
        start = input_fn("Início (HH:MM): ").strip()
        end = input_fn("Fim (HH:MM): ").strip()
        days = _parse_days(input_fn("Dias 0–6 (vazio=todos, nenhum=desativada): "))
        draft.add_window(start, end, days)
        output_fn("Horário adicionado ao rascunho.")
    elif action == "3":
        index = _read_index(input_fn("Número do horário: "), len(draft.config.windows))
        start = input_fn("Novo início (HH:MM): ").strip()
        end = input_fn("Novo fim (HH:MM): ").strip()
        days = _parse_days(input_fn("Dias 0–6 (vazio=todos, nenhum=desativada): "))
        draft.update_window(index, start, end, days)
        output_fn("Horário alterado no rascunho.")
    elif action == "4":
        index = _read_index(input_fn("Número do horário: "), len(draft.config.windows))
        draft.remove_window(index)
        output_fn("Horário removido do rascunho.")
    elif action != "0":
        raise ConfigError("opção de horários inválida")


def _edit_rules(draft: ConfigDraft, input_fn, output_fn) -> None:
    output_fn("Regras: 1 executáveis, 2 pastas, 3 proteção adicional, 4 cmdline, 0 voltar")
    selection = input_fn("Regras > ").strip()
    if selection == "0":
        return
    entry = next((item for item in _RULE_FIELDS if item[0] == selection), None)
    if entry is None:
        raise ConfigError("opção de regras inválida")
    _, field, label = entry
    values = getattr(draft.config, field)
    output_fn(f"{label}: 1 listar, 2 adicionar, 3 alterar, 4 remover, 0 voltar")
    action = input_fn("Ação > ").strip()
    if action == "0":
        return
    if action == "1":
        _show_config(draft, output_fn)
        return
    if action == "4":
        index = _read_index(input_fn("Número da regra: "), len(values))
        draft.remove_rule(field, index)
        output_fn("Regra removida do rascunho.")
        return
    if action not in ("2", "3"):
        raise ConfigError("opção de regras inválida")
    index = None
    if action == "3":
        index = _read_index(input_fn("Número da regra: "), len(values))
    if field == "block_cmdline":
        value = {
            "executable": input_fn("Executável (.exe): ").strip(),
            "contains": input_fn("Trecho literal: "),
        }
    else:
        value = input_fn("Nome .exe ou pasta absoluta: ").strip()
    if action == "2":
        draft.add_rule(field, value)
        output_fn("Regra adicionada ao rascunho.")
    else:
        draft.update_rule(field, index, value)
        output_fn("Regra alterada no rascunho.")


def run_config_editor(
    path: str | Path,
    *,
    input_fn: Callable[[str], str] | None = None,
    output_fn: Callable[[str], object] | None = None,
) -> int:
    """Edita agenda e regras de processos num rascunho, sem aplicar efeitos."""
    input_fn = input if input_fn is None else input_fn
    output_fn = print if output_fn is None else output_fn
    try:
        snapshot = read_snapshot(path)
        draft = ConfigDraft(snapshot.config)
        output_fn(f"Editando {path}. Alterações não salvas são um rascunho.")
        output_fn(
            "Salvar publica o JSON; outro Focus em execução pode recarregá-lo "
            "no próximo ciclo. A proteção adicional mantém as proteções obrigatórias."
        )
    except (EOFError, KeyboardInterrupt):
        output_fn("\nSaindo; alterações não salvas descartadas.")
        return 0
    except (ConfigError, OSError, UnicodeError, ValueError) as exc:
        output_fn(f"Erro ao abrir configuração: {exc}")
        return 1

    while True:
        try:
            output_fn(
                "\n1 horários  2 regras de processos  3 salvar  "
                "4 recarregar (descarta rascunho)  5 sair"
            )
            action = input_fn("Editor > ").strip()
            if action == "1":
                _edit_windows(draft, input_fn, output_fn)
            elif action == "2":
                _edit_rules(draft, input_fn, output_fn)
            elif action == "3":
                snapshot = save_snapshot(path, draft.config, snapshot)
                output_fn("Configuração salva.")
            elif action == "4":
                reloaded = read_snapshot(path)
                reloaded_draft = ConfigDraft(reloaded.config)
                # Falha de leitura/validação preserva o rascunho e seu baseline.
                snapshot, draft = reloaded, reloaded_draft
                output_fn("Rascunho descartado; configuração recarregada.")
            elif action == "5":
                output_fn("Saindo; alterações não salvas descartadas.")
                return 0
            else:
                output_fn("Erro: opção inválida.")
        except (EOFError, KeyboardInterrupt):
            output_fn("\nSaindo; alterações não salvas descartadas.")
            return 0
        except ConfigConflictError as exc:
            output_fn(f"Conflito: {exc}. Use Recarregar antes de salvar; isso descarta o rascunho.")
        except (ConfigError, OSError, UnicodeError, ValueError) as exc:
            output_fn(f"Erro: {exc}")

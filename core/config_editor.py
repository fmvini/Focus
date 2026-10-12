"""Rascunho de configuração em memória, sem gravação ou aplicação de regras."""

from copy import deepcopy
from collections import deque
import ntpath
import os

from core.config import ConfigError, config_to_dict, parse_config
from core.models import AppConfig


_RULE_FIELDS = ("block_exes", "block_folders", "safelist_exes", "block_cmdline")
_HISTORY_LIMIT = 50


class ConfigDraft:
    """Edita uma cópia validada; uma operação inválida não altera o rascunho.

    Salvar, detectar conflitos externos e aplicar a configuração são tarefas
    das camadas de repositório e integração. Campos opacos permanecem intactos.
    """

    def __init__(self, config: AppConfig):
        self._config = parse_config(config_to_dict(config))
        self._undo = deque(maxlen=_HISTORY_LIMIT)
        self._redo = []

    @property
    def config(self) -> AppConfig:
        """Snapshot independente, inclusive dos objetos aninhados em extra."""
        return deepcopy(self._config)

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def undo(self) -> bool:
        """Restaura edição anterior em memória; não grava nem muda o baseline."""
        if not self._undo:
            return False
        restored = parse_config(config_to_dict(self._undo[-1]))
        self._redo.append(self._config)
        self._config = restored
        self._undo.pop()
        return True

    def redo(self) -> bool:
        if not self._redo:
            return False
        restored = parse_config(config_to_dict(self._redo[-1]))
        self._undo.append(self._config)
        self._config = restored
        self._redo.pop()
        return True

    def replace_config(self, config: AppConfig) -> None:
        """Substitui o conteúdo como uma edição reversível, após validação."""
        self._accept(config_to_dict(config))

    @staticmethod
    def _index(index, values) -> int:
        if type(index) is not int or not 0 <= index < len(values):
            raise ConfigError("índice: esperado inteiro de 0 até o último item da lista")
        return index

    @staticmethod
    def _field(field: str) -> str:
        if not isinstance(field, str) or field not in _RULE_FIELDS:
            raise ConfigError("campo: esperada uma das quatro listas de processos")
        return field

    @staticmethod
    def _window(start: str, end: str, days):
        try:
            selected_days = list(range(7)) if days is None else list(days)
        except (TypeError, ValueError, RuntimeError, OverflowError) as exc:
            raise ConfigError("days: esperado iterable de dias inteiros de 0 a 6") from exc
        return {"start": start, "end": end, "days": selected_days}

    def _accept(self, candidate: dict) -> None:
        # Publicar somente após validação completa: erros mantêm a versão atual.
        validated = parse_config(candidate)
        if validated == self._config:
            return
        self._undo.append(self._config)
        self._redo.clear()
        self._config = validated

    def add_window(self, start: str, end: str, days=None) -> None:
        candidate = config_to_dict(self._config)
        candidate["windows"].append(self._window(start, end, days))
        self._accept(candidate)

    def update_window(self, index, start: str, end: str, days=None) -> None:
        candidate = config_to_dict(self._config)
        index = self._index(index, candidate["windows"])
        candidate["windows"][index] = self._window(start, end, days)
        self._accept(candidate)

    def remove_window(self, index) -> None:
        candidate = config_to_dict(self._config)
        index = self._index(index, candidate["windows"])
        del candidate["windows"][index]
        self._accept(candidate)

    def duplicate_window(self, index) -> None:
        """Acrescenta ao final uma cópia validada da janela selecionada."""
        candidate = config_to_dict(self._config)
        index = self._index(index, candidate["windows"])
        candidate["windows"].append(deepcopy(candidate["windows"][index]))
        self._accept(candidate)

    def add_rule(self, field: str, value) -> None:
        field = self._field(field)
        candidate = config_to_dict(self._config)
        candidate[field].append(value)
        self._accept(candidate)

    def add_executable_paths(self, field: str, paths) -> int:
        """Inclui nomes de arquivos selecionados em um lote validado, sem IO.

        Regras por nome abrangem qualquer instalação com o mesmo executável.
        Não lê, resolve ou executa os arquivos; caminhos não são persistidos.
        Preserva duplicatas anteriores e evita novas equivalentes por casefold.
        """
        field = self._field(field)
        if field not in ("block_exes", "safelist_exes"):
            raise ConfigError("seleção de executáveis: escolha Executáveis ou Proteção adicional")
        if isinstance(paths, (str, bytes, bytearray, os.PathLike)):
            raise ConfigError("seleção de executáveis: esperada uma coleção de caminhos")
        candidate = config_to_dict(self._config)
        known = {name.casefold() for name in candidate[field]}
        added = 0
        try:
            for path in paths:
                selected = os.fspath(path)
                if not isinstance(selected, str) or "\x00" in selected:
                    raise ConfigError("seleção de executáveis: esperado caminho textual sem NUL")
                name = ntpath.basename(selected)
                if name.casefold() not in known:
                    candidate[field].append(name)
                    known.add(name.casefold())
                    added += 1
        except ConfigError:
            raise
        except Exception as exc:
            raise ConfigError("Não foi possível ler a seleção de executáveis") from exc
        self._accept(candidate)
        return added

    def update_rule(self, field: str, index, value) -> None:
        field = self._field(field)
        candidate = config_to_dict(self._config)
        index = self._index(index, candidate[field])
        candidate[field][index] = value
        self._accept(candidate)

    def remove_rule(self, field: str, index) -> None:
        field = self._field(field)
        candidate = config_to_dict(self._config)
        index = self._index(index, candidate[field])
        del candidate[field][index]
        self._accept(candidate)

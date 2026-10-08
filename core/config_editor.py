"""Rascunho de configuração em memória, sem gravação ou aplicação de regras."""

from copy import deepcopy

from core.config import ConfigError, config_to_dict, parse_config
from core.models import AppConfig


_RULE_FIELDS = ("block_exes", "block_folders", "safelist_exes", "block_cmdline")


class ConfigDraft:
    """Edita uma cópia validada; uma operação inválida não altera o rascunho.

    Salvar, detectar conflitos externos e aplicar a configuração são tarefas
    das camadas de repositório e integração. Campos opacos permanecem intactos.
    """

    def __init__(self, config: AppConfig):
        self._config = parse_config(config_to_dict(config))

    @property
    def config(self) -> AppConfig:
        """Snapshot independente, inclusive dos objetos aninhados em extra."""
        return deepcopy(self._config)

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

    def add_rule(self, field: str, value) -> None:
        field = self._field(field)
        candidate = config_to_dict(self._config)
        candidate[field].append(value)
        self._accept(candidate)

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

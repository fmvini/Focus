"""Igualdade estrutural tipada da configuração, sem validar ou serializar."""

from dataclasses import fields

from core.models import AppConfig, CmdlineRule, ScheduleWindow


def _values_equal(left, right) -> bool:
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        # Objetos JSON têm chaves textuais; sua ordem não muda o conteúdo.
        return left.keys() == right.keys() and all(
            _values_equal(value, right[key]) for key, value in left.items()
        )
    if isinstance(left, (list, tuple)):
        return len(left) == len(right) and all(
            _values_equal(a, b) for a, b in zip(left, right)
        )
    if isinstance(left, (AppConfig, ScheduleWindow, CmdlineRule)):
        return all(
            _values_equal(getattr(left, field.name), getattr(right, field.name))
            for field in fields(left)
        )
    return left == right


def configs_equal(left: AppConfig, right: AppConfig) -> bool:
    """Compara modelos e extras JSON: bool, int e float são tipos distintos.

    Dicionários ignoram ordem; listas/tuplas preservam ordem e duplicatas.
    Não revalida caminhos/ambiente ou altera os modelos. Espera AppConfig com
    extras JSON acíclicos; validação de conteúdo continua nas APIs de edição.
    """
    if not isinstance(left, AppConfig) or not isinstance(right, AppConfig):
        raise TypeError("comparação: esperado AppConfig em ambos os argumentos")
    return _values_equal(left, right)

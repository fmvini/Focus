"""Tipos compartilhados pela configuração e pelo agendador.

As regras de entrada são verificadas por core.config. Os campos extras são
preservados no JSON, mas não são executados nesta primeira fase.
"""

from dataclasses import dataclass, field
from datetime import time
from typing import Any


@dataclass(frozen=True)
class ScheduleWindow:
    start: time
    end: time
    days: tuple[int, ...] = tuple(range(7))


@dataclass(frozen=True)
class AppConfig:
    windows: tuple[ScheduleWindow, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)

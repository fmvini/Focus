"""Tipos compartilhados pela configuração, agenda e regras de processos.

As regras de entrada são verificadas por core.config. Os campos extras são
preservados no JSON; somente campos tipados têm regras implementadas.
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
class CmdlineRule:
    executable: str
    contains: str


@dataclass(frozen=True)
class AppConfig:
    windows: tuple[ScheduleWindow, ...] = ()
    extra: dict[str, Any] = field(default_factory=dict)
    block_exes: tuple[str, ...] = ()
    block_folders: tuple[str, ...] = ()
    safelist_exes: tuple[str, ...] = ()
    block_cmdline: tuple[CmdlineRule, ...] = ()

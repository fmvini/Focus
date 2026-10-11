"""Caixa limitada para callbacks da bandeja, sem dependência de UI ou IO."""

from dataclasses import dataclass
from threading import Lock


_ACTIONS = frozenset({"show", "stop", "close", "ready", "error"})


@dataclass(frozen=True)
class TrayCommand:
    action: str
    detail: str | None = None


class TrayMailbox:
    """Coalesce por ação, mantendo a primeira posição e o último detalhe."""

    def __init__(self):
        self._lock = Lock()
        self._pending: dict[str, TrayCommand] = {}
        self._closed = False

    def post(self, action: str, detail: str | None = None) -> None:
        with self._lock:
            if self._closed:
                return
            if not isinstance(action, str) or action not in _ACTIONS:
                raise ValueError("ação desconhecida da bandeja")
            self._pending[action] = TrayCommand(action, detail)

    def drain(self) -> tuple[TrayCommand, ...]:
        with self._lock:
            commands = tuple(self._pending.values())
            self._pending.clear()
            return commands

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._pending.clear()

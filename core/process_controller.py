"""Controle explícito do motor, sem IO ou efeitos durante a construção."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
import math
from threading import Event, Lock, Thread
import time
from typing import TYPE_CHECKING, Callable

from core.config import load_config
from core.models import AppConfig
from core.scheduler import is_blocking

if TYPE_CHECKING:
    from core.proc_blocker import ScanReport


@dataclass(frozen=True)
class RuntimeSnapshot:
    state: str = "idle"
    active: bool | None = None
    last_scan: datetime | None = None
    report: ScanReport | None = None
    error: str | None = None


def _create_blocker():
    # Importação e adaptador real somente após Iniciar, dentro do worker.
    from core.proc_blocker import ProcessBlocker

    return ProcessBlocker()


def _wait_event(stop_event: Event, timeout: float) -> bool:
    return stop_event.wait(timeout)


class ProcessController:
    """Um worker não daemon por execução; snapshots não acessam widgets.

    ``blocker_factory()`` retorna um objeto com ``scan(config, may_act)``.
    ``loader(path)`` retorna configuração validada. ``clock()`` fornece data
    local ingênua; ``monotonic()`` fornece segundos da cadência.
    ``waiter(stop_event, timeout)`` deve esperar de forma interrompível como
    Event.wait. Essas fronteiras são injetáveis, sem chamadas na construção.
    """

    def __init__(
        self, path, *, blocker_factory=None, interval=5.0,
        clock: Callable[[], datetime] | None = None,
        loader: Callable[[object], AppConfig] | None = None,
        monotonic: Callable[[], float] | None = None,
        waiter: Callable[[Event, float], bool] | None = None,
    ):
        if (isinstance(interval, bool) or not isinstance(interval, (int, float))
                or not math.isfinite(interval) or interval <= 0):
            raise ValueError("interval must be a finite positive number")
        self.path = path
        self._factory = _create_blocker if blocker_factory is None else blocker_factory
        self._interval = float(interval)
        self._clock = datetime.now if clock is None else clock
        self._loader = load_config if loader is None else loader
        self._monotonic = time.monotonic if monotonic is None else monotonic
        self._waiter = _wait_event if waiter is None else waiter
        self._lock = Lock()
        self._thread: Thread | None = None
        self._stop_event: Event | None = None
        self._snapshot = RuntimeSnapshot()

    def start(self) -> bool:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return False
            stop_event = Event()
            self._stop_event = stop_event
            self._thread = None
            self._snapshot = RuntimeSnapshot(state="running")
            try:
                worker = Thread(
                    target=self._run, args=(stop_event,),
                    name="FocusProcessController", daemon=False,
                )
                self._thread = worker
                worker.start()
            except Exception as exc:
                stop_event.set()
                self._thread = None
                self._snapshot = RuntimeSnapshot(state="error", error=self._describe_error(exc))
                return False
            return True

    def stop(self) -> None:
        with self._lock:
            if self._stop_event is not None:
                self._stop_event.set()
            if self._thread is not None and self._thread.is_alive():
                if self._snapshot.state != "error":
                    self._snapshot = replace(self._snapshot, state="stopping")

    def snapshot(self) -> RuntimeSnapshot:
        with self._lock:
            return self._snapshot

    def is_alive(self) -> bool:
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def wait(self, timeout=None) -> None:
        """Espera explícita fora de callbacks; não segura o lock durante join."""
        with self._lock:
            worker = self._thread
        if worker is not None:
            worker.join(timeout)

    @staticmethod
    def _describe_error(exc: Exception) -> str:
        parts = []
        seen = set()
        cause = exc
        while cause is not None and id(cause) not in seen:
            seen.add(id(cause))
            parts.append(f"{type(cause).__name__}: {cause}")
            cause = cause.__cause__
        return " <- ".join(parts)

    def _fail(self, stop_event: Event, exc: Exception) -> None:
        # Fecha também closures de ciclos anteriores e mantém diagnóstico.
        stop_event.set()
        with self._lock:
            self._snapshot = replace(
                self._snapshot, state="error",
                report=getattr(exc, "partial_report", None),
                error=self._describe_error(exc),
            )

    def _may_act(self, stop_event: Event, config: AppConfig) -> bool:
        if stop_event.is_set():
            return False
        try:
            observed = self._clock()
            active = is_blocking(config.windows, observed)
        except Exception as exc:
            self._fail(stop_event, exc)
            raise
        with self._lock:
            # stop pode ocorrer enquanto o relógio/agenda eram avaliados.
            if stop_event.is_set():
                return False
            self._snapshot = replace(self._snapshot, active=active, last_scan=observed)
            return active

    def _run(self, stop_event: Event) -> None:
        try:
            if stop_event.is_set():
                return
            blocker = self._factory()
            if stop_event.is_set():
                return
            deadline = self._monotonic()
            while not stop_event.is_set():
                remaining = deadline - self._monotonic()
                if remaining > 0:
                    self._waiter(stop_event, remaining)
                    continue
                config = self._loader(self.path)
                if stop_event.is_set():
                    break
                observed = self._clock()
                active = is_blocking(config.windows, observed)
                with self._lock:
                    if stop_event.is_set():
                        break
                    self._snapshot = replace(self._snapshot, active=active, last_scan=observed)

                def may_act(snapshot=config):
                    return self._may_act(stop_event, snapshot)

                report = blocker.scan(config, may_act)
                with self._lock:
                    if self._snapshot.state != "error":
                        self._snapshot = replace(self._snapshot, report=report)
                if stop_event.is_set():
                    break
                deadline += self._interval
                finished = self._monotonic()
                if finished > deadline:
                    deadline += (math.floor((finished - deadline) / self._interval) + 1) * self._interval
        except Exception as exc:
            self._fail(stop_event, exc)
        finally:
            stop_event.set()
            with self._lock:
                if self._snapshot.state != "error":
                    self._snapshot = replace(self._snapshot, state="idle")

"""Uma GUI por configuração/sessão Windows, sem alterar arquivos ou guardar CLI."""

import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
from threading import Lock
from typing import Protocol


class InstanceGuardError(RuntimeError):
    """Falha ao normalizar o caminho ou criar/fechar o handle da guarda."""


class MutexBackend(Protocol):
    """Fronteira injetável: handles opacos, nenhuma aquisição de ownership.

    create_mutex retorna (handle válido, already_exists), ou levanta erro sem
    deixar handle oculto. close_handle retorna None em sucesso e levanta erro
    em falha; nesse caso o guard preserva o handle para nova tentativa.
    """

    def create_mutex(self, name: str) -> tuple[object, bool]: ...
    def close_handle(self, handle: object) -> None: ...


class WindowsMutexBackend:
    """WinDLL e assinaturas só preparados no primeiro acesso ao SO."""

    def __init__(self, *, kernel32=None):
        self._kernel32 = kernel32
        self._api = None
        self._lock = Lock()

    def _get_api(self):
        with self._lock:
            if self._api is None:
                dll = self._kernel32
                if dll is None:
                    if os.name != "nt":
                        raise OSError("A guarda gráfica de instância requer Windows")
                    dll = ctypes.WinDLL("kernel32", use_last_error=True)
                create = dll.CreateMutexW
                create.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR]
                create.restype = wintypes.HANDLE
                close = dll.CloseHandle
                close.argtypes = [wintypes.HANDLE]
                close.restype = wintypes.BOOL
                self._kernel32 = dll
                self._api = (create, close)
            return self._api

    def create_mutex(self, name: str) -> tuple[object, bool]:
        create, _ = self._get_api()
        ctypes.set_last_error(0)
        handle = create(None, False, name)
        error = ctypes.get_last_error()
        if not handle:
            raise ctypes.WinError(error)
        return handle, error == 183  # ERROR_ALREADY_EXISTS

    def close_handle(self, handle: object) -> None:
        _, close = self._get_api()
        if not close(handle):
            raise ctypes.WinError(ctypes.get_last_error())


class InstanceGuard:
    """Guarda por existência do mutex, sem ownership, espera ou ReleaseMutex.

    Construção não resolve caminhos nem acessa WinDLL/SO. No primeiro acquire,
    Path.resolve e os.path.normcase definem o nome Local\\Focus.Gui.<SHA256>
    do caminho em UTF-8; o nome permanece estável até mesmo após release.
    Não unifica hardlinks, sessões Windows diferentes ou watcher CLI.

    ``backend`` implementa MutexBackend; o padrão é WindowsMutexBackend lazy.
    acquire é idempotente quando este objeto já detém sua guarda. Um handle de
    nome existente é fechado antes de retornar False. Se fechamento falhar,
    release ou acquire tenta novamente sem perder/alocar outro handle.
    """

    def __init__(self, path, *, backend: MutexBackend | None = None):
        self._path = path
        self._backend = backend
        self._name: str | None = None
        self._handle = None
        self._owned = False
        self._lock = Lock()

    def _close(self) -> None:
        if self._handle is None:
            return
        try:
            self._backend.close_handle(self._handle)
        except Exception as exc:
            raise InstanceGuardError(f"Não foi possível fechar a guarda gráfica: {exc}") from exc
        self._handle = None
        self._owned = False

    def acquire(self) -> bool:
        with self._lock:
            if self._owned:
                return True
            # Fechamento de um handle duplicado que falhou anteriormente.
            self._close()
            try:
                if self._name is None:
                    normalized = os.path.normcase(str(Path(self._path).resolve()))
                    if "\x00" in normalized:
                        raise ValueError("Caminho de configuração contém NUL")
                    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
                    self._name = "Local\\Focus.Gui." + digest
                if self._backend is None:
                    self._backend = WindowsMutexBackend()
                handle, already_exists = self._backend.create_mutex(self._name)
                if not handle:
                    raise OSError("Backend retornou handle nulo")
            except Exception as exc:
                raise InstanceGuardError(f"Não foi possível adquirir a guarda gráfica: {exc}") from exc
            # Reter antes de qualquer tentativa de cleanup que possa falhar.
            self._handle = handle
            if already_exists:
                self._close()
                return False
            self._owned = True
            return True

    def release(self) -> None:
        with self._lock:
            self._close()

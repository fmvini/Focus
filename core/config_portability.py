"""Criação/exportação JSON exclusiva, sem sobrescrever qualquer destino."""

import os
from pathlib import Path
import tempfile

from core.config import ConfigError, _parse_config_contents, _serialize_config
from core.config_repository import ConfigConflictError, ConfigSnapshot
from core.models import AppConfig


_WINDOWS = os.name == "nt"


def _publish_new(temporary_path: Path, destination: Path) -> None:
    if _WINDOWS:
        # Windows recusa destino existente; POSIX rename pode sobrescrever.
        os.rename(temporary_path, destination)
    else:
        os.link(temporary_path, destination)


def _new_destination(
    path: str | Path, active_path: str | Path | None = None, *, conflict: bool = False,
) -> Path:
    destination = Path(path)
    resolved = destination.resolve()
    if active_path is not None:
        active = Path(active_path).resolve()
        if os.path.normcase(str(resolved)) == os.path.normcase(str(active)):
            raise ConfigError("Exportação: destino é a configuração ativa ou um alias")
    try:
        destination.lstat()
    except FileNotFoundError:
        return resolved
    # Inclui arquivos, diretórios, hard links e links simbólicos quebrados.
    if conflict:
        raise ConfigConflictError("Configuração já existe; recarregue antes de salvar")
    raise ConfigError("Exportação: destino já existe; escolha um arquivo novo")


def _write_new_contents(
    path: str | Path, contents: bytes, *, active_path: str | Path | None = None,
) -> None:
    """Publica bytes já preparados exclusivamente no mesmo volume.

    Windows usa rename, que recusa existente, inclusive em FAT/exFAT. Os demais
    sistemas usam hard link e falham se não houver suporte, sem fallback de
    sobrescrita. A limpeza remove apenas o temporário, nunca o destino.
    """
    temporary_path = None
    failure = None
    creating = active_path is None
    operation = "criar" if creating else "exportar"
    try:
        destination = _new_destination(path, active_path, conflict=creating)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=destination.parent, prefix=f".{destination.name}.",
            suffix=".tmp", delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        # Reconfere aliases e existência depois da preparação; o primitivo ainda
        # garante exclusividade se outro escritor criar o destino em seguida.
        _new_destination(destination, active_path, conflict=creating)
        _publish_new(temporary_path, destination)
        if _WINDOWS:
            temporary_path = None  # rename já consumiu o temporário.
    except ConfigError as exc:
        failure = exc
        raise
    except FileExistsError as exc:
        error_type = ConfigConflictError if creating else ConfigError
        failure = error_type(f"Não foi possível {operation} configuração em {path}: {exc}")
        raise failure from exc
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError, RuntimeError) as exc:
        failure = ConfigError(f"Não foi possível {operation} configuração em {path}: {exc}")
        raise failure from exc
    finally:
        if temporary_path is not None:
            try:
                temporary_path.unlink(missing_ok=True)
            except OSError as exc:
                message = f"Falha ao remover temporário {temporary_path}: {exc}"
                if failure is not None:
                    failure.add_note(message)
                else:
                    raise ConfigError(message) from exc


def export_new_config(
    path: str | Path, config: AppConfig, *, active_path: str | Path,
) -> None:
    """Exporta validando antes dos efeitos, sem alterar o destino ativo."""
    if active_path is None:
        raise ConfigError("Exportação: informe o caminho da configuração ativa")
    _write_new_contents(path, _serialize_config(config), active_path=active_path)


def create_new_config(path: str | Path, config: AppConfig) -> ConfigSnapshot:
    """Cria exclusivamente e retorna snapshot próprio, sem reler o destino."""
    try:
        contents = _serialize_config(config)
        published = ConfigSnapshot(_parse_config_contents(contents), contents)
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise ConfigError(f"Não foi possível preparar configuração: {exc}") from exc
    _write_new_contents(path, contents)
    return published

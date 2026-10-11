"""Exportação JSON para arquivo novo, sem sobrescrever qualquer destino."""

import os
from pathlib import Path
import tempfile

from core.config import ConfigError, _serialize_config
from core.models import AppConfig


_WINDOWS = os.name == "nt"


def _publish_new(temporary_path: Path, destination: Path) -> None:
    if _WINDOWS:
        # Windows recusa destino existente; POSIX rename pode sobrescrever.
        os.rename(temporary_path, destination)
    else:
        os.link(temporary_path, destination)


def _new_destination(path: str | Path, active_path: str | Path) -> Path:
    destination = Path(path)
    resolved = destination.resolve()
    active = Path(active_path).resolve()
    if os.path.normcase(str(resolved)) == os.path.normcase(str(active)):
        raise ConfigError("Exportação: destino é a configuração ativa ou um alias")
    try:
        destination.lstat()
    except FileNotFoundError:
        return resolved
    # Inclui arquivos, diretórios, hard links e links simbólicos quebrados.
    raise ConfigError("Exportação: destino já existe; escolha um arquivo novo")


def export_new_config(
    path: str | Path, config: AppConfig, *, active_path: str | Path,
) -> None:
    """Valida antes de escrever e publica exclusivamente no mesmo volume.

    Windows usa rename, que recusa existente, inclusive em FAT/exFAT. Os demais
    sistemas usam hard link e falham se não houver suporte, sem fallback de
    sobrescrita. A limpeza remove apenas o temporário, nunca o destino.
    """
    temporary_path = None
    failure = None
    try:
        contents = _serialize_config(config)
        destination = _new_destination(path, active_path)
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
        _new_destination(destination, active_path)
        _publish_new(temporary_path, destination)
        if _WINDOWS:
            temporary_path = None  # rename já consumiu o temporário.
    except ConfigError as exc:
        failure = exc
        raise
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError, RuntimeError) as exc:
        failure = ConfigError(f"Não foi possível exportar configuração em {path}: {exc}")
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

"""Snapshots e gravação de configuração com detecção de edição externa.

A comparação dos bytes detecta conflitos até a última conferência. Há uma
pequena corrida entre essa conferência e os.replace: isto não é CAS do sistema
operacional nem um lock para editores externos. A publicação reutiliza o
temporário/fsync/replace da configuração, sem prometer durabilidade em crash.
"""

from dataclasses import dataclass
import os
from pathlib import Path

from core.config import (
    ConfigError, _parse_config_contents, _serialize_config, _write_config_contents,
)
from core.models import AppConfig


class ConfigConflictError(ConfigError):
    """O destino foi alterado ou removido desde a captura do snapshot."""


@dataclass(frozen=True)
class ConfigSnapshot:
    config: AppConfig
    contents: bytes


def read_snapshot(path: str | os.PathLike[str]) -> ConfigSnapshot:
    """Captura bytes e valida essa mesma leitura, sem modificar o arquivo."""
    try:
        contents = Path(path).read_bytes()
        return ConfigSnapshot(_parse_config_contents(contents), contents)
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise ConfigError(f"Não foi possível ler configuração em {path}: {exc}") from exc


def _check_revision(destination: Path, snapshot: ConfigSnapshot) -> None:
    try:
        current = destination.read_bytes()
    except FileNotFoundError as exc:
        raise ConfigConflictError(
            f"Configuração removida desde a leitura: {destination}; recarregue antes de salvar"
        ) from exc
    except OSError as exc:
        raise ConfigError(f"Não foi possível conferir configuração em {destination}: {exc}") from exc
    if current != snapshot.contents:
        raise ConfigConflictError(
            f"Configuração alterada desde a leitura: {destination}; recarregue antes de salvar"
        )


def save_snapshot(
    path: str | os.PathLike[str], config: AppConfig, snapshot: ConfigSnapshot,
) -> ConfigSnapshot:
    """Publica somente se os bytes conferidos ainda correspondem ao baseline.

    O retorno representa nossos bytes publicados, mesmo se outro escritor
    modificar o destino depois do replace. Não cria configuração ausente,
    recupera inválidos, força sobrescrita nem mescla revisões.
    """
    if not isinstance(snapshot, ConfigSnapshot) or not isinstance(snapshot.contents, bytes):
        raise ConfigError("snapshot: esperado ConfigSnapshot com contents em bytes")
    contents = _serialize_config(config)
    # Preparar também o modelo do retorno antes de publicar. Não reler o destino
    # depois da gravação e adotar uma revisão de um escritor posterior.
    try:
        published = ConfigSnapshot(_parse_config_contents(contents), contents)
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise ConfigError(f"Não foi possível preparar configuração: {exc}") from exc
    destination = Path(path)
    _check_revision(destination, snapshot)
    _write_config_contents(
        destination, contents, before_replace=lambda: _check_revision(destination, snapshot),
    )
    return published

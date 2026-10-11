"""Sessão de edição compartilhável, independente da biblioteca gráfica."""

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from core.config_editor import ConfigDraft
from core.config_portability import export_new_config
from core.config_repository import read_snapshot, save_snapshot
from core.scheduler import is_blocking, next_block_start


@dataclass(frozen=True)
class AgendaStatus:
    active: bool
    next_start: datetime | None


class ConfigSession:
    """Mantém baseline e rascunho; falhas nunca descartam a edição atual."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.reload()

    @property
    def dirty(self) -> bool:
        return self.draft.config != self.snapshot.config

    def save(self) -> None:
        # Mesmo sem alterações, conferir o baseline: não ocultar conflito externo.
        self.snapshot = save_snapshot(self.path, self.draft.config, self.snapshot)

    def reload(self) -> None:
        snapshot = read_snapshot(self.path)
        draft = ConfigDraft(snapshot.config)
        self.snapshot, self.draft = snapshot, draft

    def import_config(self, path: str | Path) -> None:
        """Importa somente para edição; Salvar continua explícito e com conflito."""
        draft = ConfigDraft(read_snapshot(path).config)
        self.draft = draft

    def export_config(self, path: str | Path) -> None:
        """Exporta o rascunho validado sem mudar o baseline ou salvar o ativo."""
        export_new_config(path, self.draft.config, active_path=self.path)

    def agenda_status(self, now: datetime) -> AgendaStatus:
        """Consulta a última agenda carregada/salva, nunca o rascunho."""
        windows = self.snapshot.config.windows
        return AgendaStatus(is_blocking(windows, now), next_block_start(windows, now))

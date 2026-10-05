"""Validação e persistência JSON da agenda, sem aplicar bloqueios."""

from copy import deepcopy
from datetime import time
import json
import os
from pathlib import Path
import re
import tempfile

from core.models import AppConfig, ScheduleWindow


class ConfigError(Exception):
    """Erro de leitura, validação ou gravação da configuração."""


def _parse_time(value: object, field: str) -> time:
    if not isinstance(value, str) or re.fullmatch(
        r"(?:[01][0-9]|2[0-3]):[0-5][0-9]", value
    ) is None:
        raise ConfigError(f"{field}: esperado horário HH:MM entre 00:00 e 23:59")
    return time(int(value[:2]), int(value[3:]))


def _parse_days(value: object, field: str) -> tuple[int, ...]:
    if not isinstance(value, list):
        raise ConfigError(f"{field}: esperada lista de dias inteiros de 0 a 6")
    seen = set()
    for index, day in enumerate(value):
        if type(day) is not int or not 0 <= day <= 6:
            raise ConfigError(f"{field}[{index}]: esperado inteiro de 0 a 6")
        if day in seen:
            raise ConfigError(f"{field}[{index}]: dia {day} duplicado")
        seen.add(day)
    return tuple(value)


def parse_config(data: object) -> AppConfig:
    """Valida a agenda; campos raiz extras permanecem opacos nesta fase."""
    if not isinstance(data, dict):
        raise ConfigError("configuração: raiz deve ser um objeto JSON")
    if "windows" not in data or not isinstance(data["windows"], list):
        raise ConfigError("windows: campo obrigatório deve ser uma lista")
    windows = []
    for index, window in enumerate(data["windows"]):
        field = f"windows[{index}]"
        if not isinstance(window, dict):
            raise ConfigError(f"{field}: janela deve ser um objeto")
        unknown = [str(key) for key in window if key not in {"start", "end", "days"}]
        if unknown:
            raise ConfigError(f"{field}: campos desconhecidos: {', '.join(unknown)}")
        start = _parse_time(window.get("start"), f"{field}.start")
        end = _parse_time(window.get("end"), f"{field}.end")
        if start == end:
            raise ConfigError(f"{field}.end: início e fim devem ser diferentes")
        days = _parse_days(window.get("days", list(range(7))), f"{field}.days")
        windows.append(ScheduleWindow(start=start, end=end, days=days))
    return AppConfig(
        windows=tuple(windows),
        extra=deepcopy({key: value for key, value in data.items() if key != "windows"}),
    )


def _time_to_string(value: object, field: str) -> str:
    if (
        not isinstance(value, time)
        or value.tzinfo is not None
        or value.second != 0
        or value.microsecond != 0
    ):
        raise ConfigError(f"{field}: esperado horário local em precisão de minuto")
    return f"{value.hour:02d}:{value.minute:02d}"


def config_to_dict(config: AppConfig) -> dict:
    """Serializa os tipos compartilhados sem perder precisão ou validar extras."""
    if not isinstance(config, AppConfig):
        raise ConfigError("configuração: esperado AppConfig")
    if not isinstance(config.windows, tuple):
        raise ConfigError("windows: esperado tuple de ScheduleWindow")
    if not isinstance(config.extra, dict):
        raise ConfigError("extra: esperado dicionário de campos JSON")
    if "windows" in config.extra:
        raise ConfigError("extra.windows: campo reservado à agenda")
    windows = []
    for index, window in enumerate(config.windows):
        field = f"windows[{index}]"
        if not isinstance(window, ScheduleWindow):
            raise ConfigError(f"{field}: esperado ScheduleWindow")
        if not isinstance(window.days, tuple):
            raise ConfigError(f"{field}.days: esperado tuple de dias")
        windows.append({
            "start": _time_to_string(window.start, f"{field}.start"),
            "end": _time_to_string(window.end, f"{field}.end"),
            "days": list(window.days),
        })
    # Reutiliza as mesmas regras, também para instâncias construídas diretamente.
    parse_config({"windows": windows})
    result = deepcopy(config.extra)
    result["windows"] = windows
    return result


def _invalid_json_constant(value: str) -> None:
    raise ValueError(f"constante inválida em JSON: {value}")


def _unique_json_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ConfigError(f"chave JSON duplicada: {key}")
        result[key] = value
    return result


def load_config(path: str | os.PathLike[str]) -> AppConfig:
    """Lê UTF-8/JSON; nunca cria ou substitui o arquivo em caso de erro."""
    try:
        with Path(path).open("r", encoding="utf-8") as stream:
            data = json.load(
                stream, parse_constant=_invalid_json_constant,
                object_pairs_hook=_unique_json_object,
            )
        return parse_config(data)
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise ConfigError(f"Não foi possível ler configuração em {path}: {exc}") from exc


def save_config(path: str | os.PathLike[str], config: AppConfig) -> None:
    """Valida e substitui atomicamente usando temporário no mesmo diretório."""
    temporary_path = None
    failure = None
    try:
        data = config_to_dict(config)
        contents = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n",
            dir=destination.parent, prefix=f".{destination.name}.",
            suffix=".tmp", delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        # O arquivo temporário está fechado antes do replace, inclusive no Windows.
        os.replace(temporary_path, destination)
        temporary_path = None
    except ConfigError as exc:
        failure = exc
        raise
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
        failure = ConfigError(f"Não foi possível salvar configuração em {path}: {exc}")
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


def default_config_path() -> Path:
    """Destino instalado, sem fallback para outro perfil ou diretório."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise ConfigError("APPDATA não definido; informe um caminho de configuração")
    return Path(appdata) / "FocusBlocker" / "config.json"


def default_config() -> AppConfig:
    """Configuração inicial sem janelas ou sugestões ativadas."""
    return AppConfig()

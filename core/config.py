"""Validação e persistência JSON da agenda e regras, sem aplicar bloqueios."""

from copy import deepcopy
from datetime import time
import json
import ntpath
import os
from pathlib import Path
import re
import tempfile
from typing import Callable
import unicodedata

from core.models import AppConfig, CmdlineRule, ScheduleWindow


_PROCESS_FIELDS = ("block_exes", "block_folders", "safelist_exes", "block_cmdline")
_RESERVED_FIELDS = frozenset(("windows", *_PROCESS_FIELDS))


class ConfigError(Exception):
    """Erro de leitura, validação ou gravação da configuração."""


def _parse_executable(value: object, field: str) -> str:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or len(value) <= 4
        or not value.lower().endswith(".exe")
        or any(char in value for char in '\\/:*?<>|"')
        or any(ord(char) < 32 for char in value)
    ):
        raise ConfigError(
            f"{field}: esperado nome completo .exe, sem diretório, "
            "wildcard ou espaços externos"
        )
    return value


def _parse_folder(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ConfigError(f"{field}: esperado caminho absoluto Windows")
    # Expandir só a sintaxe aprovada %VAR%, sem resolver arquivos/instalações.
    environment = {key.casefold(): val for key, val in os.environ.items()}

    def expand_variable(match: re.Match) -> str:
        name = match.group(1)
        replacement = environment.get(name.casefold())
        if not replacement:
            raise ConfigError(f"{field}: variável %{name}% ausente ou vazia")
        return replacement

    expanded = re.sub(r"%([^%]+)%", expand_variable, value)
    if "%" in expanded:
        raise ConfigError(f"{field}: variável %VAR% inválida ou não resolvida")
    path = expanded.replace("/", "\\")
    if path.startswith(("\\\\?\\", "\\\\.\\", "\\??\\")):
        raise ConfigError(f"{field}: caminho de dispositivo não permitido")
    drive, tail = ntpath.splitdrive(path)
    if drive.startswith("\\\\"):
        parts = drive[2:].split("\\")
        absolute = len(parts) == 2 and all(parts) and (not tail or tail.startswith("\\"))
        checked_path = drive[2:] + tail
    else:
        absolute = re.fullmatch(r"[A-Za-z]:", drive) is not None and tail.startswith("\\")
        checked_path = tail
    if not absolute:
        raise ConfigError(f"{field}: esperado caminho absoluto Windows após expansão")
    if any(char in checked_path for char in '*?<>|":') or any(
        ord(char) < 32 for char in path
    ):
        raise ConfigError(f"{field}: caminho com wildcard ou caracteres inválidos")
    return value


def _parse_process_list(value: object, field: str, parser) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise ConfigError(f"{field}: esperada lista")
    return tuple(parser(item, f"{field}[{index}]") for index, item in enumerate(value))


def _parse_cmdline(value: object) -> tuple[CmdlineRule, ...]:
    if not isinstance(value, list):
        raise ConfigError("block_cmdline: esperada lista")
    rules = []
    for index, rule in enumerate(value):
        field = f"block_cmdline[{index}]"
        if not isinstance(rule, dict):
            legacy = (
                "; string legada não informa o executável; "
                "corrija explicitamente, sem migração automática"
                if isinstance(rule, str) else ""
            )
            raise ConfigError(f"{field}: esperado objeto com executable e contains{legacy}")
        unknown = [str(key) for key in rule if key not in {"executable", "contains"}]
        if unknown:
            raise ConfigError(f"{field}: campos desconhecidos: {', '.join(unknown)}")
        executable = _parse_executable(rule.get("executable"), f"{field}.executable")
        contains = rule.get("contains")
        if (
            not isinstance(contains, str)
            or not contains.strip()
            or any(unicodedata.category(char) == "Cc" for char in contains)
        ):
            raise ConfigError(f"{field}.contains: esperado trecho literal não vazio e sem controle")
        rules.append(CmdlineRule(executable=executable, contains=contains))
    return tuple(rules)


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
    """Valida agenda/regras; demais campos raiz permanecem opacos."""
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
        extra=deepcopy({key: value for key, value in data.items() if key not in _RESERVED_FIELDS}),
        block_exes=_parse_process_list(data.get("block_exes", []), "block_exes", _parse_executable),
        block_folders=_parse_process_list(data.get("block_folders", []), "block_folders", _parse_folder),
        safelist_exes=_parse_process_list(data.get("safelist_exes", []), "safelist_exes", _parse_executable),
        block_cmdline=_parse_cmdline(data.get("block_cmdline", [])),
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
    for field in _RESERVED_FIELDS:
        if field in config.extra:
            raise ConfigError(f"extra.{field}: campo reservado à configuração tipada")
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
    typed = {"windows": windows}
    for field in _PROCESS_FIELDS:
        values = getattr(config, field)
        if not isinstance(values, tuple):
            raise ConfigError(f"{field}: esperado tuple")
        if field == "block_cmdline":
            rules = []
            for index, rule in enumerate(values):
                if not isinstance(rule, CmdlineRule):
                    raise ConfigError(f"{field}[{index}]: esperado CmdlineRule")
                rules.append({"executable": rule.executable, "contains": rule.contains})
            typed[field] = rules
        else:
            typed[field] = list(values)
    # Reutiliza as mesmas regras, também para instâncias construídas diretamente.
    parse_config(typed)
    result = deepcopy(config.extra)
    result.update(typed)
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


def _parse_config_contents(contents: bytes) -> AppConfig:
    """Valida exatamente os bytes capturados, sem uma segunda leitura."""
    data = json.loads(
        contents.decode("utf-8"), parse_constant=_invalid_json_constant,
        object_pairs_hook=_unique_json_object,
    )
    return parse_config(data)


def load_config(path: str | os.PathLike[str]) -> AppConfig:
    """Lê UTF-8/JSON; nunca cria ou substitui o arquivo em caso de erro."""
    try:
        return _parse_config_contents(Path(path).read_bytes())
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise ConfigError(f"Não foi possível ler configuração em {path}: {exc}") from exc


def _serialize_config(config: AppConfig) -> bytes:
    """Valida e codifica antes de qualquer efeito de gravação."""
    try:
        data = config_to_dict(config)
        contents = json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
        return contents.encode("utf-8")
    except (UnicodeError, ValueError, TypeError, RecursionError) as exc:
        raise ConfigError(f"Não foi possível serializar configuração: {exc}") from exc


def _write_config_contents(
    path: str | os.PathLike[str], contents: bytes, *,
    before_replace: Callable[[], None] | None = None,
) -> None:
    """Publica bytes preparados; permite conferir revisão antes do replace."""
    temporary_path = None
    failure = None
    try:
        destination = Path(path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=destination.parent, prefix=f".{destination.name}.",
            suffix=".tmp", delete=False,
        ) as stream:
            temporary_path = Path(stream.name)
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        # O arquivo temporário está fechado antes do replace, inclusive no Windows.
        if before_replace is not None:
            before_replace()
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


def save_config(path: str | os.PathLike[str], config: AppConfig) -> None:
    """Valida e substitui atomicamente usando temporário no mesmo diretório."""
    _write_config_contents(path, _serialize_config(config))


def default_config_path() -> Path:
    """Destino instalado, sem fallback para outro perfil ou diretório."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise ConfigError("APPDATA não definido; informe um caminho de configuração")
    return Path(appdata) / "FocusBlocker" / "config.json"


def default_config() -> AppConfig:
    """Configuração inicial sem janelas ou sugestões ativadas."""
    return AppConfig()

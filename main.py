"""Diagnóstico da agenda da fase 1; não aplica bloqueios ao Windows.

Códigos de saída: 0 = sucesso ou Ctrl+C; 1 = erro de configuração/IO;
2 = argumentos inválidos (argparse). Somente --init-config grava dados.
A criação inicial é exclusiva, sem sobrescrita, mas não é atômica: falha de
escrita pode deixar o arquivo novo incompleto.
"""

from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys
import time

from core.config import (
    ConfigError,
    config_to_dict,
    default_config,
    default_config_path,
    load_config,
)
from core.scheduler import is_blocking, next_block_start


def _local_datetime(value: str) -> datetime:
    try:
        if "T" not in value and " " not in value:
            raise ValueError
        result = datetime.fromisoformat(value)
    except ValueError:
        raise argparse.ArgumentTypeError(
            "use data e hora ISO local, por exemplo 2026-10-05T22:00:00"
        ) from None
    if result.tzinfo is not None:
        raise argparse.ArgumentTypeError("--at exige hora local sem fuso/offset")
    return result


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Focus Blocker: diagnóstico do estado calculado da agenda.",
        epilog=(
            "Esta fase não aplica bloqueios ao Windows. Sem ação, consulta o "
            "estado. Códigos: 0 sucesso/Ctrl+C; 1 erro de configuração/IO; "
            "2 argumentos inválidos. A criação inicial é exclusiva; falha "
            "durante a escrita pode deixar o arquivo novo incompleto."
        ),
    )
    parser.add_argument("--config", type=Path, metavar="PATH", help="JSON (padrão: %%APPDATA%%/FocusBlocker/config.json)")
    parser.add_argument("--init-config", action="store_true", help="cria configuração vazia; recusa sobrescrever existente")
    parser.add_argument("--check", action="store_true", help="valida somente o contrato de configuração da fase 1")
    parser.add_argument("--status", action="store_true", help="mostra o estado calculado e o próximo início efetivo")
    parser.add_argument("--at", type=_local_datetime, metavar="ISO", help="consulta em data/hora local sem fuso")
    parser.add_argument("--watch", action="store_true", help="recarrega e reavalia a cada 5 s até Ctrl+C")
    return parser


def _init_config(path: Path) -> None:
    # Serializar antes de criar o arquivo; modo x impede sobrescrita, inclusive
    # se outro processo criar o destino entre a verificação e a abertura.
    payload = json.dumps(config_to_dict(default_config()), ensure_ascii=False, indent=2) + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open("x", encoding="utf-8") as stream:
            stream.write(payload)
    except FileExistsError:
        raise ConfigError(f"configuração já existe; não será sobrescrita: {path}") from None
    except OSError as exc:
        raise ConfigError(
            f"falha na criação de {path}: {exc}; se a escrita começou, "
            "o arquivo novo pode estar incompleto; corrija-o antes de usar"
        ) from exc


def _print_status(config, now: datetime) -> None:
    active = is_blocking(config.windows, now)
    next_start = next_block_start(config.windows, now)
    state = "dentro da janela" if active else "fora da janela"
    print(f"Consulta local: {now.isoformat()}")
    print(f"Estado calculado da agenda: {state}")
    print(
        "Próximo início efetivo: "
        + (next_start.isoformat() if next_start is not None else "nenhum")
    )
    print("Diagnóstico da fase 1: não aplica bloqueios ao Windows.", flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.watch and args.at is not None:
        parser.error("--watch usa o relógio local e não pode combinar com --at")
    show_status = args.status or args.at is not None or not (args.init_config or args.check)
    try:
        path = args.config if args.config is not None else default_config_path()
        if args.init_config:
            _init_config(path)
            print(f"Configuração criada sem janelas ativas: {path}", flush=True)
        if not (args.check or show_status or args.watch):
            return 0
        config = load_config(path)
        if args.check:
            print(f"Configuração válida para a fase 1: {path}", flush=True)
        if args.watch:
            print("Observando a agenda a cada 5 s; Ctrl+C encerra o diagnóstico.", flush=True)
            while True:
                _print_status(config, datetime.now())
                time.sleep(5)
                config = load_config(path)
        elif show_status:
            _print_status(config, args.at if args.at is not None else datetime.now())
        return 0
    except KeyboardInterrupt:
        print("\nDiagnóstico encerrado por Ctrl+C.", flush=True)
        return 0
    except (ConfigError, OSError, OverflowError) as exc:
        print(f"Erro: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

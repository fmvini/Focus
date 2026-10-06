"""Diagnóstico por padrão; aplicação de processos somente por flag explícito.

Códigos de saída: 0 = sucesso ou Ctrl+C; 1 = erro global/configuração/IO;
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
            "Por padrão, apenas diagnóstico: não aplica bloqueios ao Windows. "
            "--apply-processes com --watch encerra processos elegíveis usando "
            "o relógio local real; não combina com --at, --init-config ou --check. "
            "Sites/hosts não são alterados. Ctrl+C para a varredura e não reabre "
            "apps encerrados. Falhas por alvo são visíveis e preservam aquele "
            "alvo; erro global/configuração interrompe novas ações. "
            "Códigos: 0 sucesso/Ctrl+C; 1 erro global/configuração/IO; "
            "2 argumentos inválidos. A criação inicial é exclusiva; falha "
            "durante a escrita pode deixar o arquivo novo incompleto."
        ),
    )
    parser.add_argument("--config", type=Path, metavar="PATH", help="JSON (padrão: %%APPDATA%%/FocusBlocker/config.json)")
    parser.add_argument("--init-config", action="store_true", help="cria configuração vazia; recusa sobrescrever existente")
    parser.add_argument("--check", action="store_true", help="valida agenda e regras de processos; demais extras permanecem opacos")
    parser.add_argument("--status", action="store_true", help="mostra o estado calculado e o próximo início efetivo")
    parser.add_argument("--at", type=_local_datetime, metavar="ISO", help="consulta em data/hora local sem fuso")
    parser.add_argument("--watch", action="store_true", help="recarrega e reavalia a cada 5 s até Ctrl+C")
    parser.add_argument("--apply-processes", action="store_true", help="encerra processos elegíveis; exige --watch e relógio real")
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


def _print_status(config, now: datetime, *, applying: bool = False) -> None:
    active = is_blocking(config.windows, now)
    next_start = next_block_start(config.windows, now)
    state = "dentro da janela" if active else "fora da janela"
    print(f"Consulta local: {now.isoformat()}")
    print(f"Estado calculado da agenda: {state}")
    print(
        "Próximo início efetivo: "
        + (next_start.isoformat() if next_start is not None else "nenhum")
    )
    if applying:
        print("Aplicação somente de processos; sites/hosts não são alterados.", flush=True)
    else:
        print("Diagnóstico da fase 1: não aplica bloqueios ao Windows.", flush=True)


def _create_process_blocker():
    """Importação e adaptador real somente no modo explicitamente solicitado."""
    from core.proc_blocker import ProcessBlocker

    return ProcessBlocker()


def _print_process_report(report) -> None:
    counts = {}
    labels = {
        "terminated": "encerramento confirmado",
        "pending": "encerramento solicitado; ainda sem saída confirmada",
        "unavailable": "indisponível; alvo preservado",
        "failed": "falha; encerramento não confirmado",
        "gone": "já ausente",
        "inactive": "sem nova ação; agenda inativa",
    }
    for result in report.results:
        counts[result.status] = counts.get(result.status, 0) + 1
        if result.status in ("protected", "unmatched"):
            continue
        warning = result.status in ("unavailable", "failed")
        print(
            f"{'Aviso' if warning else 'Processo'}: PID {result.pid} "
            f"({result.name or 'nome indisponível'}): "
            f"{labels.get(result.status, result.status)}; {result.reason}",
            file=sys.stderr if warning else sys.stdout,
            flush=True,
        )
    print(
        f"Resumo de processos: {len(report.events)} encerramentos confirmados; "
        f"{counts.get('pending', 0)} pendentes; "
        f"{counts.get('unavailable', 0)} indisponíveis; "
        f"{counts.get('failed', 0)} falhas; "
        f"{counts.get('protected', 0)} protegidos; "
        f"{counts.get('unmatched', 0)} sem correspondência.",
        flush=True,
    )


def _watch_processes(path: Path, config) -> int:
    # A classe de erro também é importada apenas neste ramo. Diagnóstico/help
    # funcionam sem psutil; a fábrica pode ser substituída por um fake nos testes.
    try:
        from core.proc_blocker import ProcessBlockerError
    except ImportError as exc:
        print(f"Erro: bloqueador de processos indisponível: {exc}", file=sys.stderr, flush=True)
        return 1
    running = True
    try:
        blocker = _create_process_blocker()
        print(
            "Aplicação de processos com relógio local real; recarga a cada 5 s. "
            "Ctrl+C para a varredura; não reabre apps encerrados.",
            flush=True,
        )
        deadline = time.monotonic()
        while True:
            deadline += 5
            now = datetime.now()
            _print_status(config, now, applying=True)
            # Congelar somente a configuração; o relógio é consultado de
            # novo pelo Backend antes de CADA efeito, incluindo kill.
            def may_act(snapshot=config):
                return running and is_blocking(snapshot.windows, datetime.now())

            if not is_blocking(config.windows, now):
                print("Agenda inativa: somente reconciliação de pedidos anteriores, sem novos alvos.", flush=True)
            # O Backend reconcilia referências já solicitadas antes do gate;
            # gate falso proíbe enumeração e efeitos, mas permite confirmação.
            _print_process_report(blocker.scan(config, may_act))
            finished = time.monotonic()
            if finished > deadline:
                print("Aviso: ciclo atrasado; prazos perdidos serão pulados.", file=sys.stderr, flush=True)
                deadline += (int((finished - deadline) // 5) + 1) * 5
            time.sleep(max(0, deadline - finished))
            config = load_config(path)
    except (ProcessBlockerError, ImportError) as exc:
        partial_report = getattr(exc, "partial_report", None)
        if partial_report is not None:
            print("Relatório parcial de processos antes da falha global:", flush=True)
            _print_process_report(partial_report)
        print(f"Erro global de processos: {exc}; novas ações interrompidas.", file=sys.stderr, flush=True)
        return 1
    finally:
        running = False


def main(argv: list[str] | None = None) -> int:
    parser = _parser()
    args = parser.parse_args(argv)
    if args.apply_processes and (
        not args.watch or args.at is not None or args.init_config or args.check
    ):
        parser.error("--apply-processes exige --watch e não combina com --at, --init-config ou --check")
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
        if args.apply_processes:
            return _watch_processes(path, config)
        if args.check:
            print(f"Configuração válida: agenda e regras de processos: {path}", flush=True)
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
        message = (
            "Varredura de processos encerrada por Ctrl+C; apps encerrados não são reabertos."
            if args.apply_processes else "Diagnóstico encerrado por Ctrl+C."
        )
        print(f"\n{message}", flush=True)
        return 0
    except (ConfigError, OSError, OverflowError) as exc:
        suffix = "; novas ações interrompidas." if args.apply_processes else ""
        print(f"Erro: {exc}{suffix}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

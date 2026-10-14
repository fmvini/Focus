"""Supervisor externo para medições exploratórias, sem efeitos do motor."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import importlib.metadata
import json
import math
from pathlib import Path
import platform
import signal
import subprocess
import sys
import time


WORKSPACE = Path(__file__).resolve().parents[1]


def finite_number(text):
    value = float(text)
    if not math.isfinite(value):
        raise argparse.ArgumentTypeError("esperado número finito")
    return value


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--rules", type=int, choices=(0, 100, 1000), default=100)
    result.add_argument("--profile", choices=("H-F", "G-P", "T-P"), default="H-F")
    result.add_argument("--query", choices=("none", "single", "burst", "spaced"), default="none")
    result.add_argument("--warmup", type=finite_number, default=2.0)
    result.add_argument("--idle", type=finite_number, default=10.0)
    result.add_argument("--interval", type=finite_number, default=1.0)
    result.add_argument("--startup-timeout", type=finite_number, default=60.0)
    result.add_argument("--finish-timeout", type=finite_number, default=90.0)
    result.add_argument("--runtime", default=sys.executable)
    result.add_argument("--output", type=Path, help="pai dos runs dentro de .qa")
    return result


def validate(options):
    if type(options.rules) is not int or options.rules not in (0, 100, 1000):
        raise ValueError("carga deve ser 0, 100 ou 1000 regras")
    if options.profile not in ("H-F", "G-P", "T-P"):
        raise ValueError("perfil desconhecido")
    if options.query not in ("none", "single", "burst", "spaced") or (options.query != "none" and options.profile != "G-P"):
        raise ValueError("consulta medida exige perfil G-P e modo válido")
    for name in ("warmup", "idle", "interval", "startup_timeout", "finish_timeout"):
        value = getattr(options, name)
        if isinstance(value, bool) or not isinstance(value, (float, int)) or not math.isfinite(value):
            raise ValueError(f"{name}: esperado número finito")
        if value < 0 or (name != "warmup" and value == 0):
            raise ValueError(f"{name}: duração inválida")
    runtime = Path(options.runtime).resolve(strict=True)
    if not runtime.is_file():
        raise ValueError("runtime deve ser um executável existente")
    return runtime


def metadata():
    import psutil
    from tools.perf_artifacts import file_sha256

    def git(*arguments):
        try:
            return subprocess.check_output(["git", *arguments], cwd=WORKSPACE, text=True).strip()
        except (OSError, subprocess.CalledProcessError) as error:
            return {"unavailable": str(error)}

    versions = {}
    for name in ("psutil", "customtkinter", "Pillow", "pystray"):
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    paths = [*WORKSPACE.joinpath("tools").glob("*.py"), *WORKSPACE.joinpath("ui").glob("*.py"),
             *WORKSPACE.joinpath("core").glob("*.py")]
    return {
        "head": git("rev-parse", "HEAD"), "status": git("status", "--porcelain"),
        "source_hashes": {str(path.relative_to(WORKSPACE)): file_sha256(path) for path in paths},
        "collector_runtime": sys.executable, "collector_python": sys.version,
        "collector_pid": psutil.Process().pid, "collector_create_time": psutil.Process().create_time(),
        "collector_versions": versions, "platform": platform.platform(),
        "architecture": platform.machine(), "logical_cpus": psutil.cpu_count(),
        "physical_cores": psutil.cpu_count(logical=False),
        "ram_total_bytes": psutil.virtual_memory().total,
        "ram_available_bytes": psutil.virtual_memory().available,
        "desktop_dpi_power_job_limits": "não medidos; informar contexto na análise",
    }


def query_report_valid(query, mode, rules):
    """Recompute event evidence outside the worker's measured intervals."""
    from tools.perf_query import summarize_query
    required_checks = {"bytes", "draft", "baseline", "model", "baseline_model",
                       "history_empty", "clean", "zero_starts"}
    if (not isinstance(query, dict) or query.get("mode") != mode
            or type(query.get("query_schema_version")) is not int
            or query["query_schema_version"] != 1 or query.get("complete") is not True
            or query.get("partial") is not None):
        return False
    packets = query.get("packets")
    if not isinstance(packets, list) or len(packets) != 2:
        return False
    for packet, expected_mode in zip(packets, (mode, "reset")):
        if (not isinstance(packet, dict) or packet.get("mode") != expected_mode
                or type(packet.get("query_schema_version")) is not int
                or packet["query_schema_version"] != 1 or packet.get("status") != "complete"
                or type(packet.get("writes")) is not list or type(packet.get("renders")) is not list
                or not isinstance(packet.get("summary"), dict)
                or not isinstance(packet.get("data_checks"), dict)
                or not required_checks.issubset(packet["data_checks"])
                or any(value is not True for value in packet["data_checks"].values())):
            return False
        summary = summarize_query(packet["writes"], packet["renders"], expected_mode, rules)
        if summary["ok"] is not True or packet["summary"] != summary:
            return False
    return (packets[1]["writes"][0]["begin_ns"] > packets[0]["summary"]["final_observation_ns"]
            and packets[1]["summary"]["final_revision"] > packets[0]["summary"]["final_revision"])


def verify_owned(launcher, ready):
    import psutil

    target = psutil.Process(ready["pid"])
    if target.create_time() != ready["create_time"]:
        raise ValueError("identidade do worker mudou antes da amostragem")
    parent = target.ppid()
    if target.pid != launcher.pid and parent != launcher.pid:
        raise ValueError("PID informado não pertence ao processo lançado")
    details = {"pid": target.pid, "create_time": ready["create_time"], "ppid": parent,
               "exe": None, "affinity": None, "metadata_errors": []}
    for name, getter in (("exe", target.exe), ("affinity", getattr(target, "cpu_affinity", None))):
        if getter is not None:
            try:
                details[name] = getter()
            except (psutil.Error, OSError) as error:
                details["metadata_errors"].append(f"{name}: {error}")
    fresh = psutil.Process(ready["pid"])
    if fresh.create_time() != ready["create_time"] or fresh.ppid() != parent:
        raise ValueError("identidade do worker mudou durante verificação de ownership")
    return details


def cleanup(launcher, identity):
    """Encerra apenas o filho identificado e o launcher criado pelo supervisor."""
    import psutil

    details = []
    if identity is not None and identity["pid"] != launcher.pid:
        try:
            target = psutil.Process(identity["pid"])
            if target.create_time() == identity["create_time"] and target.ppid() == launcher.pid:
                target.terminate()
                target.wait(5)
                details.append("worker dedicado encerrado após falha")
            else:
                details.append("cleanup recusado: identidade/parent alterados")
        except psutil.NoSuchProcess:
            pass
        except (psutil.Error, OSError) as error:
            details.append(f"cleanup worker: {error}")
    if launcher.poll() is None:
        launcher.terminate()
        try:
            launcher.wait(timeout=5)
        except subprocess.TimeoutExpired:
            launcher.kill()
            launcher.wait(timeout=5)
        details.append("launcher próprio encerrado após falha")
    return details


def await_target_exit(identity, timeout):
    """Prova de saída do PID medido, separada do encerramento do launcher."""
    import psutil

    deadline = time.monotonic() + timeout
    while True:
        try:
            target = psutil.Process(identity["pid"])
            if target.create_time() != identity["create_time"]:
                return {"ended": True, "reason": "identidade original terminou; PID reutilizado"}
            if not target.is_running():
                return {"ended": True, "reason": "worker não está executando"}
        except psutil.NoSuchProcess:
            return {"ended": True, "reason": "PID medido ausente"}
        except (psutil.Error, OSError) as error:
            return {"ended": False, "error": str(error)}
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return {"ended": False, "error": "PID medido ainda vivo após saída do launcher"}
        time.sleep(min(0.05, remaining))


@dataclass
class Dependencies:
    artifacts: object
    sampler_factory: object
    summarize: object
    metadata: object = metadata
    launch: object = subprocess.Popen
    verify_owned: object = verify_owned
    cleanup: object = cleanup
    await_target_exit: object = await_target_exit
    clock_ns: object = time.perf_counter_ns
    sleep: object = time.sleep


def dependencies():
    from tools import perf_artifacts
    from tools.perf_metrics import ProcessSampler, summarize

    return Dependencies(perf_artifacts, ProcessSampler, summarize)


def read_json(path):
    def invalid_constant(value):
        raise ValueError(f"constante JSON inválida: {value}")
    return json.loads(path.read_text(encoding="utf-8"), parse_constant=invalid_constant)


@contextmanager
def retention_section():
    """Protege publicação/cleanup finais do CLI contra um segundo Ctrl+C."""
    previous = signal.getsignal(signal.SIGINT)
    installed = False
    try:
        try:
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            installed = True
        except ValueError:
            # collect() pode ser usado fora da thread principal; CLI não usa isso.
            pass
        yield
    finally:
        if installed:
            signal.signal(signal.SIGINT, previous)


def persist_result(artifacts, run_dir, samples, result):
    with retention_section():
        artifacts.write_jsonl(run_dir / "samples.jsonl", samples)
        artifacts.write_json(run_dir / "summary.json", result)


def preparation_failure(artifacts, run_dir, options, error):
    """Conserva uma falha ocorrida após registrar o diretório exclusivo."""
    result = {
        "ok": False, "rnf_accepted": False, "stage": "preparation", "run_dir": str(run_dir),
        "interrupted": isinstance(error, KeyboardInterrupt), "samples_count": 0,
        "errors": [f"{type(error).__name__}: {error}"], "identity": None, "target_exit": None,
        "exit_code": None, "resources": None, "sources_unchanged": None,
        "manifest": "manifest.json", "samples": "samples.jsonl", "worker_report": None,
    }
    with retention_section():
        if not (run_dir / "manifest.json").exists():
            artifacts.write_json(run_dir / "manifest.json", {
                "protocol_version": 1, "kind": "preparation_failed", "rnf_accepted": False,
                "profile": options.profile, "rules": options.rules, "errors": result["errors"],
            })
        persist_result(artifacts, run_dir, [], result)
    return result


def collect(options, deps=None):
    runtime = validate(options)
    deps = dependencies() if deps is None else deps
    artifacts = deps.artifacts
    run_dir = artifacts.create_run(WORKSPACE, options.output)
    try:
        config = artifacts.make_fixture(run_dir, options.rules)
        before_hash = artifacts.file_sha256(config)
        config_bytes = config.stat().st_size
        environment = deps.metadata()
    except (Exception, KeyboardInterrupt) as error:
        return preparation_failure(artifacts, run_dir, options, error)
    command = [str(runtime), "-B", "-m", "tools.perf_gui_worker", "--run-dir", str(run_dir),
               "--rules", str(options.rules), "--profile", options.profile,
               "--warmup", str(options.warmup), "--idle", str(options.idle), "--query", options.query]
    manifest = {
        "protocol_version": 1, "run_id": run_dir.name, "kind": "exploratory_subset",
        "rnf_accepted": False, "started_utc": datetime.now(timezone.utc).isoformat(),
        "environment": environment, "worker_command": command, "workspace": str(WORKSPACE),
        "profile": options.profile, "rules": options.rules,
        "query": options.query,
        "requested": {name: getattr(options, name) for name in
                      ("warmup", "idle", "interval", "startup_timeout", "finish_timeout")},
        "config_sha256": before_hash, "config_bytes": config_bytes,
        "measurement": "external PID/create_time; collector excluded; CPU covered idle span",
        "long_sessions_distributed_visual": "não implementados nesta versão",
    }
    try:
        artifacts.write_json(run_dir / "manifest.json", manifest)
    except (Exception, KeyboardInterrupt) as error:
        return preparation_failure(artifacts, run_dir, options, error)
    samples, errors, startup_reads = [], [], []
    identity = launcher = report = resource_summary = target_exit = None
    stdout = stderr = None
    exit_code = None
    interrupted = False
    try:
        stdout = (run_dir / "stdout.log").open("xb")
        stderr = (run_dir / "stderr.log").open("xb")
        launcher = deps.launch(command, cwd=WORKSPACE, stdin=subprocess.DEVNULL,
                               stdout=stdout, stderr=stderr)
        startup_deadline = deps.clock_ns() + int(options.startup_timeout * 1e9)
        ready_path = run_dir / "ready.json"
        ready = None
        while ready is None:
            if ready_path.exists():
                try:
                    ready = read_json(ready_path)
                except (OSError, UnicodeError, ValueError) as error:
                    startup_reads.append(str(error))
            if ready is not None:
                break
            if launcher.poll() is not None:
                raise RuntimeError("worker terminou antes de publicar ready.json completo")
            if deps.clock_ns() >= startup_deadline:
                raise TimeoutError("timeout aguardando ready.json")
            deps.sleep(0.05)
        if (not isinstance(ready, dict) or ready.get("ok") is not True
                or ready.get("profile") != options.profile or type(ready.get("pid")) is not int
                or isinstance(ready.get("create_time"), bool)
                or not isinstance(ready.get("create_time"), (int, float))
                or ready["pid"] <= 0 or not math.isfinite(ready["create_time"])
                or ready["create_time"] <= 0 or ready.get("rules") != options.rules):
            raise ValueError("ready.json inválido ou perfil não ficou pronto")
        identity = deps.verify_owned(launcher, ready)
        if options.query != "none" and (ready.get("query_mode") != options.query
                or type(ready.get("query_schema_version")) is not int
                or ready["query_schema_version"] != 1):
            raise ValueError("ready.json não comprova modo/schema da consulta")
        sampler = deps.sampler_factory(ready["pid"], ready["create_time"])
        finish_deadline = deps.clock_ns() + int((options.warmup + options.idle + options.finish_timeout) * 1e9)
        while launcher.poll() is None:
            if (run_dir / "report.json").exists():
                break
            samples.append(sampler.read())
            if deps.clock_ns() >= finish_deadline:
                raise TimeoutError("timeout de execução/teardown do worker")
            deps.sleep(options.interval)
        exit_code = launcher.wait(timeout=min(5.0, options.finish_timeout))
        report = read_json(run_dir / "report.json")
        if not isinstance(report, dict):
            raise ValueError("report.json deve ser objeto")
        if report.get("profile") != options.profile:
            errors.append("perfil do report não corresponde ao run")
        if options.query != "none":
            if not query_report_valid(report.get("query"), options.query, options.rules):
                errors.append("consulta/reset não comprovados pelo report")
        if report.get("pid") != ready["pid"] or report.get("create_time") != ready["create_time"]:
            errors.append("identidade do report não corresponde ao worker")
        checks = report.get("invariants", {}).get("checks", {})
        if not isinstance(checks, dict) or not checks or any(value is not True for value in checks.values()):
            errors.append("invariantes do worker não comprovadas")
        if exit_code != 0 or report.get("ok") is not True:
            errors.append(f"worker inválido: exit={exit_code}, errors={report.get('errors')}")
        if (report.get("closed") is not True or report.get("tray_alive") is not False
                or type(report.get("after_info")) is not list or report["after_info"] != []
                or report.get("errors") != []):
            errors.append("teardown não comprovado pelo report.json")
        target_exit = deps.await_target_exit(identity, min(5.0, options.finish_timeout))
        if not isinstance(target_exit, dict) or target_exit.get("ended") is not True:
            errors.append("saída do PID medido não comprovada")
        resource_summary = deps.summarize(samples, report.get("idle_begin_ns"),
                                          report.get("idle_end_ns"), environment.get("logical_cpus"))
        if resource_summary.get("ok") is not True:
            errors.append("resumo de idle insuficiente ou inválido")
    except KeyboardInterrupt:
        interrupted = True
        errors.append("KeyboardInterrupt: coleta interrompida; amostras preservadas")
    except Exception as error:
        errors.append(f"{type(error).__name__}: {error}")
    finally:
        if launcher is not None and (launcher.poll() is None or errors):
            try:
                with retention_section():
                    errors.extend(deps.cleanup(launcher, identity))
            except KeyboardInterrupt:
                interrupted = True
                errors.append("KeyboardInterrupt: cleanup interrompido; término não comprovado")
            except Exception as error:
                errors.append(f"cleanup: {type(error).__name__}: {error}")
        for handle in (stdout, stderr):
            if handle is not None:
                handle.close()
    try:
        after_hash = artifacts.file_sha256(config)
    except KeyboardInterrupt:
        interrupted = True
        after_hash = None
        errors.append("KeyboardInterrupt: hash final interrompido; amostras preservadas")
    except Exception as error:
        after_hash = None
        errors.append(f"fixture indisponível após execução: {error}")
    if after_hash != before_hash:
        errors.append("bytes da fixture alterados")
    sources_unchanged = None
    try:
        environment_after = deps.metadata()
        sources_unchanged = environment.get("source_hashes") == environment_after.get("source_hashes")
        if not sources_unchanged:
            errors.append("fontes alteradas durante o run")
    except KeyboardInterrupt:
        interrupted = True
        errors.append("KeyboardInterrupt: metadados finais interrompidos; amostras preservadas")
    except Exception as error:
        errors.append(f"metadados finais: {type(error).__name__}: {error}")
    result = {
        "ok": not errors, "rnf_accepted": False, "run_dir": str(run_dir),
        "interrupted": interrupted,
        "identity": identity, "exit_code": exit_code, "errors": errors,
        "startup_read_errors": startup_reads, "samples_count": len(samples),
        "config_sha256_before": before_hash, "config_sha256_after": after_hash,
        "sources_unchanged": sources_unchanged,
        "target_exit": target_exit,
        "resources": resource_summary, "worker_report": "report.json" if report is not None else None,
        "samples": "samples.jsonl", "manifest": "manifest.json",
    }
    persist_result(artifacts, run_dir, samples, result)
    return result


def main(argv=None):
    cli = parser()
    options = cli.parse_args(argv)
    try:
        result = collect(options)
    except KeyboardInterrupt:
        print("Coletor interrompido antes de registrar um run completo.", file=sys.stderr)
        return 130
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Erro do coletor: {error}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    return 0 if result["ok"] else 130 if result.get("interrupted") else 1


if __name__ == "__main__":
    raise SystemExit(main())

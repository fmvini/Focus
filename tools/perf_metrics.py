"""External process counters and pure exploratory summaries; no RNF acceptance.

psutil is imported only by ProcessSampler.read(). No process enumeration,
threads, sleeps, GUI imports or file writes belong to this module.
"""

from importlib import import_module
import math
from statistics import mean, median
from time import perf_counter_ns


_CPU_FIELDS = ("user_s", "system_s")
_MEMORY_FIELDS = {
    "rss_bytes": "rss",
    "peak_wset_bytes": "peak_wset",
    "private_bytes": "private",
    "vms_bytes": "vms",
}


def _number(value):
    if type(value) not in (int, float) or value < 0:
        return False
    try:
        return math.isfinite(value)
    except OverflowError:
        return False


def _integer(value):
    return type(value) is int and value >= 0


def _counter(value, field, *, integer=False):
    valid = _number(value) and (not integer or _integer(value))
    if value is not None and not valid:
        raise ValueError(f"Invalid counter {field}: expected nonnegative finite "
                         f"{'integer' if integer else 'number'} or None")
    return value


def _clock():
    value = perf_counter_ns()
    if not _integer(value):
        raise ValueError("Invalid monotonic clock: expected nonnegative integer ns")
    return value


def _issue(error, stage):
    return {"stage": stage, "type": type(error).__name__, "message": str(error)}


class ProcessSampler:
    """Read only the given PID, checking fresh identity on both sides of IO.

    read() always returns a raw record for ordinary failures. An invalid
    identity discards provisional counters; other failures may preserve partial
    counters, with ok=False. errors lists every failure; error is the first
    reason, for consumers needing a simple diagnostic.
    """

    def __init__(self, pid, create_time):
        if not _integer(pid) or pid == 0:
            raise ValueError("pid must be a positive integer")
        if not _number(create_time):
            raise ValueError("create_time must be a nonnegative finite number")
        self.pid = pid
        self.create_time = create_time

    def _identity(self, psutil):
        # Fresh instances are intentional: psutil caches create_time per object.
        process = psutil.Process(self.pid)
        actual = process.create_time()
        if (type(process.pid) is not int or process.pid != self.pid
                or not _number(actual) or actual != self.create_time):
            raise ValueError("Process identity changed (PID/create_time)")
        return process

    def read(self):
        record = {
            "ok": False, "pid": self.pid, "create_time": self.create_time,
            "read_start_ns": None, "read_end_ns": None, "mono_ns": None,
            **dict.fromkeys((*_CPU_FIELDS, *_MEMORY_FIELDS)),
            "error": None, "errors": [],
        }
        errors = record["errors"]
        provisional = {}
        clock_marks = []

        def read_clock():
            value = _clock()
            if clock_marks and value < clock_marks[-1]:
                raise ValueError("Monotonic clock moved backwards")
            clock_marks.append(value)
            return value

        stage = "read_start"
        try:
            record["read_start_ns"] = read_clock()
            stage = "psutil_import"
            psutil = import_module("psutil")
            stage = "identity_before"
            process = self._identity(psutil)
            try:
                stage = "cpu"
                cpu_start = read_clock()
                try:
                    cpu = process.cpu_times()
                    for field, attribute in zip(_CPU_FIELDS, ("user", "system")):
                        provisional[field] = _counter(getattr(cpu, attribute, None), field)
                except Exception as exc:
                    errors.append(_issue(exc, stage))
                finally:
                    cpu_end = read_clock()
                    record["mono_ns"] = (cpu_start + cpu_end) // 2
                stage = "memory"
                try:
                    memory = process.memory_info()
                    for field, attribute in _MEMORY_FIELDS.items():
                        provisional[field] = _counter(getattr(memory, attribute, None),
                                                       field, integer=True)
                except Exception as exc:
                    errors.append(_issue(exc, stage))
            except Exception as exc:
                errors.append(_issue(exc, stage))
            finally:
                # Even a denied/malformed counter read needs the second guard.
                try:
                    self._identity(psutil)
                except Exception as exc:
                    errors.append(_issue(exc, "identity_after"))
                    provisional.clear()
            record.update(provisional)
        except Exception as exc:
            errors.append(_issue(exc, stage))
        finally:
            try:
                record["read_end_ns"] = read_clock()
                start, end = record["read_start_ns"], record["read_end_ns"]
                if start is not None:
                    if record["mono_ns"] is None:
                        record["mono_ns"] = (start + end) // 2
                    if not start <= record["mono_ns"] <= end:
                        raise ValueError("Invalid monotonic read interval")
            except Exception as exc:
                errors.append(_issue(exc, "read_end"))
        record["ok"] = not errors
        if errors:
            record["error"] = f"{errors[0]['type']}: {errors[0]['message']}"
        return record


def _memory_stats(values):
    result = {"count": len(values)}
    stats = {"min": min(values), "max": max(values), "mean": mean(values),
             "median": median(values)} if values else dict.fromkeys(("min", "max", "mean", "median"))
    for name, value in stats.items():
        result[f"{name}_bytes"] = value
        result[f"{name}_mb"] = None if value is None else value / 1_000_000
        result[f"{name}_mib"] = None if value is None else value / 1_048_576
    return result


def summarize(samples, begin_ns, end_ns, logical_cpus):
    """Summarize one PID/identity and one idle window, without modifying inputs.

    Only complete reads inside [begin_ns, end_ns] contribute. Input order must
    be chronological; mixed identities, overlapping/nonincreasing CPU reads or
    decreasing counters invalidate the CPU aggregate instead of being sorted
    or bridged silently. Missing counters remain None. CPU percentages use the
    actual midpoint-to-midpoint coverage, never the requested idle duration.

    ok describes complete error-free metrics, not RNF acceptance. errors keeps
    raw failures (including outside idle); insufficient lists missing evidence.
    RAM summaries use absolute bytes, decimal MB and binary MiB, with peak_wset
    lifetime distinct from the sampled peak of rss.
    """
    if (not _integer(begin_ns) or not _integer(end_ns)
            or not _number(begin_ns) or not _number(end_ns) or begin_ns >= end_ns):
        raise ValueError("Idle endpoints must be integer ns with begin_ns < end_ns")
    if logical_cpus is not None and (not _integer(logical_cpus)
                                     or not _number(logical_cpus) or logical_cpus == 0):
        raise ValueError("logical_cpus must be a positive integer or None")
    records = list(samples)
    errors, insufficient, valid = [], [], []
    outside = 0
    in_idle = 0
    for index, record in enumerate(records):
        if not isinstance(record, dict):
            errors.append({"index": index, "error": "Sample must be a dict", "sample": record})
            continue
        start, end, mono = (record.get(field) for field in
                            ("read_start_ns", "read_end_ns", "mono_ns"))
        timestamps_valid = (all(_integer(value) for value in (start, end, mono))
                            and start <= mono <= end)
        inside = timestamps_valid and begin_ns <= start and end <= end_ns
        if timestamps_valid:
            if inside:
                in_idle += 1
            else:
                outside += 1
        reason = None
        if record.get("ok") is not True:
            reason = record.get("error") or "Sample is not ok"
        elif not timestamps_valid:
            reason = "Invalid sample timestamps"
        elif not _integer(record.get("pid")) or record["pid"] == 0 or not _number(record.get("create_time")):
            reason = "Invalid sample identity"
        else:
            try:
                for field in _CPU_FIELDS:
                    _counter(record.get(field), field)
                for field in _MEMORY_FIELDS:
                    _counter(record.get(field), field, integer=True)
            except ValueError as exc:
                reason = str(exc)
        if reason is not None:
            errors.append({"index": index, "error": reason, "sample": record})
        elif inside:
            valid.append((index, record))

    identity = (valid[0][1]["pid"], valid[0][1]["create_time"]) if valid else None
    matching = []
    mixed = False
    for index, record in valid:
        if (record["pid"], record["create_time"]) != identity:
            mixed = True
            errors.append({"index": index, "error": "Mixed process identities", "sample": record})
        else:
            matching.append(record)
    valid = matching
    ram = {field: _memory_stats([record[field] for record in valid
                               if record.get(field) is not None])
           for field in _MEMORY_FIELDS}
    for field, stats in ram.items():
        if not stats["count"]:
            insufficient.append(f"No valid {field} samples inside idle")

    cpu = [record for record in valid if all(record.get(field) is not None for field in _CPU_FIELDS)]
    result = {
        "ok": False, "mode": "exploratory", "idle_begin_ns": begin_ns,
        "idle_end_ns": end_ns, "idle_wall_s": (end_ns - begin_ns) / 1_000_000_000,
        "pid": identity[0] if identity else None,
        "create_time": identity[1] if identity else None,
        "samples_total": len(records), "samples_in_idle": in_idle,
        "samples_valid": len(valid), "samples_outside_idle": outside,
        "cpu_samples": len(cpu), "logical_cpus": logical_cpus,
        **dict.fromkeys(("coverage_begin_ns", "coverage_end_ns", "coverage_wall_s",
                         "coverage_fraction", "delta_user_s", "delta_system_s", "delta_cpu_s",
                         "cpu_pct_1_logico", "cpu_pct_total_maquina")),
        "ram": ram, "rss_sampled_peak_bytes": ram["rss_bytes"]["max_bytes"],
        "peak_wset_lifetime_bytes": ram["peak_wset_bytes"]["max_bytes"],
        "errors": errors, "insufficient": insufficient,
    }
    cpu_problem = "Mixed process identities" if mixed else None
    if len(cpu) < 2:
        cpu_problem = cpu_problem or "At least two complete CPU samples inside idle are required"
    for left, right in zip(valid, valid[1:]):
        if (right["mono_ns"] <= left["mono_ns"]
                or right["read_start_ns"] < left["read_end_ns"]):
            cpu_problem = cpu_problem or "CPU reads overlap or are not chronological"
    for field in _CPU_FIELDS:
        available = [record[field] for record in valid if record.get(field) is not None]
        if any(right < left for left, right in zip(available, available[1:])):
            cpu_problem = cpu_problem or "CPU counters decreased"
    if cpu_problem:
        insufficient.append(cpu_problem)
    else:
        first, last = cpu[0], cpu[-1]
        coverage = (last["mono_ns"] - first["mono_ns"]) / 1_000_000_000
        delta_user, delta_system = (last[field] - first[field] for field in _CPU_FIELDS)
        delta_cpu = delta_user + delta_system
        percent = 100 * delta_cpu / coverage
        if not all(_number(value) for value in (delta_user, delta_system, delta_cpu, percent)):
            insufficient.append("CPU arithmetic is not finite")
        else:
            result.update(coverage_begin_ns=first["mono_ns"], coverage_end_ns=last["mono_ns"],
                          coverage_wall_s=coverage, coverage_fraction=coverage / result["idle_wall_s"],
                          delta_user_s=delta_user, delta_system_s=delta_system, delta_cpu_s=delta_cpu,
                          cpu_pct_1_logico=percent,
                          cpu_pct_total_maquina=None if logical_cpus is None else percent / logical_cpus)
    if logical_cpus is None:
        insufficient.append("Logical CPU count unavailable; total-machine percentage unavailable")
    result["ok"] = not errors and not insufficient
    return result

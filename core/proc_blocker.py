"""Process blocking with an injectable boundary; importing this module has no effects.

The mandatory names are a technical baseline, not a universal classifier. Renamed
or portable applications and unlisted helpers may need user safelist entries.
Terminal ancestry is deliberately not inherited by every child application.
Only verifiable living ancestors can identify helpers: historical ancestry of
orphaned helpers cannot be reconstructed from a vanished/recycled parent PID.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
import ntpath
import os
from pathlib import Path, PureWindowsPath
import re
from threading import Lock
from typing import Callable, Protocol

from core.models import AppConfig


IDE_NAMES = frozenset({"code.exe", "idea64.exe", "pycharm64.exe"})
BROWSER_NAMES = frozenset({"brave.exe", "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe"})
TERMINAL_NAMES = frozenset({"windowsterminal.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "conhost.exe", "openconsole.exe"})
# Codex names below were observed in this development environment. Their presence
# is not assumed on another machine, and no installation path is manufactured.
TOOL_NAMES = frozenset({"codex.exe", "codex-code-mode-host.exe", "codex-computer-use-swift.exe", "codex-windows-sandbox-service.exe"})
SYSTEM_NAMES = frozenset({"system", "registry", "smss.exe", "csrss.exe", "wininit.exe", "services.exe", "lsass.exe", "svchost.exe", "winlogon.exe", "explorer.exe"})
MANDATORY_NAMES = IDE_NAMES | BROWSER_NAMES | TERMINAL_NAMES | TOOL_NAMES | SYSTEM_NAMES
INHERITED_NAMES = IDE_NAMES | BROWSER_NAMES | TOOL_NAMES


class ProcessBlockerError(RuntimeError):
    """The cycle could not safely initialize or enumerate processes."""

    def __init__(self, message, *, partial_report=None):
        super().__init__(message)
        self.partial_report = partial_report


class ProcessGone(RuntimeError):
    """The inspected process no longer has its original identity."""


class ProcessUnavailable(RuntimeError):
    """Required target information or permissions are unavailable."""


@dataclass(frozen=True)
class ProcessIdentity:
    pid: int
    create_time: float


@dataclass(frozen=True)
class Ancestor:
    identity: ProcessIdentity
    name: str | None


@dataclass(frozen=True)
class ProcessSnapshot:
    pid: int
    name: str | None = None
    create_time: float | None = None
    exe: str | None = None
    cmdline: tuple[str, ...] | None = None
    username: str | None = None
    ancestors: tuple[Ancestor, ...] = ()
    errors: tuple[str, ...] = ()
    gone: bool = False

    @property
    def identity(self) -> ProcessIdentity | None:
        stamp = self.create_time
        if not isinstance(self.pid, int) or isinstance(self.pid, bool) or self.pid <= 0:
            return None
        if not isinstance(stamp, (int, float)) or isinstance(stamp, bool) or not math.isfinite(stamp) or stamp <= 0 or "create_time" in self.errors:
            return None
        return ProcessIdentity(self.pid, stamp)


@dataclass(frozen=True)
class ProcessReference:
    snapshot: ProcessSnapshot
    process: object = field(compare=False, repr=False)


@dataclass(frozen=True)
class ProtectionContext:
    own_pid: int
    identities: frozenset[ProcessIdentity]
    windows_directory: str


@dataclass(frozen=True)
class WaitResult:
    gone: tuple[ProcessReference, ...] = ()
    alive: tuple[ProcessReference, ...] = ()
    unavailable: tuple[ProcessReference, ...] = ()


@dataclass(frozen=True)
class ProcessResult:
    pid: int
    name: str | None
    status: str
    reason: str


@dataclass(frozen=True)
class ProcessDiscovery:
    """A read-only prefilter result, never an actionable process snapshot.

    It intentionally has no identity, username, cmdline or ancestry fields.
    Even if its name becomes stale, its only possible effect is to skip work in
    this discovery cycle. Every candidate must become a full fresh snapshot.
    """
    pid: int
    name: str | None
    status: str
    reason: str

    def __post_init__(self):
        if self.status not in {"protected", "unmatched", "unavailable", "gone"}:
            raise ValueError("Discovery cannot authorize a process action")


@dataclass(frozen=True)
class TerminationEvent:
    identity: ProcessIdentity
    confirmed_at: datetime


@dataclass(frozen=True)
class ScanReport:
    results: tuple[ProcessResult, ...]
    events: tuple[TerminationEvent, ...]


class ProcessAdapter(Protocol):
    def protection_context(self) -> ProtectionContext: ...
    def iter_snapshots(self, config: AppConfig | None = None): ...
    def inspect_fresh(self, pid: int) -> ProcessReference: ...
    def resolve_path(self, path: str) -> str: ...
    def terminate(self, reference: ProcessReference) -> None: ...
    def kill(self, reference: ProcessReference) -> None: ...
    def wait_many(self, references: tuple[ProcessReference, ...], timeout: float) -> WaitResult: ...


def _under(path: str, directory: str) -> bool:
    """Compare resolved Windows path components, including the directory itself."""
    child = PureWindowsPath(path).parts
    root = PureWindowsPath(directory).parts
    return len(child) >= len(root) and tuple(p.casefold() for p in child[:len(root)]) == tuple(p.casefold() for p in root)


def _system_account(username: str) -> bool:
    name = username.casefold()
    return name.startswith("nt authority\\") or name in {"system", "local service", "network service"}


class ProcessBlocker:
    def __init__(self, adapter: ProcessAdapter | None = None, *, clock: Callable[[], datetime] | None = None):
        self.adapter = adapter if adapter is not None else PsutilAdapter()
        self.clock = clock if clock is not None else lambda: datetime.now(timezone.utc)
        self._pending: dict[ProcessIdentity, ProcessReference] = {}
        self._emitted: set[ProcessIdentity] = set()
        self._unreported: dict[ProcessIdentity, tuple[ProcessResult, TerminationEvent]] = {}
        self._lock = Lock()

    def _decision(self, snapshot: ProcessSnapshot, config: AppConfig, context: ProtectionContext) -> tuple[str, str]:
        if snapshot.pid in {0, 4, context.own_pid} or snapshot.identity in context.identities:
            return "protected", "self_system_or_ancestor"
        name = snapshot.name.casefold() if isinstance(snapshot.name, str) and snapshot.name else None
        if name in MANDATORY_NAMES or name in {n.casefold() for n in config.safelist_exes}:
            return "protected", "mandatory_or_user_safelist"
        if any(a.name and a.name.casefold() in INHERITED_NAMES for a in snapshot.ancestors):
            return "protected", "ide_browser_or_tool_ancestor"
        if snapshot.username and _system_account(snapshot.username):
            return "protected", "system_account"
        if snapshot.gone:
            return "gone", "disappeared_before_action"
        if snapshot.identity is None or not name or "name" in snapshot.errors:
            return "unavailable", "identity_or_name_unavailable"
        if not snapshot.username or "username" in snapshot.errors or "ancestors" in snapshot.errors or any(not a.name for a in snapshot.ancestors):
            return "unavailable", "protection_metadata_unavailable"
        if not snapshot.exe or "exe" in snapshot.errors:
            return "unavailable", "executable_unavailable"
        try:
            executable = self.adapter.resolve_path(snapshot.exe)
        except Exception:
            return "unavailable", "executable_destination_unverifiable"
        if _under(executable, context.windows_directory):
            return "protected", "windows_directory"
        # The configured lists are explicit target selection; no additional
        # certification flow is required. Unknown names are not inferred as IDEs.
        if name in {n.casefold() for n in config.block_exes}:
            return "target", "executable_rule"
        uncertain_folder = False
        for folder in config.block_folders:
            try:
                resolved = self.adapter.resolve_path(folder)
            except Exception:
                uncertain_folder = True
                continue
            if _under(executable, resolved):
                return "target", "folder_rule"
        for rule in config.block_cmdline:
            if name != rule.executable.casefold():
                continue
            if snapshot.cmdline is None or "cmdline" in snapshot.errors:
                return "unavailable", "cmdline_unavailable"
            if any(rule.contains.casefold() in argument.casefold() for argument in snapshot.cmdline):
                return "target", "cmdline_rule"
        if uncertain_folder:
            return "unavailable", "folder_destination_unverifiable"
        return "unmatched", "no_rule_matched"

    def _fresh_target(self, original: ProcessSnapshot, config: AppConfig, context: ProtectionContext):
        ref = self.adapter.inspect_fresh(original.pid)
        if original.identity is None or ref.snapshot.identity != original.identity:
            return ref, "unavailable", "identity_changed"
        status, reason = self._decision(ref.snapshot, config, context)
        return ref, status, reason

    def scan(self, config: AppConfig, may_act: Callable[[], bool]) -> ScanReport:
        if not self._lock.acquire(blocking=False):
            raise ProcessBlockerError("A process scan is already running")
        self._partial_report = None
        try:
            return self._scan(config, may_act)
        except ProcessBlockerError as exc:
            if exc.partial_report is None and self._partial_report is not None:
                exc.partial_report = self._partial_report()
                # The error delivers these confirmed events through its report;
                # they must not be delivered again on the next successful scan.
                self._unreported.clear()
            raise
        finally:
            self._partial_report = None
            self._lock.release()

    def _scan(self, config: AppConfig, may_act: Callable[[], bool]) -> ScanReport:
        results: dict[object, ProcessResult] = {key: pair[0] for key, pair in self._unreported.items()}
        events: list[TerminationEvent] = [pair[1] for pair in self._unreported.values()]
        self._partial_report = lambda: ScanReport(tuple(results.values()), tuple(events))

        def record(snapshot, status, reason):
            key = snapshot.identity if snapshot.identity is not None else ("unknown", snapshot.pid)
            results[key] = ProcessResult(snapshot.pid, snapshot.name, status, reason)

        def confirm(ref):
            identity = ref.snapshot.identity
            if identity not in self._pending:
                return
            if identity not in self._emitted:
                observed = self.clock()
                if observed.tzinfo is None or observed.utcoffset() is None:
                    raise ProcessBlockerError("Confirmation clock must be timezone-aware")
                event = TerminationEvent(identity, observed)
                result = ProcessResult(ref.snapshot.pid, ref.snapshot.name, "terminated", "exit_confirmed")
                self._unreported[identity] = (result, event)
                events.append(event)
                self._emitted.add(identity)
            self._pending.pop(identity)
            record(ref.snapshot, "terminated", "exit_confirmed")

        def wait(refs, timeout):
            if not refs:
                return ()
            try:
                waited = self.adapter.wait_many(tuple(refs), timeout)
            except Exception as exc:
                for ref in refs:
                    record(ref.snapshot, "failed", "confirmation_failed:" + type(exc).__name__)
                return ()
            supplied = {ref.snapshot.identity: ref for ref in refs}
            seen = set()
            for ref in waited.gone:
                identity = ref.snapshot.identity
                if identity in supplied:
                    confirm(supplied[identity])
                    seen.add(identity)
            alive = []
            for ref in waited.alive:
                identity = ref.snapshot.identity
                if identity in supplied and identity not in seen:
                    original = supplied[identity]
                    record(original.snapshot, "pending", "exit_not_yet_confirmed")
                    alive.append(original)
                    seen.add(identity)
            for ref in refs:
                if ref.snapshot.identity not in seen:
                    record(ref.snapshot, "unavailable", "confirmation_unavailable")
            return tuple(alive)

        pending_at_start = set(self._pending)
        wait(tuple(self._pending.values()), 0.0)

        def gate():
            try:
                return bool(may_act())
            except Exception as exc:
                raise ProcessBlockerError("Blocking gate could not be evaluated") from exc

        def protection_context():
            try:
                current = self.adapter.protection_context()
                if not current.windows_directory or not PureWindowsPath(current.windows_directory).is_absolute():
                    raise ProcessBlockerError("Windows protection directory is unavailable")
                return current
            except Exception as exc:
                raise ProcessBlockerError("Unable to establish mandatory protection context") from exc

        # Reconciliation observes only previously accepted references. Outside
        # the window it does not even enumerate possible new targets.
        if not gate():
            self._unreported.clear()
            return ScanReport(tuple(results.values()), tuple(events))
        context = protection_context()
        try:
            # Exhaust discovery before effects: a partial enumeration is global failure.
            snapshots = tuple(self.adapter.iter_snapshots(config))
        except Exception as exc:
            raise ProcessBlockerError("Unable to enumerate processes") from exc
        accepted = []
        for snapshot in snapshots:
            if isinstance(snapshot, ProcessDiscovery):
                # Light discovery never supplies identity or authorizes effects.
                # Pending references have already been reconciled independently.
                if not any(identity.pid == snapshot.pid for identity in pending_at_start):
                    results[("discovery", snapshot.pid)] = ProcessResult(snapshot.pid, snapshot.name, snapshot.status, snapshot.reason)
                continue
            if snapshot.identity in pending_at_start or snapshot.identity in self._pending or snapshot.identity in self._emitted:
                continue
            status, reason = self._decision(snapshot, config, context)
            if status != "target":
                record(snapshot, status, reason)
                continue
            current_context = protection_context()
            try:
                ref, status, reason = self._fresh_target(snapshot, config, current_context)
                if status != "target":
                    record(snapshot, status, reason)
                    continue
            except ProcessGone:
                record(snapshot, "gone", "disappeared_before_action")
            except ProcessUnavailable:
                record(snapshot, "unavailable", "action_or_inspection_denied")
            except Exception as exc:
                record(snapshot, "failed", "action_or_inspection_failed:" + type(exc).__name__)
            else:
                if not gate():
                    record(snapshot, "inactive", "blocking_gate_closed")
                    continue
                try:
                    self.adapter.terminate(ref)
                except ProcessGone:
                    record(snapshot, "gone", "disappeared_before_action")
                    continue
                except ProcessUnavailable:
                    record(snapshot, "unavailable", "action_or_inspection_denied")
                    continue
                except Exception as exc:
                    record(snapshot, "failed", "action_or_inspection_failed:" + type(exc).__name__)
                    continue
                self._pending[snapshot.identity] = ref
                accepted.append(ref)
                record(snapshot, "pending", "termination_requested")

        survivors = wait(accepted, 2.0)
        for original in survivors:
            snapshot = original.snapshot
            current_context = protection_context()
            try:
                ref, status, reason = self._fresh_target(snapshot, config, current_context)
                if status != "target":
                    record(snapshot, status, reason)
                    continue
            except ProcessGone:
                # An earlier request was accepted; only waiting the original
                # reference can confirm it. Do not signal the replacement PID.
                record(snapshot, "pending", "awaiting_original_exit_confirmation")
            except ProcessUnavailable:
                record(snapshot, "unavailable", "kill_or_inspection_denied")
            except Exception as exc:
                record(snapshot, "failed", "kill_or_inspection_failed:" + type(exc).__name__)
            else:
                if not gate():
                    record(snapshot, "inactive", "blocking_gate_closed")
                    continue
                try:
                    self.adapter.kill(ref)
                except ProcessGone:
                    record(snapshot, "pending", "awaiting_original_exit_confirmation")
                except ProcessUnavailable:
                    record(snapshot, "unavailable", "kill_or_inspection_denied")
                except Exception as exc:
                    record(snapshot, "failed", "kill_or_inspection_failed:" + type(exc).__name__)
        # No second positive timeout, including if kill failed or became unsafe.
        # Keep actionable diagnostic results when zero-time confirmation is pending.
        saved = dict(results)
        wait(tuple(ref for ref in accepted if ref.snapshot.identity in self._pending), 0.0)
        for key, value in saved.items():
            if key in results and results[key].status == "pending" and value.status not in {"pending", "terminated"}:
                results[key] = value
        self._unreported.clear()
        return ScanReport(tuple(results.values()), tuple(events))


class _WaitProbe:
    """Isolate permission failures inside psutil's collective wait."""
    def __init__(self, reference, psutil):
        self.reference = reference
        self.psutil = psutil
        self.error = False

    def wait(self, timeout):
        if self.error:
            raise self.psutil.TimeoutExpired(timeout)
        try:
            if not self.reference.process.is_running():
                return None
            return self.reference.process.wait(timeout=timeout)
        except self.psutil.TimeoutExpired:
            raise
        except Exception:
            self.error = True
            raise self.psutil.TimeoutExpired(timeout) from None

    def is_running(self):
        if self.error:
            return True
        try:
            return self.reference.process.is_running()
        except Exception:
            self.error = True
            return True


class PsutilAdapter:
    """Windows adapter. Tests inject psutil/resolution; no live-process test needed."""
    def __init__(self, *, psutil_module=None, path_resolver=None, windows_directory=None, own_pid=None):
        if psutil_module is None:
            if os.name != "nt":
                raise ProcessBlockerError("Process application is supported only on Windows")
            try:
                import psutil as psutil_module
            except ImportError as exc:
                raise ProcessBlockerError("psutil is required to apply process rules") from exc
        self.psutil = psutil_module
        self._resolver = path_resolver if path_resolver is not None else lambda value: str(Path(value).resolve(strict=True))
        self._windows_directory = windows_directory
        self._own_pid = os.getpid() if own_pid is None else own_pid

    def resolve_path(self, path):
        def expand(match):
            variable = match.group(1)
            value = os.environ.get(variable)
            if value is None:
                raise ProcessUnavailable("Unknown path variable")
            return value
        expanded = re.sub(r"%([^%]+)%", expand, path)
        if "%" in expanded or not PureWindowsPath(expanded).is_absolute() or any(c in expanded for c in "*?") or expanded.startswith(("\\\\?\\", "\\\\.\\")):
            raise ProcessUnavailable("Path cannot be safely resolved")
        resolved = self._resolver(expanded)
        if not resolved or not PureWindowsPath(resolved).is_absolute():
            raise ProcessUnavailable("Absolute path destination is unavailable")
        return ntpath.normpath(resolved)

    def _windows_root(self):
        if self._windows_directory is not None:
            return self.resolve_path(self._windows_directory)
        # Read the OS directory, rather than assuming a C: drive or trusting a
        # configured game path/environment override as the Windows root.
        import ctypes
        buffer = ctypes.create_unicode_buffer(32768)
        length = ctypes.windll.kernel32.GetWindowsDirectoryW(buffer, len(buffer))
        if not length or length >= len(buffer):
            raise ProcessBlockerError("Windows directory lookup failed")
        return self.resolve_path(buffer.value)

    def inspect_fresh(self, pid):
        try:
            process = self.psutil.Process(pid)
        except self.psutil.NoSuchProcess as exc:
            raise ProcessGone("Process no longer exists") from exc
        except self.psutil.AccessDenied as exc:
            raise ProcessUnavailable("Process inspection denied") from exc
        values = {}
        errors = []
        for attr in ("name", "create_time", "exe", "cmdline", "username"):
            try:
                value = getattr(process, attr)()
                values[attr] = tuple(value) if attr == "cmdline" and value is not None else value
            except self.psutil.AccessDenied:
                values[attr] = None
                errors.append(attr)
            except self.psutil.NoSuchProcess:
                return ProcessReference(ProcessSnapshot(pid, **values, errors=tuple(errors), gone=True), process)
            except Exception:
                values[attr] = None
                errors.append(attr)
        ancestors = []
        try:
            current = process
            seen = {pid}
            while True:
                parent = current.parent()
                if parent is None:
                    parent_pid = current.ppid()
                    if parent_pid != 0:
                        if not isinstance(parent_pid, int) or isinstance(parent_pid, bool) or parent_pid <= 0:
                            raise ProcessUnavailable("Parent PID unavailable")
                        try:
                            former = self.psutil.Process(parent_pid)
                            former_stamp = former.create_time()
                            child_stamp = current.create_time()
                            if any(not isinstance(stamp, (int, float)) or isinstance(stamp, bool) or not math.isfinite(stamp) or stamp <= 0 for stamp in (former_stamp, child_stamp)):
                                raise ProcessUnavailable("Parent lifetime unavailable")
                            # An extant holder born after this child is a reused
                            # PID, not a living ancestor of the child.
                            if former_stamp <= child_stamp and former.is_running():
                                raise ProcessUnavailable("Existing parent unexpectedly uninspectable")
                        except self.psutil.NoSuchProcess:
                            # Confirmed absent: finish the living ancestor chain.
                            pass
                    break
                if parent.pid in seen:
                    raise ProcessUnavailable("Cyclic ancestry")
                seen.add(parent.pid)
                stamp = parent.create_time()
                if not isinstance(stamp, (int, float)) or isinstance(stamp, bool) or not math.isfinite(stamp) or stamp <= 0:
                    raise ProcessUnavailable("Ancestor identity unavailable")
                parent_identity = ProcessSnapshot(parent.pid, create_time=stamp).identity
                if parent_identity is None:
                    raise ProcessUnavailable("Ancestor PID unavailable")
                ancestors.append(Ancestor(parent_identity, parent.name()))
                if not parent.is_running():
                    raise ProcessUnavailable("Ancestor identity changed during inspection")
                current = parent
        except Exception:
            errors.append("ancestors")
        try:
            if not process.is_running():
                return ProcessReference(ProcessSnapshot(pid, **values, ancestors=tuple(ancestors), errors=tuple(errors), gone=True), process)
        except self.psutil.NoSuchProcess:
            return ProcessReference(ProcessSnapshot(pid, **values, ancestors=tuple(ancestors), errors=tuple(errors), gone=True), process)
        except Exception:
            values["create_time"] = None
            errors.append("create_time")
        return ProcessReference(ProcessSnapshot(pid, **values, ancestors=tuple(ancestors), errors=tuple(errors)), process)

    def iter_snapshots(self, config=None):
        """Prefilter using only names/paths; fully inspect possible targets.

        Resolution memoization lasts one discovery only, and is never used by
        the independent full inspection/decision immediately before an action.
        Without a config retain the full read-only inspection interface.
        """
        if config is None:
            yield from self._iter_full_snapshots()
            return
        protected_names = MANDATORY_NAMES | {n.casefold() for n in config.safelist_exes}
        candidate_names = {n.casefold() for n in config.block_exes} | {r.executable.casefold() for r in config.block_cmdline}
        windows_root = self._windows_root() if config.block_folders else None
        path_cache = {}

        def resolve_for_discovery(path):
            if path not in path_cache:
                try:
                    path_cache[path] = self.resolve_path(path)
                except Exception:
                    path_cache[path] = None
            return path_cache[path]

        folders = tuple(resolve_for_discovery(path) for path in config.block_folders)
        for discovered in self.psutil.process_iter():
            pid = discovered.pid
            if pid in {0, 4, self._own_pid}:
                yield ProcessDiscovery(pid, None, "protected", "self_or_special_pid")
                continue
            name = None
            try:
                # process_iter instances may cache stale names. Use a new
                # instance for the cheap reads, not prior-cycle cached values.
                process = self.psutil.Process(pid)
                name = process.name()
                if not isinstance(name, str) or not name:
                    yield ProcessDiscovery(pid, None, "unavailable", "discovery_name_unavailable")
                    continue
                normalized = name.casefold()
                if normalized in protected_names:
                    yield ProcessDiscovery(pid, name, "protected", "mandatory_or_user_safelist")
                    continue
                if normalized not in candidate_names:
                    if not folders:
                        yield ProcessDiscovery(pid, name, "unmatched", "no_name_rule_candidate")
                        continue
                    executable = process.exe()
                    if not isinstance(executable, str) or not executable:
                        yield ProcessDiscovery(pid, name, "unavailable", "discovery_executable_unavailable")
                        continue
                    destination = resolve_for_discovery(executable)
                    if destination is None:
                        yield ProcessDiscovery(pid, name, "unavailable", "executable_destination_unverifiable")
                        continue
                    if _under(destination, windows_root):
                        yield ProcessDiscovery(pid, name, "protected", "windows_directory")
                        continue
                    if not any(folder is not None and _under(destination, folder) for folder in folders):
                        if any(folder is None for folder in folders):
                            yield ProcessDiscovery(pid, name, "unavailable", "folder_destination_unverifiable")
                        else:
                            yield ProcessDiscovery(pid, name, "unmatched", "no_folder_rule_candidate")
                        continue
                # Reopen independently. A light name/path candidate is not an
                # identity and may have changed since the prefilter reads.
                yield self.inspect_fresh(pid).snapshot
            except (ProcessGone, self.psutil.NoSuchProcess):
                yield ProcessDiscovery(pid, name, "gone", "disappeared_during_discovery")
            except (ProcessUnavailable, self.psutil.AccessDenied):
                yield ProcessDiscovery(pid, name, "unavailable", "discovery_metadata_denied")
            except Exception:
                yield ProcessDiscovery(pid, name, "unavailable", "discovery_metadata_unavailable")

    def _iter_full_snapshots(self):
        for process in self.psutil.process_iter():
            try:
                yield self.inspect_fresh(process.pid).snapshot
            except ProcessGone:
                yield ProcessSnapshot(process.pid, gone=True)
            except ProcessUnavailable:
                yield ProcessSnapshot(process.pid, errors=("identity",))

    def protection_context(self):
        try:
            own = self.inspect_fresh(self._own_pid).snapshot
            if own.gone or own.identity is None or "ancestors" in own.errors:
                raise ProcessBlockerError("App identity or ancestry unavailable")
            return ProtectionContext(self._own_pid, frozenset({own.identity, *(a.identity for a in own.ancestors)}), self._windows_root())
        except Exception as exc:
            raise ProcessBlockerError("Unable to establish mandatory protection context") from exc

    def _signal(self, reference, method):
        if reference.snapshot.identity is None:
            raise ProcessUnavailable("No verified process identity")
        try:
            if not reference.process.is_running():
                raise ProcessGone("Process identity no longer exists")
            if reference.process.pid != reference.snapshot.pid or reference.process.create_time() != reference.snapshot.create_time:
                raise ProcessGone("Process identity changed")
            getattr(reference.process, method)()
        except self.psutil.NoSuchProcess as exc:
            raise ProcessGone("Process identity no longer exists") from exc
        except self.psutil.AccessDenied as exc:
            raise ProcessUnavailable("Process action denied") from exc

    def terminate(self, reference):
        self._signal(reference, "terminate")

    def kill(self, reference):
        self._signal(reference, "kill")

    def wait_many(self, references, timeout):
        probes = [_WaitProbe(ref, self.psutil) for ref in references]
        gone, alive = self.psutil.wait_procs(probes, timeout=timeout)
        return WaitResult(tuple(p.reference for p in gone if not p.error), tuple(p.reference for p in alive if not p.error), tuple(p.reference for p in probes if p.error))

"""Mutexes de fixtures isoladas; sem GUI, bloqueador ou processos encerrados."""

import ctypes
from ctypes import wintypes
import hashlib
import os
from pathlib import Path
from queue import Queue
import shutil
import subprocess
import sys
from threading import Barrier, Event, Lock, Thread
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

from core.instance_guard import InstanceGuard, InstanceGuardError, WindowsMutexBackend

_UNSET = object()


class FakeBackend:
    """Existência compartilhada por nome e handles opacos independentes."""

    def __init__(self):
        self.live = {}
        self.created = []
        self.closed = []
        self.close_errors = []
        self.create_error = None
        self.lock = Lock()

    def create_mutex(self, name):
        with self.lock:
            if self.create_error is not None:
                raise self.create_error
            exists = name in self.live.values()
            handle = object()
            self.live[handle] = name
            self.created.append((name, handle, exists))
            return handle, exists

    def close_handle(self, handle):
        with self.lock:
            if self.close_errors:
                raise self.close_errors.pop(0)
            del self.live[handle]
            self.closed.append(handle)


class InstanceGuardTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / f".editor-integration-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = self.root / "Ação 日本語 🎮.JSON"
        self.backend = FakeBackend()
        self.guards = []

    def guard(self, path=_UNSET, backend=None):
        guard = InstanceGuard(self.path if path is _UNSET else path,
                              backend=self.backend if backend is None else backend)
        self.guards.append(guard)
        return guard

    def tearDown(self):
        for guard in self.guards:
            guard.release()
        self.assertEqual(self.backend.live, {})

    def join(self, worker):
        worker.join(3)
        self.assertFalse(worker.is_alive(), "thread fake deve terminar")

    def test_import_and_construction_do_not_load_windows_or_process_dependencies(self):
        script = '''
import builtins, ctypes
from pathlib import Path
from unittest.mock import Mock, patch
real_import = builtins.__import__
def guarded(name, *args, **kwargs):
    if name in ('psutil', 'pystray', 'tkinter', 'core.proc_blocker'):
        raise AssertionError('dependency imported')
    return real_import(name, *args, **kwargs)
builtins.__import__ = guarded
blocked = Mock(side_effect=AssertionError('construction effect'))
with patch.object(ctypes, 'WinDLL', blocked, create=True), patch.object(Path, 'resolve', blocked):
    from core.instance_guard import InstanceGuard, WindowsMutexBackend
    guard = InstanceGuard('missing.json')
    guard.release()
    guard.release()
    backend = WindowsMutexBackend()
blocked.assert_not_called()
'''
        result = subprocess.run([sys.executable, "-B", "-c", script],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_injected_backend_and_path_are_untouched_until_acquire(self):
        boundary = Mock(side_effect=AssertionError("construction IO"))

        class PathLike:
            __fspath__ = boundary

        backend = Mock()
        guard = InstanceGuard(PathLike(), backend=backend)
        guard.release()
        boundary.assert_not_called()
        backend.create_mutex.assert_not_called()
        backend.close_handle.assert_not_called()

    def test_default_backend_rejects_non_windows_without_loading_a_library(self):
        backend = WindowsMutexBackend()
        with patch("core.instance_guard.os.name", "posix"), \
             patch.object(ctypes, "WinDLL", create=True) as load:
            with self.assertRaisesRegex(OSError, "requer Windows"):
                backend.create_mutex("Local\\Focus.Gui.fixture")
            load.assert_not_called()

    def test_acquire_and_release_are_idempotent_and_close_exact_handle_once(self):
        guard = self.guard()
        self.assertTrue(guard.acquire())
        handle = self.backend.created[0][1]
        self.assertTrue(guard.acquire())
        self.assertEqual(len(self.backend.created), 1)
        self.assertIsNone(guard.release())
        self.assertIsNone(guard.release())
        self.assertEqual(self.backend.closed, [handle])
        self.assertTrue(guard.acquire())
        self.assertEqual(len(self.backend.created), 2)
        self.assertIsNot(self.backend.created[1][1], handle)

    def test_duplicate_false_closes_only_duplicate_handle_and_owner_survives(self):
        first, second = self.guard(), self.guard()
        self.assertTrue(first.acquire())
        self.assertFalse(second.acquire())
        owner_handle, duplicate_handle = [item[1] for item in self.backend.created]
        self.assertEqual(self.backend.closed, [duplicate_handle])
        self.assertIn(owner_handle, self.backend.live)
        second.release()
        self.assertEqual(self.backend.closed, [duplicate_handle])
        first.release()
        self.assertTrue(second.acquire())
        self.assertFalse(self.backend.created[-1][2])

    def test_normalized_unicode_name_matches_utf8_sha256_not_filename(self):
        guard = self.guard()
        self.assertTrue(guard.acquire())
        normalized = os.path.normcase(str(self.path.resolve()))
        expected = "Local\\Focus.Gui." + hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        name = self.backend.created[0][0]
        self.assertEqual(name, expected)
        self.assertRegex(name, r"^Local\\Focus\.Gui\.[0-9a-f]{64}$")
        self.assertNotIn("日本語", name)
        self.assertFalse(self.path.exists())

    def test_absolute_relative_dot_and_pathlike_aliases_share_same_name(self):
        aliases = (
            self.path, str(self.path), os.path.relpath(self.path),
            self.root / "subfolder" / ".." / self.path.name,
        )
        owner = self.guard(aliases[0])
        self.assertTrue(owner.acquire())
        for alias in aliases[1:]:
            with self.subTest(alias=alias):
                duplicate = self.guard(alias)
                self.assertFalse(duplicate.acquire())
                self.assertEqual(self.backend.created[-1][0], self.backend.created[0][0])

    @unittest.skipUnless(os.name == "nt", "Windows normcase")
    def test_windows_case_and_slash_aliases_share_same_name(self):
        owner = self.guard()
        self.assertTrue(owner.acquire())
        for alias in (str(self.path).upper(), str(self.path).lower(),
                      str(self.path).replace("\\", "/")):
            with self.subTest(alias=alias):
                self.assertFalse(self.guard(alias).acquire())
                self.assertEqual(self.backend.created[-1][0], self.backend.created[0][0])

    def test_same_basename_different_directory_and_different_files_are_independent(self):
        for path in (self.path, self.root / "other" / self.path.name, self.root / "other.json"):
            self.assertTrue(self.guard(path).acquire())
        self.assertEqual(len({entry[0] for entry in self.backend.created}), 3)

    def test_name_resolved_once_and_preserved_across_release_and_reacquire(self):
        guard = self.guard("relative.json")
        with patch.object(Path, "resolve", side_effect=[self.path, self.root / "changed.json"]) as resolve:
            self.assertTrue(guard.acquire())
            guard.release()
            self.assertTrue(guard.acquire())
            resolve.assert_called_once_with()
        self.assertEqual(self.backend.created[0][0], self.backend.created[1][0])

    def test_backend_creation_error_is_exception_with_original_cause_and_allows_retry(self):
        failure = OSError("Access denied")
        self.backend.create_error = failure
        guard = self.guard()
        with self.assertRaises(InstanceGuardError) as caught:
            guard.acquire()
        self.assertIs(caught.exception.__cause__, failure)
        self.assertIn("Access denied", str(caught.exception))
        self.assertEqual(self.backend.created, [])
        self.assertEqual(self.backend.closed, [])
        guard.release()
        self.backend.create_error = None
        self.assertTrue(guard.acquire())

    def test_invalid_path_and_resolution_failure_do_not_touch_backend(self):
        for path in (None, object(), "bad\x00name.json"):
            with self.subTest(path=path), self.assertRaises(InstanceGuardError):
                self.guard(path).acquire()
        guard = self.guard()
        with patch.object(Path, "resolve", side_effect=OSError("path denied")):
            with self.assertRaisesRegex(InstanceGuardError, "path denied"):
                guard.acquire()
        self.assertEqual(self.backend.created, [])
        self.assertTrue(guard.acquire())

    def test_null_backend_handle_is_failure_without_close_and_can_retry(self):
        backend = Mock()
        backend.create_mutex.side_effect = [(None, False), (0, True), (2**40 + 71, False)]
        guard = self.guard(backend=backend)
        for _ in range(2):
            with self.assertRaisesRegex(InstanceGuardError, "handle nulo"):
                guard.acquire()
        backend.close_handle.assert_not_called()
        self.assertTrue(guard.acquire())
        guard.release()
        backend.close_handle.assert_called_once_with(2**40 + 71)

    def test_owned_close_failure_retains_handle_and_ownership_for_retry(self):
        guard = self.guard()
        self.assertTrue(guard.acquire())
        handle = self.backend.created[0][1]
        failure = OSError("Close failed")
        self.backend.close_errors.append(failure)
        with self.assertRaises(InstanceGuardError) as caught:
            guard.release()
        self.assertIs(caught.exception.__cause__, failure)
        self.assertIn(handle, self.backend.live)
        self.assertTrue(guard.acquire())
        self.assertEqual(len(self.backend.created), 1)
        guard.release()
        guard.release()
        self.assertEqual(self.backend.closed, [handle])

    def test_duplicate_close_failure_retains_pending_handle_until_release(self):
        owner, duplicate = self.guard(), self.guard()
        self.assertTrue(owner.acquire())
        self.backend.close_errors.append(OSError("duplicate close failed"))
        with self.assertRaisesRegex(InstanceGuardError, "duplicate close failed"):
            duplicate.acquire()
        owner_handle, duplicate_handle = [entry[1] for entry in self.backend.created]
        self.assertEqual(set(self.backend.live), {owner_handle, duplicate_handle})
        duplicate.release()
        duplicate.release()
        self.assertEqual(self.backend.closed, [duplicate_handle])
        self.assertTrue(owner.acquire())

    def test_acquire_retries_pending_duplicate_cleanup_before_allocating_new_handle(self):
        owner, duplicate = self.guard(), self.guard()
        owner.acquire()
        self.backend.close_errors.extend([OSError("first close"), OSError("second close")])
        with self.assertRaises(InstanceGuardError):
            duplicate.acquire()
        with self.assertRaises(InstanceGuardError):
            duplicate.acquire()
        self.assertEqual(len(self.backend.created), 2)
        pending_handle = self.backend.created[-1][1]
        self.assertFalse(duplicate.acquire())
        self.assertEqual(self.backend.closed[0], pending_handle)
        self.assertEqual(len(self.backend.created), 3)

    def test_repeated_duplicate_attempts_leave_no_handles_after_owner_releases(self):
        owner, duplicate = self.guard(), self.guard()
        owner.acquire()
        for _ in range(20):
            self.assertFalse(duplicate.acquire())
            self.assertEqual(len(self.backend.live), 1)
        owner.release()
        self.assertEqual(self.backend.live, {})
        self.assertEqual(len(self.backend.closed), 21)

    def test_acquire_and_release_do_not_open_modify_or_delete_config(self):
        self.path.write_bytes(b'original config bytes')
        with patch.object(Path, "open", side_effect=AssertionError("open prohibited")), \
             patch.object(Path, "unlink", side_effect=AssertionError("unlink prohibited")), \
             patch("os.remove", side_effect=AssertionError("remove prohibited")):
            guard = self.guard()
            guard.acquire()
            guard.release()
        self.assertEqual(self.path.read_bytes(), b'original config bytes')

    def test_concurrent_same_guard_acquires_once_and_releases_once(self):
        guard = self.guard()
        barrier = Barrier(9)
        results = Queue()

        def acquire():
            barrier.wait(3)
            results.put(guard.acquire())

        workers = [Thread(target=acquire) for _ in range(8)]
        for worker in workers:
            worker.start()
        barrier.wait(3)
        for worker in workers:
            self.join(worker)
        self.assertTrue(all(results.get(timeout=3) for _ in workers))
        self.assertEqual(len(self.backend.created), 1)

        barrier = Barrier(9)
        def release():
            barrier.wait(3)
            guard.release()

        workers = [Thread(target=release) for _ in range(8)]
        for worker in workers:
            worker.start()
        barrier.wait(3)
        for worker in workers:
            self.join(worker)
        self.assertEqual(len(self.backend.closed), 1)

    def test_concurrent_guards_have_one_owner_and_close_every_duplicate(self):
        guards = [self.guard() for _ in range(8)]
        barrier = Barrier(9)
        results = Queue()

        def acquire(guard):
            barrier.wait(3)
            results.put(guard.acquire())

        workers = [Thread(target=acquire, args=(guard,)) for guard in guards]
        for worker in workers:
            worker.start()
        barrier.wait(3)
        for worker in workers:
            self.join(worker)
        self.assertEqual(sum(results.get(timeout=3) for _ in workers), 1)
        self.assertEqual(len(self.backend.live), 1)
        self.assertEqual(len(self.backend.closed), 7)

    def test_release_racing_create_waits_for_publication_and_closes_returned_handle(self):
        entered, unblock, release_called = Event(), Event(), Event()

        class HeldBackend(FakeBackend):
            def create_mutex(self, name):
                entered.set()
                if not unblock.wait(3):
                    raise AssertionError("create fake not released")
                return super().create_mutex(name)

        backend = HeldBackend()
        guard = self.guard(backend=backend)
        results = Queue()

        def acquire():
            results.put(guard.acquire())

        def release():
            release_called.set()
            guard.release()

        acquirer = Thread(target=acquire)
        releaser = Thread(target=release)
        acquirer.start()
        try:
            self.assertTrue(entered.wait(3))
            releaser.start()
            self.assertTrue(release_called.wait(3))
            self.assertEqual(backend.closed, [])
        finally:
            unblock.set()
            self.join(acquirer)
            if releaser.ident is not None:
                self.join(releaser)
        self.assertTrue(results.get(timeout=3))
        self.assertEqual(backend.live, {})
        self.assertEqual(backend.closed, [backend.created[0][1]])

    def test_acquire_racing_release_waits_for_close_then_creates_new_handle(self):
        entered, unblock, acquire_called = Event(), Event(), Event()

        class HeldBackend(FakeBackend):
            def close_handle(self, handle):
                entered.set()
                if not unblock.wait(3):
                    raise AssertionError("close fake not released")
                super().close_handle(handle)

        backend = HeldBackend()
        guard = self.guard(backend=backend)
        self.assertTrue(guard.acquire())
        first_handle = backend.created[0][1]
        results = Queue()

        def acquire():
            acquire_called.set()
            results.put(guard.acquire())

        releaser = Thread(target=guard.release)
        acquirer = Thread(target=acquire)
        releaser.start()
        try:
            self.assertTrue(entered.wait(3))
            acquirer.start()
            self.assertTrue(acquire_called.wait(3))
            self.assertEqual(len(backend.created), 1)
        finally:
            unblock.set()
            self.join(releaser)
            if acquirer.ident is not None:
                self.join(acquirer)
        self.assertTrue(results.get(timeout=3))
        self.assertEqual(backend.closed, [first_handle])
        self.assertEqual(len(backend.created), 2)
        self.assertIsNot(backend.created[1][1], first_handle)
        guard.release()
        self.assertEqual(backend.live, {})


@unittest.skipUnless(os.name == "nt", "ctypes Windows last-error API")
class WindowsMutexBackendTests(unittest.TestCase):
    def setUp(self):
        self.dll = Mock()
        self.dll.CreateMutexW.return_value = 2**40 + 37
        self.dll.CloseHandle.return_value = 1
        self.backend = WindowsMutexBackend(kernel32=self.dll)

    def test_win_dll_loading_is_lazy_last_error_enabled_and_cached(self):
        with patch("core.instance_guard.ctypes.WinDLL", return_value=self.dll) as load:
            backend = WindowsMutexBackend()
            load.assert_not_called()
            handle, exists = backend.create_mutex("Local\\Focus.Gui.fixture")
            self.assertEqual(handle, 2**40 + 37)
            self.assertFalse(exists)
            backend.close_handle(handle)
            load.assert_called_once_with("kernel32", use_last_error=True)

    def test_pointer_size_signatures_unicode_false_owner_and_exact_large_handle(self):
        handle, exists = self.backend.create_mutex("Local\\Focus.Gui.Ação 日本語 🎮")
        self.assertFalse(exists)
        self.assertEqual(handle, 2**40 + 37)
        self.assertEqual(self.dll.CreateMutexW.argtypes,
                         [ctypes.c_void_p, wintypes.BOOL, wintypes.LPCWSTR])
        self.assertIs(self.dll.CreateMutexW.restype, wintypes.HANDLE)
        self.assertEqual(ctypes.sizeof(self.dll.CreateMutexW.restype), ctypes.sizeof(ctypes.c_void_p))
        self.assertEqual(self.dll.CloseHandle.argtypes, [wintypes.HANDLE])
        self.assertIs(self.dll.CloseHandle.restype, wintypes.BOOL)
        self.dll.CreateMutexW.assert_called_once_with(None, False, "Local\\Focus.Gui.Ação 日本語 🎮")
        self.backend.close_handle(handle)
        self.dll.CloseHandle.assert_called_once_with(2**40 + 37)
        self.dll.ReleaseMutex.assert_not_called()
        self.dll.WaitForSingleObject.assert_not_called()

    def test_last_error_is_reset_before_success_to_avoid_stale_already_exists(self):
        ctypes.set_last_error(183)
        _, exists = self.backend.create_mutex("fixture")
        self.assertFalse(exists)
        self.assertEqual(ctypes.get_last_error(), 0)

    def test_already_exists_preserves_valid_handle_until_caller_closes(self):
        def create(*args):
            ctypes.set_last_error(183)
            return 2**40 + 11

        self.dll.CreateMutexW.side_effect = create
        handle, exists = self.backend.create_mutex("fixture")
        self.assertTrue(exists)
        self.assertEqual(handle, 2**40 + 11)
        self.dll.CloseHandle.assert_not_called()
        self.backend.close_handle(handle)
        self.dll.CloseHandle.assert_called_once_with(handle)

    def test_create_null_preserves_native_winerror_in_exception(self):
        def create(*args):
            ctypes.set_last_error(5)
            return None

        self.dll.CreateMutexW.side_effect = create
        with self.assertRaises(OSError) as caught:
            self.backend.create_mutex("fixture")
        self.assertEqual(caught.exception.winerror, 5)
        self.dll.CloseHandle.assert_not_called()

    def test_close_failure_preserves_native_winerror(self):
        def close(handle):
            ctypes.set_last_error(6)
            return 0

        self.dll.CloseHandle.side_effect = close
        with self.assertRaises(OSError) as caught:
            self.backend.close_handle(2**40 + 13)
        self.assertEqual(caught.exception.winerror, 6)

    def test_load_failure_is_wrapped_by_guard_and_can_retry(self):
        guard = InstanceGuard(Path.cwd() / f".editor-integration-{uuid4().hex}" / "config.json")
        with patch("core.instance_guard.ctypes.WinDLL", side_effect=OSError("DLL denied")):
            with self.assertRaisesRegex(InstanceGuardError, "DLL denied"):
                guard.acquire()
        guard.release()
        with patch("core.instance_guard.ctypes.WinDLL", return_value=self.dll):
            try:
                self.assertTrue(guard.acquire())
            finally:
                guard.release()
        self.dll.CloseHandle.assert_called_once_with(2**40 + 37)


@unittest.skipUnless(os.name == "nt", "native Windows mutex")
class NativeInstanceGuardTests(unittest.TestCase):
    def setUp(self):
        # Somente nomes derivados de fixture UUID; não usa configuração real.
        self.root = Path(__file__).resolve().parents[1] / f".editor-integration-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = self.root / "ação 日本語.json"

    def guard(self, path=None):
        guard = InstanceGuard(self.path if path is None else path)
        self.addCleanup(guard.release)
        return guard

    def test_native_exclusion_duplicate_cleanup_release_and_reacquire(self):
        owner, duplicate = self.guard(), self.guard()
        self.assertTrue(owner.acquire())
        self.assertTrue(owner.acquire())
        self.assertFalse(duplicate.acquire())
        duplicate.release()
        owner.release()
        owner.release()
        self.assertTrue(duplicate.acquire())
        self.assertFalse(owner.acquire())
        duplicate.release()
        self.assertTrue(owner.acquire())
        self.assertFalse(self.path.exists())

    def test_native_unicode_relative_case_aliases_and_different_path(self):
        owner = self.guard()
        self.assertTrue(owner.acquire())
        for alias in (os.path.relpath(self.path), str(self.path).upper(),
                      self.root / "sub" / ".." / self.path.name):
            with self.subTest(alias=alias):
                self.assertFalse(self.guard(alias).acquire())
        self.assertTrue(self.guard(self.root / "other.json").acquire())

    def test_native_release_from_other_thread_needs_no_initial_ownership(self):
        owner = self.guard()
        self.assertTrue(owner.acquire())
        results = Queue()

        def release():
            try:
                owner.release()
                results.put(None)
            except Exception as exc:
                results.put(exc)

        worker = Thread(target=release)
        worker.start()
        worker.join(3)
        self.assertFalse(worker.is_alive())
        self.assertIsNone(results.get(timeout=3))
        self.assertTrue(self.guard().acquire())

    def test_native_other_named_object_collision_is_error_not_duplicate(self):
        name = "Local\\Focus.Gui." + hashlib.sha256(
            os.path.normcase(str(self.path.resolve())).encode("utf-8")
        ).hexdigest()
        dll = ctypes.WinDLL("kernel32", use_last_error=True)
        dll.CreateEventW.argtypes = [ctypes.c_void_p, wintypes.BOOL, wintypes.BOOL, wintypes.LPCWSTR]
        dll.CreateEventW.restype = wintypes.HANDLE
        dll.CloseHandle.argtypes = [wintypes.HANDLE]
        dll.CloseHandle.restype = wintypes.BOOL
        handle = dll.CreateEventW(None, False, False, name)
        self.assertTrue(handle)
        try:
            guard = self.guard()
            with self.assertRaises(InstanceGuardError) as caught:
                guard.acquire()
            self.assertIsInstance(caught.exception.__cause__, OSError)
            self.assertEqual(caught.exception.__cause__.winerror, 6)
            guard.release()
        finally:
            self.assertTrue(dll.CloseHandle(handle))
        self.assertTrue(guard.acquire())


if __name__ == "__main__":
    unittest.main()

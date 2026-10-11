"""Mutex Windows real entre subprocessos exclusivos das fixtures, sem GUI/motor."""

import json
import os
from pathlib import Path
from queue import Empty, Queue
import shutil
import subprocess
import sys
from threading import Thread
import unittest
from uuid import uuid4


_CHILD = """
import json
import os
import sys
from core.instance_guard import InstanceGuard

guard = InstanceGuard(sys.argv[1])

def emit(operation, **fields):
    print(json.dumps(dict(operation=operation, **fields)), flush=True)

try:
    acquired = guard.acquire()
    forbidden = {'tkinter', 'customtkinter', 'pystray', 'psutil', 'core.process_controller'}
    emit('ready', acquired=acquired, unexpected_modules=sorted(forbidden & sys.modules.keys()))
    for line in sys.stdin:
        operation = line.strip()
        if operation == 'acquire':
            emit('acquire', acquired=guard.acquire())
        elif operation == 'release':
            guard.release()
            emit('release')
        elif operation == 'crash':
            os._exit(73)  # Somente este subprocesso de teste; sem release/finally.
        elif operation == 'exit':
            break
        else:
            raise ValueError(operation)
finally:
    guard.release()
"""


class FixtureProcess:
    """Protocolo com timeout; nunca enumera ou encerra processos de terceiros."""

    def __init__(self, path, workspace):
        self.process = subprocess.Popen(
            [sys.executable, "-B", "-u", "-c", _CHILD, str(path)],
            cwd=workspace, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, encoding="utf-8",
        )
        self.lines = Queue()
        self.reader = Thread(target=self._read_lines, name="FixtureMutexOutput", daemon=True)
        self.reader.start()

    def _read_lines(self):
        try:
            for line in self.process.stdout:
                self.lines.put(line)
        finally:
            self.lines.put(None)

    def event(self):
        try:
            line = self.lines.get(timeout=10)
        except Empty as exc:
            raise AssertionError(f"Fixture sem resposta; returncode={self.process.poll()}") from exc
        if line is None:
            self.process.wait(timeout=5)
            raise AssertionError(f"Fixture terminou prematuramente: {self.process.stderr.read()}")
        return json.loads(line)

    def send(self, operation):
        self.process.stdin.write(operation + "\n")
        self.process.stdin.flush()

    def request(self, operation):
        self.send(operation)
        result = self.event()
        if result["operation"] != operation:
            raise AssertionError(f"Resposta inesperada: {result}")
        return result

    def cleanup(self):
        try:
            if self.process.poll() is None:
                try:
                    self.send("exit")
                except (BrokenPipeError, OSError):
                    pass
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Somente o handle Popen criado por esta fixture.
                    self.process.kill()
                    self.process.wait(timeout=5)
            self.reader.join(timeout=5)
            if self.reader.is_alive():
                raise AssertionError("Leitor do subprocesso de teste não terminou")
        finally:
            for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
                stream.close()


@unittest.skipUnless(os.name == "nt", "Integração de mutex exige Windows real")
class InstanceGuardIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.workspace = Path(__file__).resolve().parents[1]
        self.root = self.workspace / f".editor-integration-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = self.root / "config-ação.json"
        self.other_path = self.root / "other-config.json"
        self.original = b"fixture: guard must not parse or rewrite this file"
        self.path.write_bytes(self.original)
        self.other_path.write_bytes(self.original)

    def spawn(self, path):
        child = FixtureProcess(path, self.workspace)
        self.addCleanup(child.cleanup)
        return child

    def ready(self, child):
        event = child.event()
        self.assertEqual(event["operation"], "ready")
        self.assertEqual(event["unexpected_modules"], [])
        return event["acquired"]

    def assert_files_intact(self):
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertEqual(self.other_path.read_bytes(), self.original)
        self.assertEqual(set(self.root.iterdir()), {self.path, self.other_path})

    def test_same_path_excludes_second_process_and_owner_acquire_is_idempotent(self):
        owner = self.spawn(self.path)
        self.assertTrue(self.ready(owner))
        contender = self.spawn(self.path)
        self.assertFalse(self.ready(contender))
        self.assertTrue(owner.request("acquire")["acquired"])
        self.assertFalse(contender.request("acquire")["acquired"])
        self.assertIsNone(owner.process.poll())
        self.assertIsNone(contender.process.poll())
        self.assert_files_intact()

    def test_distinct_path_can_hold_guard_while_first_path_remains_exclusive(self):
        owner = self.spawn(self.path)
        self.assertTrue(self.ready(owner))
        independent = self.spawn(self.other_path)
        self.assertTrue(self.ready(independent))
        first_contender = self.spawn(self.path)
        second_contender = self.spawn(self.other_path)
        self.assertFalse(self.ready(first_contender))
        self.assertFalse(self.ready(second_contender))
        self.assertTrue(owner.request("acquire")["acquired"])
        self.assertTrue(independent.request("acquire")["acquired"])
        self.assert_files_intact()

    def test_release_allows_previous_contender_and_a_later_process_to_acquire(self):
        owner = self.spawn(self.path)
        self.assertTrue(self.ready(owner))
        contender = self.spawn(self.path)
        self.assertFalse(self.ready(contender))
        owner.request("release")
        owner.request("release")  # Nenhum handle duplicado/órfão deve reter o nome.
        self.assertIsNone(owner.process.poll())
        self.assertTrue(contender.request("acquire")["acquired"])
        later = self.spawn(self.path)
        self.assertFalse(self.ready(later))
        contender.request("release")
        self.assertTrue(later.request("acquire")["acquired"])
        self.assertFalse(owner.request("acquire")["acquired"])
        self.assert_files_intact()

    def test_abrupt_exit_without_release_allows_next_process_to_acquire(self):
        owner = self.spawn(self.path)
        self.assertTrue(self.ready(owner))
        denied = self.spawn(self.path)
        self.assertFalse(self.ready(denied))
        owner.send("crash")
        self.assertEqual(owner.process.wait(timeout=5), 73)
        # Contender rejeitado continua vivo; seu handle foi fechado em acquire.
        successor = self.spawn(self.path)
        self.assertTrue(self.ready(successor))
        self.assertFalse(denied.request("acquire")["acquired"])
        successor.request("release")
        self.assertTrue(denied.request("acquire")["acquired"])
        self.assert_files_intact()

    def test_relative_dot_and_case_aliases_compete_for_same_windows_name(self):
        owner = self.spawn(self.path)
        self.assertTrue(self.ready(owner))
        aliases = (
            Path(os.path.relpath(self.path, self.workspace)),
            self.root / "absent" / ".." / self.path.name,
            str(self.path).upper(),
        )
        for alias in aliases:
            with self.subTest(alias=alias):
                contender = self.spawn(alias)
                self.assertFalse(self.ready(contender))
        self.assert_files_intact()

    def test_simultaneous_processes_have_exactly_one_owner_until_release(self):
        children = [self.spawn(self.path) for _ in range(4)]
        results = [self.ready(child) for child in children]
        self.assertEqual(sum(results), 1)
        owner = children[results.index(True)]
        losers = [child for child, acquired in zip(children, results) if not acquired]
        for child in losers:
            self.assertFalse(child.request("acquire")["acquired"])
        owner.request("release")
        self.assertTrue(losers[0].request("acquire")["acquired"])
        for child in losers[1:]:
            self.assertFalse(child.request("acquire")["acquired"])
        self.assert_files_intact()


if __name__ == "__main__":
    unittest.main()

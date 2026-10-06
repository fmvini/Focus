"""Exercita wait_procs instalado com referências falsas, sem processos do SO."""

import unittest

import psutil

from core.proc_blocker import (
    ProcessIdentity, ProcessReference, ProcessSnapshot, PsutilAdapter,
)


class WaitHandle:
    def __init__(self, pid, state):
        self.pid = pid
        self.state = state
        self.timeouts = []

    def is_running(self):
        if self.state == "reused":
            return False
        return True

    def wait(self, timeout):
        self.timeouts.append(timeout)
        if self.state == "denied":
            raise psutil.AccessDenied(self.pid)
        if self.state == "interrupted":
            raise KeyboardInterrupt
        if self.state == "alive":
            raise psutil.TimeoutExpired(timeout, self.pid)
        return 0


def reference(pid, state):
    return ProcessReference(
        ProcessSnapshot(pid, name="synthetic.exe", create_time=100.0),
        WaitHandle(pid, state),
    )


class InstalledWaitIntegrationTests(unittest.TestCase):
    def setUp(self):
        # Não criar contexto nem enumerar o sistema: só a fronteira de espera.
        self.adapter = PsutilAdapter(psutil_module=psutil)

    def test_real_wait_procs_separates_confirmation_alive_and_denied(self):
        exited, alive, denied = (
            reference(901, "exited"), reference(902, "alive"), reference(903, "denied")
        )
        result = self.adapter.wait_many((exited, alive, denied), timeout=0)
        self.assertEqual(result.gone, (exited,))
        self.assertEqual(result.alive, (alive,))
        self.assertEqual(result.unavailable, (denied,))
        for ref in (exited, alive, denied):
            self.assertEqual(ref.process.timeouts, [0])

    def test_reused_pid_confirms_only_the_original_reference(self):
        original = reference(901, "reused")
        result = self.adapter.wait_many((original,), timeout=0)
        self.assertEqual(result.gone, (original,))
        self.assertEqual(result.gone[0].snapshot.identity, ProcessIdentity(901, 100.0))
        self.assertEqual(original.process.timeouts, [])

    def test_interrupt_propagates_through_real_wait_procs(self):
        with self.assertRaises(KeyboardInterrupt):
            self.adapter.wait_many((reference(901, "interrupted"),), timeout=0)

    def test_empty_batch_has_no_handles_or_waits(self):
        result = self.adapter.wait_many((), timeout=0)
        self.assertEqual((result.gone, result.alive, result.unavailable), ((), (), ()))


if __name__ == "__main__":
    unittest.main()

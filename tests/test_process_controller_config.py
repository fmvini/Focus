"""Controlador com JSON real e bloqueadores fake; nenhum processo é encerrado."""

from datetime import datetime
import json
from pathlib import Path
from queue import Queue
import shutil
import unittest
from uuid import uuid4

from core.config import load_config
from core.config_repository import ConfigConflictError
from core.config_session import ConfigSession
from core.proc_blocker import ScanReport
from core.process_controller import ProcessController


class StepWaiter:
    """Cada token autoriza um próximo ciclo; filas sincronizam sem sleeps."""

    def __init__(self):
        self.entered = Queue()
        self.tokens = Queue()
        self.time = 0.0

    def __call__(self, stop_event, timeout):
        self.entered.put(timeout)
        self.tokens.get(timeout=5)
        self.time += timeout
        return stop_event.is_set()

    def next_cycle(self):
        self.tokens.put(None)

    def await_cycle(self):
        # O worker publica o snapshot do scan antes de chegar à espera.
        return self.entered.get(timeout=5)


class RecordingBlocker:
    def __init__(self):
        self.scans = []

    def scan(self, config, may_act):
        self.scans.append((config, may_act, may_act()))
        return ScanReport((), ())


class ProcessControllerConfigTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / f".editor-integration-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = self.root / "config.json"
        self.now = datetime(2026, 10, 12, 12)  # Segunda, dentro da janela original.
        self.original_data = self.config_data("original.exe", "11:00", "13:00")
        self.write_json(self.path, self.original_data)
        self.original_bytes = self.path.read_bytes()
        self.original = load_config(self.path)
        self.controllers = []
        self.addCleanup(self.cleanup_controllers)

    @staticmethod
    def config_data(executable, start, end):
        return {
            "windows": [{"start": start, "end": end, "days": [0]}],
            "block_exes": [executable],
            "block_cmdline": [{"executable": "javaw.exe", "contains": " literal.* ação "}],
            "future": {"ação": [True, None, "日本語"]},
        }

    @staticmethod
    def write_json(path, data):
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

    def new_controller(self):
        waiter = StepWaiter()
        blockers = []

        def factory():
            blocker = RecordingBlocker()
            blockers.append(blocker)
            return blocker

        # loader não é injetado: toda validação/leitura passa pelo JSON real.
        controller = ProcessController(
            self.path, blocker_factory=factory, clock=lambda: self.now,
            interval=5.0, monotonic=lambda: waiter.time, waiter=waiter,
        )
        self.controllers.append((controller, waiter))
        return controller, waiter, blockers

    def cleanup_controllers(self):
        for controller, waiter in self.controllers:
            controller.stop()
            waiter.next_cycle()
            controller.wait(timeout=5)
            self.assertFalse(controller.is_alive(), "Worker fake deve terminar antes de limpar o JSON")

    def start_first_cycle(self):
        controller, waiter, blockers = self.new_controller()
        self.assertTrue(controller.start())
        waiter.await_cycle()
        self.assertEqual(len(blockers), 1)
        return controller, waiter, blockers

    def test_first_scan_loads_persisted_config_without_touching_json(self):
        controller, _, blockers = self.start_first_cycle()
        config, gate, allowed = blockers[0].scans[0]
        self.assertEqual(config, self.original)
        self.assertEqual(config.extra, {"future": self.original_data["future"]})
        self.assertEqual(config.block_cmdline[0].contains, " literal.* ação ")
        self.assertTrue(allowed)
        self.assertTrue(gate())
        self.assertEqual(controller.snapshot().state, "running")
        self.assertTrue(controller.snapshot().active)
        self.assertEqual(self.path.read_bytes(), self.original_bytes)

    def test_valid_external_edit_reloads_rules_and_schedule_for_next_scan_and_gate(self):
        controller, waiter, blockers = self.start_first_cycle()
        replacement = self.config_data("external.exe", "20:00", "21:00")
        replacement["block_exes"] = ["external.exe", "external.exe"]
        self.write_json(self.path, replacement)
        expected = load_config(self.path)
        external_bytes = self.path.read_bytes()
        waiter.next_cycle()
        waiter.await_cycle()
        self.assertEqual(len(blockers[0].scans), 2)
        config, gate, allowed = blockers[0].scans[-1]
        self.assertEqual(config, expected)
        self.assertNotEqual(config, self.original)
        self.assertFalse(allowed)
        self.assertFalse(gate())  # A janela antiga era ativa neste mesmo relógio.
        self.assertFalse(controller.snapshot().active)
        self.assertEqual(self.path.read_bytes(), external_bytes)

    def test_invalid_external_edit_stops_reload_without_scanning_old_config_or_open_gate(self):
        for contents in (
            b"{", b"\xff", b'{"windows":[],"windows":[]}',
            b'{"windows":[{"start":"11:00","end":"11:00"}]}',
            b'{"windows":[],"block_cmdline":["legacy"]}',
        ):
            with self.subTest(contents=contents):
                self.path.write_bytes(self.original_bytes)
                controller, waiter, blockers = self.start_first_cycle()
                previous_gate = blockers[0].scans[0][1]
                self.assertTrue(previous_gate())
                self.path.write_bytes(contents)
                waiter.next_cycle()
                controller.wait(timeout=5)
                self.assertFalse(controller.is_alive())
                state = controller.snapshot()
                self.assertEqual(state.state, "error")
                self.assertIsNotNone(state.error)
                self.assertTrue(state.active)  # Última agenda observada, não o gate de efeitos.
                self.assertEqual(len(blockers[0].scans), 1)
                self.assertFalse(previous_gate())
                self.assertEqual(self.path.read_bytes(), contents)

    def test_removed_file_stops_without_recreation_or_scan_with_old_config(self):
        controller, waiter, blockers = self.start_first_cycle()
        previous_gate = blockers[0].scans[0][1]
        self.path.unlink()
        waiter.next_cycle()
        controller.wait(timeout=5)
        self.assertFalse(controller.is_alive())
        self.assertEqual(controller.snapshot().state, "error")
        self.assertIsNotNone(controller.snapshot().error)
        self.assertTrue(controller.snapshot().active)
        self.assertFalse(previous_gate())
        self.assertEqual(len(blockers[0].scans), 1)
        self.assertFalse(self.path.exists())

    def test_invalid_initial_json_never_scans_or_creates_a_valid_replacement(self):
        contents = b'{"windows":[],"block_exes":["not executable"]}'
        self.path.write_bytes(contents)
        controller, _, blockers = self.new_controller()
        self.assertTrue(controller.start())
        controller.wait(timeout=5)
        self.assertFalse(controller.is_alive())
        self.assertEqual(controller.snapshot().state, "error")
        self.assertIsNotNone(controller.snapshot().error)
        self.assertIsNone(controller.snapshot().active)
        self.assertEqual(sum(len(blocker.scans) for blocker in blockers), 0)
        self.assertEqual(self.path.read_bytes(), contents)

    def test_imported_draft_changes_engine_only_after_successful_save(self):
        session = ConfigSession(self.path)
        baseline = session.snapshot
        imported_path = self.root / "importação.json"
        imported_data = self.config_data("imported.exe", "20:00", "21:00")
        self.write_json(imported_path, imported_data)
        imported = load_config(imported_path)
        imported_bytes = imported_path.read_bytes()
        controller, waiter, blockers = self.start_first_cycle()
        session.import_config(imported_path)
        self.assertTrue(session.dirty)
        self.assertIs(session.snapshot, baseline)
        self.assertEqual(self.path.read_bytes(), self.original_bytes)
        waiter.next_cycle()
        waiter.await_cycle()
        self.assertEqual(blockers[0].scans[-1][0], self.original)
        self.assertTrue(blockers[0].scans[-1][2])
        self.assertTrue(controller.snapshot().active)
        session.save()
        self.assertFalse(session.dirty)
        waiter.next_cycle()
        waiter.await_cycle()
        self.assertEqual(len(blockers[0].scans), 3)
        config, gate, allowed = blockers[0].scans[-1]
        self.assertEqual(config, imported)
        self.assertFalse(allowed)
        self.assertFalse(gate())
        self.assertFalse(controller.snapshot().active)
        self.assertEqual(imported_path.read_bytes(), imported_bytes)
        self.assertEqual(load_config(self.path), imported)

    def test_save_conflict_preserves_external_json_and_engine_uses_external_not_draft_or_baseline(self):
        session = ConfigSession(self.path)
        baseline = session.snapshot
        imported_path = self.root / "importação.json"
        self.write_json(imported_path, self.config_data("draft.exe", "10:00", "14:00"))
        session.import_config(imported_path)
        draft = session.draft
        controller, waiter, blockers = self.start_first_cycle()
        external = self.config_data("external.exe", "20:00", "21:00")
        self.write_json(self.path, external)
        external_bytes = self.path.read_bytes()
        with self.assertRaises(ConfigConflictError):
            session.save()
        self.assertIs(session.snapshot, baseline)
        self.assertIs(session.draft, draft)
        self.assertTrue(session.dirty)
        self.assertEqual(self.path.read_bytes(), external_bytes)
        waiter.next_cycle()
        waiter.await_cycle()
        config, gate, allowed = blockers[0].scans[-1]
        self.assertEqual(config, load_config(self.path))
        self.assertNotEqual(config, baseline.config)
        self.assertNotEqual(config, draft.config)
        self.assertFalse(allowed)
        self.assertFalse(gate())
        self.assertFalse(controller.snapshot().active)
        self.assertEqual(self.path.read_bytes(), external_bytes)

    def test_save_conflict_against_invalid_json_closes_old_gate_without_restoring_baseline(self):
        session = ConfigSession(self.path)
        session.draft.add_rule("block_exes", "draft.exe")
        controller, waiter, blockers = self.start_first_cycle()
        previous_gate = blockers[0].scans[-1][1]
        invalid = b'{"windows":broken}'
        self.path.write_bytes(invalid)
        with self.assertRaises(ConfigConflictError):
            session.save()
        waiter.next_cycle()
        controller.wait(timeout=5)
        self.assertFalse(controller.is_alive())
        self.assertEqual(controller.snapshot().state, "error")
        self.assertTrue(controller.snapshot().active)
        self.assertFalse(previous_gate())
        self.assertEqual(len(blockers[0].scans), 1)
        self.assertTrue(session.dirty)
        self.assertEqual(self.path.read_bytes(), invalid)

    def test_retry_after_repair_loads_new_json_and_keeps_previous_gate_closed(self):
        controller, waiter, blockers = self.start_first_cycle()
        previous_gate = blockers[0].scans[0][1]
        self.path.write_bytes(b"invalid")
        waiter.next_cycle()
        controller.wait(timeout=5)
        self.assertFalse(controller.is_alive())
        self.assertFalse(previous_gate())
        repaired = self.config_data("repaired.exe", "20:00", "21:00")
        self.write_json(self.path, repaired)
        self.assertTrue(controller.start())
        waiter.await_cycle()
        self.assertEqual(len(blockers), 2)
        config, new_gate, allowed = blockers[1].scans[0]
        self.assertEqual(config, load_config(self.path))
        self.assertFalse(allowed)
        self.assertFalse(new_gate())
        self.assertFalse(previous_gate())
        self.assertEqual(controller.snapshot().state, "running")
        self.assertFalse(controller.snapshot().active)
        self.assertIsNone(controller.snapshot().error)


if __name__ == "__main__":
    unittest.main()

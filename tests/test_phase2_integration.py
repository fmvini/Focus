"""JSON, agenda, CLI e bloqueador real integrados com fronteira de SO falsa."""

from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime
import io
import json
import ntpath
from pathlib import Path
import shutil
import unittest
from unittest.mock import Mock, patch
from uuid import uuid4

import main
from core.config import load_config
from core.proc_blocker import (
    ProcessAdapter, ProcessBlocker, ProcessReference, ProcessSnapshot,
    ProtectionContext, WaitResult,
)


class Phase2IntegrationTests(unittest.TestCase):
    def test_pending_exit_is_confirmed_after_window_end_without_applying_reloaded_rule(self):
        root = Path(__file__).resolve().parents[1] / f".phase2-integration-{uuid4().hex}"
        root.mkdir()
        self.addCleanup(shutil.rmtree, root)
        path = root / "config.json"
        source = {
            "windows": [{"start": "09:00", "end": "10:00", "days": [0]}],
            "block_cmdline": [{"executable": "JAVAW.EXE", "contains": ".minecraft"}],
            "future": {"preserve": True},
        }
        path.write_text(json.dumps(source), encoding="utf-8")
        targets = (
            ProcessSnapshot(101, "javaw.exe", 100.0, r"C:\Games\javaw.exe",
                            (r"--folder=C:\Data\.MINECRAFT",), "PC\\Student"),
            ProcessSnapshot(102, "Code.exe", 110.0, r"C:\Games\Code.exe",
                            (".minecraft",), "PC\\Student"),
            ProcessSnapshot(103, "newgame.exe", 120.0, r"C:\Games\newgame.exe",
                            (), "PC\\Student"),
        )
        adapter = Mock(spec=ProcessAdapter)
        adapter.protection_context.return_value = ProtectionContext(999, frozenset(), r"C:\Windows")
        adapter.iter_snapshots.return_value = targets
        adapter.resolve_path.side_effect = ntpath.normpath
        by_pid = {snapshot.pid: snapshot for snapshot in targets}
        adapter.inspect_fresh.side_effect = lambda pid: ProcessReference(by_pid[pid], object())
        wait_number = 0

        def wait(references, timeout):
            nonlocal wait_number
            wait_number += 1
            # Primeira varredura: termine+kill aceitos, saída ainda pendente.
            # Segunda: confirmar a referência anterior, mesmo fora da janela.
            return WaitResult(**{"alive" if wait_number <= 2 else "gone": references})

        adapter.wait_many.side_effect = wait
        blocker = ProcessBlocker(adapter)
        now = datetime(2026, 10, 5, 9, 59, 59)
        sleeps = 0

        def advance(_seconds):
            nonlocal now, sleeps
            sleeps += 1
            if sleeps > 1:
                raise KeyboardInterrupt
            now = datetime(2026, 10, 5, 10, 0)
            source["block_exes"] = ["newgame.exe", "Code.exe"]
            path.write_text(json.dumps(source), encoding="utf-8")

        out, err = io.StringIO(), io.StringIO()
        with patch.object(main, "_create_process_blocker", return_value=blocker), \
             patch.object(main, "datetime", wraps=datetime) as clock, \
             patch.object(main.time, "monotonic", return_value=0), \
             patch.object(main.time, "sleep", side_effect=advance), \
             redirect_stdout(out), redirect_stderr(err):
            clock.now.side_effect = lambda: now
            self.assertEqual(main.main(["--config", str(path), "--watch", "--apply-processes"]), 0)

        self.assertEqual(err.getvalue(), "")
        self.assertEqual(adapter.iter_snapshots.call_count, 1)
        self.assertEqual(adapter.terminate.call_count, 1)
        self.assertEqual(adapter.kill.call_count, 1)
        self.assertEqual(adapter.terminate.call_args.args[0].snapshot.pid, 101)
        self.assertEqual(adapter.kill.call_args.args[0].snapshot.pid, 101)
        self.assertIn("0 encerramentos confirmados; 1 pendentes", out.getvalue())
        self.assertIn("1 encerramentos confirmados; 0 pendentes", out.getvalue())
        self.assertIn("somente reconciliação", out.getvalue())
        self.assertEqual(load_config(path).block_exes, ("newgame.exe", "Code.exe"))
        self.assertEqual(load_config(path).extra, {"future": {"preserve": True}})
        self.assertEqual(set(root.iterdir()), {path})


if __name__ == "__main__":
    unittest.main()

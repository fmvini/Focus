"""Caixa da bandeja com concorrência real, sem Tk, ícone ou motor."""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import FrozenInstanceError
from pathlib import Path
import subprocess
import sys
from threading import Barrier, Event
import unittest

from ui.tray_commands import TrayCommand, TrayMailbox


class TrayMailboxTests(unittest.TestCase):
    ACTIONS = ("show", "stop", "close", "ready", "error")

    def test_command_is_frozen_with_optional_detail(self):
        command = TrayCommand("show")
        self.assertIsNone(command.detail)
        for field, value in (("action", "stop"), ("detail", "ação")):
            with self.subTest(field=field), self.assertRaises(FrozenInstanceError):
                setattr(command, field, value)

    def test_initial_drain_is_empty_tuple(self):
        mailbox = TrayMailbox()
        self.assertEqual(mailbox.drain(), ())
        self.assertIsInstance(mailbox.drain(), tuple)

    def test_all_actions_preserve_first_order_and_drain_empties_mailbox(self):
        mailbox = TrayMailbox()
        for action in self.ACTIONS:
            self.assertIsNone(mailbox.post(action, f"ação {action} 日本語"))
        self.assertEqual(mailbox.drain(), tuple(TrayCommand(action, f"ação {action} 日本語") for action in self.ACTIONS))
        self.assertEqual(mailbox.drain(), ())

    def test_coalescing_preserves_first_position_and_only_latest_detail(self):
        mailbox = TrayMailbox()
        mailbox.post("error", "primeiro")
        mailbox.post("show")
        mailbox.post("error", "último 🎮")
        mailbox.post("ready", "pronto")
        mailbox.post("show", "restaurar")
        self.assertEqual(mailbox.drain(), (
            TrayCommand("error", "último 🎮"), TrayCommand("show", "restaurar"), TrayCommand("ready", "pronto"),
        ))

    def test_none_replaces_previous_detail_and_drain_starts_new_order(self):
        mailbox = TrayMailbox()
        mailbox.post("error", "antigo")
        mailbox.post("error")
        mailbox.post("show")
        previous = mailbox.drain()
        self.assertEqual(previous, (TrayCommand("error"), TrayCommand("show")))
        mailbox.post("show", "novo")
        mailbox.post("error", "nova falha")
        self.assertEqual(mailbox.drain(), (TrayCommand("show", "novo"), TrayCommand("error", "nova falha")))
        self.assertEqual(previous, (TrayCommand("error"), TrayCommand("show")))

    def test_unknown_actions_raise_value_error_without_affecting_queue(self):
        mailbox = TrayMailbox()
        mailbox.post("show", "preservado")
        for action in ("start", "SHOW", "", None, 1, [], {}):
            with self.subTest(action=action), self.assertRaises(ValueError):
                mailbox.post(action)
        self.assertEqual(mailbox.drain(), (TrayCommand("show", "preservado"),))

    def test_close_is_idempotent_discards_queue_and_ignores_future_posts(self):
        mailbox = TrayMailbox()
        for action in self.ACTIONS:
            mailbox.post(action, "pendente")
        self.assertIsNone(mailbox.close())
        self.assertIsNone(mailbox.close())
        self.assertEqual(mailbox.drain(), ())
        for action in (*self.ACTIONS, "desconhecida", None):
            self.assertIsNone(mailbox.post(action, "tardio"))
        self.assertEqual(mailbox.drain(), ())

    def test_close_menu_command_does_not_close_the_mailbox_itself(self):
        mailbox = TrayMailbox()
        mailbox.post("close")
        self.assertEqual(mailbox.drain(), (TrayCommand("close"),))
        mailbox.post("show")  # Cancelar Sair na GUI ainda pode usar a caixa.
        self.assertEqual(mailbox.drain(), (TrayCommand("show"),))

    def test_concurrent_producers_coalesce_to_five_latest_commands(self):
        mailbox = TrayMailbox()
        barrier = Barrier(len(self.ACTIONS))

        def producer(action):
            barrier.wait(timeout=5)
            for index in range(1000):
                mailbox.post(action, f"{action}:{index}")

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(producer, action) for action in self.ACTIONS]
            for future in futures:
                future.result(timeout=10)
        result = mailbox.drain()
        self.assertEqual(len(result), 5)
        self.assertEqual({command.action for command in result}, set(self.ACTIONS))
        self.assertEqual({command.detail for command in result}, {f"{action}:999" for action in self.ACTIONS})
        self.assertEqual(mailbox.drain(), ())

    def test_concurrent_drains_deliver_each_pending_command_once(self):
        mailbox = TrayMailbox()
        for action in self.ACTIONS:
            mailbox.post(action)
        barrier = Barrier(8)

        def consumer():
            barrier.wait(timeout=5)
            return mailbox.drain()

        with ThreadPoolExecutor(max_workers=8) as pool:
            futures = [pool.submit(consumer) for _ in range(8)]
            batches = [future.result(timeout=10) for future in futures]
        self.assertEqual(sum(bool(batch) for batch in batches), 1)
        self.assertEqual(tuple(command for batch in batches for command in batch), tuple(TrayCommand(action) for action in self.ACTIONS))

    def test_producer_and_drainer_race_keeps_bound_uniqueness_and_latest_final_posts(self):
        mailbox = TrayMailbox()
        barrier = Barrier(2)
        finished = Event()

        def producer():
            barrier.wait(timeout=5)
            try:
                for index in range(1000):
                    for action in self.ACTIONS:
                        mailbox.post(action, str(index))
            finally:
                finished.set()

        def consumer():
            barrier.wait(timeout=5)
            batches = []
            while not finished.is_set():
                batch = mailbox.drain()
                if batch:
                    batches.append(batch)
            batches.append(mailbox.drain())
            return batches

        with ThreadPoolExecutor(max_workers=2) as pool:
            posts = pool.submit(producer)
            drains = pool.submit(consumer)
            posts.result(timeout=10)
            batches = drains.result(timeout=10)
        for batch in batches:
            self.assertLessEqual(len(batch), 5)
            self.assertEqual(len({command.action for command in batch}), len(batch))
        latest = {command.action: command.detail for batch in batches for command in batch}
        self.assertEqual(latest, {action: "999" for action in self.ACTIONS})

    def test_close_races_with_posts_and_drains_and_permanently_discards_late_callbacks(self):
        mailbox = TrayMailbox()
        barrier = Barrier(3)
        closed = Event()

        def producer():
            barrier.wait(timeout=5)
            for index in range(1000):
                mailbox.post(self.ACTIONS[index % 5], str(index))
            self.assertTrue(closed.wait(timeout=5))
            for action in self.ACTIONS:
                mailbox.post(action, "após close")

        def closer():
            barrier.wait(timeout=5)
            mailbox.close()
            closed.set()

        def consumer():
            barrier.wait(timeout=5)
            for _ in range(100):
                result = mailbox.drain()
                self.assertLessEqual(len(result), 5)
                self.assertEqual(len({command.action for command in result}), len(result))

        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = [pool.submit(function) for function in (producer, closer, consumer)]
            for future in futures:
                future.result(timeout=10)
        self.assertEqual(mailbox.drain(), ())
        mailbox.post("show", "callback depois dos workers")
        self.assertEqual(mailbox.drain(), ())

    def test_module_import_does_not_import_gui_tray_or_controller(self):
        result = subprocess.run(
            [sys.executable, "-B", "-c", "import sys; import ui.tray_commands; "
             "assert not {'tkinter','customtkinter','pystray','psutil','core.process_controller'} & sys.modules.keys()"],
            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

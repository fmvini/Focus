"""Threads da bandeja com fronteiras determinísticas; nenhum motor de processos."""

import builtins
import importlib.util
from pathlib import Path
import sys
from threading import Event, Thread, get_ident
import unittest
from unittest.mock import Mock, patch

from ui.tray_commands import TrayMailbox
from ui.windows_tray import WindowsTray, _create_icon


class IconDouble:
    def __init__(self):
        self.visible_value = False
        self.entered = Event()
        self.setup_allowed = Event()
        self.setup_allowed.set()
        self.show_entered = Event()
        self.show_allowed = Event()
        self.show_allowed.set()
        self.stop_entered = Event()
        self.stop_allowed = Event()
        self.stop_allowed.set()
        self.exit = Event()
        self.run_error = None
        self.return_unexpectedly = False
        self.refuse_visible = False
        self.setup_thread = None
        self.stop_thread_id = None

    @property
    def visible(self):
        return self.visible_value

    @visible.setter
    def visible(self, value):
        if value:
            self.show_entered.set()
            if not self.show_allowed.wait(3):
                raise RuntimeError("timeout de fixture")
        self.visible_value = value and not self.refuse_visible

    def run(self, setup):
        self.entered.set()
        if self.run_error:
            raise self.run_error
        if not self.setup_allowed.wait(3):
            raise RuntimeError("timeout de fixture")
        self.setup_thread = Thread(target=setup, args=(self,), daemon=False)
        self.setup_thread.start()
        if not self.return_unexpectedly and not self.exit.wait(3):
            raise RuntimeError("timeout de fixture")

    def stop(self):
        self.stop_thread_id = get_ident()
        self.stop_entered.set()
        if not self.stop_allowed.wait(3):
            raise RuntimeError("timeout de fixture")
        self.exit.set()

    def finish_setup(self):
        if self.setup_thread is not None:
            self.setup_thread.join(3)


class RecordingMailbox(TrayMailbox):
    def __init__(self):
        super().__init__()
        self.notification = Event()

    def post(self, action, detail=None):
        super().post(action, detail)
        if action in ("ready", "error"):
            self.notification.set()


class WindowsTrayTests(unittest.TestCase):
    def setUp(self):
        self.mailbox = RecordingMailbox()
        self.icon = IconDouble()
        self.callbacks = None

        def factory(callbacks):
            self.callbacks = callbacks
            return self.icon

        self.factory = Mock(side_effect=factory)
        self.tray = WindowsTray(self.mailbox, icon_factory=self.factory)
        self.addCleanup(self.cleanup_tray)

    def cleanup_tray(self):
        self.tray.stop()
        self.icon.setup_allowed.set()
        self.icon.show_allowed.set()
        self.icon.stop_allowed.set()
        self.tray.wait(4)
        self.assertFalse(self.tray.is_alive())
        if self.icon.setup_thread is not None:
            self.assertFalse(self.icon.setup_thread.is_alive())

    def test_construction_and_idle_stop_do_not_import_or_create_workers(self):
        importer = builtins.__import__

        def guarded(name, *args, **kwargs):
            if name.startswith(("pystray", "PIL", "tkinter", "customtkinter", "psutil")):
                raise AssertionError(name)
            return importer(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=guarded):
            path = Path(__file__).resolve().parents[1] / "ui/windows_tray.py"
            spec = importlib.util.spec_from_file_location("_lazy_tray_test", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            with patch.object(module, "Thread", side_effect=AssertionError("thread")):
                tray = module.WindowsTray(self.mailbox)
                tray.stop()
                tray.wait()
                self.assertFalse(tray.is_alive())
        self.factory.assert_not_called()

    def test_ready_after_visible_callbacks_only_post_and_stop_runs_off_caller(self):
        self.tray.start()
        self.assertTrue(self.mailbox.notification.wait(2))
        self.assertTrue(self.icon.visible)
        self.assertEqual([c.action for c in self.mailbox.drain()], ["ready"])
        self.assertTrue(self.tray.is_alive())
        self.tray.start()
        self.factory.assert_called_once()
        for action in ("show", "stop", "close"):
            callback = self.callbacks[action]
            callback(self.icon, None)
            self.assertEqual([c.action for c in self.mailbox.drain()], [action])
        self.assertFalse(self.icon.stop_entered.is_set())
        self.tray.stop()
        self.tray.wait(2)
        self.assertFalse(self.tray.is_alive())
        self.assertFalse(self.icon.visible)
        self.assertNotEqual(self.icon.stop_thread_id, get_ident())
        for action in ("show", "stop", "close"):
            self.callbacks[action](None, None)
        self.callbacks["error"]("erro tardio depois de stop")
        self.assertEqual(self.mailbox.drain(), ())

    def test_stop_during_factory_skips_run_and_ready(self):
        entered, release = Event(), Event()

        def factory(callbacks):
            entered.set()
            self.assertTrue(release.wait(3))
            return self.icon

        self.factory.side_effect = factory
        self.addCleanup(release.set)
        self.tray.start()
        self.assertTrue(entered.wait(2))
        self.tray.stop()
        self.assertTrue(self.tray.is_alive())
        release.set()
        self.tray.wait(2)
        self.assertFalse(self.icon.entered.is_set())
        self.assertFalse(self.icon.visible)
        self.assertEqual(self.mailbox.drain(), ())

    def test_stop_before_delayed_setup_prevents_icon_and_ready(self):
        self.icon.setup_allowed.clear()
        self.tray.start()
        self.assertTrue(self.icon.entered.wait(2))
        self.tray.stop()
        self.icon.setup_allowed.set()
        self.tray.wait(2)
        self.assertFalse(self.tray.is_alive())
        self.assertFalse(self.icon.show_entered.is_set())
        self.assertEqual(self.mailbox.drain(), ())

    def test_stop_during_visibility_is_nonblocking_and_prevents_late_ready(self):
        self.icon.show_allowed.clear()
        self.tray.start()
        self.assertTrue(self.icon.show_entered.wait(2))
        self.tray.stop()
        self.assertTrue(self.tray.is_alive())
        self.icon.show_allowed.set()
        self.tray.wait(2)
        self.assertFalse(self.icon.visible)
        self.assertFalse(self.tray.is_alive())
        self.assertEqual(self.mailbox.drain(), ())

    def test_stop_does_not_wait_for_blocked_icon_stop_and_is_alive_covers_setup(self):
        self.icon.stop_allowed.clear()
        self.tray.start()
        self.assertTrue(self.mailbox.notification.wait(2))
        self.tray.stop()
        self.assertTrue(self.icon.stop_entered.wait(2))
        self.tray.wait(0.01)
        self.assertTrue(self.tray.is_alive())
        self.icon.stop_allowed.set()
        self.tray.wait(2)
        self.assertFalse(self.tray.is_alive())

    def test_factory_run_and_visibility_failure_publish_error_and_end_threads(self):
        for failure in ("factory", "run", "visible"):
            with self.subTest(failure=failure):
                icon = IconDouble()
                if failure == "run":
                    icon.run_error = RuntimeError("run falhou")
                if failure == "visible":
                    icon.refuse_visible = True
                factory = (Mock(side_effect=RuntimeError("factory falhou")) if failure == "factory"
                           else Mock(return_value=icon))
                mailbox = RecordingMailbox()
                tray = WindowsTray(mailbox, icon_factory=factory)
                tray.start()
                self.assertTrue(mailbox.notification.wait(2))
                tray.wait(2)
                self.assertFalse(tray.is_alive())
                commands = mailbox.drain()
                self.assertTrue(any(c.action == "error" for c in commands))
                self.assertFalse(any(c.action == "ready" for c in commands))
                if icon.setup_thread:
                    self.assertFalse(icon.setup_thread.is_alive())

    def test_thread_construction_and_start_failure_are_reported_and_retry_is_possible(self):
        for thread in (Mock(side_effect=RuntimeError("Thread falhou")),
                       Mock(return_value=Mock(start=Mock(side_effect=RuntimeError("start falhou"))))):
            with patch("ui.windows_tray.Thread", thread):
                self.tray.start()
            self.assertFalse(self.tray.is_alive())
            self.assertEqual(self.mailbox.drain()[0].action, "error")
        self.tray.start()
        self.assertTrue(self.mailbox.notification.wait(2))

    def test_unexpected_return_reports_error_and_joins_setup(self):
        self.icon.return_unexpectedly = True
        self.tray.start()
        self.tray.wait(2)
        self.assertFalse(self.tray.is_alive())
        self.assertFalse(self.icon.setup_thread.is_alive())
        self.assertTrue(any(c.action == "error" and "inesperadamente" in c.detail
                            for c in self.mailbox.drain()))

    def test_closed_mailbox_discards_all_callbacks(self):
        self.tray.start()
        self.assertTrue(self.mailbox.notification.wait(2))
        self.mailbox.close()
        for action in ("show", "stop", "close"):
            self.callbacks[action](None, None)
        self.callbacks["error"]("erro depois de mailbox.close")
        self.tray.stop()
        self.tray.wait(2)
        self.assertEqual(self.mailbox.drain(), ())


@unittest.skipUnless(sys.platform == "win32" and importlib.util.find_spec("pystray")
                     and importlib.util.find_spec("PIL"), "Dependências da bandeja Windows ausentes")
class NativeTrayAdapterTests(unittest.TestCase):
    def test_native_add_result_controls_ready_and_delete_false_is_not_fatal(self):
        import ctypes
        import pystray
        from pystray._util import win32

        for accepted in (False, True):
            with self.subTest(accepted=accepted):
                exited = Event()
                icons, messages = [], []

                def run(icon):
                    icon._hwnd = 1234
                    icon._mark_ready()
                    if not exited.wait(3):
                        raise RuntimeError("timeout do loop fake")
                    icon._running = False

                def notify(code, data):
                    messages.append((code, data))
                    return accepted if code == win32.NIM_ADD else False

                def factory(callbacks):
                    icon = _create_icon(callbacks)
                    icons.append(icon)
                    return icon

                mailbox = RecordingMailbox()
                tray = WindowsTray(mailbox, icon_factory=factory)
                with patch.object(pystray.Icon, "_register_class", return_value=1), \
                        patch.object(pystray.Icon, "_assert_icon_handle"), \
                        patch.object(pystray.Icon, "_update_menu"), \
                        patch.object(pystray.Icon, "_run", run), \
                        patch.object(pystray.Icon, "_stop", side_effect=exited.set), \
                        patch.object(win32, "Shell_NotifyIcon", side_effect=notify):
                    try:
                        tray.start()
                        self.assertTrue(mailbox.notification.wait(2))
                        commands = mailbox.drain()
                        if accepted:
                            self.assertEqual([c.action for c in commands], ["ready"])
                            self.assertTrue(icons[0].visible)
                            with patch.object(win32, "Shell_NotifyIcon", return_value=False):
                                with self.assertRaisesRegex(RuntimeError, "NIM_ADD"):
                                    icons[0]._on_taskbarcreated(0, 0)
                            self.assertTrue(tray.is_alive())
                            late = mailbox.drain()
                            self.assertEqual([c.action for c in late], ["error"])
                            self.assertIn("NIM_ADD", late[0].detail)
                        else:
                            self.assertEqual([c.action for c in commands], ["error"])
                            self.assertIn("NIM_ADD", commands[0].detail)
                            self.assertFalse(icons[0].visible)
                    finally:
                        tray.stop()
                        tray.wait(3)
                    self.assertFalse(tray.is_alive())
                    self.assertFalse(icons[0]._setup_thread.is_alive())
                    self.assertEqual(mailbox.drain(), ())
                add = next(data for code, data in messages if code == win32.NIM_ADD)
                self.assertEqual(add.cbSize, ctypes.sizeof(win32.NOTIFYICONDATAW))
                self.assertEqual(add.hWnd, 1234)
                self.assertEqual(add.hID, id(icons[0]))
                # O campo nativo uID permanece igual ao original da versão.
                self.assertEqual(add.uID, 0)
                self.assertEqual(add.uCallbackMessage, win32.WM_NOTIFY)
                if accepted:
                    self.assertTrue(any(code == win32.NIM_DELETE for code, _ in messages))

    def test_default_adapter_failure_before_mark_ready_joins_internal_setup(self):
        import pystray

        icons = []

        def factory(callbacks):
            icon = _create_icon(callbacks)
            icons.append(icon)
            return icon

        mailbox = RecordingMailbox()
        tray = WindowsTray(mailbox, icon_factory=factory)
        with patch.object(pystray.Icon, "_run", side_effect=RuntimeError("native run antes de ready")):
            tray.start()
            tray.wait(2)
        self.assertFalse(tray.is_alive())
        self.assertFalse(icons[0]._setup_thread.is_alive())
        self.assertEqual([c.action for c in mailbox.drain()], ["error"])
        self.assertEqual(icons[0].icon.size, (32, 32))
        self.assertEqual([(item.text, item.default) for item in icons[0].menu.items],
                         [("Mostrar Focus", True), ("Parar motor", False), ("Sair", False)])

    def test_default_adapter_setup_thread_construction_and_start_failure(self):
        for thread in (Mock(side_effect=RuntimeError("setup Thread falhou")),
                       Mock(return_value=Mock(ident=None, start=Mock(side_effect=RuntimeError("setup start falhou"))))):
            with self.subTest(thread=thread):
                def factory(callbacks):
                    icon = _create_icon(callbacks)
                    original_run = icon.run

                    def run(setup):
                        with patch("ui.windows_tray.Thread", thread):
                            original_run(setup)

                    icon.run = run
                    return icon

                mailbox = RecordingMailbox()
                tray = WindowsTray(mailbox, icon_factory=factory)
                tray.start()
                tray.wait(2)
                self.assertFalse(tray.is_alive())
                self.assertEqual([c.action for c in mailbox.drain()], ["error"])

    def test_default_windows_icon_ready_and_stop_without_menu_or_motor(self):
        mailbox = RecordingMailbox()
        tray = WindowsTray(mailbox)

        def cleanup():
            tray.stop()
            tray.wait(5)
            self.assertFalse(tray.is_alive())

        self.addCleanup(cleanup)
        tray.start()
        self.assertTrue(mailbox.notification.wait(5), "A bandeja não respondeu ao startup")
        commands = mailbox.drain()
        self.assertEqual([c.action for c in commands], ["ready"], commands)
        self.assertTrue(tray.is_alive())
        tray.stop()
        tray.wait(5)
        self.assertFalse(tray.is_alive())
        self.assertEqual(mailbox.drain(), ())


if __name__ == "__main__":
    unittest.main()

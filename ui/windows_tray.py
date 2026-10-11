"""Bandeja Windows lazy; callbacks só publicam comandos na mailbox.

icon_factory(callbacks) retorna um ícone com run(setup), visible e stop.
callbacks mapeia show/stop/close para MenuItem e error(detail) para falhas.
A fábrica padrão adapta o setup de pystray 0.19.5 para falhas antes de ready.
"""

from threading import Event, Lock, Thread, current_thread
import sys


def _create_icon(callbacks):
    if sys.platform != "win32":
        raise RuntimeError("A bandeja do Focus requer Windows")
    import pystray
    import ctypes
    from pystray._util import win32
    from PIL import Image, ImageDraw

    class ManagedIcon(pystray.Icon):
        def _message(self, code, flags, **kwargs):
            # Mesma estrutura/identificação de _win32.Icon na versão 0.19.5.
            # A implementação original ignora o BOOL: não ocultar Tk se ADD
            # foi recusado. DELETE pode falhar depois de remoção pelo shell.
            data = win32.NOTIFYICONDATAW(
                cbSize=ctypes.sizeof(win32.NOTIFYICONDATAW),
                hWnd=self._hwnd,
                hID=id(self),
                uFlags=flags,
                **kwargs,
            )
            accepted = win32.Shell_NotifyIcon(code, data)
            if code == win32.NIM_ADD and not accepted:
                detail = "O Windows recusou criar o ícone da bandeja (NIM_ADD)"
                # Inclui recriação após Explorer reiniciar: o dispatcher do
                # pystray só registra exceções, mantendo seu loop vivo.
                callbacks["error"](detail)
                raise RuntimeError(detail)

        def _start_setup(self, setup):
            # O setup original espera numa Queue sem cancelamento. Aqui o
            # término de run também acorda a thread se _mark_ready não ocorreu.
            self._focus_ready = Event()
            self._focus_finished = Event()

            def invoke():
                self._focus_ready.wait()
                if not self._focus_finished.is_set():
                    setup(self)

            self._setup_thread = Thread(target=invoke, name="FocusTraySetup", daemon=False)
            self._setup_thread.start()

        def _mark_ready(self):
            try:
                super()._mark_ready()
            finally:
                self._focus_ready.set()

        def finish_setup(self):
            if hasattr(self, "_focus_finished"):
                self._focus_finished.set()
                self._focus_ready.set()
                thread = getattr(self, "_setup_thread", None)
                if thread is not None and thread.ident is not None:
                    thread.join()

    image = Image.new("RGBA", (32, 32), "#167D77")
    drawing = ImageDraw.Draw(image)
    drawing.rectangle((8, 6, 23, 10), fill="white")
    drawing.rectangle((8, 6, 12, 25), fill="white")
    drawing.rectangle((8, 14, 21, 18), fill="white")
    menu = pystray.Menu(
        pystray.MenuItem("Mostrar Focus", callbacks["show"], default=True),
        pystray.MenuItem("Parar motor", callbacks["stop"]),
        pystray.MenuItem("Sair", callbacks["close"]),
    )
    return ManagedIcon("Focus", image, "Focus", menu)


class WindowsTray:
    """Um worker não daemon; stop só sinaliza, wait é externo a Tk.

    A biblioteca chama setup numa thread própria. Ela aguarda o Event e
    executa Icon.stop fora de Tk (pystray evita join do próprio setup).
    O worker permanece vivo até o setup terminar, inclusive falha de startup.
    """

    def __init__(self, mailbox, *, icon_factory=None):
        self._mailbox = mailbox
        self._factory = _create_icon if icon_factory is None else icon_factory
        self._lock = Lock()
        self._stop_event = Event()
        self._worker = None

    def start(self):
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return
            stopped = Event()
            self._stop_event = stopped
            try:
                worker = Thread(target=self._run, args=(stopped,), name="FocusWindowsTray", daemon=False)
                self._worker = worker
                worker.start()
            except Exception as exc:
                stopped.set()
                self._worker = None
                self._mailbox.post("error", f"Não foi possível iniciar a bandeja: {exc}")

    def stop(self):
        # Este lock protege somente Event/publicação, nunca IO do ícone/join.
        with self._lock:
            self._stop_event.set()

    def is_alive(self):
        with self._lock:
            return self._worker is not None and self._worker.is_alive()

    def wait(self, timeout=None):
        with self._lock:
            worker = self._worker
        if worker is not None:
            worker.join(timeout)

    def _run(self, stopped):
        icon = None
        setup_thread = None
        setup_finished = Event()

        def post(action):
            def callback(*_):
                with self._lock:
                    if not stopped.is_set():
                        self._mailbox.post(action)
            return callback

        def report_error(detail):
            with self._lock:
                if not stopped.is_set():
                    self._mailbox.post("error", str(detail))

        def setup(value):
            nonlocal setup_thread
            setup_thread = current_thread()
            try:
                if not stopped.is_set():
                    value.visible = True
                    with self._lock:
                        if not stopped.is_set():
                            if not value.visible:
                                raise RuntimeError("O ícone não confirmou visibilidade")
                            self._mailbox.post("ready")
                if stopped.is_set() and value.visible:
                    value.visible = False
                stopped.wait()
                if value.visible:
                    value.visible = False
                value.stop()
            except Exception as exc:
                self._mailbox.post("error", f"Falha na bandeja: {exc}")
                stopped.set()
                try:
                    value.stop()
                except Exception as stop_exc:
                    self._mailbox.post("error", f"Falha ao parar a bandeja: {stop_exc}")
            finally:
                setup_finished.set()

        try:
            if stopped.is_set():
                return
            callbacks = {action: post(action) for action in ("show", "stop", "close")}
            callbacks["error"] = report_error
            icon = self._factory(callbacks)
            if stopped.is_set():
                return
            icon.run(setup=setup)
            if not stopped.is_set():
                self._mailbox.post("error", "A bandeja encerrou inesperadamente. A janela será restaurada.")
        except Exception as exc:
            self._mailbox.post("error", f"Não foi possível abrir a bandeja: {exc}")
        finally:
            stopped.set()
            if icon is not None:
                # Adaptador padrão também acorda setup que nunca entrou.
                finish = getattr(icon, "finish_setup", None)
                if finish is not None:
                    finish()
                if setup_thread is not None and setup_thread is not current_thread():
                    setup_finished.wait()
                    setup_thread.join()

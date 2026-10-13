"""Editor e controle explícito de processos; widgets usados somente por Tk."""

from datetime import datetime, timedelta
from dataclasses import replace
from pathlib import Path
import sys
from time import monotonic

from core.config import ConfigError
from core.config_comparison import configs_equal
from core.config_review import review_config
from core.config_diff import diff_config
from core.config_repository import ConfigConflictError
from core.config_session import ConfigSession
from core.agenda_preview import week_preview
from core.process_controller import ProcessController
from core.instance_guard import InstanceGuard, InstanceGuardError
from core.initial_setup import PROCESS_SUGGESTIONS, with_process_suggestions
from ui.runtime_presenter import format_runtime
from ui.review_navigation import review_links
from ui.rule_list_view import rule_view_indices
from ui.config_diff_presenter import format_config_diff
from ui.tray_commands import TrayMailbox
from ui.windows_tray import WindowsTray


def run_config_gui(path: str | Path) -> int:
    guard = InstanceGuard(path)
    result = 1
    try:
        try:
            acquired = guard.acquire()
        except InstanceGuardError as exc:
            print(f"Erro ao adquirir guarda da interface: {exc}", file=sys.stderr)
        else:
            if acquired:
                result = _run_guarded_config_gui(path)
            else:
                print("Erro: já existe uma interface Focus para este arquivo de configuração.", file=sys.stderr)
    finally:
        try:
            guard.release()
        except InstanceGuardError as exc:
            print(f"Erro ao liberar guarda da interface: {exc}", file=sys.stderr)
            result = 1
    return result


def _run_guarded_config_gui(path: str | Path) -> int:
    """Importação gráfica opcional: os demais modos funcionam sem Tk/CTk."""
    try:
        import customtkinter as ctk
        import tkinter as tk
        from tkinter import filedialog, messagebox
    except ImportError as exc:
        print(
            f"Erro: interface gráfica indisponível ({exc}). "
            "Instale as dependências com .\\.venv\\Scripts\\python.exe "
            "-m pip install -r requirements.txt.",
            file=sys.stderr,
        )
        return 1

    try:
        try:
            session = ConfigSession(path)
        except ConfigError as exc:
            # A leitura estrita mantém o erro original como causa. for_new
            # reconfere com lstat: não recuperar inválidos/links quebrados.
            if not isinstance(exc.__cause__, FileNotFoundError):
                raise
            session = ConfigSession.for_new(path)
    except ConfigError as exc:
        print(f"Erro ao abrir configuração: {exc}. O destino foi preservado.", file=sys.stderr)
        return 1

    controller = ProcessController(session.path)
    mailbox = TrayMailbox()
    tray = WindowsTray(mailbox)
    app = None
    try:
        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        app = _build_app(ctk, tk, filedialog, messagebox, session, controller=controller,
                         tray=tray, mailbox=mailbox)
        app.mainloop()
        return 0
    except tk.TclError as exc:
        print(f"Erro ao iniciar interface gráfica: {exc}", file=sys.stderr)
        return 1
    finally:
        mailbox.close()
        controller.stop()
        tray.stop()
        try:
            controller.wait()
        finally:
            tray.wait()
            if app is not None:
                app.finish_close()


def _build_app(ctk, tk, filedialog, messagebox, session, controller=None, tray=None, mailbox=None):
    """Constrói widgets somente quando a GUI é solicitada."""
    accent = "#167D77"
    controller = ProcessController(session.path) if controller is None else controller
    mailbox = TrayMailbox() if mailbox is None else mailbox
    tray = WindowsTray(mailbox) if tray is None else tray
    muted = "#52656A"
    days = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")
    rule_fields = {
        "Executáveis": "block_exes",
        "Pastas": "block_folders",
        "Proteção adicional": "safelist_exes",
        "Linha de comando": "block_cmdline",
    }
    rule_orders = {"Cadastro": "registered", "Nome A–Z": "name_asc", "Nome Z–A": "name_desc"}
    descriptions = {
        "block_exes": "Nomes completos, como jogo.exe. A comparação ignora maiúsculas e minúsculas. "
                      "Selecionar arquivos adiciona apenas nomes, válidos em qualquer pasta.",
        "block_folders": "Pastas absolutas do Windows. As regras incluem subpastas.",
        "safelist_exes": "Aplicativos que devem ser preservados, por nome em qualquer pasta. "
                         "As proteções obrigatórias continuam valendo.",
        "block_cmdline": "O executável e o trecho literal precisam corresponder juntos, dentro de um argumento.",
    }

    class Editor(ctk.CTk):
        def __init__(self):
            super().__init__()
            self.title("Focus — Editor de configuração")
            self.geometry("1000x740")
            self.minsize(880, 660)
            self.configure(fg_color="#F3F6F5")
            self.grid_columnconfigure(0, weight=1)
            self.grid_rowconfigure(2, weight=1)
            self.modal = None
            self.status_timer = None
            self.close_timer = None
            self.closing = False
            self.closed = False
            self.controller = controller
            self.stop_requested = False
            self.selecting_executables = False
            self.picker_active = False
            self.review_generation = 0
            self.review_choices = {}
            self.review_selected = None
            self.review_snapshot = self.review_draft = None
            self.review_rows = {}
            self.row_generation = {"windows": 0, "rules": 0}
            self.highlighted_row = None
            self.visual_rule_order = "registered"
            self.rule_selection_mode = False
            self.rule_selection_generation = 0
            self.rule_selection_context = None
            self.rule_selection_indices = set()
            self.rule_selection_boxes = {}
            self.confirming_rule_removal = False
            self.tray = tray
            self.mailbox = mailbox
            self.tray_pending = self.tray_ready = self.tray_hidden = False
            self.tray_stopping = False
            self.tray_deadline = None
            self.preview_anchor = datetime.now().date()
            self.protocol("WM_DELETE_WINDOW", self.close_editor)

            header = ctk.CTkFrame(self, fg_color="transparent")
            header.grid(row=0, column=0, sticky="ew", padx=28, pady=(24, 12))
            header.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(header, text="Focus", font=ctk.CTkFont(size=32, weight="bold"),
                         text_color=accent).grid(row=0, column=0, sticky="w")
            ctk.CTkLabel(header, text="Organize seus horários e aplicativos", text_color=muted,
                         font=ctk.CTkFont(size=15)).grid(row=1, column=0, sticky="w")
            self.dirty_label = ctk.CTkLabel(header, text="", text_color=muted)
            self.dirty_label.grid(row=0, column=1, rowspan=2)
            self.runtime_title = ctk.CTkLabel(header, text="", anchor="w",
                                              font=ctk.CTkFont(size=17, weight="bold"))
            self.runtime_title.grid(row=2, column=0, sticky="ew", pady=(10, 0))
            runtime_actions = ctk.CTkFrame(header, fg_color="transparent")
            runtime_actions.grid(row=2, column=1, sticky="e", pady=(10, 0))
            self.start_button = ctk.CTkButton(runtime_actions, text="Iniciar", width=95,
                                              fg_color=accent, command=self.start_runtime)
            self.start_button.pack(side="left", padx=(0, 8))
            self.stop_button = ctk.CTkButton(runtime_actions, text="Parar", width=95,
                                             fg_color=accent, command=self.stop_runtime)
            self.stop_button.pack(side="left")
            self.runtime_detail = ctk.CTkTextbox(header, height=62, wrap="word", fg_color="white")
            self.runtime_detail.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(6, 0))
            self.runtime_detail.configure(state="disabled")
            self.runtime_detail_text = None

            summary = ctk.CTkFrame(self, fg_color="white", corner_radius=12)
            summary.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 12))
            summary.grid_columnconfigure(0, weight=1)
            self.agenda_label = ctk.CTkLabel(summary, text="", anchor="w",
                                            font=ctk.CTkFont(size=17, weight="bold"))
            self.agenda_label.grid(row=0, column=0, sticky="ew", padx=18, pady=(12, 0))
            self.next_label = ctk.CTkLabel(summary, text="", anchor="w", text_color=muted)
            self.next_label.grid(row=1, column=0, sticky="ew", padx=18)
            self.end_label = ctk.CTkLabel(summary, text="", anchor="w", text_color=muted)
            self.end_label.grid(row=2, column=0, sticky="ew", padx=18)
            self.agenda_hint = ctk.CTkLabel(summary, text="", text_color=muted, anchor="w")
            self.agenda_hint.grid(row=3, column=0, sticky="ew", padx=18, pady=(0, 12))

            self.tabs = ctk.CTkTabview(self, fg_color="white", segmented_button_selected_color=accent,
                                       segmented_button_selected_hover_color="#10645F")
            self.tabs.grid(row=2, column=0, sticky="nsew", padx=28)
            overview = self.tabs.add("Visão geral")
            schedules = self.tabs.add("Horários")
            processes = self.tabs.add("Jogos / Apps")
            settings = self.tabs.add("Configuração")
            settings.grid_columnconfigure(0, weight=1)
            settings.grid_rowconfigure(0, weight=1)
            settings_content = ctk.CTkScrollableFrame(settings, fg_color="transparent")
            settings_content.grid(row=0, column=0, sticky="nsew")
            settings = settings_content
            overview.grid_columnconfigure(0, weight=1)
            overview.grid_rowconfigure(0, weight=1)
            overview_content = ctk.CTkScrollableFrame(overview, fg_color="transparent")
            overview_content.grid(row=0, column=0, sticky="nsew")
            overview = overview_content
            for tab in (schedules, processes):
                tab.grid_columnconfigure(0, weight=1)
                tab.grid_rowconfigure(2, weight=1)

            overview.grid_columnconfigure(0, weight=1)
            overview.grid_rowconfigure(4, weight=1)
            self.setup_note = ctk.CTkLabel(overview, text="", anchor="w", justify="left",
                                           wraplength=730, text_color=muted)
            self.setup_note.grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
            self.preview_summary = ctk.CTkLabel(overview, text="", anchor="w", justify="left",
                                               font=ctk.CTkFont(size=20, weight="bold"))
            self.preview_summary.grid(row=1, column=0, sticky="ew", padx=14, pady=(10, 0))
            self.preview_note = ctk.CTkLabel(overview, text="", anchor="w", justify="left",
                                            text_color=muted, wraplength=760)
            self.preview_note.grid(row=2, column=0, sticky="ew", padx=14, pady=8)
            navigation = ctk.CTkFrame(overview, fg_color="transparent")
            navigation.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 8))
            for title, command in (
                ("Semana anterior", lambda: self.change_week(-7)),
                ("Esta semana", lambda: self.change_week(0)),
                ("Próxima semana", lambda: self.change_week(7)),
            ):
                ctk.CTkButton(navigation, text=title, width=130, fg_color=accent,
                              command=command).pack(side="left", padx=(0, 8))
            self.preview_days = ctk.CTkScrollableFrame(overview, fg_color="#F3F6F5")
            self.preview_days.grid(row=4, column=0, sticky="nsew", padx=14)
            self.preview_days.grid_columnconfigure(0, weight=1)
            self.orientation = ctk.CTkLabel(overview, text="", anchor="w", justify="left",
                                            wraplength=760, text_color=muted)
            self.orientation.grid(row=5, column=0, sticky="ew", padx=14, pady=8)
            shortcuts = ctk.CTkFrame(overview, fg_color="transparent")
            shortcuts.grid(row=6, column=0, sticky="w", padx=14, pady=(0, 14))
            for title, tab in (("Ir para Horários", "Horários"), ("Ir para Jogos / Apps", "Jogos / Apps")):
                ctk.CTkButton(shortcuts, text=title, fg_color=accent,
                              command=lambda name=tab: self.select_tab(name)).pack(side="left", padx=(0, 8))
            ctk.CTkButton(overview, text="Escolher sugestões de aplicativos", fg_color=accent,
                          command=lambda: self.select_tab("Configuração")).grid(
                              row=7, column=0, sticky="w", padx=14, pady=(0, 14))
            self.review_title = ctk.CTkLabel(overview, text="", anchor="w", justify="left",
                                              font=ctk.CTkFont(size=18, weight="bold"))
            self.review_title.grid(row=8, column=0, sticky="ew", padx=14, pady=(12, 8))
            self.review_detail = ctk.CTkTextbox(overview, height=150, wrap="word", fg_color="#F3F6F5")
            self.review_detail.grid(row=9, column=0, sticky="ew", padx=14, pady=(0, 14))
            self.review_detail.configure(state="disabled")
            review_actions = ctk.CTkFrame(overview, fg_color="transparent")
            review_actions.grid(row=10, column=0, sticky="ew", padx=14, pady=(0, 14))
            review_actions.grid_columnconfigure(0, weight=1)
            self.review_choice = ctk.StringVar(value="Escolha um apontamento")
            self.review_picker = ctk.CTkOptionMenu(review_actions, variable=self.review_choice,
                                                   values=["Escolha um apontamento"], width=420,
                                                   fg_color=accent, button_color=accent)
            self.review_picker.grid(row=0, column=0, sticky="ew", padx=(0, 8))
            self.review_go = ctk.CTkButton(review_actions, text="Ir para item", width=125, fg_color=accent,
                                            state="disabled")
            self.review_go.grid(row=0, column=1)

            ctk.CTkLabel(schedules, text="Horários de foco", font=ctk.CTkFont(size=20, weight="bold"),
                         anchor="w").grid(row=0, column=0, sticky="w", padx=14, pady=(10, 0))
            ctk.CTkButton(schedules, text="Adicionar horário", fg_color=accent,
                          command=self.edit_window).grid(row=0, column=1, padx=14, pady=(10, 0))
            ctk.CTkLabel(schedules, text="Horários podem atravessar a meia-noite; o dia é o de início.",
                         text_color=muted, anchor="w").grid(row=1, column=0, columnspan=2, sticky="w", padx=14, pady=10)
            self.windows_list = ctk.CTkScrollableFrame(schedules, fg_color="#F3F6F5")
            self.windows_list.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=14, pady=(0, 14))
            self.windows_list.grid_columnconfigure(0, weight=1)

            self.rule_category = ctk.StringVar(value="Executáveis")
            ctk.CTkOptionMenu(processes, variable=self.rule_category, values=list(rule_fields),
                              width=220, fg_color=accent, button_color=accent,
                              command=lambda _: self.render_rules()).grid(row=0, column=0, sticky="w", padx=14, pady=(10, 0))
            rule_actions = ctk.CTkFrame(processes, fg_color="transparent")
            rule_actions.grid(row=0, column=1, padx=14, pady=(10, 0))
            ctk.CTkButton(rule_actions, text="Adicionar regra", width=130, fg_color=accent,
                          command=self.edit_rule).pack(side="left", padx=(0, 8))
            self.executable_picker = ctk.CTkButton(rule_actions, text="Selecionar .exe…", width=145,
                                                   fg_color=accent, command=self.select_executables)
            self.executable_picker.pack(side="left")
            self.rule_description = ctk.CTkLabel(processes, text="", text_color=muted, anchor="w", wraplength=760)
            self.rule_description.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=10)
            self.rule_search = ctk.StringVar(value="")
            ctk.CTkLabel(processes, text="Buscar regras · Ctrl+F · Esc limpa", anchor="w", text_color=muted
                         ).grid(row=2, column=0, sticky="ew", padx=14)
            self.rule_selection_begin = ctk.CTkButton(processes, text="Selecionar regras", width=145,
                                                       fg_color=accent)
            self.rule_selection_begin.grid(row=2, column=1, sticky="w", padx=14)
            search_controls = ctk.CTkFrame(processes, fg_color="transparent")
            search_controls.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 10))
            search_controls.grid_columnconfigure(0, weight=1)
            self.rule_search_entry = ctk.CTkEntry(search_controls, textvariable=self.rule_search)
            self.rule_search_entry.grid(row=0, column=0, sticky="ew")
            self.rule_search_entry.bind("<Escape>", self.clear_rule_search)
            ctk.CTkButton(search_controls, text="Limpar", width=65, fg_color=accent,
                          command=self.clear_rule_search).grid(row=0, column=1, padx=(8, 0))
            order_controls = ctk.CTkFrame(processes, fg_color="transparent")
            order_controls.grid(row=3, column=1, sticky="w", padx=14, pady=(0, 10))
            ctk.CTkLabel(order_controls, text="Ordem visual", text_color=muted).pack(side="left", padx=(0, 10))
            self.rule_order = ctk.StringVar(value="Cadastro")
            self.rule_order_picker = ctk.CTkOptionMenu(order_controls, variable=self.rule_order,
                                                       values=list(rule_orders), width=155,
                                                       fg_color=accent, button_color=accent,
                                                       command=self.change_rule_order)
            self.rule_order_picker.pack(side="left")
            self.rule_area = processes
            self.rule_selection_bar = ctk.CTkFrame(processes, fg_color="transparent")
            self.rule_selection_count = None
            self.rule_selection_actions = {}
            self.rules_list = ctk.CTkScrollableFrame(processes, fg_color="#F3F6F5")
            processes.grid_rowconfigure(2, weight=0)
            processes.grid_rowconfigure(4, weight=1)
            self.rules_list.grid(row=4, column=0, columnspan=2, sticky="nsew", padx=14, pady=(0, 14))
            self.rules_list.grid_columnconfigure(0, weight=1)
            self.rule_search.trace_add("write", lambda *_: self.render_rules())

            settings.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(settings, text="Arquivo de configuração", font=ctk.CTkFont(size=20, weight="bold"),
                         anchor="w").grid(row=0, column=0, sticky="w", padx=18, pady=(18, 8))
            path_box = ctk.CTkTextbox(settings, height=70, wrap="word", fg_color="#F3F6F5")
            path_box.grid(row=1, column=0, sticky="ew", padx=18)
            path_box.insert("1.0", str(session.path.absolute()))
            path_box.configure(state="disabled")
            ctk.CTkButton(settings, text="Ver alterações", fg_color=accent,
                          command=self.show_changes).grid(row=2, column=0, sticky="w", padx=18, pady=(12, 0))
            ctk.CTkLabel(settings, justify="left", anchor="nw", wraplength=730, text=(
                "As alterações ficam em um rascunho até você clicar em Salvar. No primeiro uso, "
                "Salvar cria o arquivo; fechar e descartar não cria nada. Salvar não inicia o motor.\n\n"
                "Desfazer/Refazer restaura até 50 edições do rascunho nesta sessão. Salvar mantém o histórico; "
                "Importar e Recarregar o reiniciam.\n\n"
                "Recarregar lê o arquivo novamente e descarta o rascunho e seu histórico. Se outro editor alterar "
                "o arquivo, o Focus informa o conflito antes de salvar.\n\n"
                "Iniciar exige confirmação e usa o JSON salvo. O motor pode ler alterações salvas no próximo ciclo. "
                "Parar impede novas ações; uma chamada já iniciada pode terminar e aplicativos não são reabertos. "
                "Enviar à bandeja mantém motor e rascunho. O X continua saindo; fechar aguarda motor e bandeja. "
                "Uma CLI separada continua independente.\n\n"
                "Importar JSON substitui apenas o rascunho, após confirmação. Clique em Salvar para aplicar ao arquivo ativo.\n\n"
                "Exportar JSON grava o rascunho em um destino novo. Não salva a configuração ativa."
            )).grid(row=3, column=0, sticky="ew", padx=18, pady=18)
            portability = ctk.CTkFrame(settings, fg_color="transparent")
            portability.grid(row=4, column=0, sticky="w", padx=18)
            ctk.CTkButton(portability, text="Importar JSON", fg_color=accent,
                          command=self.import_config).pack(side="left", padx=(0, 8))
            ctk.CTkButton(portability, text="Exportar JSON", fg_color=accent,
                          command=self.export_config).pack(side="left")

            ctk.CTkLabel(settings, text="Sugestões de jogos e aplicativos", anchor="w",
                         font=ctk.CTkFont(size=20, weight="bold")).grid(
                             row=5, column=0, sticky="ew", padx=18, pady=(22, 8))
            ctk.CTkLabel(settings, text=(
                "Escolha somente os aplicativos que deseja incluir no rascunho. Nada está selecionado inicialmente. "
                "As sugestões não verificam instalações; revise e edite as regras em Jogos / Apps. "
                "Minecraft Java exige javaw.exe junto ao trecho .minecraft. Proteções obrigatórias têm prioridade."
            ), anchor="w", justify="left", wraplength=730, text_color=muted).grid(
                row=6, column=0, sticky="ew", padx=18, pady=(0, 12))
            self.suggestion_vars = {}
            suggestions = ctk.CTkFrame(settings, fg_color="transparent")
            suggestions.grid(row=7, column=0, sticky="ew", padx=18)
            for index, suggestion in enumerate(PROCESS_SUGGESTIONS):
                variable = tk.IntVar(value=0)
                self.suggestion_vars[suggestion.key] = variable
                detail = suggestion.executable
                if suggestion.contains is not None:
                    detail += f" + trecho {suggestion.contains}"
                ctk.CTkCheckBox(suggestions, text=f"{suggestion.label} · {detail}",
                                variable=variable).grid(row=index, column=0, sticky="w", pady=6)
            ctk.CTkButton(settings, text="Adicionar selecionadas", fg_color=accent,
                          command=self.add_suggestions).grid(row=8, column=0, sticky="w", padx=18, pady=14)

            footer = ctk.CTkFrame(self, fg_color="transparent")
            footer.grid(row=3, column=0, sticky="ew", padx=28, pady=16)
            footer.grid_columnconfigure(0, weight=1)
            self.feedback = ctk.CTkLabel(footer, text="", anchor="w", justify="left", wraplength=350, text_color=muted)
            self.feedback.grid(row=0, column=0, sticky="ew", padx=(0, 12))
            self.tray_button = ctk.CTkButton(footer, text="Enviar à bandeja", width=145, fg_color=accent,
                                             command=self.send_to_tray)
            self.tray_button.grid(row=0, column=1, padx=(0, 8))
            ctk.CTkButton(footer, text="Recarregar", width=110, fg_color="#E0E8E6", text_color="#263D3A",
                          hover_color="#CEDAD7", command=self.reload_config).grid(row=0, column=2, padx=(0, 8))
            ctk.CTkButton(footer, text="Salvar", width=110, fg_color=accent,
                          command=self.save_config).grid(row=0, column=3)
            history = ctk.CTkFrame(footer, fg_color="transparent")
            history.grid(row=1, column=0, columnspan=4, sticky="w", pady=(8, 0))
            self.undo_button = ctk.CTkButton(history, text="Desfazer", width=90, fg_color=accent,
                                              command=self.undo_draft)
            self.undo_button.pack(side="left", padx=(0, 8))
            self.redo_button = ctk.CTkButton(history, text="Refazer", width=90, fg_color=accent,
                                              command=self.redo_draft)
            self.redo_button.pack(side="left", padx=(0, 12))
            ctk.CTkLabel(history, text="Somente rascunho · Ctrl+Z / Ctrl+Y", text_color=muted).pack(side="left")
            self.bind("<Control-s>", lambda _: self.save_config() if self.modal is None else None)
            self.bind("<Control-r>", lambda _: self.reload_config() if self.modal is None else None)
            self.bind("<Control-z>", lambda event: self.history_shortcut(event, redo=False))
            self.bind("<Control-y>", lambda event: self.history_shortcut(event, redo=True))
            self.bind("<Control-f>", self.focus_rule_search)
            self.render()
            self.refresh_status()
            if session.is_new:
                self.notify("Arquivo ainda não criado. Clique em Salvar para criar.")

        def notify(self, text, *, error=False):
            self.feedback.configure(text=text, text_color="#A33232" if error else muted)

        def configure_if_changed(self, widget, **desired):
            changes = {key: value for key, value in desired.items() if widget.cget(key) != value}
            if changes:
                widget.configure(**changes)

        def render(self):
            if self.closing or self.closed:
                return
            self.render_preview()
            self.render_review()
            self.render_windows()
            self.render_rules()
            self.dirty_label.configure(text=("Arquivo ainda não criado" if session.is_new else
                                            "Alterações não salvas" if session.dirty else "Sem alterações pendentes"))
            self.setup_note.configure(text=(
                "Primeira configuração: o arquivo ainda não foi criado. Escolha horários e aplicativos; "
                "as sugestões são opcionais. Clique em Salvar para criar, depois confirme Iniciar quando desejar.\n"
                f"Destino: {session.path.absolute()}"
            ) if session.is_new else "Configuração carregada. Edite o rascunho e clique em Salvar para gravar alterações.")
            self.update_runtime()

        def update_history(self):
            enabled = not self.closing and self.modal is None and not self.picker_active and not self.selecting_executables
            self.configure_if_changed(self.undo_button, state="normal" if enabled and session.draft.can_undo else "disabled")
            self.configure_if_changed(self.redo_button, state="normal" if enabled and session.draft.can_redo else "disabled")

        def undo_draft(self):
            return self.change_history(redo=False)

        def redo_draft(self):
            return self.change_history(redo=True)

        def change_history(self, *, redo):
            if self.closing or self.closed or self.modal is not None or self.picker_active or self.selecting_executables:
                return False
            try:
                changed = session.draft.redo() if redo else session.draft.undo()
            except ConfigError as exc:
                self.notify(f"Não foi possível restaurar a edição: {exc}. Rascunho preservado.", error=True)
                return False
            if not changed:
                return False
            self.render()
            action = "refeita" if redo else "desfeita"
            state = "Salve para aplicar ao arquivo." if session.dirty else "Rascunho corresponde à versão carregada."
            self.notify(f"Alteração {action} no rascunho. {state}")
            return True

        def history_shortcut(self, event, *, redo):
            if self.closing or self.closed or self.modal is not None or self.picker_active or self.selecting_executables:
                return None
            widget = getattr(event, "widget", None)
            if widget is not None:
                try:
                    if widget.winfo_class() in {"Entry", "Text", "Spinbox", "TEntry", "TSpinbox"}:
                        return None
                except tk.TclError:
                    return None
            return "break" if self.change_history(redo=redo) else None

        def render_review(self):
            self.clear_review_highlight()
            self.review_generation += 1
            self.review_snapshot = session.draft.config
            self.review_draft = session.draft
            self.review_selected = None
            review = review_config(self.review_snapshot)
            self.review_title.configure(text=(
                f"Revisão do rascunho · {review.active_windows} horários ativos · "
                f"{review.target_rules} regras cadastradas de bloqueio"
            ))
            labels = {"windows": "Horários", "block_exes": "Executáveis", "block_folders": "Pastas",
                      "safelist_exes": "Proteção adicional", "block_cmdline": "Linha de comando"}
            lines = ["Análise estática, sem verificar processos ou instalações. Não altera suas regras."]
            for ordinal, item in enumerate(review.items[:10]):
                position = f", item {item.index + 1}" if type(item.index) is int and item.index >= 0 else ""
                detail = " ".join(item.detail.split())
                if len(detail) > 260:
                    detail = detail[:259] + "…"
                lines.append(f"{ordinal + 1}. {labels.get(item.field, 'Categoria desconhecida')}{position}: {detail}")
            if not review.items:
                lines.append("Nenhum apontamento estático. Proteções adicionais do motor também continuam valendo.")
            elif len(review.items) > 10:
                lines.append(f"Mais {len(review.items) - 10} apontamentos. Revise as listas em Jogos / Apps e Horários.")
            self.review_detail.configure(state="normal")
            self.review_detail.delete("1.0", "end")
            self.review_detail.insert("1.0", "\n".join(lines))
            self.review_detail.configure(state="disabled")
            self.review_choices = {link.label: link for link in review_links(review)}
            self.review_choice.set("Escolha um apontamento")
            generation = self.review_generation
            self.review_picker.configure(values=list(self.review_choices) or ["Nenhum item para navegar"],
                                           command=lambda label: self.choose_review(label, generation))
            self.review_go.configure(command=lambda: None)
            self.update_review_navigation()

        def navigation_available(self):
            return not (self.closing or self.closed or self.modal is not None
                        or self.picker_active or self.selecting_executables)

        def review_is_current(self):
            return (self.review_draft is session.draft and self.review_snapshot is not None
                    and configs_equal(self.review_snapshot, session.draft.config))

        def update_review_navigation(self):
            available = self.navigation_available()
            self.configure_if_changed(self.rule_order_picker, state="normal" if available else "disabled")
            self.configure_if_changed(self.review_picker, state="normal" if available and self.review_choices else "disabled")
            self.configure_if_changed(self.review_go, state="normal" if available and self.review_selected is not None else "disabled")
            self.update_rule_selection_controls()

        def choose_review(self, label, generation):
            if (not isinstance(label, str) or not self.navigation_available()
                    or generation != self.review_generation or not self.review_is_current()):
                return False
            link = self.review_choices.get(label)
            if link is None:
                return False
            token = (generation, link.field, link.index)
            self.review_selected = token
            self.review_choice.set(label)
            self.review_go.configure(command=lambda: self.navigate_review_choice(token))
            self.update_review_navigation()
            return True

        def navigate_review_choice(self, token):
            if token != self.review_selected or token[0] != self.review_generation:
                return False
            return self.navigate_review(token[1], token[2])

        def navigate_review(self, field, index):
            if not self.navigation_available():
                return False
            if not isinstance(field, str) or field not in ("windows", *rule_fields.values()) or type(index) is not int:
                return False
            if not self.review_is_current():
                self.notify("A revisão mudou. Escolha um apontamento atualizado.")
                return False
            values = getattr(session.draft.config, field)
            if not 0 <= index < len(values):
                return False
            if field == "windows":
                self.tabs.set("Horários")
                self.render_windows()
            else:
                self.tabs.set("Jogos / Apps")
                self.rule_category.set(next(label for label, value in rule_fields.items() if value == field))
                if self.rule_search.get():
                    self.rule_search.set("")  # o trace renderiza a categoria atual
                else:
                    self.render_rules()
            row = self.review_rows.get((field, index))
            if row is None:
                return False
            self.clear_review_highlight()
            self.highlighted_row = row
            row.configure(fg_color="#E1F1ED", border_color=accent, border_width=2)
            row.review_detail_label.configure(text=f"Selecionado pela revisão · item {index + 1}\n{row.review_base_detail}")
            self.queue_review_scroll(row, field, index)
            self.notify(f"Item {index + 1} destacado. Use Editar para alterar o rascunho.")
            return True

        def clear_review_highlight(self):
            row = self.highlighted_row
            if row is None:
                return
            self.highlighted_row = None
            if row.review_scroll_timer is not None:
                row.after_cancel(row.review_scroll_timer)
                row.review_scroll_timer = None
            row.configure(fg_color="white", border_width=0)
            row.review_detail_label.configure(text=row.review_base_detail)

        def queue_review_scroll(self, row, field, index):
            kind = "windows" if field == "windows" else "rules"
            frame = self.windows_list if kind == "windows" else self.rules_list
            generation, review_generation = self.row_generation[kind], self.review_generation

            def scroll():
                row.review_scroll_timer = None
                if (not self.navigation_available() or generation != self.row_generation[kind]
                        or review_generation != self.review_generation or self.highlighted_row is not row
                        or self.review_rows.get((field, index)) is not row or not self.review_is_current()):
                    return
                # CTk 6.0.0 não expõe scroll-to-item público. Só este adaptador
                # usa o canvas interno; o destaque continua útil se indisponível.
                canvas = getattr(frame, "_parent_canvas", None)
                if (canvas is None or not callable(getattr(canvas, "yview_moveto", None))
                        or not callable(getattr(canvas, "bbox", None)) or not callable(getattr(row, "winfo_y", None))):
                    self.notify("Item destacado; use a rolagem da lista para vê-lo.")
                    return
                bounds = canvas.bbox("all")
                if bounds is not None and bounds[3] > bounds[1]:
                    canvas.yview_moveto(max(0.0, min(1.0, (row.winfo_y() - bounds[1]) / (bounds[3] - bounds[1]))))

            # A linha possui o comando Tcl: clear/cancel_widget_callbacks o
            # cancela antes de destroy. Nenhum timer de scroll pertence à raiz.
            row.review_scroll_timer = row.after(40, scroll)

        def add_suggestions(self):
            if self.closing or self.closed or self.modal is not None:
                return
            keys = [key for key, variable in self.suggestion_vars.items() if variable.get()]
            if not keys:
                self.notify("Selecione os aplicativos que deseja adicionar ao rascunho.")
                return
            try:
                session.draft.replace_config(with_process_suggestions(session.draft.config, keys))
            except ConfigError as exc:
                self.notify(f"Não foi possível adicionar sugestões: {exc}. Rascunho preservado.", error=True)
                return
            for variable in self.suggestion_vars.values():
                variable.set(0)
            self.render()
            self.notify("Sugestões adicionadas ao rascunho. Revise em Jogos / Apps e clique em Salvar.")

        def select_tab(self, name):
            if not self.closing and not self.closed:
                self.tabs.set(name)

        def restore_window(self):
            self.tray_pending = self.tray_hidden = False
            self.tray_deadline = None
            self.deiconify()
            self.lift()
            if self.modal is not None:
                self.modal.deiconify()
                self.modal.lift()

        def send_to_tray(self):
            if self.closing or self.closed:
                return
            if self.picker_active:
                self.notify("Termine a seleção antes de enviar à bandeja.")
                return
            if self.modal is not None or self.tray_pending:
                return
            if self.tray_stopping and tray.is_alive():
                self.notify("Aguarde a bandeja terminar antes de tentar novamente.", error=True)
                return
            self.tray_stopping = False
            self.tray_pending = True
            self.tray_deadline = monotonic() + 10.0
            if self.tray_ready and tray.is_alive():
                self.hide_to_tray()
            else:
                self.tray_ready = False
                tray.start()
                self.notify("Preparando a bandeja. A janela permanece visível até o ícone estar pronto.")

        def hide_to_tray(self):
            if not self.tray_pending or not self.tray_ready or self.tray_stopping or self.closing:
                return
            if self.picker_active:
                self.restore_window()
                self.notify("Termine a seleção antes de enviar à bandeja.")
                return
            if self.modal is not None:
                self.restore_window()
                self.notify("Feche o formulário antes de enviar à bandeja.")
                return
            self.withdraw()
            self.tray_hidden = True
            self.tray_pending = False
            self.tray_deadline = None

        def tray_error(self, detail):
            self.tray_ready = False
            self.tray_stopping = True
            tray.stop()
            self.restore_window()
            self.notify(f"Bandeja indisponível: {detail}", error=True)

        def drain_tray(self):
            for command in mailbox.drain():
                if self.closing or self.closed:
                    break
                if command.action == "ready":
                    if not self.tray_stopping and tray.is_alive():
                        self.tray_ready = True
                        self.hide_to_tray()
                elif command.action == "error":
                    self.tray_error(command.detail or "falha ao preparar o ícone")
                elif command.action == "show":
                    self.restore_window()
                elif command.action == "stop":
                    self.stop_runtime()
                elif command.action == "close":
                    self.close_editor()
            if self.closing or self.closed:
                return
            if self.tray_pending and self.tray_deadline is not None and monotonic() >= self.tray_deadline:
                self.tray_error("O ícone não ficou pronto em 10 segundos. Tente novamente após a parada.")
            elif self.tray_ready and not tray.is_alive():
                self.tray_error("A bandeja encerrou inesperadamente.")

        def update_runtime(self):
            snapshot = controller.snapshot()
            alive = controller.is_alive()
            if self.stop_requested and alive and snapshot.state != "error":
                snapshot = replace(snapshot, state="stopping")
            if not alive:
                self.stop_requested = False
            view = format_runtime(snapshot)
            self.configure_if_changed(self.runtime_title, text=view.title)
            if view.detail != self.runtime_detail_text:
                self.runtime_detail.configure(state="normal")
                self.runtime_detail.delete("1.0", "end")
                self.runtime_detail.insert("1.0", view.detail)
                self.runtime_detail.configure(state="disabled")
                self.runtime_detail_text = view.detail
            self.configure_if_changed(self.start_button, state="normal" if (
                view.start_enabled and not alive and self.modal is None and not self.closing
                and not session.is_new and not self.picker_active and not self.selecting_executables
            ) else "disabled")
            self.configure_if_changed(self.stop_button, state="normal" if view.stop_enabled and not self.closing else "disabled")
            self.update_history()
            self.update_review_navigation()

        def start_runtime(self):
            if (self.closing or self.closed or self.modal is not None or controller.is_alive()
                    or self.picker_active or self.selecting_executables):
                return
            if session.is_new:
                self.notify("Crie a configuração clicando em Salvar antes de iniciar.", error=True)
                return
            if session.dirty:
                self.notify("Salve as alterações ou descarte o rascunho com Recarregar antes de iniciar.", error=True)
                return
            if not messagebox.askyesno(
                "Iniciar bloqueador de processos",
                "Aplicativos elegíveis podem ser encerrados sem salvar seu estado.\n"
                "O motor usará exclusivamente o JSON salvo, incluindo alterações externas.\n\nIniciar agora?", parent=self
            ):
                return
            if self.closing or self.closed or session.dirty or session.is_new:
                return
            if controller.start():
                self.stop_requested = False
                self.notify("Motor iniciado com a configuração salva. Confira o resultado do último ciclo acima.")
            self.update_runtime()

        def stop_runtime(self):
            if self.closing or self.closed:
                return
            self.stop_requested = True
            controller.stop()
            self.update_runtime()
            self.notify("Parada solicitada. Uma chamada já iniciada pode terminar; aplicativos não são reabertos.")

        @staticmethod
        def planned_time(minutes):
            hours, remainder = divmod(minutes, 60)
            return f"{hours} h {remainder:02d} min"

        def change_week(self, offset):
            if self.closing or self.closed:
                return
            self.preview_anchor = (self.preview_anchor + timedelta(days=offset)
                                   if offset else datetime.now().date())
            self.render_preview()

        def render_preview(self):
            config = session.draft.config
            preview = week_preview(config.windows, self.preview_anchor)
            end = preview.start + timedelta(days=6)
            self.preview_summary.configure(text=(
                f"Semana {preview.start:%d/%m/%Y} a {end:%d/%m/%Y}\n"
                f"Horas PLANEJADAS: {self.planned_time(preview.total_minutes)}"
            ))
            state = ("Arquivo ainda não criado" if session.is_new else
                     "Alterações não salvas" if session.dirty else "Sem alterações pendentes")
            self.preview_note.configure(text=(
                f"Prévia do rascunho · {state}\n"
                "Horas planejadas pela agenda, não uma medição de foco. Sobreposições contam uma vez."
            ))
            self.clear(self.preview_days)
            for index, day in enumerate(preview.days):
                intervals = []
                for interval in day.intervals:
                    finish = "24:00" if interval.end.date() > day.date else interval.end.strftime("%H:%M")
                    intervals.append(f"{interval.start:%H:%M} → {finish}")
                text = (f"{days[index]} {day.date:%d/%m} · {self.planned_time(day.minutes)} planejados\n"
                        + ("  |  ".join(intervals) or "Sem horário planejado"))
                ctk.CTkLabel(self.preview_days, text=text, anchor="w", justify="left", wraplength=730
                             ).grid(row=index, column=0, sticky="ew", padx=14, pady=8)
            if not config.windows:
                guidance = "Comece em Horários: adicione um horário e escolha os dias. Depois escolha Jogos / Apps e clique em Salvar."
            elif not any(window.days for window in config.windows):
                guidance = "Nenhum horário ativo. Em Horários, edite um horário e selecione os dias. Depois escolha os alvos em Jogos / Apps e clique em Salvar."
            elif not any(getattr(config, field) for field in ("block_exes", "block_folders", "block_cmdline")):
                guidance = "Escolha os jogos ou aplicativos em Jogos / Apps. Clique em Salvar para gravar horários e regras."
            else:
                guidance = "Revise horários e regras usando os atalhos abaixo. Clique em Salvar para gravar o rascunho."
            self.orientation.configure(text=guidance)

        def cancel_widget_callbacks(self, widget):
            if not hasattr(widget, "tk"):
                return
            commands = set()

            def collect(owner):
                commands.update(getattr(owner, "_tclCommands", None) or ())
                for child in owner.winfo_children():
                    collect(child)

            collect(widget)
            for timer in widget.tk.splitlist(widget.tk.call("after", "info")):
                script = widget.tk.call("after", "info", timer)[0]
                parts = widget.tk.splitlist(script)
                if parts and parts[0] in commands:
                    widget.tk.call("after", "cancel", timer)

        def clear(self, frame):
            if frame is self.windows_list or frame is self.rules_list:
                kind = "windows" if frame is self.windows_list else "rules"
                keys = [key for key in self.review_rows if (key[0] == "windows") == (kind == "windows")]
                if self.highlighted_row in (self.review_rows[key] for key in keys):
                    self.clear_review_highlight()
                for key in keys:
                    del self.review_rows[key]
                self.row_generation[kind] += 1
            for child in frame.winfo_children():
                self.cancel_widget_callbacks(child)
                child.destroy()

        def dismiss_modal(self):
            if self.modal is None:
                return
            dialog = self.modal
            for timer in dialog.startup_timers:
                dialog.after_cancel(timer)
            self.cancel_widget_callbacks(dialog)
            self.modal = None
            dialog.destroy()

        def model_is_current(self, draft, config):
            return session.draft is draft and configs_equal(config, session.draft.config)

        def action_context(self, field, index, *, row=None, config=None):
            if field not in ("windows", *rule_fields.values()) or type(index) is not int or index < 0:
                return None
            config = session.draft.config if config is None else config
            if index >= len(getattr(config, field)):
                return None
            kind = "windows" if field == "windows" else "rules"
            view = None if kind == "windows" else (self.rule_category.get(), self.rule_search.get(), self.visual_rule_order)
            return (kind, field, index, self.row_generation[kind], row, session.draft, config, view)

        def action_is_current(self, context, *, during_confirmation=False):
            if (not self.navigation_available() or (self.confirming_rule_removal and not during_confirmation)
                    or context is None):
                return False
            kind, field, index, generation, row, draft, config, view = context
            if (generation != self.row_generation[kind] or not self.model_is_current(draft, config)
                    or type(index) is not int or not 0 <= index < len(getattr(config, field))
                    or (row is not None and self.review_rows.get((field, index)) is not row)):
                return False
            return view is None or view == (self.rule_category.get(), self.rule_search.get(), self.visual_rule_order)

        def form_is_current(self, dialog, draft, config, error):
            if (self.closing or self.closed or self.picker_active or self.selecting_executables
                    or self.confirming_rule_removal or self.modal is not dialog):
                return False
            if not self.model_is_current(draft, config):
                error.configure(text="O rascunho mudou. Feche este formulário e reabra o item para editar a versão atual.")
                return False
            return True

        def item_row(self, frame, index, title, detail, edit, remove, duplicate=None, selection=None, action=None):
            row = ctk.CTkFrame(frame, fg_color="white", corner_radius=8)
            row.grid(row=index, column=0, sticky="ew", pady=(0, 8))
            if action is not None:
                field, original_index, config = action
                row_action_context = self.action_context(field, original_index, row=row, config=config)
                row.action_context = row_action_context
                edit = (lambda i=original_index, ctx=row_action_context: self.edit_window(i, context=ctx)) if field == "windows" else (
                    lambda i=original_index, f=field, ctx=row_action_context: self.edit_rule(i, f, context=ctx))
                remove = lambda f=field, i=original_index, ctx=row_action_context: self.remove_item(f, i, context=ctx)
                if duplicate is not None:
                    duplicate = lambda i=original_index, ctx=row_action_context: self.duplicate_window(i, context=ctx)
            text_column = 0 if selection is None else 1
            row.grid_columnconfigure(text_column, weight=1)
            wrap = 390 if duplicate is not None else 500 if selection is not None else 540
            if selection is not None:
                selection_context, original_index = selection
                variable = tk.IntVar(value=0)
                checkbox = ctk.CTkCheckBox(row, text="", width=24, checkbox_width=20, checkbox_height=20,
                                         variable=variable, command=lambda ctx=selection_context, i=original_index,
                                         current_row=row, var=variable: self.selection_toggle(ctx, i, current_row, var))
                checkbox.grid(row=0, column=0, rowspan=2, padx=(8, 0))
                self.rule_selection_boxes[original_index] = (row, variable, checkbox)
            ctk.CTkLabel(row, text=title, anchor="w", justify="left", wraplength=wrap,
                         font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=text_column, sticky="ew", padx=14, pady=(10, 0))
            row.review_base_detail = detail
            row.review_scroll_timer = None
            row.review_detail_label = ctk.CTkLabel(row, text=detail, text_color=muted, anchor="w", justify="left", wraplength=wrap)
            row.review_detail_label.grid(row=1, column=text_column, sticky="ew", padx=14, pady=(0, 10))
            ctk.CTkButton(row, text="Editar", width=75, fg_color=accent,
                          command=edit).grid(row=0, column=text_column + 1, rowspan=2, padx=6)
            ctk.CTkButton(row, text="Remover", width=85, fg_color="#E0E8E6", text_color="#263D3A",
                          hover_color="#CEDAD7", command=remove).grid(row=0, column=text_column + 2, rowspan=2, padx=(0, 12))
            if duplicate is not None:
                ctk.CTkButton(row, text="Duplicar", width=85, fg_color=accent,
                              command=duplicate).grid(row=0, column=3, rowspan=2, padx=(0, 12))
            return row

        def render_windows(self):
            if self.closing or self.closed:
                return
            self.clear(self.windows_list)
            config = session.draft.config
            windows = config.windows
            if not windows:
                ctk.CTkLabel(self.windows_list, text="Nenhum horário cadastrado.\nAdicione seu primeiro horário para começar.",
                             text_color=muted).grid(row=0, column=0, pady=45)
            for index, window in enumerate(windows):
                day_text = ", ".join(days[day] for day in window.days) or "Desativado — nenhum dia selecionado"
                self.review_rows[("windows", index)] = self.item_row(self.windows_list, index,
                              f"{window.start:%H:%M} → {window.end:%H:%M}", day_text,
                              lambda i=index: self.edit_window(i),
                              lambda i=index: self.remove_item("windows", i),
                              lambda i=index: self.duplicate_window(i), action=("windows", index, config))

        def duplicate_window(self, index, *, context=None):
            if not self.navigation_available() or self.confirming_rule_removal or type(index) is not int:
                return False
            context = self.action_context("windows", index) if context is None else context
            if not self.action_is_current(context) or context[1:3] != ("windows", index):
                return False
            try:
                context[5].duplicate_window(index)
            except ConfigError as exc:
                self.notify(f"Não foi possível duplicar: {exc}", error=True)
                return False
            self.render()
            self.notify("Horário duplicado no rascunho. Clique em Salvar para gravar.")
            return True

        def focus_rule_search(self, event=None):
            if not self.navigation_available():
                return None
            self.tabs.set("Jogos / Apps")
            self.rule_search_entry.focus_set()
            self.rule_search_entry.select_range(0, "end")
            self.rule_search_entry.icursor("end")
            return "break"

        def clear_rule_search(self, event=None):
            if not self.navigation_available():
                return None if event is not None else False
            changed = bool(self.rule_search.get())
            if changed:
                self.rule_search.set("")  # o trace reconstrói a lista uma única vez
            return "break" if event is not None else changed

        def change_rule_order(self, label):
            if self.closing or self.closed:
                return False
            if not self.navigation_available() or not isinstance(label, str) or label not in rule_orders:
                self.rule_order.set(next(title for title, value in rule_orders.items() if value == self.visual_rule_order))
                return False
            self.visual_rule_order = rule_orders[label]
            self.rule_order.set(label)
            self.render_rules()
            return True

        def begin_rule_selection(self, generation=None):
            if (not self.navigation_available() or self.confirming_rule_removal or self.rule_selection_mode
                    or (generation is not None and generation != self.rule_selection_generation)):
                return False
            self.rule_selection_mode = True
            self.render_rules()
            return True

        def selection_is_current(self, context, *, during_confirmation=False):
            if (not self.navigation_available() or not self.rule_selection_mode
                    or (self.confirming_rule_removal and not during_confirmation)
                    or context is None or context is not self.rule_selection_context):
                return False
            generation, field, indices, draft, config, query, order = context
            if (generation != self.rule_selection_generation or session.draft is not draft
                    or not configs_equal(config, session.draft.config)):
                return False
            if (rule_fields.get(self.rule_category.get()) != field or self.rule_search.get() != query
                    or self.visual_rule_order != order):
                return False
            values = getattr(config, field)
            return (all(type(index) is int and 0 <= index < len(values) for index in indices)
                    and self.rule_selection_indices.issubset(indices)
                    and all(self.rule_selection_boxes.get(index) is not None
                            and self.review_rows.get((field, index)) is self.rule_selection_boxes[index][0]
                            for index in indices))

        def update_rule_selection_controls(self):
            available = self.navigation_available() and not self.confirming_rule_removal
            self.configure_if_changed(self.rule_selection_begin, state="normal" if available and not self.rule_selection_mode else "disabled")
            context = self.rule_selection_context
            if self.rule_selection_count is None or context is None:
                return
            selected, shown = len(self.rule_selection_indices), len(context[2])
            self.configure_if_changed(self.rule_selection_count, text=f"{selected} selecionadas / {shown} exibidas\nAtualizar a lista limpa a seleção.")
            current = self.selection_is_current(context)
            for action, control in self.rule_selection_actions.items():
                enabled = current and (shown > 0 if action == "all" else selected > 0 if action in {"clear", "remove"} else True)
                self.configure_if_changed(control, state="normal" if enabled else "disabled")
            for _, _, checkbox in self.rule_selection_boxes.values():
                state = "normal" if current else "disabled"
                if checkbox.cget("state") != state:
                    checkbox.configure(state=state)

        def selection_toggle(self, context, index, row, variable):
            if (not self.selection_is_current(context) or type(index) is not int
                    or self.review_rows.get((context[1], index)) is not row
                    or self.rule_selection_boxes.get(index, ())[:2] != (row, variable)):
                return False
            if variable.get():
                self.rule_selection_indices.add(index)
            else:
                self.rule_selection_indices.discard(index)
            self.update_rule_selection_controls()
            return True

        def selection_select_all(self, context):
            if not self.selection_is_current(context):
                return False
            self.rule_selection_indices = set(context[2])
            for _, variable, _ in self.rule_selection_boxes.values():
                variable.set(1)
            self.update_rule_selection_controls()
            return True

        def selection_clear(self, context):
            if not self.selection_is_current(context):
                return False
            self.rule_selection_indices.clear()
            for _, variable, _ in self.rule_selection_boxes.values():
                variable.set(0)
            self.update_rule_selection_controls()
            return True

        def selection_close(self, context):
            if not self.selection_is_current(context):
                return False
            self.rule_selection_mode = False
            self.render_rules()
            return True

        def selection_remove(self, context):
            if not self.selection_is_current(context):
                return False
            indices = tuple(index for index in context[2] if index in self.rule_selection_indices)
            if not indices:
                return False
            field, draft = context[1], context[3]
            rows = tuple(self.review_rows[(field, index)] for index in indices)
            category = next(label for label, value in rule_fields.items() if value == field)
            self.confirming_rule_removal = True
            try:
                self.update_rule_selection_controls()
                confirmed = messagebox.askyesno("Remover regras selecionadas",
                    f"Remover {len(indices)} regra(s) de {category} do rascunho?\n"
                    "A remoção pode ser desfeita. Clique em Salvar para gravar no arquivo.", parent=self)
                if (not confirmed or not self.selection_is_current(context, during_confirmation=True)
                        or indices != tuple(index for index in context[2] if index in self.rule_selection_indices)
                        or rows != tuple(self.review_rows.get((field, index)) for index in indices)):
                    return False
                try:
                    removed = draft.remove_rules(field, indices)
                except ConfigError as exc:
                    self.notify(f"Não foi possível remover as regras: {exc}. Rascunho preservado.", error=True)
                    return False
                self.render()
                self.notify(f"{removed} regra(s) removida(s) do rascunho de {category}. Clique em Salvar para gravar.")
                return True
            finally:
                self.confirming_rule_removal = False
                if not self.closing and not self.closed:
                    self.update_rule_selection_controls()

        def build_rule_selection_bar(self, context):
            self.rule_selection_count = ctk.CTkLabel(self.rule_selection_bar, text="", width=215,
                                                      wraplength=205, anchor="w", justify="left", text_color=muted)
            self.rule_selection_count.pack(side="left")
            for action, title, width, callback in (
                ("all", "Selecionar exibidas", 125, self.selection_select_all),
                ("clear", "Limpar seleção", 105, self.selection_clear),
                ("remove", "Remover selecionadas", 155, self.selection_remove),
                ("close", "Fechar seleção", 110, self.selection_close),
            ):
                control = ctk.CTkButton(self.rule_selection_bar, text=title, width=width,
                                      fg_color=accent, command=lambda action=callback: action(context))
                control.pack(side="left", padx=(6, 0))
                self.rule_selection_actions[action] = control

        def render_rules(self):
            if self.closing or self.closed:
                return
            self.rule_selection_generation += 1
            self.rule_selection_indices.clear()
            self.rule_selection_boxes.clear()
            self.rule_selection_context = None
            self.clear(self.rule_selection_bar)
            self.rule_selection_count = None
            self.rule_selection_actions = {}
            generation = self.rule_selection_generation
            self.rule_selection_begin.configure(command=lambda: self.begin_rule_selection(generation))
            self.rule_area.grid_rowconfigure(4, weight=0 if self.rule_selection_mode else 1)
            self.rule_area.grid_rowconfigure(5, weight=1 if self.rule_selection_mode else 0)
            if self.rule_selection_mode:
                self.rule_selection_bar.grid(row=4, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 4))
            else:
                self.rule_selection_bar.grid_remove()
            self.rules_list.grid(row=5 if self.rule_selection_mode else 4, column=0, columnspan=2,
                                 sticky="nsew", padx=14, pady=(0, 14))
            self.clear(self.rules_list)
            field = rule_fields[self.rule_category.get()]
            self.rule_description.configure(text=descriptions[field])
            self.executable_picker.configure(state="normal" if (
                field in {"block_exes", "safelist_exes"} and self.modal is None and not self.selecting_executables
            ) else "disabled")
            config = session.draft.config
            values = getattr(config, field)
            indices = rule_view_indices(config, field, query=self.rule_search.get(), order=self.visual_rule_order)
            context = None
            if self.rule_selection_mode:
                context = (generation, field, indices, session.draft, config, self.rule_search.get(), self.visual_rule_order)
                self.rule_selection_context = context
                self.build_rule_selection_bar(context)
            if not values:
                ctk.CTkLabel(self.rules_list, text="Nenhuma regra nesta lista.", text_color=muted
                             ).grid(row=0, column=0, pady=45)
                self.update_rule_selection_controls()
                return
            for visible, index in enumerate(indices):
                value = values[index]
                title = value.executable if field == "block_cmdline" else value
                detail = f"Contém: {value.contains}" if field == "block_cmdline" else self.rule_category.get()
                self.review_rows[(field, index)] = self.item_row(self.rules_list, visible, title, detail,
                              lambda i=index, f=field: self.edit_rule(i, f),
                              lambda i=index, f=field: self.remove_item(f, i),
                              selection=(context, index) if context is not None else None,
                              action=(field, index, config))
            if not indices:
                ctk.CTkLabel(self.rules_list, text="Nenhuma regra corresponde à busca nesta categoria.",
                             text_color=muted).grid(row=0, column=0, pady=45)
            self.update_rule_selection_controls()

        def open_picker(self, choose, **options):
            # Desfaz a intenção anterior de ocultar, inclusive ready que só
            # chegar depois do retorno do seletor. Enviar continua explícito.
            if self.tray_pending:
                self.restore_window()
                self.notify("Termine a seleção antes de enviar à bandeja.")
            self.picker_active = True
            self.update_runtime()
            try:
                return choose(**options)
            finally:
                self.picker_active = False
                if not self.closing and not self.closed:
                    self.update_runtime()

        def select_executables(self):
            if self.closing or self.closed or self.modal is not None or self.picker_active or self.selecting_executables:
                return
            field = rule_fields[self.rule_category.get()]
            if field not in {"block_exes", "safelist_exes"}:
                return
            self.selecting_executables = True
            self.executable_picker.configure(state="disabled")
            self.update_runtime()
            try:
                selected = self.open_picker(filedialog.askopenfilenames,
                    parent=self,
                    title=("Selecionar executáveis para bloquear por nome" if field == "block_exes"
                           else "Selecionar executáveis para proteção adicional"),
                    filetypes=[("Executáveis Windows", "*.exe")],
                )
            except tk.TclError as exc:
                if not self.closing and not self.closed:
                    self.notify(f"Não foi possível abrir o seletor: {exc}", error=True)
                return
            finally:
                self.selecting_executables = False
                if not self.closing and not self.closed:
                    self.update_runtime()
                    self.render_rules()
            if not selected or self.closing or self.closed or self.modal is not None:
                return
            try:
                added = session.draft.add_executable_paths(field, selected)
            except ConfigError as exc:
                self.notify(f"Não foi possível adicionar executáveis: {exc}. Rascunho preservado.", error=True)
                return
            if not added:
                self.notify("Os executáveis selecionados já estão nesta lista.")
                return
            self.render()
            category = "bloqueio" if field == "block_exes" else "proteção adicional"
            label = "executável adicionado" if added == 1 else "executáveis adicionados"
            self.notify(f"{added} {label} ao rascunho de {category}, por nome em qualquer pasta. "
                        "Clique em Salvar para gravar.")

        def remove_item(self, field, index, *, context=None):
            if not self.navigation_available() or self.confirming_rule_removal or type(index) is not int:
                return False
            context = self.action_context(field, index) if context is None else context
            if not self.action_is_current(context) or context[1:3] != (field, index):
                return False
            self.confirming_rule_removal = True
            try:
                if not messagebox.askyesno("Remover item", "Remover este item do rascunho?", parent=self):
                    return False
                if not self.action_is_current(context, during_confirmation=True):
                    return False
                try:
                    if field == "windows":
                        context[5].remove_window(index)
                    else:
                        context[5].remove_rule(field, index)
                except ConfigError as exc:
                    self.notify(f"Não foi possível remover: {exc}. Rascunho preservado.", error=True)
                    return False
                self.render()
                self.notify("Item removido do rascunho. Clique em Salvar para gravar.")
                return True
            finally:
                self.confirming_rule_removal = False
                if not self.closing and not self.closed:
                    self.update_rule_selection_controls()

        def show_changes(self):
            if self.closing or self.closed or self.modal is not None or self.picker_active or self.selecting_executables:
                return
            baseline = None if session.is_new else session.snapshot.config
            view = format_config_diff(diff_config(baseline, session.draft.config))
            dialog, form, _, _, _ = self.new_dialog(view.title, read_only=True)
            form.grid_rowconfigure(0, weight=1)
            dialog.diff_text = ctk.CTkTextbox(form, wrap="none", fg_color="#F3F6F5")
            dialog.diff_text.grid(row=0, column=0, sticky="nsew")
            dialog.diff_text.insert("1.0", view.detail)
            dialog.diff_text.configure(state="disabled")
            dialog.startup_timers.append(dialog.after(150, dialog.diff_text.focus_set))

        def new_dialog(self, title, *, read_only=False):
            dialog = ctk.CTkToplevel(self)
            dialog.read_only = read_only
            dialog.title(title)
            dialog.geometry("760x560" if read_only else "560x430")
            dialog.resizable(read_only, read_only)
            if read_only:
                dialog.minsize(620, 420)
                dialog.grid_rowconfigure(1, weight=1)
            dialog.transient(self)
            dialog.grid_columnconfigure(0, weight=1)
            self.modal = dialog
            dialog.startup_timers = []

            def close():
                if self.modal is dialog:
                    self.dismiss_modal()
                    self.update_runtime()

            dialog.protocol("WM_DELETE_WINDOW", close)
            dialog.bind("<Escape>", lambda _: close())
            ctk.CTkLabel(dialog, text=title, font=ctk.CTkFont(size=22, weight="bold"), anchor="w"
                         ).grid(row=0, column=0, sticky="ew", padx=24, pady=(22, 14))
            form = ctk.CTkFrame(dialog, fg_color="transparent")
            form.grid(row=1, column=0, sticky="nsew", padx=24)
            form.grid_columnconfigure(0, weight=1)
            error_label = ctk.CTkLabel(dialog, text="", text_color="#A33232", wraplength=510, justify="left")
            error_label.grid(row=2, column=0, sticky="ew", padx=24, pady=10)
            actions = ctk.CTkFrame(dialog, fg_color="transparent")
            actions.grid(row=3, column=0, sticky="e", padx=24, pady=(0, 20))
            ctk.CTkButton(actions, text="Fechar" if read_only else "Cancelar", fg_color="#E0E8E6", text_color="#263D3A",
                          command=close).pack(side="left", padx=(0, 8))
            dialog.startup_timers.append(dialog.after(100, dialog.grab_set))
            self.update_runtime()
            return dialog, form, error_label, actions, close

        def finish_edit(self, operation, error_label, close):
            if self.closing or self.closed:
                return
            try:
                operation()
            except ConfigError as exc:
                error_label.configure(text=str(exc))
                return
            close()
            self.render()
            self.notify("Rascunho atualizado. Clique em Salvar para gravar.")

        def edit_window(self, index=None, *, context=None):
            if not self.navigation_available() or self.confirming_rule_removal:
                return False
            if index is not None:
                context = self.action_context("windows", index) if context is None else context
                if type(index) is not int or not self.action_is_current(context) or context[1:3] != ("windows", index):
                    return False
            draft, config = session.draft, session.draft.config
            value = None if index is None else config.windows[index]
            dialog, form, error, actions, close = self.new_dialog("Adicionar horário" if index is None else "Editar horário")
            if not self.form_is_current(dialog, draft, config, error):
                return False
            dialog.geometry("560x470")
            ctk.CTkLabel(form, text="Início (HH:MM)", anchor="w").grid(row=0, column=0, sticky="w")
            start = ctk.CTkEntry(form, placeholder_text="HH:MM")
            start.grid(row=1, column=0, sticky="ew", pady=(0, 8))
            ctk.CTkLabel(form, text="Fim (HH:MM)", anchor="w").grid(row=2, column=0, sticky="w")
            end = ctk.CTkEntry(form, placeholder_text="HH:MM")
            end.grid(row=3, column=0, sticky="ew", pady=(0, 10))
            if value is not None:
                start.insert(0, value.start.strftime("%H:%M"))
                end.insert(0, value.end.strftime("%H:%M"))
            checks = ctk.CTkFrame(form, fg_color="transparent")
            checks.grid(row=4, column=0, sticky="ew")
            selected = []
            for day, label in enumerate(days):
                variable = tk.IntVar(value=int(value is None or day in value.days))
                selected.append(variable)
                ctk.CTkCheckBox(checks, text=label, variable=variable, width=62, checkbox_width=18,
                                checkbox_height=18, fg_color=accent).grid(row=0, column=day, padx=(0, 6), pady=8)

            def form_is_current():
                return self.form_is_current(dialog, draft, config, error)

            def select_days(chosen):
                if not form_is_current():
                    return False
                for day, variable in enumerate(selected):
                    variable.set(int(day in chosen))
                return True

            presets = ctk.CTkFrame(form, fg_color="transparent")
            presets.grid(row=5, column=0, sticky="w", pady=(0, 4))
            for title, chosen, width in (("Todos", tuple(range(7)), 70), ("Seg–Sex", tuple(range(5)), 88),
                                         ("Fim de semana", (5, 6), 120), ("Nenhum", (), 80)):
                ctk.CTkButton(presets, text=title, width=width, fg_color=accent,
                              command=lambda days=chosen: select_days(days)).pack(side="left", padx=(0, 8))
            ctk.CTkLabel(form, text="Sem dias selecionados, o horário fica desativado.", text_color=muted
                         ).grid(row=6, column=0, sticky="w")

            def apply():
                final_days = {day for day, variable in enumerate(selected) if variable.get()}
                original_days = () if value is None else value.days
                chosen = [day for day in original_days if day in final_days]
                chosen.extend(day for day in range(7) if day in final_days and day not in original_days)
                if index is None:
                    draft.add_window(start.get().strip(), end.get().strip(), chosen)
                else:
                    draft.update_window(index, start.get().strip(), end.get().strip(), chosen)

            def apply_form():
                if not form_is_current():
                    return False
                self.finish_edit(apply, error, close)

            ctk.CTkButton(actions, text="Adicionar" if index is None else "Aplicar alteração", fg_color=accent,
                          command=apply_form).pack(side="left")
            dialog.startup_timers.append(dialog.after(150, start.focus_set))

        def edit_rule(self, index=None, field=None, *, context=None):
            if not self.navigation_available() or self.confirming_rule_removal:
                return False
            field = rule_fields[self.rule_category.get()] if field is None else field
            if field not in rule_fields.values():
                return False
            if index is not None:
                context = self.action_context(field, index) if context is None else context
                if type(index) is not int or not self.action_is_current(context) or context[1:3] != (field, index):
                    return False
            draft, config = session.draft, session.draft.config
            value = None if index is None else getattr(config, field)[index]
            dialog, form, error, actions, close = self.new_dialog("Adicionar regra" if index is None else "Editar regra")
            if not self.form_is_current(dialog, draft, config, error):
                return False
            label = "Pasta absoluta" if field == "block_folders" else "Executável (.exe)"
            ctk.CTkLabel(form, text=label, anchor="w").grid(row=0, column=0, sticky="w")
            name = ctk.CTkEntry(form)
            name.grid(row=1, column=0, sticky="ew", pady=(0, 10))
            if value is not None:
                name.insert(0, value.executable if field == "block_cmdline" else value)
            contains = None
            if field == "block_cmdline":
                ctk.CTkLabel(form, text="Trecho literal da linha de comando", anchor="w").grid(row=2, column=0, sticky="w")
                contains = ctk.CTkEntry(form)
                contains.grid(row=3, column=0, sticky="ew", pady=(0, 10))
                if value is not None:
                    contains.insert(0, value.contains)
            elif field == "block_folders":
                def choose_folder():
                    if not self.form_is_current(dialog, draft, config, error):
                        return
                    try:
                        chosen = self.open_picker(filedialog.askdirectory, parent=dialog, title="Selecionar pasta")
                    except tk.TclError as exc:
                        if self.form_is_current(dialog, draft, config, error):
                            error.configure(text=f"Não foi possível abrir o seletor de pasta: {exc}")
                        return
                    if not chosen or not self.form_is_current(dialog, draft, config, error):
                        return
                    name.delete(0, "end")
                    name.insert(0, str(Path(chosen)))
                ctk.CTkButton(form, text="Escolher pasta…", fg_color=accent,
                              command=choose_folder).grid(row=2, column=0, sticky="w")
            ctk.CTkLabel(form, text=descriptions[field], text_color=muted, wraplength=500, justify="left"
                         ).grid(row=4, column=0, sticky="w", pady=14)

            def apply():
                entered = name.get().strip()
                if contains is not None:
                    entered = {"executable": entered, "contains": contains.get()}
                if index is None:
                    draft.add_rule(field, entered)
                else:
                    draft.update_rule(field, index, entered)

            def apply_form():
                if not self.form_is_current(dialog, draft, config, error):
                    return False
                self.finish_edit(apply, error, close)

            ctk.CTkButton(actions, text="Adicionar" if index is None else "Aplicar alteração", fg_color=accent,
                          command=apply_form).pack(side="left")
            dialog.startup_timers.append(dialog.after(150, name.focus_set))

        def import_config(self):
            if self.closing or self.closed or self.modal is not None or self.picker_active:
                return
            try:
                selected = self.open_picker(filedialog.askopenfilename, parent=self, title="Importar configuração JSON",
                                            filetypes=[("Configuração JSON", "*.json"), ("Todos os arquivos", "*.*")])
            except tk.TclError as exc:
                if not self.closing and not self.closed:
                    self.notify(f"Não foi possível abrir o seletor de importação: {exc}", error=True)
                return
            if not selected or self.closing or self.closed:
                return
            if not messagebox.askyesno(
                "Substituir rascunho", "Substituir todo o rascunho pelo JSON selecionado?\n"
                "Alterações não salvas e o histórico de edição serão descartados. "
                "O arquivo ativo só muda ao clicar em Salvar.", parent=self
            ):
                return
            if self.closing or self.closed:
                return
            try:
                session.import_config(selected)
            except ConfigError as exc:
                self.notify(f"Não foi possível importar: {exc}. Rascunho preservado.", error=True)
                return
            self.render()
            self.notify("JSON importado no rascunho. Clique em Salvar para gravar a configuração ativa.")

        def export_config(self):
            if self.closing or self.closed or self.modal is not None or self.picker_active:
                return
            try:
                selected = self.open_picker(filedialog.asksaveasfilename,
                    parent=self, title="Exportar rascunho para um novo JSON", defaultextension=".json",
                    filetypes=[("Configuração JSON", "*.json")], confirmoverwrite=False
                )
            except tk.TclError as exc:
                if not self.closing and not self.closed:
                    self.notify(f"Não foi possível abrir o seletor de exportação: {exc}", error=True)
                return
            if not selected or self.closing or self.closed:
                return
            try:
                session.export_config(selected)
            except ConfigError as exc:
                self.notify(f"Não foi possível exportar: {exc}. Escolha um destino novo.", error=True)
                return
            self.notify("Rascunho exportado. A exportação não salva a configuração ativa.")

        def save_config(self):
            if self.closing or self.closed:
                return False
            creating = session.is_new
            try:
                session.save()
            except ConfigConflictError as exc:
                self.notify(f"Conflito: {exc}. Seu rascunho foi preservado.", error=True)
                messagebox.showerror("Conflito de configuração", f"{exc}\n\nRecarregar descarta o rascunho e lê o arquivo atual.", parent=self)
                return False
            except ConfigError as exc:
                self.notify(f"Não foi possível salvar: {exc}", error=True)
                return False
            self.render()
            self.refresh_status(schedule=False)
            self.notify("Arquivo de configuração criado. Motor permanece parado." if creating else "Configuração salva.")
            return True

        def reload_config(self):
            if not self.navigation_available() or self.confirming_rule_removal:
                return False
            draft, config = session.draft, session.draft.config
            generation = self.review_generation
            history = draft.can_undo, draft.can_redo
            self.confirming_rule_removal = True
            try:
                if session.dirty and not messagebox.askyesno(
                    "Recarregar configuração", "Descartar as alterações não salvas e o histórico de edição e recarregar o arquivo?", parent=self
                ):
                    return False
                if (not self.navigation_available() or not self.model_is_current(draft, config)
                        or generation != self.review_generation or history != (draft.can_undo, draft.can_redo)):
                    return False
                try:
                    session.reload()
                except ConfigError as exc:
                    self.notify(f"Não foi possível recarregar: {exc}. Rascunho preservado.", error=True)
                    return False
                self.render()
                self.refresh_status(schedule=False)
                self.notify("Configuração recarregada.")
                return True
            finally:
                self.confirming_rule_removal = False
                if not self.closing and not self.closed:
                    self.update_rule_selection_controls()

        def refresh_status(self, *, schedule=True):
            if self.closing or self.closed:
                return
            self.drain_tray()
            if self.closing or self.closed:
                return
            status = session.agenda_status(datetime.now())
            self.configure_if_changed(self.agenda_label, text=("Agenda ainda não salva" if session.is_new else
                                             "Agenda carregada: dentro da janela" if status.active else "Agenda carregada: fora da janela"))
            self.configure_if_changed(self.next_label, text=("Salvar cria o arquivo; Iniciar continua exigindo confirmação." if session.is_new else
                "Próximo início: " + (status.next_start.strftime("%d/%m/%Y às %H:%M") if status.next_start else "nenhum horário ativo")))
            if session.is_new:
                ending = "Nenhuma janela salva em andamento."
            elif not status.active:
                ending = "Nenhuma janela carregada em andamento."
            elif status.current_end is None:
                ending = "Agenda carregada: cobertura semanal contínua, sem fim previsto."
            else:
                ending = "Fim da janela carregada: " + status.current_end.strftime("%d/%m/%Y às %H:%M")
            self.configure_if_changed(self.end_label, text=ending)
            self.configure_if_changed(self.agenda_hint, text=("Prévia do rascunho abaixo; motor parado até salvar e confirmar Iniciar." if session.is_new else
                                              "Consulta da agenda carregada; o estado do motor aparece acima."))
            self.update_runtime()
            if schedule and self.status_timer is None:
                self.status_timer = self.after(250, self.poll_status)

        def poll_status(self):
            self.status_timer = None
            self.refresh_status()

        def close_editor(self):
            if self.closing or self.closed:
                return
            self.restore_window()
            if session.dirty:
                answer = messagebox.askyesnocancel("Alterações não salvas", "Salvar as alterações antes de sair?", parent=self)
                if answer is None or (answer and not self.save_config()):
                    return
            self.closing = True
            self.stop_requested = True
            mailbox.close()
            controller.stop()
            tray.stop()
            if self.status_timer is not None:
                self.after_cancel(self.status_timer)
                self.status_timer = None
            self.dismiss_modal()
            self.disable_actions(self)
            self.notify("Fechando: aguardando motor e bandeja pararem…")
            self.poll_close()

        def disable_actions(self, frame):
            for child in frame.winfo_children():
                if isinstance(child, (ctk.CTkButton, ctk.CTkEntry, ctk.CTkCheckBox, ctk.CTkOptionMenu)):
                    child.configure(state="disabled")
                self.disable_actions(child)

        def poll_close(self):
            self.close_timer = None
            if controller.is_alive() or tray.is_alive():
                self.update_runtime()
                self.close_timer = self.after(100, self.poll_close)
            else:
                self.finish_close()

        def finish_close(self):
            if self.closed:
                return
            if controller.is_alive() or tray.is_alive():
                return
            self.closing = True
            mailbox.close()
            for timer in (self.status_timer, self.close_timer):
                if timer is not None:
                    self.after_cancel(timer)
            self.status_timer = self.close_timer = None
            self.dismiss_modal()
            # A raiz possui seu próprio interpretador. Inclui callbacks CTk
            # (DPI/aparência/scrollbars), que não podem sobreviver à sua saída.
            if hasattr(self, "tk"):
                for timer in self.tk.splitlist(self.tk.call("after", "info")):
                    # Cancelar no Tcl mantém a propriedade dos comandos Python:
                    # cada widget os remove uma única vez no seu destroy().
                    self.tk.call("after", "cancel", timer)
            self.closed = True
            self.destroy()

    return Editor()

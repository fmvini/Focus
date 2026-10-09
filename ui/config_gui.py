"""Editor gráfico independente; não importa nem inicia bloqueadores."""

from datetime import datetime
from pathlib import Path
import sys

from core.config import ConfigError
from core.config_repository import ConfigConflictError
from core.config_session import ConfigSession


def run_config_gui(path: str | Path) -> int:
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
        session = ConfigSession(path)
    except ConfigError as exc:
        print(
            f"Erro ao abrir configuração: {exc}. Se o arquivo ainda não existe, "
            "crie-o com --config PATH --init-config antes de usar --gui.",
            file=sys.stderr,
        )
        return 1

    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    try:
        app = _build_app(ctk, tk, filedialog, messagebox, session)
        app.mainloop()
        return 0
    except tk.TclError as exc:
        print(f"Erro ao iniciar interface gráfica: {exc}", file=sys.stderr)
        return 1


def _build_app(ctk, tk, filedialog, messagebox, session):
    """Constrói widgets somente quando a GUI é solicitada."""
    accent = "#167D77"
    muted = "#52656A"
    days = ("Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom")
    rule_fields = {
        "Executáveis": "block_exes",
        "Pastas": "block_folders",
        "Proteção adicional": "safelist_exes",
        "Linha de comando": "block_cmdline",
    }
    descriptions = {
        "block_exes": "Nomes completos, como jogo.exe. A comparação ignora maiúsculas e minúsculas.",
        "block_folders": "Pastas absolutas do Windows. As regras incluem subpastas.",
        "safelist_exes": "Aplicativos que devem ser preservados. As proteções obrigatórias continuam valendo.",
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

            summary = ctk.CTkFrame(self, fg_color="white", corner_radius=12)
            summary.grid(row=1, column=0, sticky="ew", padx=28, pady=(0, 12))
            summary.grid_columnconfigure(0, weight=1)
            self.agenda_label = ctk.CTkLabel(summary, text="", anchor="w",
                                            font=ctk.CTkFont(size=17, weight="bold"))
            self.agenda_label.grid(row=0, column=0, sticky="ew", padx=18, pady=(12, 0))
            self.next_label = ctk.CTkLabel(summary, text="", anchor="w", text_color=muted)
            self.next_label.grid(row=1, column=0, sticky="ew", padx=18)
            ctk.CTkLabel(summary, text="Consulta da agenda carregada. Este editor não inicia bloqueios.",
                         text_color=muted, anchor="w").grid(row=2, column=0, sticky="ew", padx=18, pady=(0, 12))

            self.tabs = ctk.CTkTabview(self, fg_color="white", segmented_button_selected_color=accent,
                                       segmented_button_selected_hover_color="#10645F")
            self.tabs.grid(row=2, column=0, sticky="nsew", padx=28)
            schedules = self.tabs.add("Horários")
            processes = self.tabs.add("Jogos / Apps")
            settings = self.tabs.add("Configuração")
            for tab in (schedules, processes):
                tab.grid_columnconfigure(0, weight=1)
                tab.grid_rowconfigure(2, weight=1)

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
            ctk.CTkButton(processes, text="Adicionar regra", fg_color=accent,
                          command=self.edit_rule).grid(row=0, column=1, padx=14, pady=(10, 0))
            self.rule_description = ctk.CTkLabel(processes, text="", text_color=muted, anchor="w", wraplength=760)
            self.rule_description.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=10)
            self.rules_list = ctk.CTkScrollableFrame(processes, fg_color="#F3F6F5")
            self.rules_list.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=14, pady=(0, 14))
            self.rules_list.grid_columnconfigure(0, weight=1)

            settings.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(settings, text="Arquivo de configuração", font=ctk.CTkFont(size=20, weight="bold"),
                         anchor="w").grid(row=0, column=0, sticky="w", padx=18, pady=(18, 8))
            path_box = ctk.CTkTextbox(settings, height=70, wrap="word", fg_color="#F3F6F5")
            path_box.grid(row=1, column=0, sticky="ew", padx=18)
            path_box.insert("1.0", str(session.path.absolute()))
            path_box.configure(state="disabled")
            ctk.CTkLabel(settings, justify="left", anchor="nw", wraplength=730, text=(
                "As alterações ficam em um rascunho até você clicar em Salvar.\n\n"
                "Recarregar lê o arquivo novamente e descarta o rascunho. Se outro editor alterar "
                "o arquivo, o Focus informa o conflito antes de salvar.\n\n"
                "Um bloqueador iniciado separadamente pode ler os horários e regras salvos no próximo ciclo.\n\n"
                "Bloqueio de sites, pausa, bandeja e estatísticas serão adicionados em etapas futuras."
            )).grid(row=2, column=0, sticky="ew", padx=18, pady=18)

            footer = ctk.CTkFrame(self, fg_color="transparent")
            footer.grid(row=3, column=0, sticky="ew", padx=28, pady=16)
            footer.grid_columnconfigure(0, weight=1)
            self.feedback = ctk.CTkLabel(footer, text="", anchor="w", justify="left", wraplength=560, text_color=muted)
            self.feedback.grid(row=0, column=0, sticky="ew", padx=(0, 12))
            ctk.CTkButton(footer, text="Recarregar", width=110, fg_color="#E0E8E6", text_color="#263D3A",
                          hover_color="#CEDAD7", command=self.reload_config).grid(row=0, column=1, padx=(0, 8))
            ctk.CTkButton(footer, text="Salvar", width=110, fg_color=accent,
                          command=self.save_config).grid(row=0, column=2)
            self.bind("<Control-s>", lambda _: self.save_config() if self.modal is None else None)
            self.bind("<Control-r>", lambda _: self.reload_config() if self.modal is None else None)
            self.render()
            self.refresh_status()

        def notify(self, text, *, error=False):
            self.feedback.configure(text=text, text_color="#A33232" if error else muted)

        def render(self):
            self.render_windows()
            self.render_rules()
            self.dirty_label.configure(text="Alterações não salvas" if session.dirty else "Sem alterações pendentes")

        @staticmethod
        def clear(frame):
            for child in frame.winfo_children():
                child.destroy()

        def item_row(self, frame, index, title, detail, edit, remove):
            row = ctk.CTkFrame(frame, fg_color="white", corner_radius=8)
            row.grid(row=index, column=0, sticky="ew", pady=(0, 8))
            row.grid_columnconfigure(0, weight=1)
            ctk.CTkLabel(row, text=title, anchor="w", justify="left", wraplength=540,
                         font=ctk.CTkFont(size=16, weight="bold")).grid(row=0, column=0, sticky="ew", padx=14, pady=(10, 0))
            ctk.CTkLabel(row, text=detail, text_color=muted, anchor="w", justify="left", wraplength=540
                         ).grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
            ctk.CTkButton(row, text="Editar", width=75, fg_color=accent,
                          command=edit).grid(row=0, column=1, rowspan=2, padx=6)
            ctk.CTkButton(row, text="Remover", width=85, fg_color="#E0E8E6", text_color="#263D3A",
                          hover_color="#CEDAD7", command=remove).grid(row=0, column=2, rowspan=2, padx=(0, 12))

        def render_windows(self):
            self.clear(self.windows_list)
            windows = session.draft.config.windows
            if not windows:
                ctk.CTkLabel(self.windows_list, text="Nenhum horário cadastrado.\nAdicione seu primeiro horário para começar.",
                             text_color=muted).grid(row=0, column=0, pady=45)
            for index, window in enumerate(windows):
                day_text = ", ".join(days[day] for day in window.days) or "Desativado — nenhum dia selecionado"
                self.item_row(self.windows_list, index,
                              f"{window.start:%H:%M} → {window.end:%H:%M}", day_text,
                              lambda i=index: self.edit_window(i),
                              lambda i=index: self.remove_item("windows", i))

        def render_rules(self):
            self.clear(self.rules_list)
            field = rule_fields[self.rule_category.get()]
            self.rule_description.configure(text=descriptions[field])
            values = getattr(session.draft.config, field)
            if not values:
                ctk.CTkLabel(self.rules_list, text="Nenhuma regra nesta lista.", text_color=muted
                             ).grid(row=0, column=0, pady=45)
            for index, value in enumerate(values):
                title = value.executable if field == "block_cmdline" else value
                detail = f"Contém: {value.contains}" if field == "block_cmdline" else self.rule_category.get()
                self.item_row(self.rules_list, index, title, detail,
                              lambda i=index: self.edit_rule(i),
                              lambda i=index, f=field: self.remove_item(f, i))

        def remove_item(self, field, index):
            if not messagebox.askyesno("Remover item", "Remover este item do rascunho?", parent=self):
                return
            if field == "windows":
                session.draft.remove_window(index)
            else:
                session.draft.remove_rule(field, index)
            self.render()
            self.notify("Item removido do rascunho. Clique em Salvar para gravar.")

        def new_dialog(self, title):
            dialog = ctk.CTkToplevel(self)
            dialog.title(title)
            dialog.geometry("560x430")
            dialog.resizable(False, False)
            dialog.transient(self)
            dialog.grid_columnconfigure(0, weight=1)
            self.modal = dialog
            dialog.startup_timers = []

            def close():
                for timer in dialog.startup_timers:
                    dialog.after_cancel(timer)
                self.modal = None
                dialog.destroy()

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
            ctk.CTkButton(actions, text="Cancelar", fg_color="#E0E8E6", text_color="#263D3A",
                          command=close).pack(side="left", padx=(0, 8))
            dialog.startup_timers.append(dialog.after(100, dialog.grab_set))
            return dialog, form, error_label, actions, close

        def finish_edit(self, operation, error_label, close):
            try:
                operation()
            except ConfigError as exc:
                error_label.configure(text=str(exc))
                return
            close()
            self.render()
            self.notify("Rascunho atualizado. Clique em Salvar para gravar.")

        def edit_window(self, index=None):
            dialog, form, error, actions, close = self.new_dialog("Adicionar horário" if index is None else "Editar horário")
            value = None if index is None else session.draft.config.windows[index]
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
            ctk.CTkLabel(form, text="Sem dias selecionados, o horário fica desativado.", text_color=muted
                         ).grid(row=5, column=0, sticky="w")

            def apply():
                chosen = [day for day, variable in enumerate(selected) if variable.get()]
                if index is None:
                    session.draft.add_window(start.get().strip(), end.get().strip(), chosen)
                else:
                    session.draft.update_window(index, start.get().strip(), end.get().strip(), chosen)

            ctk.CTkButton(actions, text="Adicionar" if index is None else "Aplicar alteração", fg_color=accent,
                          command=lambda: self.finish_edit(apply, error, close)).pack(side="left")
            dialog.startup_timers.append(dialog.after(150, start.focus_set))

        def edit_rule(self, index=None):
            field = rule_fields[self.rule_category.get()]
            dialog, form, error, actions, close = self.new_dialog("Adicionar regra" if index is None else "Editar regra")
            value = None if index is None else getattr(session.draft.config, field)[index]
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
                    chosen = filedialog.askdirectory(parent=dialog, title="Selecionar pasta")
                    if chosen:
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
                    session.draft.add_rule(field, entered)
                else:
                    session.draft.update_rule(field, index, entered)

            ctk.CTkButton(actions, text="Adicionar" if index is None else "Aplicar alteração", fg_color=accent,
                          command=lambda: self.finish_edit(apply, error, close)).pack(side="left")
            dialog.startup_timers.append(dialog.after(150, name.focus_set))

        def save_config(self):
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
            self.notify("Configuração salva.")
            return True

        def reload_config(self):
            if session.dirty and not messagebox.askyesno(
                "Recarregar configuração", "Descartar as alterações não salvas e recarregar o arquivo?", parent=self
            ):
                return
            try:
                session.reload()
            except ConfigError as exc:
                self.notify(f"Não foi possível recarregar: {exc}. Rascunho preservado.", error=True)
                return
            self.render()
            self.refresh_status(schedule=False)
            self.notify("Configuração recarregada.")

        def refresh_status(self, *, schedule=True):
            status = session.agenda_status(datetime.now())
            self.agenda_label.configure(text="Agenda carregada: dentro da janela" if status.active else "Agenda carregada: fora da janela")
            self.next_label.configure(text="Próximo início: " + (status.next_start.strftime("%d/%m/%Y às %H:%M") if status.next_start else "nenhum horário ativo"))
            if schedule:
                self.status_timer = self.after(1000, self.refresh_status)

        def close_editor(self):
            if session.dirty:
                answer = messagebox.askyesnocancel("Alterações não salvas", "Salvar as alterações antes de sair?", parent=self)
                if answer is None or (answer and not self.save_config()):
                    return
            if self.status_timer is not None:
                self.after_cancel(self.status_timer)
            if self.modal is not None:
                for timer in self.modal.startup_timers:
                    self.modal.after_cancel(timer)
                self.modal.destroy()
                self.modal = None
            self.destroy()

    return Editor()

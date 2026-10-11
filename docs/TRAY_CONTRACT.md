# Contrato — bandeja e instância gráfica

Unidade 2026-10-11, continuação autorizada pelo usuário. Complementa controle
gráfico de processos; não conclui a fase 5 inteira.

## Comportamento

- A janela e o motor continuam abrindo visíveis e parados. Fechar pelo X
  continua resolvendo rascunho e saindo com parada ordenada.
- Botão explícito **Enviar à bandeja** mantém motor/rascunho e só oculta a
  janela quando o ícone estiver pronto. Falha mantém/restaura janela visível.
- Menu: **Mostrar Focus** (ação padrão), **Parar motor**, **Sair**. Não iniciar
  motor pelo menu; confirmação e revisão continuam na janela.
- Mostrar restaura janela. Sair restaura antes de resolver salvar/descartar/
  cancelar; cancelamento mantém janela e motor. Parar fecha gate no polling Tk.
- Callbacks pystray apenas publicam comandos; nunca acessam Tk nem controller.
  Timer Tk existente drena caixa limitada e executa ações na thread principal.
- Encerramento solicita stop do ícone e aguarda sua thread fora de callbacks.
  Não deixar thread não daemon viva na saída nem ocultar sem ícone pronto.
- Uma GUI por caminho normalizado de configuração na sessão Windows. Segunda
  abertura informa erro e não cria janela/motor. CLI continua independente.
  Não implementar IPC, ativação da janela existente, auto-start ou elevação.

## APIs e ownership

Backend: `core/instance_guard.py`, `tests/test_instance_guard.py`.

- `InstanceGuard(path, *, backend=None)`, construção sem efeitos.
- `acquire() -> bool`: true se detém guarda; false se nome já existente;
  falha de SO levanta `InstanceGuardError`. `release() -> None` idempotente.
- Windows: CreateMutexW com initial owner false, handle mantido e CloseHandle
  na liberação. Nome Local\\Focus.Gui.<SHA256 do caminho resolve/normcase>.
  Não bloquear esperando mutex nem apagar arquivos. Não garante aliases de
  hardlinks, diferentes sessões Windows ou watcher CLI.
- Backend injetável: `create_mutex(name) -> (handle, already_exists: bool)` e
  `close_handle(handle) -> None`; erros levantam exceções. Handle preservado
  para retry se fechamento falhar; não abandonar silenciosamente a guarda.

Banco: `ui/tray_commands.py`, `tests/test_tray_commands.py`,
`tests/test_instance_guard_integration.py`.

- `TrayCommand(action: str, detail: str | None = None)` frozen.
- `TrayMailbox.post(action, detail=None) -> None`, `drain() -> tuple[TrayCommand,...]`,
  `close() -> None`. Actions show/stop/close/ready/error, desconhecida ValueError.
  Coalescer por action, preservar ordem da primeira ocorrência e último detail;
  até cinco pendentes. close descarta fila e ignora posts posteriores.
- Sem Tk/pystray/psutil/IO no módulo. Testes reais de mutex subprocesso usam
  somente nomes derivados de fixtures isoladas; nenhum bloqueador real.

Frontend: `ui/windows_tray.py`, `ui/config_gui.py`, testes GUI/tray relacionados.

- `WindowsTray(mailbox, *, icon_factory=None)`, `start() -> None` não bloqueante,
  `stop() -> None`, `is_alive() -> bool`, `wait(timeout=None) -> None` fora de Tk.
  Fábrica lazy pystray/Pillow no worker, imagem pequena desenhada em código.
  Setup só publica ready depois de icon.visible confirmado; failures publicam
  error e nunca chamam Tk. stop durante startup deve impedir publicação/ícone
  tardio; callbacks depois de close não têm efeito.
  Adapter Windows verifica BOOL de Shell_NotifyIconW em NIM_ADD: false é erro,
  sem ready/ocultação. Não usar apenas flag visible interna como prova de criação.
  Não verifica se usuário viu ícone (ele pode ficar no overflow da bandeja).
  `icon_factory(callbacks)` recebe show/stop/close para MenuItem e
  `error(detail)` para falhas nativas, inclusive reconstituição do ícone após
  Explorer reiniciar. Error publica só mailbox; polling Tk restaura janela.
- `_build_app(..., controller=None, tray=None, mailbox=None)` mantém injeção.
  run_config_gui detém InstanceGuard até finalizar motor, ícone e janela.
  GUI polling de saída aguarda ambos os workers. Finally stop/wait ambos;
  libera guarda por último, inclusive exceções.

Maestro: `main.py`, dependências, contrato/documentação/log, integração e commit.
Não editar arquivos em trabalho de outro agente; sem commits individuais/push.

## Fontes técnicas

- [pystray usage](https://pystray.readthedocs.io/en/latest/usage.html): run em
  worker é suportado para Windows; setup indica ícone pronto; stop encerra loop.
- [CreateMutexW](https://learn.microsoft.com/en-us/windows/win32/api/synchapi/nf-synchapi-createmutexw):
  handle e ERROR_ALREADY_EXISTS; [CloseHandle](https://learn.microsoft.com/en-us/windows/win32/api/handleapi/nf-handleapi-closehandle).
- [Shell_NotifyIconW](https://learn.microsoft.com/en-us/windows/win32/api/shellapi/nf-shellapi-shell_notifyiconw):
  retorna true em sucesso e false em falha; pystray 0.19.5 ignora retorno em
  _message, exigindo verificação no adapter de NIM_ADD antes de ready.
- [pystray 0.19.5](https://pypi.org/project/pystray/0.19.5/) e
  [Pillow 12.3.0](https://pypi.org/project/pillow/12.3.0/) fixados em requisitos
  e instalados no `.venv` com wheel cp314 Windows. Importação somente ao usar
  bandeja, sem quebrar CLI.

## Validação

Testar ocultar só após ready, startup/erro/stop concorrentes, show/close com
rascunho/modal, saída/cancelamento, fila limitada, teardown de callbacks e mutex
entre processos/recuperação após crash. Nenhum aplicativo do usuário encerrado.
Registrar separadamente smoke nativo, inspeção visual/DPI e bandeja real.

## Evidência de guarda e mailbox

- Backend/Banco: 52 testes aprovados no Windows, sem skips: 33 guard (inclui
  quatro mutexes nativos), seis integrações reais entre subprocessos e 13 mailbox.
- Guard cobre assinatura HANDLE de 64 bits, last-error, colisão nativa com
  Event, concorrência local, aliases relativos/case, release em outra thread,
  recusa/liberação/crash entre processos. Nenhum JSON é lido/modificado.
- Mailbox cobre cinco produtores/5000 posts, consumidores concorrentes,
  drain/close concorrentes, frozen, import independente e até cinco pendências.
- Runtime validado é Python 3.14.6/Windows 10 build 19045. Sintaxe 3.12 não
  substitui ensaio de runtime 3.12; sessões distintas/hardlinks/IPC fora do escopo.
- Maestro confirmou entrada real `main.py --gui` em subprocesso enquanto
  guarda da mesma fixture estava detida: retorno 1 com mensagem de instância
  existente, sem janela/motor nem alteração dos bytes do JSON.

## Evidência integrada final

- Suíte final fora do sandbox: 503 descobertos, 502 aprovados e um skip conhecido
  de symlink/WinError 1314, em 30,474 s. Inclui dez nativeGUI, 14 tray, 52
  guard/mailbox, 41 fakeGUI, 13 mainGUI e regressões anteriores.
- Smoke real: Shell aceitou NIM_ADD, ready e stop completaram com worker/setup
  encerrados. Não abriu menu nem iniciou motor. Dentro do sandbox, ADD foi
  recusado explicitamente; não foi ignorado ou marcado como skip.
- Falha de ADD após reconstituição por Explorer publica error mesmo quando
  dispatcher pystray mantém loop vivo; polling restaura janela e preserva motor.
  Testado com API nativa falsa, sem reiniciar Explorer real.
- Captura visual tentou novamente/reselecionou e falhou duas vezes por timeout;
  inspeção visual/DPI/menu permanece pendente. Runtime 3.12 não executado;
  AST 3.12/UTF-8 conferidos nos 49 arquivos Python.

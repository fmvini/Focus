# Contrato — controle gráfico do bloqueador de processos

Unidade autorizada em 2026-10-11, após commit `7ed71d4` da evolução do editor.
Coordenação pelo Maestro no Maestri; reutiliza o bloqueador de processos e
suas proteções conforme [PHASE2_CONTRACT.md](PHASE2_CONTRACT.md).

## Comportamento

- Abrir `--gui` mantém o motor parado. Iniciar exige confirmação explícita
  de que aplicativos elegíveis podem ser encerrados sem salvar seu estado.
  Rascunho pendente deve ser salvo ou descartado antes de iniciar.
- Motor usa exclusivamente o JSON persistido, validado a cada ciclo, relógio
  local real e gates antes de efeitos. Alterações do rascunho não mudam o motor;
  um Salvar bem-sucedido pode ser observado no próximo ciclo.
- Thread dedicada executa ciclos sem sobreposição, com cadência monotônica
  de 5 s e espera interrompível. Nenhum widget é acessado pelo worker.
- Parar fecha o gate imediatamente e sinaliza a thread; a UI mostra Parando
  até ela terminar. Uma chamada já iniciada pode completar; parar não reabre
  aplicativos. Não fazer novas solicitações de encerramento com gate fechado.
- Estado do motor, resultado do último ciclo e erro ficam separados da
  consulta da agenda e da prévia do rascunho. Motor em execução não equivale
  a bloqueio confirmado; falha por alvo e falha global permanecem visíveis.
- JSON inválido/ausente e falha global param novas ações, com erro explícito;
  não reutilizar configuração antiga. Novo Iniciar explícito permite retry.
- Fechar trata alterações pendentes primeiro; cancelamento mantém a execução.
  Após decisão de sair, solicitar parada e aguardar por polling Tk, sem join
  bloqueante em callback. Só destruir a janela depois do worker encerrar.
- Não implementar sites/hosts, pausa, bandeja, SQLite ou auto-start nesta unidade.
  CLI de aplicação continua disponível e não é controlada por esta janela.

## API compartilhada

`core/process_controller.py`:

- `ProcessController(path, *, blocker_factory=None, interval=5.0, clock=None,
  loader=None, monotonic=None, waiter=None)`: fronteiras injetáveis para testes.
  Defaults: fábrica sem args, `load_config(path)`, `datetime.now`,
  `time.monotonic` e espera `Event.wait`. Construção sem IO,
  importação de psutil ou criação de worker. Fábrica padrão lazy no worker.
- `start() -> bool`: inicia apenas se não houver worker vivo; false se já
  iniciando/executando/parando. Retry após erro exige worker anterior terminado.
- `stop() -> None`: idempotente, não bloqueante, fecha gate e interrompe espera.
- `snapshot() -> RuntimeSnapshot`: dados imutáveis com `state` (`idle`,
  `running`, `stopping`, `error`), `active: bool | None`,
  `last_scan: datetime | None`, `report: ScanReport | None`, `error: str | None`.
  `active` é a última avaliação da agenda, preservada ao parar/errar, não o
  Event de autorização. Avaliação e `last_scan` são publicados juntos; uma
  avaliação atrasada após stop concorrente não modifica o snapshot.
- `is_alive() -> bool`, `wait(timeout=None)`: consulta e espera explícita para
  testes/saída fora de callback; GUI usa polling. Sem workers daemon abandonados.

`ui/runtime_presenter.py`:

- `RuntimeView(title, detail, start_enabled, stop_enabled)` e
  `format_runtime(snapshot) -> RuntimeView`: tradução pura de estados/relatórios,
  contagem do último ciclo sem inventar histórico ou medição de foco.
  Encerramentos confirmados contam `events`; pendências/falhas contam results.
  Erro global preserva causa e relatório parcial, quando fornecido. Presenter
  limita a três linhas de diagnóstico, informa excedentes e limita campos,
  sem importar controlador/psutil/Tk. GUI mostra detail integral em textbox
  somente leitura/rolável, com guardas adicionais de worker vivo/modal/saída.

`ui/config_gui.py`:

- `_build_app(..., session, controller=None)` recebe controlador opcional para
  testes. Cabeçalho do motor e botões Iniciar/Parar; atualização pelo timer Tk.
  Caminho salvo usado pelo controlador; importação continua apenas no rascunho.
- `run_config_gui` garante sinalização de parada ao sair do mainloop, inclusive
  erro/KeyboardInterrupt; espera fora de callbacks quando necessária.

## Divisão e validação

- Backend: controlador/worker e testes de lifecycle/gates/cadência/falhas.
- Banco: presenter puro e testes com JSON real de recarga, conflitos e erros
  do controlador; sem alterações concorrentes no controlador ou na GUI.
- Frontend: GUI, lifecycle da janela e testes simulados/nativos correspondentes.
- Maestro: revisão/integração, documentos e commit local único com testes.

Testar início duplicado, parar na espera/durante scan, gate antes de terminate
e kill, retry, saída/cancelamento, recarga externa inválida, config salva versus
rascunho e estados sem widgets reais. Não encerrar aplicativos do usuário nos
testes. Inspeção visual e aceites Windows reais devem ser registrados à parte.

## Evidência integrada — 2026-10-11

- `.venv/Scripts/python.exe -B -m unittest discover -s tests`: **426 testes,
  425 aprovados e 1 ignorado**, 37,077 s em Python 3.14.6/Windows. Skip é symlink
  sem privilégio (WinError 1314), não relacionado ao controlador.
- Oito smoke tests de widgets reais passaram, incluindo polling de saída e
  limpeza de after callbacks sem bgerrors. Formulários/linhas cancelam apenas
  callbacks da própria árvore; saída cancela os after do próprio interpretador.
- Configuração/agenda reais e adaptadores controlados testam reload por ciclo,
  rascunho versus save, conflitos, erro sem baseline antigo, cadência, races,
  gate antes de terminate/kill e retry. Nenhum motor real iniciou nos testes.
- Janela de QA aberta com JSON isolado/alvos vazios e motor parado. Captura
  falhou com `FrameArrived timed out` e, após reseleção, `window capture timed
  out`; nenhuma interação gráfica foi realizada. Inspeção visual/DPI pendente.
- Parada é cooperativa: IO/factory/scan que não retorna pode prolongar saída.
  Encerramentos Windows reais, runtime Python 3.12 e fase 5 completa pendentes.

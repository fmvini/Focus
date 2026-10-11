# Contrato — primeira configuração gráfica

Unidade de continuidade de 2026-10-11. D13 já confirma configuração antes de
ativar, horários inicialmente vazios e listas do escopo apresentadas como
sugestões. Este contrato não fecha decisões de avisos, pausa ou sites.

## Comportamento

- `--gui` abre configuração existente como antes. Somente destino realmente
  ausente permite abrir um rascunho inicial; arquivo inválido, diretório,
  permissão negada e symlink quebrado não são substituídos.
- O rascunho inicial começa sem horários ou regras. A janela informa que o
  arquivo ainda não foi criado; Salvar cria explicitamente. Cancelar/descartar
  saída não grava nada. Motor começa parado e não pode iniciar antes de salvar.
- Horários, CRUD, prévia, importação e exportação reutilizam o editor existente.
  Sugestões de executáveis do §6 são opt-in, inicialmente desmarcadas, editáveis
  após inclusão. Não descobrir instalações nem sugerir pastas por adivinhação.
  Minecraft Java usa executável `javaw.exe` junto ao trecho `.minecraft`, nunca
  somente o nome. Proteções obrigatórias permanecem prioritárias.
- Sugestões só alteram o rascunho. Nenhum horário ou motor é ativado ao incluí-las
  ou salvar. Um próximo Iniciar continua exigindo confirmação explícita.
- Primeira gravação prepara JSON completo e publica exclusivamente, recusando
  qualquer destino existente, inclusive criado concorrentemente. Falha conserva
  o rascunho. Não reutilizar publicação por replace para primeira criação.
- Guarda gráfica é adquirida antes da sessão e mantida até finalizar os workers.
  Cancelar criação/erro respeita a saída ordenada já existente.

## APIs e propriedade dos arquivos

Backend: somente novo `core/initial_setup.py` e `tests/test_initial_setup.py`.

- `ProcessSuggestion(key: str, label: str, executable: str, contains: str | None = None)` frozen.
- `PROCESS_SUGGESTIONS: tuple[ProcessSuggestion, ...]`, nomes exatos do §6.
- `with_process_suggestions(config: AppConfig, keys: Iterable[str]) -> AppConfig`:
  cópia validada, só IDs selecionados, consumo único, ordem do catálogo, sem
  duplicar nomes existentes por casefold ou pares executable/contains por
  casefold. Preserve duplicatas preexistentes, extras, horários e demais regras.
  IDs inválidos/iterable com falha não publicam resultado parcial. Sem IO,
  descoberta, relógio, psutil ou GUI. Selecionar vazio retorna cópia validada.

Banco: `core/config_session.py`, `core/config_portability.py` e testes relacionados;
novo `tests/test_initial_setup_integration.py` se necessário.

- `ConfigSession.for_new(path) -> ConfigSession`: criação explícita de sessão
  nova, somente destino ausente; não cria diretórios/JSON. `snapshot` fica None,
  `draft` vazio, `is_new` bool; `dirty` True enquanto não publicada, mesmo vazio.
- Construtor normal permanece estrito. `save()` em sessão nova publica JSON
  completo exclusivamente e adota snapshot dos próprios bytes, sem reler/adotar
  escritor posterior. Em sucesso `is_new` False; erro não modifica a sessão.
- `agenda_status(now)` em nova sessão retorna inactive/next_start None porque
  nenhuma agenda foi salva. Import só rascunho/export não altera estado novo.
  `reload()` continua leitura estrita e só substitui sessão em sucesso.
- Reutilizar primitivas de exportação para criação exclusiva, preservando todos
  os limites/recusas/cleanup da exportação. API pública adicional coordenada
  com Frontend antes de implementação. Não alterar config/repository/editor.

Frontend: `ui/config_gui.py`, `tests/test_config_gui.py`,
`tests/test_config_gui_main.py`, `tests/test_config_gui_native.py`.

- Após ConfigSession estrita falhar por FileNotFoundError de leitura, tentar
  for_new, que reconfere ausência por lstat. Nunca usar exists para tratar erro
  de leitura/JSON como primeira execução.
- Exibir orientação inicial, destino e Salvar para criar; sugestões explícitas
  por seleção e botão Adicionar selecionadas. Sem seleção, nenhum efeito.
- Preservar confirmação dirty/modal/saída, tray/finally/guard/atalhos/conflitos.
  Iniciar e agenda carregada não fingem configuração salva. Resumo/feedback
  relê sessão após save/reload/import/sugestões. CTk real testável sem processos.

Maestro: `main.py`, docs/log, perguntas pendentes em USER_ANSWERS, integração,
testes completos e commit local conjunto. Sem alterações cruzadas, commits
individuais ou push. Cada agente coordena API por maestri ask e informa lote
final/limites por `maestri ask Maestro` (ask back), congelando edits ao terminar.

## Validação

JSON ausente ainda ausente após abrir/cancelar/exportar; primeira gravação
roundtrip completo, concorrência e falhas sem sobrescrita; arquivo inválido e
aliases preservados; import/save/reload/conflict; sugestões selecionadas e Java
conjunto; GUI primeira execução/iniciar/saída/modal/tray/teardown. Fixtures
isoladas, nenhum aplicativo do usuário encerrado. Runtime 3.12 e inspeção
visual/DPI registrados separadamente dos testes de sintaxe/widgets.

## Entrega integrada

Backend implementou catálogo/testes, Banco iniciou sessão/publicação e Frontend
integrou GUI/fluxos/mainGUI. Os três pararam por limite de uso; Maestro assumiu
finalização, corrigiu recusa de active_path None na exportação, completou testes
de criação/publicação e nativeGUI, revisou e executou integração final.

- API adicional: `create_new_config(path, config) -> ConfigSnapshot`, em
  config_portability, valida/prepara bytes/snapshot antes de efeitos e publica
  exclusivamente; sessão adota somente o retorno em sucesso.
- Suíte completa: 551 descobertos, 550 aprovados e um skip symlink/WinError 1314,
  38,140 s, Python 3.14.6/Windows. Doze nativeGUI e bandeja real passaram.
- Sintaxe 3.12 nos 52 arquivos Python, UTF-8, links locais e diff conferidos.
  Runtime 3.12 e inspeção visual/DPI não executados. Nenhum processo do usuário
  ou hosts alterado. Resultados detalhados em TEST_PLAN/DEVELOPMENT_LOG.
- Publicação Windows usa rename exclusivo e POSIX usa link, sem replace/fallback
  sobrescritor. Falha de limpeza POSIX após publicar pode deixar arquivo completo
  e sessão ainda nova; Recarregar recupera pela leitura estrita. Diretórios
  preparados podem permanecer em falha. Sem garantia absoluta em crash ou lock
  contra alteração adversarial de diretórios; mesmas fronteiras da exportação.

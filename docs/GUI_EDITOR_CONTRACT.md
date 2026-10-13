# Contrato — editor gráfico de configuração

Continuidade autorizada em 2026-10-09. Unidade complementar às fases 1/2,
independente das respostas ainda vazias Q-HOSTS-01–05. Implementa edição
gráfica de RF01 e parte de RF24; a fase 5 completa permanece pendente.

## Escopo implementado

Evolução em 2026-10-11: a quarta aba **Visão geral** acrescenta painel semanal
do rascunho e orientação inicial; horários ganham duplicação, regras ganham
busca e Configuração ganha importação/exportação. APIs e comportamento no
[contrato da evolução](CONFIG_EVOLUTION_CONTRACT.md). A janela também controla
um motor de processos por início/parada explícitos, conforme
[contrato do controle gráfico](PROCESS_GUI_CONTRACT.md).
Botão Enviar à bandeja e guarda gráfica por configuração/sessão são definidos
no [contrato de bandeja](TRAY_CONTRACT.md); fechar pelo X continua sair.

- `--gui` abre um JSON existente, com o mesmo `--config`/APPDATA da CLI.
  Destino ausente permite rascunho inicial, criado somente ao Salvar, conforme
  [primeira configuração](INITIAL_SETUP_CONTRACT.md). `--init-config` continua
  disponível pela CLI; arquivo inválido não é substituído. A flag rejeita
  outros modos antes de IO/importações.
- Quatro abas: Visão geral, Horários, Jogos / Apps e Configuração. Janela CustomTkinter na
  thread principal; motor e ícone de bandeja em workers separados. Callbacks
  da bandeja publicam fila limitada; somente polling Tk opera widgets/motor.
- Desfazer/Refazer e Ctrl+Z/Ctrl+Y restauram até 50 edições em memória. Atalhos
  não interceptam Entry/Text/Spinbox, formulários ou seletor em andamento.
  `ConfigDraft.can_undo/can_redo`, `undo()/redo() -> bool` e `replace_config`
  usam modelos revalidados antes de mover stacks; falha/no-op preservam histórico,
  nova edição após undo descarta redo. Sugestões/lotes são uma única edição.
  Save mantém histórico; import/reload bem-sucedidos criam draft novo e o
  reiniciam. Restauração atualiza dirty/prévia/revisão, mantendo arquivo salvo
  e motor sob seus comandos explícitos. Histórico não persiste ao fechar.
- Visão geral inclui Revisão do rascunho: duplicatas de horários/quatro listas,
  regras por nome/cmdline sobrepostas à proteção obrigatória/adicional e escopo
  Java por nome. `review_config(config) -> ConfigReview` é puro, validado e
  frozen; índices referem-se às listas originais. Não altera regras nem bloqueia
  save/start. Textbox somente leitura/rolável mostra até dez apontamentos com
  detalhe limitado a 260 caracteres e quantidade excedente, sem ampliar janela.
  Não consulta processos/arquivos, resolve aliases de pastas ou certifica
  classificações; pastas duplicadas comparam somente texto ignorando caixa.
- Selecionar .exe permite inclusão múltipla nas categorias Executáveis e
  Proteção adicional. `ConfigDraft.add_executable_paths(field, paths) -> int`
  extrai nomes textuais sem ler/resolver/executar arquivos e publica lote
  validado atomicamente. Dedup casefold apenas de novas regras; duplicatas
  preexistentes permanecem. Nomes valem em qualquer pasta, explicado antes
  da seleção. Arquivos inválidos/falha de iterable deixam draft intacto.
  Cancelar não altera feedback/draft; modal/reentrância/saída impedem a ação,
  Iniciar fica indisponível durante o seletor. Categoria capturada antes do
  diálogo; retorno tardio depois de sair é descartado. Salvar permanece explícito.
- Horários: adicionar/editar/remover; sete checkboxes, todos selecionados por
  padrão. Atalhos Todos/Seg–Sex/Fim de semana/Nenhum alteram somente a seleção
  local até aplicar; dias vazios aplicados desativam. Edição conserva ordem
  dos dias retidos e acrescenta novos em ordem semanal, evitando alteração
  estrutural sem mudança efetiva. Cancelar/Escape descartam o formulário;
  callbacks antigos são recusados antes de Tk/draft. Modal horário 560×470,
  raiz mínima 880×660 preservada. Ver [contrato dos dias](WINDOW_DAYS_CONTRACT.md).
  Mesma validação de horários noturnos, igualdade inválida, dias e união já
  existente no núcleo.
- Quatro categorias de processos: executáveis, pastas, proteção adicional e
  linha de comando. Cmdline mantém executável e trecho juntos, preservando
  espaços do trecho literal. Seletor de pastas opcional. Nenhuma lista
  predefinida ou executável inferido.
- Ctrl+F abre Jogos / Apps na categoria atual e foca/seleciona a busca existente,
  sem novo timer. Escape somente nessa entrada e botão Limpar retiram o filtro
  por uma reconstrução via trace; vazio é no-op. Ordem visual, índices, histórico
  e dados permanecem intactos. Guardas de modal/seletor/saída antecedem Tk;
  Escape dos formulários continua fechando o formulário. Rótulo Buscar regras ·
  Ctrl+F · Esc limpa e controle compacto na linha existente, conforme
  [contrato da busca por teclado](RULE_SEARCH_KEYBOARD_CONTRACT.md).
- Selecionar regras ativa checkboxes e barra com contador N selecionadas/M
  exibidas; Selecionar exibidas abrange todos os resultados do filtro atual,
  inclusive fora do viewport. Limpar/Fechar seleção não editam dados. Toda
  atualização da lista limpa seleção; callbacks capturam contexto/geração,
  modelo e identidade da linha. Remover selecionadas confirma quantidade e
  categoria, revalida antes/depois do diálogo e aplica uma edição Undo/Redo
  sem gravar. Flag em try/finally impede reentrância. Layout padrão mantém
  lista na linha 4; somente modo ativo mostra barra e desloca lista à linha 5.
  Polling altera estado dos checkboxes apenas quando necessário, evitando
  redesenhos repetidos. Ver [contrato do lote](RULE_BULK_REMOVE_CONTRACT.md).
- Diálogos aplicam alterações ao rascunho; Cancelar/Escape/fechar o diálogo
  descartam somente os campos desse formulário. Remover exige confirmação.
- Salvar/Ctrl+S publica pelo repositório existente. Erro/conflito preserva
  rascunho e baseline. Recarregar/Ctrl+R lê a versão atual; se houver edição
  pendente, pede confirmação de descarte. Recarga inválida preserva a sessão.
- Fechar a janela com rascunho pendente oferece salvar/descartar/cancelar.
  Falha ao salvar mantém a janela aberta e o motor. Após decidir sair, a GUI
  sinaliza parada e espera motor/ícone por polling antes de destruir a janela.
- Consulta da agenda por timer Tk usa exclusivamente a última versão
  carregada/salva. Não representa confirmação de bloqueio aplicado, nem
  observa automaticamente alterações externas; Recarregar atualiza a leitura.
- `AgendaStatus.current_end` identifica o fim da união em andamento pelo
  calendário local. None com active false significa fora de janela; None com
  active true significa cobertura semanal contínua. A GUI mostra o fim ou
  essa distinção, separado do estado efetivo do motor e da prévia do rascunho.
- Um watcher separado poderá ler o arquivo salvo no próximo ciclo. O editor
  não interrompe nem controla esse watcher, e fechá-lo não encerra o watcher.

## Implementação

`core/config_session.py` contém `ConfigSession`: caminho, snapshot e
`ConfigDraft`; `dirty` compara a configuração editada ao baseline. `save()`
adota somente o snapshot retornado após sucesso; `reload()` só publica a nova
sessão após leitura/validação completas. `agenda_status(now)` retorna estado
e próximo início do baseline, sem efeitos de sistema.

A comparação de conteúdo distingue os tipos JSON em extras aninhados:
importar `true` para `1` indica alteração pendente e fechar pede a decisão
de salvar/descartar/cancelar. Ordem de chaves não cria alteração artificial.
Todos os seletores mantêm uma guarda durante seu loop nativo, impedindo
ocultação na bandeja e início/restauração do rascunho. Abrir um seletor cancela
a intenção anterior de ocultar; um ready tardio exige novo Enviar à bandeja.
O seletor de pastas descarta retorno após fechar/substituir seu formulário,
antes de acessar os campos; falha de abertura é informada sem alterar draft.

**Ver alterações**, na aba Configuração, abre comparação de leitura entre
baseline e rascunho em modal redimensionável/rolável. Apresenta índices de
cada lado, Antes/Depois e somente indicador para extras; limites explícitos
evitam crescimento ilimitado do texto. Abrir/fechar não grava nem altera
histórico/motor. Guardas de modal/seletor/saída e cleanup dos timers são os
mesmos dos formulários; Salvar continua explícito, sem nova confirmação.
Detalhes em [CONFIG_DIFF_CONTRACT.md](CONFIG_DIFF_CONTRACT.md).

Na revisão da Visão geral, escolha um apontamento numerado e use **Ir para
item**. A ação abre a aba/categoria e destaca/rola a linha original; limpar
busca não altera regras. Links consideram somente os dez apontamentos
mostrados e omitem os sem índice. Geração da revisão, identidade do draft
e comparação tipada do snapshot recusam escolhas antigas após alterações;
campo/int/faixa são conferidos antes de navegar. Rolagem pertence à linha
e é cancelada antes de destroy; Iniciar/Save/history não são acionados pela
navegação. Ver [REVIEW_NAVIGATION_CONTRACT.md](REVIEW_NAVIGATION_CONTRACT.md).

**Ordem visual**, ao lado da busca em Jogos / Apps, oferece Cadastro/Nome
A–Z/Nome Z–A. É preferência somente da janela e combina com filtro; empates
preservam cadastro nos dois sentidos. Helper puro retorna índices originais,
mantendo callbacks e mapa da revisão. Alterar view cancela scroll/highlight
das linhas reconstruídas, sem alterar geração/snapshot da revisão ou dados.
Ver [RULE_LIST_VIEW_CONTRACT.md](RULE_LIST_VIEW_CONTRACT.md).

Listas de regras materializam 25 resultados por página. O universo completo
do filtro/ordem permanece disponível para selecionar/remover entre páginas;
trocar página preserva seleção, enquanto mudança lógica da vista reinicia.
Revisão revela a página pelo índice original e preserva um filtro que já
inclua o alvo. Pager/rows usam épocas distintas do owner lógico para recusar
callbacks antigos. Ver [RULE_PAGINATION_CONTRACT.md](RULE_PAGINATION_CONTRACT.md).

A digitação na busca agrupa escritas por um timer Tk de 200 ms, invalidando
seleção/owner/bindings imediatamente. Linhas antigas ficam inertes até a
reconstrução da consulta atual. Clear/ordem/categoria/modelo/review continuam
resolvendo o destino em uma reconstrução; fronteiras de diálogo suspendem o
timer e retomam a pendência sem render duplicado. Token monotônico e
cancelamento owned impedem callbacks tardios após saída. Detalhes em
[RULE_SEARCH_DEBOUNCE_CONTRACT.md](RULE_SEARCH_DEBOUNCE_CONTRACT.md).

`ui/config_gui.py` importa CustomTkinter/Tk somente na execução de `--gui`.
A fábrica `_build_app` recebe toolkit, diálogos, sessão e controlador opcional
para testar os callbacks com arquivos reais sem dependência gráfica. Abertura
não inicia worker nem importa psutil; Iniciar é explícito. Diagnóstico e editor
CLI continuam com importações independentes. O presenter puro separa estado do
motor, última agenda observada e relatório de encerramentos.

CustomTkinter 6.0.0 é fixado em `requirements.txt`, conforme a versão publicada
no [PyPI](https://pypi.org/project/customtkinter/6.0.0/); widgets seguem a
[documentação oficial](https://customtkinter.tomschimansky.com/documentation/).
Não há mudança de schema, SQLite ou migração. Campos opacos continuam
preservados. Detecção de conflitos por bytes mantém a pequena corrida entre
a conferência final e o replace; não equivale a CAS/lock de escritores externos.

## Validação e limites

Ações individuais e formulários recusam contextos antigos após reconstrução
da lista ou mudança do rascunho. Remoção revalida antes/depois da confirmação;
Apply verifica identidade modal/draft e conteúdo tipado antes de ler campos.
Recarregar não executa durante formulário, seletor ou outra confirmação e
preserva mudanças de memória feitas durante o prompt. Detalhes em
[EDITOR_ACTION_CONTEXT_CONTRACT.md](EDITOR_ACTION_CONTEXT_CONTRACT.md).

Medições de construção/reconstrução/repouso, com fixtures isoladas e limites
de interpretação, ficam em [GUI_PERFORMANCE.md](GUI_PERFORMANCE.md). A
atualização condicional de texto/estado no polling tem contrato próprio em
[GUI_IDLE_UPDATES_CONTRACT.md](GUI_IDLE_UPDATES_CONTRACT.md).

- `tests/test_config_session.py`: persistência real, rascunho/baseline,
  consulta de agenda salva, dias vazios, conflitos, remoção, falhas e retry.
- `tests/test_config_gui_main.py`: flag, importações sob demanda, abertura
  sem bloqueadores, erros e parada/espera garantidas na saída do mainloop.
- `tests/test_config_gui.py`: callbacks de CRUD, validação e correção,
  categorias, salvamento, recarga e saída usando widgets simulados com JSON
  e repositório reais. Não valida renderização ou compatibilidade dos widgets.
- `tests/test_config_gui_native.py`: cinquenta smoke tests com CustomTkinter real
  quando instalado, com janelas ocultas; não substituem inspeção visual.

As dependências estão instaladas no `.venv`/QA 3.12. Os smoke tests exercitam
callbacks e teardown de widgets reais. Controlador simulado,
sem encerramentos reais. A janela de QA abriu com JSON isolado e alvos vazios,
mas a captura falhou duas vezes por timeout; inspeção visual, DPI e rolagem em
tamanho mínimo continuam pendentes. Não considerar a fase 5 completa entregue.

O roteiro reproduzível atual está em [GUI_ACCEPTANCE.md](GUI_ACCEPTANCE.md),
com registros reais separados em [GUI_ACCEPTANCE_RESULTS.md](GUI_ACCEPTANCE_RESULTS.md).
A tentativa sobre `79607c9` abriu primeiro uso em 880×660, mas não obteve
captura nem confirmou foco dos controles pela UIA; não aprova visual/DPI
ou acessibilidade. Preparação das fixtures validada não equivale ao aceite.

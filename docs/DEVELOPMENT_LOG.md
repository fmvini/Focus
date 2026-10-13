## 2026-10-13 — Custo da interface e polling

### Implementado
- Medição isolada na base `7d3ad6d`: snapshot/helper sub-ms, construção/render de 1000 regras 30,538 s/35,648 s, RSS idle 195,31 MiB. Idle 0/100/1000 aproximadamente 7,49%/8,11%/7,50% de um núcleo. Dados e limites em `docs/GUI_PERFORMANCE.md`.
- Implementada atualização condicional dos setters de texto/estado no polling. Instrumentação fake inicial confirmou 13 configure por poll igual; regressões finais verificam zero configure após sincronização, preservando avaliações e mudanças reais.

### Arquivos principais alterados
- `ui/config_gui.py`, `tests/test_config_gui.py`, `tests/test_config_gui_native.py`.
- `docs/GUI_PERFORMANCE.md`, `docs/GUI_IDLE_UPDATES_CONTRACT.md`, `docs/GUI_EDITOR_CONTRACT.md`, `docs/README.md`, `docs/TEST_PLAN.md`, `docs/DEVELOPMENT_LOG.md`.

### Decisões técnicas
- Comparar cget público e configurar somente deltas, sem cache de modelo, nova cadência ou skip de avaliações. Preservar transições/guardas/saída e seleção de todos os resultados do filtro.
- Não escolher paginação/limites nem reescrever renderização nesta unidade. Custo de listas extensas exige evolução separada.

### Estado atual
- Benchmark terminou, fixtures removidas e base limpa antes desta unidade. Um processo por cenário, raízes ocultas/motor fake, sem efeitos em processos/hosts do usuário. Não prova RNF01, visual/DPI ou comportamento de seleção ativa.
- Fonte GUI congelada: Frontend 133 GUI/mainfake e dois novos native aprovados nos dois runtimes, 11,943 s/11,870 s, zero skips. Três fake/dois native novos testam polling estável e transições reais, incluindo toolbar ativa, agenda/mailbox/controller avaliados e closing com worker vivo.
- Backend/Banco revisão estática sem achados. Backend confirmou AST idêntica ao HEAD após normalizar novos setters e remover helper; somente deltas de text/state mudaram.
- Medição posterior exclusiva 0/100 com mesmo protocolo: CPU idle 0,937%/0,312% de um núcleo contra 7,49%/8,11% antes, RSS 62,71/75,09 MiB próximo do anterior. Uma amostra/quantização, sem garantia estatística/RNF01; não repetido 1000. Processos e fixtures encerrados.
- Suíte completa final Maestro: **808 descobertos, 807 aprovados e um skip conhecido** symlink/WinError 1314 nos dois runtimes Windows AMD64: Python 3.14.6/199,132 s e Python 3.12.14/229,239 s. Quarenta e cinco nativeGUI, ícone real e guardas passaram. AST 3.12/UTF-8 nos 73 arquivos, links e diff conferidos.

### Próximos passos
- Avaliar renderização progressiva em próxima unidade; respostas de sites/pausa/avisos e visual/DPI permanecem pendentes.

## 2026-10-13 — Integridade das ações e formulários individuais

### Implementado
- Contextos de linhas capturados no render recusam Editar/Remover/Duplicar antigos após reconstrução ou troca de draft/modelo/vista. Remover individual revalida antes/depois da confirmação e usa o draft capturado.
- Ambos formulários guardam identidade modal/draft e snapshot tipado antes de getters/Apply; campos antigos não sobrescrevem modelo novo. Recarregar recusa formulário/seletor/confirmação e preserva mudanças de memória durante o prompt, permitindo alterações somente do arquivo externo.

### Arquivos principais alterados
- `ui/config_gui.py`, `tests/test_config_gui.py`, `tests/test_config_gui_native.py`.
- `README.md`, `docs/EDITOR_ACTION_CONTEXT_CONTRACT.md`, `docs/GUI_EDITOR_CONTRACT.md`, `docs/README.md`, `docs/TEST_PLAN.md`, `docs/DEVELOPMENT_LOG.md`.

### Decisões técnicas
- Snapshot compartilhado por lista, sem cópia por linha; contextos individuais e de lote distintos, argumentos de callbacks capturados na construção. Confirmação individual/lote/recarga compartilha flag com finally contra reentrância.
- Core/schema/igualdade, dias preservados, histórico e salvamento explícito permanecem existentes. Sem novo timer nem efeitos sobre o motor.

### Estado atual
- Base `d128a78`. Sete fake/três native novos cobrem callbacks antigos, identidade/modelo tipado/vista/geração, Apply antes de Tk, criação de diálogo alterada, prompt/reentrância/finally, recarga sem IO e CRUD individual no modo de seleção em lote.
- Frontend dez novos finais aprovados nos dois runtimes, 25,351 s/26,713 s; Banco dez finais, 24,686 s/23,771 s, sem achados; Backend quatro essenciais, 5,048 s/5,623 s, sem achados. Maestro dez novos, 18,754 s/17,718 s. P2 de closure ACTION/BULK introduzido na primeira versão foi corrigido e ganhou duas regressões antes desses resultados.
- Primeira suíte completa encontrou dois erros de fixtures legadas que tentavam abrir editor durante picker ativo, agora corretamente recusado. Frontend ajustou somente a simulação externa de modal substituto; dois testes passaram nos dois runtimes, 2,556 s/2,600 s, sem alteração de produção.
- Suíte completa final Maestro: **803 descobertos, 802 aprovados e um skip conhecido** symlink/WinError 1314 nos dois runtimes Windows AMD64: Python 3.14.6/225,621 s e Python 3.12.14/262,128 s. Quarenta e três nativeGUI, ícone real e guardas passaram. AST 3.12/UTF-8 nos 73 arquivos, links dos 27 documentos e diff conferidos.
- Widgets ocultos/fakes não aceitam visual/DPI/acessibilidade; nenhum efeito em processos/hosts/configuração do usuário. Hipótese de clique físico antes de grab_set não demonstrada.

### Próximos passos
- Medir custo de renderização e repouso da GUI com listas extensas antes de escolher a próxima otimização; usar raízes ocultas, configuração isolada e motor simulado.
- Visual/DPI/acessibilidade e perguntas de sites/pausa/avisos pendentes.

## 2026-10-12 — Remoção de regras selecionadas em lote

### Implementado
- Modo explícito Selecionar regras com checkboxes, contador N selecionadas/M exibidas e ações Selecionar exibidas/Limpar seleção/Remover selecionadas/Fechar seleção. Somente resultados da categoria/filtro atual, incluindo fora do viewport; qualquer atualização da lista limpa seleção.
- Remoção confirmada aplica posições originais em um lote validado, uma edição Undo/Redo e nenhum Save automático. Contexto/geração/modelo/linha revalidados antes/depois do prompt; flag finally impede reentrância e protege cancelamento/retorno tardio.

### Arquivos principais alterados
- `core/config_editor.py`, `tests/test_rule_bulk_remove.py`, `tests/test_rule_bulk_remove_integration.py`, `ui/config_gui.py`, `tests/test_config_gui.py`, `tests/test_config_gui_native.py`.
- `README.md`, `docs/RULE_BULK_REMOVE_CONTRACT.md`, `docs/CONFIG_EDITOR_CONTRACT.md`, `docs/GUI_EDITOR_CONTRACT.md`, `docs/DATA_MODEL.md`, `docs/README.md`, `docs/TEST_PLAN.md`, `docs/DEVELOPMENT_LOG.md`.

### Decisões técnicas
- Uma operação no rascunho e uma edição Undo/Redo; validar todo iterable/índice antes de publicar. Vazio conserva redo; dedup somente de posições, nunca de valores de regras.
- Seleção limitada aos resultados da categoria/filtro atual e resetada em toda atualização da lista. Modo desligado preserva layout existente. Geração/view/row identity e snapshot tipado antes e depois da confirmação impedem callback antigo ou seleção alterada.
- Salvar/conflito/baseline continuam existentes, sem nova persistência, schema ou efeito no motor. Frontend/Banco não executarão fonte core em edição; freezes explícitos antes de integração.

### Estado atual
- Base `3cc801b`. Backend congelou núcleo e 15 testes novos: 50 núcleo/editor/history/comparison aprovados nos dois runtimes, 0,880 s/1,270 s. Banco congelou quatro integrações e passou nos dois runtimes, 0,217 s/0,197 s. Maestro revisou ambas as fontes sem achados.
- GUI final congelada após corrigir chamada de teste nativo `invoke` para `toggle` e eliminar configure(state) redundante dos checkboxes no polling (CTk redesenha mesmo em valor igual). O último ajuste inclui regressão de polling/disabled/enabled sem alterar dados/geração.
- Frontend validou fonte final em 124 GUI/main/três novos native nos dois runtimes, 119,048 s/116,961 s. Backend revisão sem achados, 13 GUI relevantes em 3.14/112,058 s e somente nova regressão polling em 3.12/0,041 s; Banco fonte final 11 novos GUI/nativos nos dois runtimes, 112,393 s/111,544 s, sem achados. Runs anteriores com invoke/sem ajuste polling não representam fonte final.
- Suíte completa final Maestro: **793 descobertos, 792 aprovados e um skip conhecido** symlink/WinError 1314 nos dois runtimes Windows AMD64: Python 3.14.6/213,791 s e Python 3.12.14/231,287 s. Quarenta nativeGUI, ícone real e guardas passaram. AST 3.12/UTF-8 nos 73 arquivos, links/diff conferidos. Sem efeitos em processos/hosts/configuração do usuário; visual/DPI/acessibilidade permanece pendente.

### Próximos passos
- Próxima revisão de integridade: validar callbacks e confirmação de remoção individuais e formulários de edição perante troca de modelo/formulário. Backend/Banco fazem probes somente leitura após fontes congeladas; qualquer correção será próxima unidade após este commit.
- Visual/DPI/acessibilidade e respostas de sites/pausa/avisos continuam pendentes.

## 2026-10-12 — Busca de regras pelo teclado

### Implementado
- Ctrl+F abre Jogos / Apps na categoria atual, foca a busca e seleciona texto existente. Escape somente na entrada e botão Limpar retiram o filtro; vazio não reconstrói a lista. Categoria, ordem visual e índices originais preservados.

### Arquivos principais alterados
- `ui/config_gui.py`, `tests/test_config_gui.py`, `tests/test_config_gui_native.py`.
- `README.md`, `docs/RULE_SEARCH_KEYBOARD_CONTRACT.md`, `docs/GUI_EDITOR_CONTRACT.md`, `docs/README.md`, `docs/TEST_PLAN.md`, `docs/DEVELOPMENT_LOG.md`.

### Decisões técnicas
- Ações somente de visualização, sem novos timers, dados ou confirmação. Preservar consulta/ordem ao focar e usar trace para uma reconstrução ao limpar.
- Frontend possui três arquivos GUI/testes; Backend/Banco somente leitura; Maestro docs/integração/commit. Não retomar lotes antigos após recuperação de cota.

### Estado atual
- Base `8d040af`. Sete novos testes verificam categorias/consulta/ordem/foco/seleção, clear único/vazio, duplicatas/CRUD, noIO/history/draft/baseline/motor, guards/callbacks antigos e Escape dos formulários preservado.
- Frontend congelou GUI/testes com quatro fake e três native novos. Rótulo intencionalmente atualizado exigiu corrigir uma asserção legada; produção/nativos permaneceram iguais. Seleção final 113 GUI/main passou nos dois runtimes (6,567 s/6,512 s), e os 37 nativos das execuções anteriores passaram. Não atribuir uma seleção 150 verde a um único run.
- Backend e Banco revisaram a fonte final sem achados, com 25/25 (30,414 s/32,795 s) e 54/54 (33,836 s/32,313 s) aprovados nos dois runtimes. AST 3.12/UTF-8 nos 71 arquivos, links/diff conferidos.
- Suíte completa final Maestro: **763 descobertos, 762 aprovados e um skip conhecido** symlink/WinError 1314 nos dois runtimes Windows AMD64: Python 3.14.6/173,387 s e Python 3.12.14/200,022 s. Trinta e sete nativeGUI, ícone real e guardas passaram. Sem efeitos em processos/hosts/configuração do usuário; visual/DPI/foco físico/acessibilidade permanecem pendentes.

### Próximos passos
- Próxima melhoria: remoção em lote de regras selecionadas, somente draft e uma edição Undo/Redo. Design revisado pelos três agentes, ainda sem implementação. Iniciar depois do commit desta unidade.
- Sites/pausa/avisos continuam dependendo das respostas abertas; visual/DPI/acessibilidade pendentes.

## 2026-10-12 — Atalhos dos dias e edição fiel de horários

### Implementado
- Atalhos Todos/Seg–Sex/Fim de semana/Nenhum ajustam somente checkboxes até aplicar. Cancelar/Escape descartam seleção local; Nenhum aplicado desativa a janela.
- Apply conserva a ordem dos dias retidos e acrescenta novos em ordem semanal, corrigindo o P3 que marcava dirty e perdia redo ao aplicar uma janela intacta `(6, 0)`. Callbacks antigos de presets/Apply são recusados antes de Tk/draft/finish_edit. Modal de horário 560×470; raiz mínima preservada.

### Arquivos principais alterados
- `ui/config_gui.py`, `tests/test_config_gui.py`, `tests/test_config_gui_native.py`.
- `README.md`, `docs/WINDOW_DAYS_CONTRACT.md`, `docs/GUI_EDITOR_CONTRACT.md`, `docs/DELIVERY_PLAN.md`, `docs/README.md`, `docs/TEST_PLAN.md`, `docs/DEVELOPMENT_LOG.md`.

### Decisões técnicas
- Preservar dias retidos na ordem original e acrescentar dias novos em ordem semanal. Não normalizar core, comparação ou arquivo inteiro. Atalhos alteram somente o formulário até aplicar; nenhum novo comportamento de salvamento.
- Frontend implementou/congelou três arquivos GUI/testes. Backend/Banco enviaram invariantes cedo; revisões finais interrompidas pelo limite de uso dos agentes, sem alegar conclusão. Maestro revisou fonte/testes e integrou suíte/docs/commit conjunto.

### Estado atual
- Base `ac2bb84`; seis fakeGUI e três nativeGUI novos. Frontend confirmou 143 GUI/main/native aprovados em 3.14 (117,879 s) e freeze explícito; relatório final de QA 3.12 interrompido pela cota. AST 3.12/UTF-8 nos 71 arquivos conferida pelo Maestro.
- Suíte completa Maestro: **756 descobertos, 755 aprovados e um skip conhecido** symlink/WinError 1314 nos dois runtimes Windows AMD64: Python 3.14.6/227,984 s e Python 3.12.14/240,553 s. Trinta e quatro nativeGUI, ícone real e guardas passaram. Sem efeitos em processos/hosts/configuração do usuário; visual/DPI/acessibilidade permanece pendente.

### Próximos passos
- Próxima melhoria independente: Ctrl+F para alcançar a busca da categoria de regras e limpar filtro pelo teclado, preservando ordem visual, dados e guardas de modal/seletor/saída.
- Visual/DPI e respostas sobre sites/pausa/avisos permanecem pendentes.

## 2026-10-12 — Ordenação visual das regras sem alterar o cadastro

### Implementado
- Cadastro/Nome A–Z/Nome Z–A combinados com busca, mantendo dados/índices originais. Controle compacto ao lado da busca preserva a área da lista em 880×660; preferência somente da janela, sem schema/gravação/histórico/motor.

### Arquivos principais alterados
- `ui/rule_list_view.py`, `tests/test_rule_list_view.py`, `tests/test_rule_list_view_integration.py`, `ui/config_gui.py`, `tests/test_config_gui.py`, `tests/test_config_gui_native.py`.
- `README.md`, `docs/RULE_LIST_VIEW_CONTRACT.md`, `docs/GUI_EDITOR_CONTRACT.md`, `docs/README.md`, `docs/TEST_PLAN.md`, `docs/DEVELOPMENT_LOG.md`.

### Decisões técnicas
- Estado somente visual, sem schema/gravação/histórico/motor. Helper puro retorna índices originais, ordenação estável e casefold de nomes/pares cmdline, pastas literais sem expansão.
- Backend helper/testes; Frontend GUI/testes; Banco integração de sessão em teste exclusivo; Maestro docs/revisão/suíte/commit. Manter navegação e CRUD nos índices originais após sort/filter.

### Estado atual
- Suíte completa: **747 descobertos, 746 aprovados e um skip conhecido** nos dois runtimes Windows AMD64: Python 3.14.6/147,755 s e Python 3.12.14/167,510 s. Trinta e um nativeGUI, ícone real e guardas passaram. AST 3.12/UTF-8 nos 71 arquivos e links/diff conferidos. Sources revisadas/congeladas para commit conjunto; sem efeitos em processos/hosts/configuração do usuário; visual/DPI segue pendente.
- Base `d61279e`. Novos 26 testes: 14 helper, quatro integrações, cinco fakeGUI/três nativeGUI. Seleções anteriores passaram nos dois runtimes: helper (0,222 s/0,639 s), integração (0,182 s/0,141 s), 134 GUI/main/native (87,015 s/86,196 s).

### Próximos passos
- Próxima unidade do formulário de horários: atalhos de dias e preservar ordem original dos dias ao aplicar edição sem mudanças (P3 confirmado por Backend).
- Sites/avisos/pausa seguem as perguntas abertas de USER_ANSWERS.

## 2026-10-12 — Navegação dos apontamentos às linhas originais

### Implementado
- Helper puro produz links dos apontamentos mostrados às categorias/índices originais, com numeração humana consistente. Seletor e Ir para item navegam explicitamente, revelam a categoria/linha e destacam sem abrir formulário nem editar dados.

### Arquivos principais alterados
- `ui/review_navigation.py`, `tests/test_review_navigation.py`, `ui/config_gui.py`, `tests/test_config_gui.py`, `tests/test_config_gui_native.py`.
- `README.md`, `docs/REVIEW_NAVIGATION_CONTRACT.md`, `docs/GUI_EDITOR_CONTRACT.md`, `docs/README.md`, `docs/TEST_PLAN.md`, `docs/DEVELOPMENT_LOG.md`.

### Decisões técnicas
- Prefixo de dez apontamentos antes de filtrar os sem índice, com numeração humana consistente. Navegação e destaque somente na interface; não edita/salva/inicia motor.
- Banco possui helper/testes; Frontend GUI/testes; Backend revisão somente leitura; Maestro integra/docs/commit. Respeitar escolha obsoleta, busca/índice original, guards e callback owned pela linha.
- Geração da revisão, identidade do draft e comparação tipada do snapshot evitam redirecionamento por escolha antiga. Mapa (field, índice original) separado da posição filtrada mantém CRUD; callback de rolagem pertence à linha, com gerações de linha/revisão antes de tocar canvas.
- Adaptador limitado ao canvas interno CTk 6.0.0, com fallback de destaque/rolagem manual e revalidação em upgrade. Limpeza da busca usa trace ou render direto, nunca duas reconstruções por navegação.

### Estado atual
- Base `7ee59e8`, suíte anterior completa700/699 OK/um skip nos dois runtimes. Helper: dez novos testes e nove reviewer, todos aprovados nos dois runtimes (0,645 s/1,298 s). Frontend: 126 GUI/main/native aprovados nos dois runtimes (61,771 s/62,241 s), incluindo sete fake/quatro native novos. Backend revisou sem achados e passou 30 testes selecionados nos dois runtimes (10,425 s/27,063 s).
- Suíte completa: **721 descobertos, 720 aprovados e um skip conhecido** symlink/WinError 1314 nos dois runtimes Windows AMD64: Python 3.14.6/128,213 s e Python 3.12.14/152,385 s. Vinte e oito nativeGUI, ícone real e guardas passaram. AST 3.12/UTF-8 nos 68 arquivos e links/diff conferidos. Nenhum processo/hosts/configuração do usuário alterado; visual/DPI permanece pendente. Fontes revisadas/congeladas para commit conjunto.

### Próximos passos
- Próxima evolução: ordenação visual das regras em Jogos / Apps, mantendo cadastro/JSON/índices originais e compatibilidade da navegação/CRUD.
- Sites/avisos/pausa continuam dependendo das decisões abertas em USER_ANSWERS.

## 2026-10-12 — Comparação das alterações pendentes na GUI e CLI

### Implementado
- Núcleo puro compara baseline/rascunho ordenados, apresentando inclusões/remoções/alterações com índices de cada lado e indicador privado de extras. Primeiro arquivo distingue criação mesmo vazia.
- Presenter compartilhado mostra título/contagens, índices humanos, Antes/Depois, limites de 100 mudanças/1000 caracteres por valor e aviso de excedentes/truncamento. Controles escapados preservam espaços e impedem linhas enganosas. CLI menu 8 e botão Ver alterações na GUI usam a mesma apresentação.
- Modal somente leitura, redimensionável/rolável, preserva rascunho/histórico/baseline/motor. Consultas seguintes acompanham Undo/Redo/Save/Reload/Import; não relê disco nem contorna conflito externo.

### Arquivos principais alterados
- `core/config_diff.py`, `ui/config_diff_presenter.py`, `ui/config_gui.py`, `ui/config_cli.py`.
- `tests/test_config_diff.py`, `tests/test_config_diff_presenter.py`, `tests/test_config_gui.py`, `tests/test_config_gui_native.py`, `tests/test_config_cli.py`, `tests/test_config_editor_integration.py`.
- `README.md`, `docs/CONFIG_DIFF_CONTRACT.md`, `docs/CONFIG_EDITOR_CONTRACT.md`, `docs/GUI_EDITOR_CONTRACT.md`, `docs/README.md`, `docs/TEST_PLAN.md`, `docs/DEVELOPMENT_LOG.md`.

### Decisões técnicas
- Modelo frozen e SequenceMatcher exato sem casefold/dedup; indicador de extras usa comparação JSON tipada compartilhada. Bordas iguais são preservadas antes de comparar o miolo, mantendo índices globais/API. Comparação é estrutural, não previsão de efeitos nem script mínimo/identidade de duplicatas. Sem fallback aproximado; miolo residual repetitivo ainda pode ter custo quadrático.
- Acesso opcional antes de Salvar, sem nova confirmação obrigatória, IO, consulta de processos ou alteração de conflito/baseline. Presenter compartilhado evita apresentação divergente na GUI/CLI.

### Estado atual
- Suíte completa: **700 descobertos, 699 aprovados e um skip conhecido** nos dois runtimes Windows AMD64: Python 3.14.6/172,667 s e Python 3.12.14/186,035 s. Vinte e quatro nativeGUI, ícone real e guardas passaram; AST 3.12/UTF-8 nos 66 arquivos e links/diff conferidos.
- Novos 64 testes: 32 núcleo (incluindo 992 reconstruções bidirecionais), 18 presenter, sete GUI fake, quatro nativeGUI e três CLI. CLI/reviewer relevante: 85/85 em 4,021 s. Frontend: 115/115 GUI/main/native nos dois runtimes (131,989 s/132,484 s). Banco reviu GUI/CLI sem achados e executou 113/113 nos dois runtimes (11,077 s/15,314 s).
- Medição local Backend em 2000 regras uniformes com troca central: antes 1480,65 ms, depois 0,664 ms no Python 3.14.6 e 0,403 ms no 3.12.14 (sete amostras, entradas pré-alocadas). Não é garantia de latência/renderização/RSS; residual quadrático permanece. Nenhum processo/hosts/configuração do usuário alterado; visual/DPI pendente. Base `f2385a0`, unidade validada para commit conjunto.

### Próximos passos
- Próxima evolução independente: navegar de apontamentos da revisão para a categoria/linha original, destacando o item sem alterar rascunho.
- Avisos/pausa/sites permanecem nas perguntas abertas de USER_ANSWERS.

## 2026-10-11 — Preservação de edições JSON e seletores seguros

### Implementado
- Comparação estrutural tipada compartilhada entre dirty e no-op: diferenças bool/int/float em extras aninhados são edições reais, com Undo/Redo e prompt de saída corretos. Ordem de chaves continua irrelevante; listas, regras e dias mantêm ordem/duplicatas.
- Guarda única durante todos os seletores impede ocultação na bandeja, início e restauração do histórico. Abrir seletor cancela intenção pendente de ocultar, inclusive ready tardio. Retorno de pasta após fechar/substituir formulário é descartado antes de tocar widgets; falhas TclError são informadas no contexto ainda válido.
- Fixture nativa inicializa CTk antes de agendar fechamento; mantém assertions de bgerror/after e não suprime exceções.

### Arquivos principais alterados
- `core/config_comparison.py`, `core/config_editor.py`, `core/config_session.py`.
- `ui/config_gui.py`, `tests/test_config_comparison.py`, `tests/test_config_history.py`, `tests/test_config_session.py`, `tests/test_config_gui.py`, `tests/test_config_gui_native.py`.
- `.gitignore`, `README.md`, `docs/CONFIG_EDITOR_CONTRACT.md`, `docs/GUI_EDITOR_CONTRACT.md`, `docs/TEST_PLAN.md`, `docs/DEVELOPMENT_LOG.md`.

### Decisões técnicas
- Comparador puro de modelos/extras JSON acíclicos, sem serialização, validação ambiental, IO ou descoberta. Validação e conflito por bytes continuam nas APIs existentes; não há igualdade redefinida globalmente em AppConfig.
- Banco e Frontend implementaram arquivos exclusivos; Maestro revisa/integra e mantém docs/commit. Backend já desenvolve diff em dois arquivos separados, fora desta unidade e das suítes de integração em andamento.
- Python 3.12.14 instalado por uv em `.qa/`, sem registro/PATH, com ambiente virtual e dependências fixadas do projeto; diretório de QA ignorado. O `.venv` Python 3.14.6 permanece disponível.

### Estado atual
- Banco: 122 testes, 121 aprovados e um skip conhecido, 7,688 s. Frontend: 104 aprovados/zero skips, incluindo 20 nativeGUI, 35,428 s; os dois smokes instáveis passaram três vezes cada, 6 testes/17,199 s.
- Suítes integradas: **636 descobertos, 635 aprovados e um skip conhecido** em ambos runtimes: Python 3.14.6/79,903 s e Python 3.12.14/103,041 s, Windows AMD64. Todos os 20 nativeGUI, ícone real e mutexes passaram; apenas diff ainda não entregue foi excluído antes de carregar módulos. A compatibilidade runtime 3.12 foi verificada, além de AST/UTF-8.
- Nenhum processo/hosts/configuração do usuário alterado; inspeção visual/DPI permanece pendente. Base `83d78cc`; arquivos desta unidade revisados e preparados para commit conjunto.

### Próximos passos
- Integrar diff legível do baseline para o rascunho em nova unidade e repetir a suíte com o módulo novo após congelamento.
- Avisos/pausa/sites continuam aguardando decisões em USER_ANSWERS.

## 2026-10-11 — Revisão da configuração pela CLI

### Implementado
- `--review` revisa o JSON salvo com índices humanos, contagens e todos os apontamentos estáticos, sem GUI/psutil/relógio/workers ou gravação. Combina somente com --config; validade com apontamentos retorna 0, erro de arquivo/validação 1 e modos incompatíveis 2.
- Reutiliza reviewer/catálogo puro da GUI. Import sob demanda preserva outros modos; arquivo inválido/ausente é preservado, sem recuperação automática ou primeiro rascunho. Erro de encoding da saída agora retorna 1 com mensagem, inclusive caminhos Unicode em stream cp1252.

### Arquivos principais alterados
- `main.py`, `ui/config_review_cli.py`, `tests/test_config_review_cli.py`.
- `README.md`, `docs/PHASE1_CONTRACT.md`, `docs/TEST_PLAN.md`, `docs/DEVELOPMENT_LOG.md`.

### Decisões técnicas
- Diagnóstico humano independente, não simulação de processos; stdout para apontamentos informativos e stderr de erro via dispatch existente. Interrupção segue retorno normal dos diagnósticos.
- Unidade implementada pelo Maestro. Equipe recebeu nova revisão somente leitura dos lotes integrados, com proibição de retomar edições anteriores durante quota.

### Estado atual
- Oito novos testes e regressões de flags/dispatch: 79 aprovados em 3,122 s. Backend revisou somente leitura; achado UnicodeError corrigido com TextIOWrapper/UTF-8 e preservação dos bytes. A suíte completa anterior descobriu 610 testes: 608 aprovados, um skip conhecido e um erro no smoke nativo de fechamento, devido à inicialização CTk/mainloop que processa o fechamento antes de restaurar wm state (64,432 s). Frontend recebeu correção separada; nenhum teste CLI falhou e nenhum processo/hosts/configuração do usuário foi alterado.
- AST 3.12/UTF-8 nos 60 arquivos Python e diff conferidos. Base `f22f6f5`; runtime 3.12 e visual/DPI seguem pendentes.

### Próximos passos
- Integrar correções revisadas de igualdade JSON no dirty/history, retorno tardio dos seletores e estabilização do smoke nativo; repetir suíte completa após os edits congelarem.
- Próxima melhoria independente: apresentação e navegação das regras com listas extensas; medir antes de otimizar.

## 2026-10-11 — Desfazer e refazer edições do rascunho

### Implementado
- Desfazer/Refazer na GUI e menu 6/7 na CLI restauram até 50 edições em memória, incluindo CRUD, duplicação, sugestões e seleção de executáveis. Lotes são uma edição; nenhuma restauração grava arquivo ou altera estado do motor.
- Ctrl+Z/Ctrl+Y fora de formulários/campos de texto, botões conforme disponibilidade e guardas para seletor/saída. Prévia, revisão e dirty atualizam após restauração.
- Save mantém histórico e baseline continua determinando dirty; import/reload bem-sucedidos reiniciam histórico. Falhas/no-op não destroem redo; nova edição após undo inicia outro caminho.

### Arquivos principais alterados
- `core/config_editor.py`, `ui/config_gui.py`, `ui/config_cli.py`, `tests/test_config_history.py`, `tests/test_config_gui.py`, `tests/test_config_gui_native.py`, `tests/test_config_editor_integration.py`.
- `README.md`, `docs/GUI_EDITOR_CONTRACT.md`, `docs/CONFIG_EDITOR_CONTRACT.md`, `docs/TEST_PLAN.md`, `docs/DEVELOPMENT_LOG.md`.

### Decisões técnicas
- Modelos históricos são privados; getters retornam cópias defensivas. Undo/redo revalidam modelo antes de alterar qualquer stack, inclusive variáveis de pasta que mudaram. Limite de 50 estados controla retenção; não há persistência/SQLite ou novo schema.
- Sugestões agora usam `replace_config` no draft existente para preservar edições anteriores. Import/reload continuam substituindo draft após leitura válida, conforme contrato existente. Save/conflitos não são contornados pelo histórico.

### Estado atual
- Suíte completa: **603 descobertos, 602 aprovados e 1 skip conhecido**, 47,046 s, Python 3.14.6/Windows. Dezesseis nativeGUI e ícone real passaram; nenhum processo/hosts do usuário alterado. Seleções relevantes anteriores: 133 em 22,097 s e 34 CLI/integração/history em 2,233 s.
- Nove novos testes history, cinco GUI, um nativeGUI e uma integração CLI por subprocesso. Cobrem limite/branch/no-op/falha de revalidação, cópias defensivas, CRUD/lotes, baseline/save/import/reload, foco/modal/seletor/saída e ausência de IO. AST 3.12/UTF-8 nos 58 arquivos, links locais e diff conferidos. Unidade integrada para commit conjunto, sem push; agentes seguem parados por cota.
- Base `84e2ab8`; runtime 3.12 e visual/DPI pendentes.

### Próximos passos
- Próximo lote: disponibilizar a revisão estática por diagnóstico CLI independente.
- Avisos/pausa/sites aguardam decisões em USER_ANSWERS.

## 2026-10-11 — Revisão estática do rascunho

### Implementado
- Painel de revisão na Visão geral aponta duplicatas de horários/regras, bloqueio de nomes já protegidos e abrangência de Java por nome. Mostra quantidade de horários ativos e regras cadastradas, sem confundir com encerramentos possíveis/confirmados.
- Análise acompanha rascunho, sem consultas de processos/instalações, alterações automáticas, impedimento de save/start ou novas confirmações. Textbox readonly/rolável limita dez apontamentos/detalhes e informa excedentes.
- Catálogo obrigatório extraído para fonte compartilhada entre revisão/motor, preservando conjuntos, nomes públicos e todas as guardas anteriores.

### Arquivos principais alterados
- `core/config_review.py`, `core/process_catalog.py`, `core/proc_blocker.py`, `ui/config_gui.py`, `tests/test_config_review.py`, `tests/test_config_gui.py`, `tests/test_config_gui_native.py`.
- `README.md`, `docs/ARCHITECTURE_BACKEND.md`, `docs/GUI_EDITOR_CONTRACT.md`, `docs/TEST_PLAN.md`, `docs/DEVELOPMENT_LOG.md`.

### Decisões técnicas
- Dados frozen/puro sem importar controlador/bloqueador/psutil/Tk. Casefold reproduz igualdade de nomes/pares; pastas só texto, sem presumir aliases/junctions. Prioridade obrigatória/adicional é a já implementada, não decisão nova.
- Desconhecidos/helpers/usuários/caminhos/ancestrais continuam dependentes de inspeção real do motor; revisão não promete classificação universal. Nenhuma persistência ou schema novo.

### Estado atual
- Suíte completa: **587 descobertos, 586 aprovados e 1 skip conhecido** symlink/WinError 1314, 42,744 s, Python 3.14.6/Windows. Quinze nativeGUI e ícone real passaram; guardas/adapter/controller/CLI e import lazy preservados. Seleção relevante anterior: 178 testes em 19,696 s.
- Nove novos testes reviewer, dois fluxos GUI e um nativeGUI. Verificam pureza/frozen/índices/duplicatas/literais/proteções, catálogo compartilhado, rascunho sem IO e apontamentos sem bloquear save/start. AST 3.12/UTF-8 nos 57 arquivos, links locais e diff conferidos. Unidade integrada para commit conjunto, sem push ou efeitos em processos/hosts do usuário.
- Maestro segue implementando diretamente com agentes parados por cota. Base `d952905`. Runtime 3.12 e visual/DPI pendentes.

### Próximos passos
- Próximo lote: edição reversível do rascunho com Desfazer/Refazer, preservando save explícito e histórico só em memória.
- Avisos/pausa/sites aguardam respostas em USER_ANSWERS; não tratadas como aprovação.

## 2026-10-11 — Fim da janela na agenda carregada

### Implementado
- Consulta da agenda na GUI mostra o fim efetivo da janela em andamento, unindo horários sobrepostos/adjacentes e continuação noturna/semanal. Cobertura semanal contínua aparece explicitamente, distinta de agenda inativa ou ainda não salva.
- `current_block_end(windows, now)` puro e `AgendaStatus.current_end` consultam apenas baseline carregado/salvo, separados do rascunho e do estado do motor. Não mudam gates, bloqueadores, schema ou política de pausa/avisos.

### Arquivos principais alterados
- `core/scheduler.py`, `core/config_session.py`, `ui/config_gui.py`, `tests/test_schedule_end.py`, `tests/test_config_session.py`, `tests/test_config_gui.py`, `tests/test_config_gui_native.py`.
- `README.md`, `docs/GUI_EDITOR_CONTRACT.md`, `docs/TEST_PLAN.md`, `docs/DEVELOPMENT_LOG.md`.

### Decisões técnicas
- Reutiliza união semanal recorrente, incluindo domingo/segunda, sem inferir fim pela lista finita de ocorrências. None representa intervalo ausente ou cobertura total; active distingue os casos. Horários locais ingênuos e precisão de minuto conforme scheduler.
- Implementação pelo Maestro; agentes seguem parados por cota. Desenvolvimento contínuo autorizado pelo usuário; próximos lotes independentes seguem após esta unidade.

### Estado atual
- Suíte completa: **575 descobertos, 574 aprovados e 1 skip conhecido** symlink/WinError 1314, 41,137 s, Python 3.14.6/Windows. Quatorze nativeGUI e ícone real passaram. Núcleo/sessão anterior: 38 testes em 1,246 s, com referência independente por minuto em cenários fixos/aleatórios.
- Oito novos testes scheduler, dois fluxos GUI e um nativeGUI; testes de sessão estendidos. AST 3.12/UTF-8 nos 54 arquivos, diff conferido. Unidade validada para commit conjunto; nenhum motor real ou processo/hosts do usuário alterado.
- Runtime 3.12 e visual/DPI pendentes. Base anterior `b2ce8c6`.

### Próximos passos
- Próximo lote: revisão de regras para duplicatas/conflitos, sem alterar regras automaticamente.
- Avisos/pausa/sites aguardam respostas em USER_ANSWERS.

## 2026-10-11 — Seleção múltipla de executáveis

### Implementado
- Selecionar .exe nas categorias Executáveis e Proteção adicional adiciona vários nomes ao rascunho, sem digitação manual. Regra por nome em qualquer pasta é explicada antes da escolha; caminhos não são persistidos.
- Inclusão atômica validada, ordem da seleção e dedup casefold de novas regras, preservando regras/extras/duplicatas anteriores. Cancelamento não altera feedback/rascunho; falha preserva lote anterior. Salvar continua explícito, sem executar arquivos ou iniciar motor.
- Guardas de modal/reentrância/saída, categoria capturada antes do diálogo e Iniciar indisponível durante seletor. Maestro implementou diretamente após confirmar os três agentes parados por limite de uso.

### Arquivos principais alterados
- `core/config_editor.py`, `ui/config_gui.py`, `tests/test_executable_selection.py`, `tests/test_config_gui.py`, `tests/test_config_gui_native.py`.
- `README.md`, `docs/GUI_EDITOR_CONTRACT.md`, `docs/TEST_PLAN.md`, `docs/DEVELOPMENT_LOG.md`.

### Decisões técnicas
- Reutiliza matcher e schema por nome existentes; não cria regra por caminho do arquivo. `ConfigDraft.add_executable_paths(field, paths) -> int` aceita lote de str/PathLike textuais, usa basename Windows e valida completamente antes da publicação. Sem stat, leitura, resolução, descoberta ou execução.
- Seletor opera na thread Tk; processamento de nomes é somente em memória. Fechamento durante diálogo descarta retorno tardio sem acessar widgets destruídos; nenhuma espera de worker em callback.

### Estado atual
- Suíte completa fora do sandbox: **564 descobertos, 563 aprovados e 1 skip conhecido**, 39,227 s em Python 3.14.6/Windows. Treze nativeGUI e ícone real passaram; after vazio e bgerrors vazios no teardown. Seleção relevante anterior: 90 testes aprovados, 17,429 s.
- Sete novos testes core de lote/pureza/atomicidade e cinco fluxos GUI: cancelamento, categorias, falhas, reentrância/start/saída e categoria capturada; um nativeGUI em 880×660 com diálogo simulado/JSON real. AST Python 3.12/UTF-8 nos 53 arquivos, links locais e diff conferidos. Unidade integrada para commit local conjunto, sem push.
- Nenhum hosts, executável ou processo do usuário modificado/executado. Interação com o seletor nativo por usuário não foi automatizada; widgets foram testados com retorno do diálogo simulado.
- Visual/DPI e runtime Python 3.12 permanecem pendentes. Base anterior `471a92b`; nenhum novo default, dependência ou decisão de sites/pausa/avisos.

### Próximos passos
- Conferir seletor nativo por interação/visual quando captura estiver disponível. Avisos/pausa aguardam Q-PAUSE/Q-WARN; sites Q-HOSTS em USER_ANSWERS.

## 2026-10-11 — Primeira configuração gráfica

### Implementado
- Abertura gráfica de destino ausente com rascunho vazio, sem criar arquivo ao abrir; orientação identifica arquivo ainda não criado e agenda ainda não salva. Salvar cria explicitamente; descartar saída não grava nada.
- Sugestões do §6, treze itens desmarcados por padrão, adicionam somente escolhas ao rascunho em ordem do catálogo, sem duplicar regras equivalentes por casefold. Minecraft Java é regra conjunta `javaw.exe`/`.minecraft`; nenhuma descoberta de instalações, pasta presumida ou ativação automática.
- Primeira gravação valida/prepara JSON completo e publica exclusivamente, recusando destinos existentes/concorrentes. Importar/exportar preserva estado novo; recarga estrita pode adotar arquivo externo após confirmação. Iniciar fica desabilitado até salvar e continua exigindo confirmação depois.
- Maestro definiu contrato/arquivos dos três agentes; após os agentes pararem por limite de uso, assumiu finalização, revisão e testes restantes. D13 preservado, sem fechar decisões pendentes.
- Perguntas complementares Q-PAUSE-01/02 e Q-WARN-01/02 adicionadas em USER_ANSWERS para preparar avisos/pausa; respostas anteriores preservadas. Campos vazios não foram tratados como aprovação.

### Arquivos principais alterados
- `core/initial_setup.py`, `core/config_session.py`, `core/config_portability.py`, `ui/config_gui.py`, `main.py`.
- `tests/test_initial_setup.py`, `tests/test_initial_setup_integration.py`, `tests/test_config_gui.py`, `tests/test_config_gui_main.py`, `tests/test_config_gui_native.py`.
- `docs/INITIAL_SETUP_CONTRACT.md`, `docs/USER_ANSWERS.md`, `README.md`, `docs/GUI_EDITOR_CONTRACT.md`, `docs/README.md`, `docs/DATA_MODEL.md`, `docs/ARCHITECTURE_BACKEND.md`, `docs/DECISIONS.md`, `docs/DELIVERY_PLAN.md`, `docs/TEST_PLAN.md`, `docs/DEVELOPMENT_LOG.md`.

### Decisões técnicas
- Reutilizar editor existente e sessão nova sem baseline; configuração existente permanece leitura estrita. Nunca converter JSON inválido/permissão/diretório/link quebrado em primeira execução.
- Publicação exclusiva da primeira gravação, reaproveitando temporário/fsync/primitivos sem sobrescrita. Sugestões apenas por seleção, sem horários ativados ou descoberta de instalações; Java somente regra conjunta.
- Snapshot novo é dos próprios bytes preparados, nunca de leitura após publicação; escritor posterior é detectado no próximo Salvar. Exportação continua recusando active_path inválido/aliases. Em falha de cleanup após publicação POSIX, arquivo completo pode existir enquanto sessão conserva estado novo; Recarregar lê estritamente para recuperar. Sem lock adversarial de diretórios ou garantia absoluta em crash.

### Estado atual
- Suíte completa fora do sandbox: **551 descobertos, 550 aprovados e 1 skip**, 38,140 s em Python 3.14.6/Windows. Único skip conhecido: symlink/WinError 1314. Inclui doze nativeGUI sem bgerrors/callbacks restantes, bandeja real e regressões guard/controller/config/CLI.
- Novos testes: 22 catálogo/pureza, 14 sessão/publicação, sete fluxos GUI simulados, três mainGUI e dois nativeGUI. Corridas reais de rename/link preservaram destino externo, falhas fsync/publicação mantiveram rascunho, snapshot próprio preservado após escritor posterior. Sintaxe 3.12/UTF-8 nos 52 arquivos Python, links locais e diff conferidos.
- Unidade integrada/validada para commit local conjunto, sem push; base anterior `86a5bcf`. Bloqueadores falsos e fixtures isoladas nesta suíte; nenhum aplicativo do usuário encerrado.
- Runtime Python 3.12 e inspeção visual/DPI permanecem pendentes. Nenhum hosts ou processo do usuário alterado nesta etapa.

### Próximos passos
- Retomar avisos/pausa após respostas Q-PAUSE/Q-WARN; sites aguardam Q-HOSTS. Conferir primeira execução visual/DPI quando captura estiver disponível.

## 2026-10-11 — Bandeja explícita e guarda da interface

### Implementado
- Botão Enviar à bandeja mantém rascunho/motor e só oculta após ready. Menu Mostrar Focus/Parar motor/Sair publica comandos para polling Tk; iniciar permanece confirmado na janela. X continua sair; cancelar saída preserva execução.
- Guarda de uma GUI por caminho resolvido/normalizado na sessão Windows, mantida até finalizar motor/ícone/janela. Segunda abertura retorna erro sem criar outro motor. Mutex lazy, sem ownership/espera/arquivo-lock, com handle preservado para retry se fechamento falhar.
- Caixa de até cinco ações coalescidas, thread-safe e frozen; fechamento descarta pendências/ignora callbacks tardios. Ícone lazy em worker, stop sinaliza Event sem bloquear Tk e shutdown aguarda os workers por polling/finally externo.
- Dependências de bandeja fixadas/instaladas no `.venv`: pystray 0.19.5 e Pillow 12.3.0. Fonte oficial e limites em `docs/TRAY_CONTRACT.md`. Não há mudança de JSON/SQLite nem novas regras/defaults de bloqueio.

### Arquivos principais alterados
- `core/instance_guard.py`, `ui/tray_commands.py`, `ui/windows_tray.py`, `ui/config_gui.py`, `main.py`, `requirements.txt`.
- `tests/test_instance_guard.py`, `tests/test_instance_guard_integration.py`, `tests/test_tray_commands.py`, `tests/test_windows_tray.py`, `tests/test_config_gui.py`, `tests/test_config_gui_main.py`, `tests/test_config_gui_native.py`.
- `docs/TRAY_CONTRACT.md`, `README.md`, `docs/ARCHITECTURE_BACKEND.md`, `docs/DATA_MODEL.md`, `docs/DECISIONS.md`, `docs/DELIVERY_PLAN.md`, `docs/GUI_EDITOR_CONTRACT.md`, `docs/README.md`, `docs/REQUIREMENTS.md`, `docs/TEST_PLAN.md`, `docs/UI_FLOWS.md`, `docs/DEVELOPMENT_LOG.md`.

### Decisões técnicas
- Ocultar é explícito e não altera política do X. Startup lento/falha mantém/restaura janela; timeout da GUI impede esconder sem ready e retry aguarda worker antigo. Callback da bandeja não chama widgets nem controlador.
- pystray pode bloquear em stop aguardando setup; adapter faz essa espera fora de Tk. Setup original pode ficar preso se run falhar antes de ready; adapter gerenciado acorda/aguarda sua thread também nesse caso. Versão fixada e fronteiras internas documentadas/testadas. Adapter verifica BOOL de Shell_NotifyIconW/NIM_ADD, ignorado pela biblioteca, antes de ready/ocultação; não prova que usuário viu ícone, que pode estar no overflow.
- Mutex Local com SHA256 do path resolve/normcase, sem ReleaseMutex; não coordena CLI, hardlinks, sessões diferentes nem ativa primeira janela por IPC. Import/construção sem IO/workers/WinDLL/psutil/Tk/pystray.
- Backend entregou guard/tests; Banco mailbox/integração real entre processos; Frontend adapter/GUI/lifecycle/tests; Maestro contrato, revisão, dependências, aceites e integração. Respostas em `docs/USER_ANSWERS.md` preservadas; hosts/pausa/foco não antecipados.

### Estado atual
- Suíte integrada final fora do sandbox: **503 testes descobertos, 502 aprovados e 1 ignorado**, 30,474 s em Python 3.14.6/Windows. Único skip: symlink/WinError 1314. Passaram dez smoke tests com widgets reais, o ícone real e mutexes entre processos; bgerrors/after de teardown conferidos. Bloqueadores injetados na suíte, sem encerramento de aplicativos do usuário.
- Backend/Banco: 52 testes de guarda/mailbox. Frontend: 41 fluxos GUI simulados, 13 mainGUI, dez nativeGUI e 14 de bandeja incluindo o smoke real. Sintaxe Python 3.12/UTF-8 validada nos 49 arquivos Python; links locais e diff conferidos. Runtime executado permanece 3.14.6.
- Entrada `main.py --gui` real em subprocesso recusou guarda concorrente da mesma fixture com retorno 1/mensagem explícita, sem criar janela/motor ou alterar JSON.
- Smoke de ícone real revelou recusa NIM_ADD no desktop isolado do sandbox, sem ocultação/threads restantes. Execução fora do sandbox passou: NIM_ADD aceito, ready e stop completos em 0,306 s; sem abrir menu ou iniciar motor. A suíte final também passou nesse desktop Windows; a recusa no sandbox não é suprimida ou convertida em skip. Recriação após reinício do Explorer e fallback da janela testados com API nativa falsa; Explorer não foi reiniciado no aceite real.
- Aceite ProcessController/psutil padrão em Windows 10 build 19045: encerramento confirmado de alvo UUID descartável, preservação fora de janela e stop antes do ciclo após salvar regra ativa. Somente cópias temporárias de ping.exe para localhost; fixtures/processos próprios removidos. Não comprova jogos reais ou cobertura Windows 11/catálogo universal.
- Captura visual novamente falhou duas vezes com `window capture timed out: timed out waiting on channel`, após reseleção. Janela abriu com JSON isolado/alvos vazios e motor parado; nenhuma interação visual realizada. Execução/fixture de QA removidas. Visual/DPI/rolagem/menu por interação seguem pendentes; runtime Python 3.12 não disponível (somente 3.14).
- Lotes anteriores nos commits locais `7ed71d4` e `3844ad1`; sem push. Unidade atual integrada e validada para commit local conjunto, sem declarar fase 5 completa ou MVP original.

### Próximos passos
- Conferir `--gui` e menu/retorno da bandeja em Windows, minsize 880×660, DPI, diagnóstico/rolagem e seletores/modal. Investigar helper de captura antes de retomar aceite visual automatizado; smoke nativo não substitui esse aceite.
- Definir contrato de avisos/pausa e esclarecer detalhes de D09/D10 antes de comportamentos dependentes. Sites aguardam Q-HOSTS-01–05; medição de foco/Brave, SQLite, instalador/auto-start e instância elevada global permanecem etapas posteriores.

## 2026-10-11 — Controle gráfico do motor de processos

### Implementado
- Iniciar/Parar na janela, com motor inicialmente parado, confirmação de encerramento sem salvar estado e recusa de rascunho pendente/modal/worker vivo. Monitoramento usa JSON salvo recarregado por ciclo; importação permanece no rascunho até Salvar.
- Worker não daemon, cadência monotônica de 5 s sem sobreposição, parada por Event e gates antes de efeitos. Erro global/configuração interrompe novas ações sem configuração antiga; nova tentativa só após worker anterior terminar.
- Cabeçalho separa estado do motor, última agenda avaliada e relatório do último ciclo da consulta do editor/prévia. Presenter puro mostra encerramentos confirmados, pendências, falhas e diagnósticos limitados; detalhe integral somente leitura/rolável.
- Fechar resolve salvar/descartar/cancelar, sinaliza parada e aguarda por polling antes de destruir. Cancelamento/conflito mantém execução. Finally garante stop/wait fora de callbacks na saída do mainloop. Limpeza de callbacks CustomTkinter em modais/linhas/raiz evita comandos Tcl órfãos.
- Maestro coordenou os três agentes existentes: Backend controlador, Banco presenter/integração JSON, Frontend GUI/lifecycle, Maestro revisão/contratos/docs/validação. Lote anterior já registrado no commit local `7ed71d4`.

### Arquivos principais alterados
- `core/process_controller.py`, `ui/runtime_presenter.py`, `ui/config_gui.py`, `main.py`.
- `tests/test_process_controller.py`, `tests/test_process_controller_config.py`, `tests/test_runtime_presenter.py`, `tests/test_config_gui.py`, `tests/test_config_gui_main.py`, `tests/test_config_gui_native.py`.
- `docs/PROCESS_GUI_CONTRACT.md`, `README.md`, `docs/GUI_EDITOR_CONTRACT.md`, `docs/ARCHITECTURE_BACKEND.md`, `docs/DATA_MODEL.md`, `docs/UI_FLOWS.md`, `docs/DELIVERY_PLAN.md`, `docs/TEST_PLAN.md`, `docs/README.md`, `docs/DEVELOPMENT_LOG.md`.

### Decisões técnicas
- Construção/importação não faz IO, cria thread ou importa psutil; fábrica padrão lazy somente no worker. Widgets permanecem na thread Tk, snapshots são frozen e fronteiras são injetáveis.
- `active` registra a última avaliação da agenda e é preservado ao parar/errar; não representa gate aberto. Avaliação/instante são publicados juntos e avaliações atrasadas após stop não alteram snapshot. Events por execução mantêm gates antigos fechados após retry.
- Parada cooperativa não cancela chamada de SO já iniciada; factory/IO/scan que não retorna pode prolongar a saída. Botões e polling consideram is_alive, inclusive entre publicação de idle/error e término real da thread. CLI independente não é controlada pela janela.
- Sem novo schema, SQLite, histórico de processos, pausa, hosts ou bandeja. Respostas existentes em `docs/USER_ANSWERS.md` preservadas. Dependências já fixadas foram instaladas no `.venv`, sem alteração de requisitos.

### Estado atual
- Suíte integrada: **426 testes descobertos, 425 aprovados e 1 ignorado**, 37,077 s em Python 3.14.6/Windows. Único skip: symlink/WinError 1314. Oito smoke tests nativos passaram, com bgerrors vazios e sem callbacks after restantes na saída. Nenhum bloqueador real foi iniciado nos testes e nenhum aplicativo do usuário foi encerrado.
- Sintaxe Python 3.12/UTF-8 validada nos 42 arquivos Python; links locais e diff conferidos. Runtime executado permanece 3.14.6.
- Janela de QA abriu fora do sandbox, com JSON isolado/alvos vazios e motor parado. Captura falhou com `FrameArrived timed out` e novamente `window capture timed out` após reseleção; nenhuma interação visual foi executada. Execuções temporárias de QA foram encerradas pelo caminho exclusivo da fixture. Inspeção visual/DPI/rolagem e encerramentos reais permanecem pendentes.
- Unidade completa e validada para commit local conjunto, sem push. Fase 5 completa e MVP do escopo original continuam pendentes; painel planejado não mede foco.

### Próximos passos
- Abrir `.venv/Scripts/python.exe main.py --config ./data/config.json --gui` em Windows; conferir quatro abas, minsize 880×660, DPI, scroll de diagnósticos e seletores/modal. Investigar indisponibilidade da captura antes de retomar aceite automatizado.
- Validar iniciar/parar/fim de janela com aplicativo descartável dedicado e JSON isolado, nunca aplicativos do usuário. Executar runtime Python 3.12; sintaxe compatível não substitui esse ensaio.
- Próxima evolução independente: definir contrato da bandeja/instância única e ocultar versus sair, preservando início explícito e shutdown ordenado. Para sites, fechar Q-HOSTS-01–05 em USER_ANSWERS antes de implementar comportamentos dependentes. Pausas/avisos, foco/SQLite e instalador permanecem etapas posteriores.

## 2026-10-11 — Painel semanal e portabilidade da configuração

### Implementado
- Aba inicial Visão geral com intervalos/horas planejadas por dia e semana, navegação entre semanas e orientação de primeiro uso. Prévia acompanha o rascunho; consulta da agenda continua usando baseline salvo, sem confundir planejamento com foco medido ou bloqueio efetivo.
- Duplicação de horários validada, busca nas quatro categorias com índices originais de edição/remoção e mensagens distintas para lista vazia/filtro sem resultados. Orientação identifica horários desativados e proteção adicional sem alvos.
- Importar JSON substitui somente o rascunho após confirmação/validação; Salvar permanece explícito e detecta conflitos. Exportar cria JSON novo com extras/Unicode/regras preservados, sem sobrescrever destinos ou alterar baseline/dirty. Configuração tem rolagem interna.
- Coordenação dos agentes existentes no Maestri: Backend entregou prévia/duplicação; Banco, portabilidade/sessão; Frontend, GUI/testes; Maestro definiu contrato, revisou/refinou, integrou e validou.

### Arquivos principais alterados
- `core/agenda_preview.py`, `core/config_editor.py`, `core/config_session.py`, `core/config_portability.py`, `ui/config_gui.py`.
- `tests/test_agenda_preview.py`, `tests/test_config_editor.py`, `tests/test_config_portability.py`, `tests/test_config_gui.py`, `tests/test_config_gui_native.py`.
- `README.md`, `docs/CONFIG_EVOLUTION_CONTRACT.md`, `docs/GUI_EDITOR_CONTRACT.md`, `docs/ARCHITECTURE_BACKEND.md`, `docs/DATA_MODEL.md`, `docs/UI_FLOWS.md`, `docs/DELIVERY_PLAN.md`, `docs/TEST_PLAN.md`, `docs/README.md`, `docs/DEVELOPMENT_LOG.md`.

### Decisões técnicas
- Prévia pura reutiliza união do scheduler e recorta por dia civil de segunda a domingo; inclui cauda do domingo anterior, sem dupla contagem. Apenas minutos planejados, sem SQLite/coleta de foco, dependências novas ou alteração de schema.
- Importação preserva baseline para manter conflito externo; exportação prepara temporário/flush/fsync no diretório destino e publica sem substituição: `os.rename` no Windows e hard link nos demais sistemas. Rename evita exigir hardlinks em discos Windows removíveis; FAT/exFAT real não foi ensaiado.
- Exportação recusa ativo/aliases/destinos existentes. Limpeza remove só temporário; pode deixar temporário/diretórios preparados se houver falha de cleanup. No ramo hard link, erro de cleanup após publicação preserva destino novo completo. Não há durabilidade absoluta em crash nem proteção contra troca adversarial de diretórios/reparse points.
- Respostas existentes em `docs/USER_ANSWERS.md` preservadas. Nenhuma decisão de hosts, pausa ou medição de foco foi antecipada; esta unidade complementa o editor independente.

### Estado atual
- Suíte completa do Maestro: **359 testes descobertos, 353 aprovados e 6 ignorados**, 24,940 s em Python 3.14.6. Cinco smoke tests gráficos ignorados por CustomTkinter ausente; um teste de symlinks por WinError 1314. Corrida com `os.rename` real, aliases/hardlinks, roundtrip e referência independente de minutos passaram. Sintaxe 3.12 válida nos 37 arquivos Python; UTF-8 e diff conferidos.
- Instalação de `requirements.txt` novamente indisponível neste ambiente. GUI testada por fluxos com widgets simulados e arquivos reais; **renderização, DPI e rolagem nativa ainda não verificadas**. Runtime 3.12, FAT/exFAT real e runtime POSIX pendentes. Testes não tocaram hosts nem encerraram aplicativos.
- Unidade revisada e validada. A primeira tentativa de staging foi impedida por `.git/index.lock` com `Permission denied`; na retomada, o usuário liberou a permissão e solicitou o commit local único dos 20 arquivos relacionados. Sem push. Fase 5 completa e MVP do escopo original permanecem pendentes, incluindo controle gráfico do bloqueador/bandeja e fases 3–7.

### Próximos passos
- Em Windows com dependências disponíveis: executar `tests.test_config_gui_native` e abrir `main.py --config .\data\config.json --gui`; conferir quatro abas, prévia, busca, seletores/modal, rolagem em 880×660 e DPI. Corrigir incompatibilidades observadas antes do aceite nativo.
- Próxima evolução independente: definir contrato do controlador gráfico de processos (iniciar/parar explicitamente, snapshots de estado efetivo, worker fora de Tk, gate antes de efeitos, saída ordenada) e dividir Backend/Frontend/Banco antes da implementação; reutilizar o bloqueador existente.
- Para sites, fechar Q-HOSTS-01–05 em `docs/USER_ANSWERS.md` e criar contrato da fase 3 antes de implementar comportamentos dependentes. Pausas/avisos, bandeja, coleta de foco/SQLite e instalador continuam etapas posteriores.

## 2026-10-09 — Editor gráfico de horários e aplicativos

### Implementado
- `--gui` abre editor CustomTkinter com abas Horários, Jogos / Apps e Configuração. CRUD de janelas/dias e quatro listas de processos, seletor de pastas e campos separados de cmdline; nenhum default de bloqueio ativado.
- Diálogos atualizam o rascunho; Salvar/Ctrl+S publica pelo repositório existente. Recarregar/Ctrl+R confirma descarte quando necessário; fechar oferece salvar/descartar/cancelar. Erros e conflitos preservam a edição. Callbacks de inicialização/status são cancelados ao fechar.
- `ConfigSession` mantém baseline/rascunho e consulta a última agenda carregada/salva; não mistura edição pendente com estado de bloqueio aplicado. Dependência gráfica importada somente em `--gui`; modos existentes continuam independentes.

### Arquivos principais alterados
- `main.py`, `requirements.txt`, `core/config_session.py`, `ui/config_gui.py`.
- `tests/test_config_session.py`, `tests/test_config_gui_main.py`, `tests/test_config_gui.py`, `tests/test_config_gui_native.py`.
- `README.md`, `docs/GUI_EDITOR_CONTRACT.md`, `docs/README.md`, `docs/REQUIREMENTS.md`, `docs/UI_FLOWS.md`, `docs/ARCHITECTURE_BACKEND.md`, `docs/DATA_MODEL.md`, `docs/DECISIONS.md`, `docs/DELIVERY_PLAN.md`, `docs/TEST_PLAN.md`, `docs/DEVELOPMENT_LOG.md`.

### Decisões técnicas
- Complemento independente das fases 1/2 enquanto Q-HOSTS-01–05 continuam sem resposta; `docs/USER_ANSWERS.md` preservado. Não fechar decisões de sites, pausa, foco ou integração da bandeja nesta unidade.
- CustomTkinter 6.0.0 fixado, mantendo a stack do escopo. Nenhuma mudança de schema, migração, SQLite ou bloqueador; persistência/validação reutilizadas. Concorrência continua otimista, com pequena corrida antes do replace já documentada.
- Consulta gráfica usa o snapshot carregado/salvo, não o rascunho nem uma leitura automática de arquivos externos. Fechar este editor não encerra um watcher separado. Bandeja e fase 5 completa continuam pendentes.

### Estado atual
- Suíte final: **306 testes descobertos, 304 aprovados e 2 ignorados**, 11,390 s em Python 3.14.6. Novos testes cobrem 31 cenários de sessão/dispatch/fluxos com arquivos reais; os dois smoke tests nativos foram ignorados por ausência de CustomTkinter.
- Sintaxe Python 3.12 válida nos 33 arquivos Python; runtime 3.12 ainda não executado. UTF-8/links locais e diff conferidos. Testes não tocaram hosts/perfil real nem encerraram aplicativos.
- Editor gráfico implementado, mas **renderização e execução nativa ainda não verificadas**: ambiente impede download do PyPI, e o helper de Computer Use falhou por native pipe indisponível, inclusive após reinicialização. Não registrar fase 5 como concluída; testes simulados não substituem aceite gráfico.
- A restrição inicial de escrita em `.git/index.lock` foi resolvida na retomada com permissão explícita do usuário para o commit local. Os 19 arquivos desta unidade foram preparados em conjunto; a conferência adicional da suíte manteve 304 aprovados e 2 ignorados. Sem push.

### Próximos passos
- Em Windows com rede, instalar `requirements.txt`, executar `tests.test_config_gui_native` e abrir `main.py --config .\data\config.json --gui` (criar JSON com `--init-config` somente se ausente). Conferir abertura, diálogos, teclado, tamanhos mínimos e DPI; corrigir incompatibilidades observadas antes de declarar aceite nativo.
- Ler e preservar respostas em `docs/USER_ANSWERS.md`; fechar Q-HOSTS-01–05 antes do contrato/implementação de hosts. Ensaiar sites primeiro com arquivos isolados.
- Integração da GUI ao bloqueador/bandeja, pausas/avisos, SQLite/estatísticas e instalador permanecem etapas posteriores. Aceite de encerramentos reais e runtime 3.12 também continuam pendentes.

## 2026-10-08 — Limpeza dos temporários de testes

### Implementado
- Removidas, a pedido do usuário, 14 pastas `.config-cli-<UUID>` preexistentes na raiz, verificadas como fixtures com apenas `config.json` de teste.
- `.gitignore` cobre os oito padrões de diretórios temporários usados pela suíte, restritos à raiz do workspace.

### Arquivos principais alterados
- `.gitignore`
- `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Ignorar somente prefixos identificados no código dos testes; não usar regra genérica para pastas `.config*`. Diretórios necessários do projeto e dados locais foram preservados.
- Testes já registram cleanup; resíduos podem permanecer após interrupção/falha de limpeza. Ignorar temporários não substitui essa limpeza.

### Estado atual
- 14 resíduos removidos; os 19 testes da CLI passaram em 0,684 s sem deixar novas pastas `.config-cli-*`.
- `git check-ignore` confirmou os oito padrões e a preservação de cinco caminhos normais; `git diff --check` sem erros.

### Próximos passos
- Manter cleanup explícito nas novas fixtures e acrescentar ao `.gitignore` apenas novos prefixos temporários efetivamente usados. Desenvolvimento de hosts segue aguardando Q-HOSTS-01–05 em `docs/USER_ANSWERS.md`.

## 2026-10-08 — Editor interativo de horários e processos

### Implementado
- `--edit-config` permite listar/adicionar/alterar/remover horários e as quatro listas de processos por menu em português, sem JSON manual. Rascunho validado, Salvar explícito, Recarregar com descarte e Sair/EOF/Ctrl+C sem gravar alterações pendentes.
- Snapshots validam a mesma leitura capturada; salvar compara bytes antes da preparação e novamente antes do replace, detectando alterações/remoção externas. Falhas preservam arquivo/rascunho; baseline retornado corresponde aos próprios bytes publicados.
- Retomada coordenada dos agentes Maestri: Backend revisou rascunho/CRUD; Banco, persistência; Frontend, menus/flags/erros; Maestro integrou, validou e atualizou documentos. A unidade existente no working tree foi concluída sem promover pendências de produto a decisões.

### Arquivos principais alterados
- `core/config.py`, `core/config_editor.py`, `core/config_repository.py`, `main.py`, `ui/__init__.py`, `ui/config_cli.py`.
- `tests/test_config_editor.py`, `tests/test_config_repository.py`, `tests/test_config_cli.py`, `tests/test_config_editor_main.py`, `tests/test_config_editor_integration.py`.
- `README.md`, `docs/CONFIG_EDITOR_CONTRACT.md`, `docs/README.md`, `docs/DELIVERY_PLAN.md`, `docs/DECISIONS.md`, `docs/REQUIREMENTS.md`, `docs/ARCHITECTURE_BACKEND.md`, `docs/DATA_MODEL.md`, `docs/UI_FLOWS.md`, `docs/TEST_PLAN.md`, `docs/DEVELOPMENT_LOG.md`.

### Decisões técnicas
- Complemento independente das fases 1/2 e preparação de RF01/RF24; não entrega GUI/bandeja da fase 5. Biblioteca padrão, sem novas dependências ou mudança de schema.
- Reutilizar parsing/serialização/gravação temporária/fsync/replace existentes. Detecção por bytes é otimista: há pequena corrida entre última conferência e replace, sem CAS/lock para escritores externos, merge automático ou sobrescrita forçada.
- Extras permanecem opacos e preservados; ordem/duplicatas das listas mantidas. Editor não instancia bloqueadores, mas watcher já em execução pode observar JSON salvo no próximo ciclo. Safelist adicional não remove proteção obrigatória.

### Estado atual
- Suíte completa final: **273 testes OK**, 18,358 s em Python 3.14.6, conferidos pelo Maestro após os três relatórios; Frontend também confirmou 273 testes em 18,507 s. A contagem anterior de 272 foi substituída pela evidência final. Cinco testes de integração do editor, incluindo três subprocessos. Sintaxe 3.12 nos 27 arquivos Python e UTF-8/links locais conferidos; runtime 3.12 não executado.
- Fases 1/2 e editor CLI funcionais. Sem hosts, avisos/pausa, GUI/bandeja, SQLite, instalador ou aceite de encerramentos reais. Nenhum teste desta unidade alterou hosts/perfil ou encerrou aplicativo do usuário.
- Diretórios `.config-cli-*` já presentes na retomada foram preservados fora da unidade/commit; novas fixtures têm cleanup e a suíte passou.
- Revisões completas de Backend/Banco/Frontend recebidas e integradas à validação acima: erro de iteração dos dias convertido em ConfigError sem mutação; persistência validada contra bytes capturados/publicados; lazy import testado sem dependência da ordem de discovery. A restrição inicial de escrita em `.git/index.lock` foi resolvida na retomada com escalonamento autorizado para preparar o commit local único; sem push.

### Próximos passos
- Ler `docs/USER_ANSWERS.md` e consolidar respostas Q-HOSTS-01–05 em DECISIONS antes dos comportamentos dependentes da fase 3; campos ainda vazios, sem aprovação. Preservar integralmente respostas preenchidas.
- Após respostas, definir `docs/PHASE3_CONTRACT.md` para domínios, marcadores, backup, preservação, flush e falhas; dividir entre Backend/Banco/Frontend e validar com arquivos isolados antes de hosts real.
- Executar futuramente o runtime Python 3.12 e aceite de processos em ambiente dedicado; manter catálogo/desempenho/Windows 11 como limites pendentes. GUI segue CustomTkinter/pystray; fase 6 depende do mecanismo de domínio ativo Brave (D19).

## 2026-10-05 — Fase 2: bloqueador de processos e perguntas em arquivo

### Implementado
- Bloqueador com adaptador psutil, proteção prioritária, regra conjunta por executável/trecho literal sem caixa, pastas por destino resolvido e preservação de dados inacessíveis.
- Identidade PID+create_time revalidada antes de efeitos; uma espera coletiva de até 2 s, kill revalidado e confirmação pendente somente por leitura nos ciclos seguintes. Eventos deduplicados em memória; relatório parcial em erro global.
- JSON promove quatro listas de processos sem defaults ativos, preservando extras e bytes em erro; cmdline legada em texto exige correção explícita sem migração inferida.
- CLI mantém diagnóstico padrão; `--watch --apply-processes` aplica somente processos, com relógio real/gates, recarga validada, cadência monotônica e Ctrl+C. Fora da janela só reconcilia pedidos anteriores, sem novos alvos.
- Coordenação Maestri: Banco/Backend/Frontend implementaram seus lotes; Maestro definiu contratos, revisou e integrou. Descoberta foi otimizada sem autorizar efeitos por metadados leves.
- A pedido do usuário, `docs/USER_ANSWERS.md` centraliza perguntas/respostas para evitar interferência de relatórios do Maestri; campos preenchidos devem ser preservados. Próximas perguntas de hosts estão ali, ainda sem aprovação.

### Arquivos principais alterados
- `core/models.py`, `core/config.py`, `core/proc_blocker.py`, `main.py`, `requirements.txt`.
- `tests/test_config.py`, `tests/test_main.py`, `tests/test_phase1_integration.py`, `tests/test_process_config.py`, `tests/test_proc_blocker.py`, `tests/test_process_adapter.py`, `tests/test_process_main.py`, `tests/test_process_wait_integration.py`, `tests/test_phase2_integration.py`.
- `README.md`, `docs/PHASE2_CONTRACT.md`, `docs/USER_ANSWERS.md` e documentos de decisões/arquitetura/dados/requisitos/validação/entrega.

### Decisões técnicas
- Usuário confirmou D14/D15 e reconfirmou VS Code/IntelliJ/PyCharm/terminal/Codex e trecho cmdline sem caixa por argumento. Nenhuma instalação/lista de bloqueio foi inventada.
- psutil 7.2.2 fixado em ambiente virtual local; testes doubles evitam encerramentos reais. ProcessDiscovery não tem identidade nem autoriza ação; cache de caminhos só vale na descoberta, nunca nas guardas antes de efeito.
- Ancestral já ausente ou PID comprovadamente reutilizado termina cadeia de ancestrais vivos; acesso negado/identidade ambígua preserva a guarda. Corrigida recusa de inicialização causada pelo ancestral já encerrado do Explorer.
- Arquivo de respostas será lido antes de novas etapas; vazio não é aprovação. Decisões confirmadas são consolidadas em DECISIONS sem reescrever respostas do usuário.

### Estado atual
- Implementação da fase 2 integrada. Suíte final: **206 testes OK**, 10,542 s em Python 3.14.6/psutil 7.2.2; sintaxe 3.12 em 18 arquivos Python e links locais/UTF-8 conferidos. Runtime 3.12 ainda não executado.
- Windows build 10.0.19045: contexto próprio e varreduras somente por leitura passaram. Com cerca de 293 processos, vazio/nome/pasta levaram 0,910/0,923/1,243 s; chamadas terminate/kill impedidas, zero chamadas/eventos. Antes da otimização, inspeção completa levou 21,899 s.
- Não houve teste de encerramento real de jogos/apps, nem edição de hosts/perfil do usuário. Aceite Windows dedicado, Windows 11, recursos RNF01, muitos alvos/latência e elevação continuam pendentes. Catálogo não garante classificação universal de apps renomeados/portáteis/helpers órfãos; incluir ferramentas adicionais na safelist.
- Sem sites, avisos/pausa, GUI/bandeja, SQLite, mutex/instalador ou histórico durável; fases correspondentes permanecem futuras. Encerramento no Windows é forçado e não garante salvar o jogo.

### Próximos passos
- Ler `docs/USER_ANSWERS.md`; aguardar respostas Q-HOSTS-01–05 antes dos comportamentos dependentes da fase 3. Não enviar perguntas por formulários enquanto este fluxo em arquivo estiver em uso.
- Fase 3: definir contrato do hosts/backup/marcadores/flush/preservação e implementar primeiro com arquivos isolados, sem tocar hosts real antes das decisões e revisão.
- Manter aceite de processos reais em ambiente dedicado pendente; não tratar catálogo finito ou amostras locais como prova universal.
- Fase 6 continua dependendo do mecanismo de domínio ativo Brave (D19); eventos de processos ainda não são SQLite.

## 2026-10-05 — Fase 1: configuração JSON e agendador

### Implementado
- Configuração JSON com validação de horários/dias, janelas desativadas por `days: []`, preservação de campos adicionais da raiz e erros que mantêm o arquivo intacto.
- Gravação validada por temporário no mesmo diretório, flush/fsync e substituição atômica; testes de falha de escrita/substituição verificam preservação do original.
- Agendador puro com dias pelo início, meia-noite, virada semanal, união de sobrepostas/adjacentes, bordas início incluído/fim excluído e próximo início efetivo sem reinícios falsos.
- CLI para criar configuração vazia explicitamente, validar, consultar data local e reavaliar a cada 5 s com recarga do JSON e encerramento por Ctrl+C.
- Trabalho distribuído: Backend implementou agenda; Banco, JSON; Frontend, CLI/integração; Maestro, tipos compartilhados, comparação independente, documentação e integração.

### Arquivos principais alterados
- `core/models.py`
- `core/config.py`
- `core/scheduler.py`
- `main.py`
- `tests/test_config.py`
- `tests/test_scheduler.py`
- `tests/test_scheduler_reference.py`
- `tests/test_main.py`
- `tests/test_phase1_integration.py`
- `README.md`
- `.gitignore`
- `docs/PHASE1_CONTRACT.md`
- `docs/DECISIONS.md`
- `docs/DELIVERY_PLAN.md`
- `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Biblioteca padrão e unittest nesta fase; APIs compartilhadas definidas em PHASE1_CONTRACT. Sem instalar dependências das fases posteriores.
- JSON inválido interrompe com erro e é preservado; dias vazios salvam janela desativada, conforme novas respostas D17/D20.
- Campos desconhecidos na janela e chaves JSON duplicadas são rejeitados para evitar descarte/override silencioso; extras da raiz continuam opacos e não aplicados.
- Transições futuras calculadas pela união semanal recorrente; materialização de intervalos datados não inventa início no limite de geração.
- Fixtures usam diretórios UUID isolados com permissões herdadas para compatibilidade com o sandbox Windows/Python 3.14, sem mudar código produtivo ou ACLs globais; os 68 temporários vazios identificados no workspace foram removidos.

### Estado atual
- Fase 1 funcional por CLI; nenhuma janela ativa na configuração inicial. Avaliação da agenda não executa bloqueadores no Windows.
- `python -B -m unittest discover -s tests -v`: 75 testes passaram em Python 3.14.6, incluindo subprocessos, recarga e Ctrl+C controlado, preservação de dados e referência independente de calendário.
- Sintaxe Python 3.12 verificada por ast.parse nos 11 arquivos Python; execução em runtime 3.12 ainda não verificada.
- Ainda pendentes: processos/hosts, avisos e pausa, bandeja/GUI, SQLite/estatísticas, instalador e medição de CPU/RAM. Identificação de domínio ativo do Brave continua sem mecanismo aprovado.
- Criação inicial da CLI usa modo exclusivo para impedir sobrescrita; falha após início da escrita pode deixar um arquivo novo incompleto, com erro explícito. Substituição atômica de configuração existente é oferecida por save_config; não há promessa de durabilidade absoluta em crash.

### Próximos passos
- Fase 2: fechar D14 (proteção obrigatória) e D15 (cmdline/pastas) antes de implementar qualquer encerramento; preservar a regra conjunta Minecraft e a safelist prioritária.
- Backend implementa proc_blocker com adaptador testável; Banco alinha eventos de processos efetivamente encerrados (D16); Frontend prepara feedback de falhas sem antecipar bloqueio aplicado.
- Manter fase 1 reutilizável pela UI futura; sugestões de listas, edição gráfica e integração Windows ainda pertencem às fases seguintes.
- Executar testes relevantes e atualizar este log no mesmo commit da próxima unidade concluída, sem push automático.

## 2026-10-05 — Base documental e decisões de desenvolvimento

### Implementado
- Análise do escopo e criação da documentação de requisitos, arquitetura, interface, dados, decisões, plano de entrega e validação, com índice de leitura.
- Coordenação dos agentes Backend, Frontend e Banco de dados pelo Maestro; cada especialista produziu seu documento, posteriormente consolidado com as respostas do usuário.
- Registro de decisões: avisos 5/1 min, Sair com liberação, recuperação após crash ao reabrir, janelas noturnas pelo dia inicial, segunda=0 até domingo=6, início incluído/fim excluído, igualdade inválida e união de adjacentes.
- Foco apenas nas janelas e fora da pausa de descanso; apps de estudo editáveis; uma conta Windows; configuração escolhida antes de ativar; semana local segunda–domingo; tentativas por processo efetivamente encerrado; dados mínimos e exclusão do histórico na desinstalação.
- Regra adicional para Brave: contar por domínios de estudo adicionados pelo usuário, com lista de bloqueio também personalizável; não contar uso indiscriminado do navegador.

### Arquivos principais alterados
- `docs/README.md`
- `docs/REQUIREMENTS.md`
- `docs/DECISIONS.md`
- `docs/ARCHITECTURE_BACKEND.md`
- `docs/UI_FLOWS.md`
- `docs/DATA_MODEL.md`
- `docs/DELIVERY_PLAN.md`
- `docs/TEST_PLAN.md`
- `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Preservar o escopo original; respostas explícitas prevalecem nos documentos complementares e ficam rastreadas em `DECISIONS.md`.
- Separar requisitos, propostas técnicas e pendências. Contratos de código, schema SQLite, migrações e integrações ainda não foram aprovados nem implementados.
- Recuperação diferida escolhida pelo usuário mantém a arquitetura de processo único; não há watchdog exigido. Após crash, hosts pode continuar bloqueado até reabrir.
- Não inferir executáveis a partir dos nomes Brave, IDEs, Codex, Claude e ChatGPT; identificação real depende de configuração e ambiente.

### Estado atual
- Repositório contém documentação; não há aplicação, testes executáveis, banco criado ou instalador.
- A documentação fornece RF01–RF24 rastreados, sete fases e critérios de validação planejados; não constitui evidência de funcionamento do app.
- Validação documental: os 10 arquivos Markdown (escopo original + 9 novos) foram lidos como UTF-8; links locais conferidos e RF01–RF24 presentes na matriz. Não há testes de aplicação para executar nesta etapa.
- Regra de produto D19 respondida: lista editável de domínios de estudo; mecanismo de identificação da aba/domínio ainda pendente. Medir somente processo em primeiro plano não atende essa distinção. Não há extensão, coleta de histórico ou nova API aprovada.
- Outras pendências estão registradas: proteção obrigatória, correspondência cmdline/pastas, interrupções de pausa, avisos, configuração inválida, durabilidade, identidade elevada e critérios de desempenho.

### Próximos passos
- Antes da fase 6, propor fonte do domínio ativo no Brave e representação da lista de estudo (D19), submetendo mecanismo e políticas de subdomínios/conflitos à revisão; preservar dados mínimos.
- Para a fase 1, fechar contrato de validação/persistência JSON (D17), preservando calendário e fluxo inicial já respondidos; propor interfaces concretas Backend/Banco/Frontend para revisão.
- Antes da fase 2, resolver proteção de processos (D14) e regra conjunta `javaw.exe` + `.minecraft`/normalização de pastas (D15).
- Consultar `DELIVERY_PLAN.md` ao iniciar software; manter testes acompanhantes e este log no mesmo commit da unidade correspondente, sem push automático.

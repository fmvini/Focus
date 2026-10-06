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

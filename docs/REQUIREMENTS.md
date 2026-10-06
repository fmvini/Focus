# Requisitos e rastreabilidade

Fonte: [escopo original](Focus%20Blocker_%20escopo%20do%20projeto.md), seções 1–13, e respostas do usuário em 2026-10-05, registradas em `DECISIONS.md`. Os IDs RF são os da fonte. Os IDs RNF e C usados aqui são identificadores documentais, sem criar novos requisitos.

Status: agenda/JSON/CLI e regras de processos implementados, conforme contratos das fases 1/2. RF01 tem persistência, edição gráfica fica na fase 5; RF02–RF04 têm agenda/ciclo; RF07–RF11 têm matcher, guardas, adaptação Windows e confirmação por identidade testados com doubles. Contexto real verificado por leitura; encerramentos reais e classificação universal de RF10 não foram comprovados. Resultados/limites em TEST_PLAN/DEVELOPMENT_LOG; ambiguidades em [DECISIONS.md](DECISIONS.md).

## Objetivo e fronteira

Confirmado pelas seções 1, 3 e 12: aplicativo local para Windows 10/11, Python 3.12+, bloqueio leve de jogos, launchers e sites em múltiplas janelas. Mantém ferramentas de estudo/desenvolvimento livres. Há bandeja, configuração, pausa e estatísticas; distribuição por instalador com início no login. Não há conta, nuvem, bloqueio de celular, proxy DNS, exceções por canal ou modo anti-burla.

## Requisitos funcionais

| ID | Requisito confirmado | Critério observável derivado | Pendência |
| --- | --- | --- | --- |
| RF01 | Criar, editar e excluir janelas; todos os dias por padrão; início incluído/fim excluído e igualdade inválida (D08) | Alteração válida salva; segunda=0 até domingo=6 (D04); primeiro uso sem horários ativos (D13) | Demais validações/gravação: D17 |
| RF02 | Suportar meia-noite; dia selecionado é o de início (D04) | Segunda 22:00–02:00 inclui terça até 02:00, usando convenção aprovada | D04 respondida |
| RF03 | Unir sobreposições e adjacências (D08) | Janelas sobrepostas ou com fim=início seguinte formam bloqueio contínuo | D10: avisos da união |
| RF04 | Reavaliar bloqueio a cada 5 s | Núcleo consulta horário/configuração no ciclo previsto; evidência também sob carga | D08; desempenho real pendente |
| RF05 | Toast 5 e 1 min antes do início | Avisos emitidos nas duas antecedências para a janela elegível | D01, D10 |
| RF06 | Avisar apenas com jogo/launcher aberto; opção de sempre avisar | Condição e opção refletem configuração e processos presentes | D10, D13 |
| RF07 | Encerrar processo pelo nome do executável | Processo elegível é encerrado durante bloqueio | D15 |
| RF08 | Encerrar processo cujo caminho pertença à pasta bloqueada | Processo da pasta elegível é encerrado; fora dela permanece livre | D15 |
| RF09 | Encerrar processo por padrão na linha de comando | Caso Minecraft com `.minecraft` é detectado; `javaw.exe` de IDE não é encerrado indiscriminadamente | D15 |
| RF10 | Safelist prevalece, protegendo IDE, terminal, navegador e sistema | Conflito entre lista de bloqueio e proteção preserva o protegido | D14, D15 |
| RF11 | Reencerrar processo reaberto; varredura de 5 s | Reabertura elegível é detectada no próximo ciclo de varredura | D16; ciclo sob muitos processos a validar |
| RF12 | Escrever domínios no hosts para `127.0.0.1` e `::1` | Entrada em bloqueio produz bloco delimitado com as duas famílias | D03, D13 |
| RF13 | Remover apenas linhas do app ao liberar | Conteúdo externo ao bloco `FOCUS-BLOCKER-START/END` permanece preservado | D03; marcador corrompido pendente |
| RF14 | Executar flush DNS após cada mudança | Mudança efetiva no hosts aciona `ipconfig /flushdns` e registra falha caso ocorra | Tratamento/repetição de erros pendente |
| RF15 | Backup antes da primeira alteração do hosts | Backup existe antes de qualquer escrita inicial | D17 |
| RF16 | Pausar só durante bloqueio; espera cancelável de 60 s mantém bloqueio (D09) | Cancelamento não libera nem conta pausa; início de espera não libera | D09: pedidos repetidos/limites |
| RF17 | Liberar sites/apps por 15 min e indicar tempo restante | Ao terminar espera, bloqueadores liberam e bandeja informa contagem | D09 |
| RF18 | Avisar 1 min antes do fim da pausa; retomar somente se houver janela ativa (D09) | Não reativar bloqueio fora do horário | D10: condicional e canal de aviso |
| RF19 | Registrar pausa efetivada; espera cancelada não conta (D09) | Uma liberação corresponde a pausa; cancelamento não incrementa total | D09: interrupção/atribuição diária |
| RF20 | Apps elegíveis em primeiro plano nas janelas e fora da pausa; ociosidade >5 min interrompe; Brave conta só em domínios de estudo escolhidos (D19) | Fora da janela/descanso não conta; Brave em domínio não elegível não conta; domínio elegível e usuário ativo podem contar | D06: identificação; D12: medição; D19: mecanismo/subdomínios |
| RF21 | Foco por dia, semana segunda–domingo e total; pausas e tentativas por processo encerrado com sucesso (D12/D16) | Agregações conferem com dados; calendário local; visitas web e falhas de encerramento não incrementam tentativas | D11–D12, D16: mecanismos pendentes |
| RF22 | Bandeja: estados bloqueando/livre/pausado; Abrir/Pausar/Sair | Estado e menu acompanham núcleo; janela abre sob demanda | D02, D09; representação visual pendente |
| RF23 | Abas Horários, Sites, Jogos/Apps, Estatísticas, Configurações | As cinco áreas ficam acessíveis pela janela | Detalhes em UI_FLOWS |
| RF24 | Editar domínios, executáveis e pastas pela UI | Adicionar/remover e persistir listas sem editar JSON manualmente | D06, D13, D14, D15 |

## Requisitos não funcionais

| ID | Fonte | Exigência confirmada | Evidência necessária |
| --- | --- | --- | --- |
| RNF01 | §3 | CPU abaixo de 1% e RAM abaixo de 80 MB em repouso | Medição em ambiente/hardware e metodologia ainda a definir, D18 |
| RNF02 | §3–4 | Uma instância, por mutex | Segunda abertura não cria outro núcleo; escopo por usuário/máquina depende de D07 |
| RNF03 | §3, §10 | Início com Windows, elevado, sem UAC a cada login | Instalação e tarefa agendada testadas; identidade e contas dependem de D07 |
| RNF04 | §3, §8; D02–D03 | Sair limpa hosts; após falha, limpar ao reabrir, conforme ajuste explícito do usuário | Ensaios de saída normal e crash seguido de reabertura; bloqueio pode persistir até reabrir |
| RNF05 | §3 | Dados locais; sem internet ou conta | Aplicação não exige serviço remoto; dados/diagnóstico dependem de D11 |
| RNF06 | §1 | Windows 10/11, Python 3.12+ | Executável e instalador validados nas versões e arquiteturas-alvo, D18 |

## Restrições e comportamentos complementares

| ID | Fonte | Confirmado |
| --- | --- | --- |
| C01 | §4 | Processo elevado único, núcleo em thread de fundo, bandeja pystray, janela CustomTkinter; estado compartilhado protegido por lock |
| C02 | §4–5, §10 | Configuração JSON; estatísticas SQLite; dados finais em `%APPDATA%\FocusBlocker` |
| C03 | §7 | Encerramento de processo: `terminate()`, espera 2 s, `kill()` se necessário; métrica de tentativa bloqueada |
| C04 | §8 | Inicializar limpa bloco antigo e reavalia; encerramento normal faz cleanup; ligar no meio da janela aplica bloqueio sem aviso |
| C05 | §8 | Suspensão/hibernação: próximo ciclo reavalia; mudança do relógio é aceita para o bloqueio leve |
| C06 | §8 | Falha ao editar hosts: registrar erro e alertar na bandeja |
| C07 | §6, §8–9 | Hosts sem curinga; lista de domínios é ponto de partida; conexões Brave já abertas podem persistir; DNS seguro deve ser desativado |
| C08 | §10 | PyInstaller `--noconsole --uac-admin`; Inno Setup; tarefa de login elevada; desinstalação remove tarefa e limpa hosts |
| C09 | §1, §6 | Sites-alvo: YouTube, Netflix, Instagram, TikTok, X, Twitch, Prime Video, Disney+ e Max |
| C10 | §1 | Reddit, Google, docs, IDE e terminal livres; demais alvos fora das listas livres; safelist tem prioridade |
| C11 | Resposta D06 | Apps de estudo configuráveis na UI; incluir Brave, IDEs, Codex, Claude e ChatGPT, com processos reais ainda a identificar |
| C12 | Resposta D07 | Uso por uma única conta Windows |
| C13 | Resposta D13 | Primeiro uso sem horários ativos; listas como sugestões; bloqueio só após escolher/salvar; horários do exemplo não são defaults |
| C14 | Resposta D11 | Dados mínimos para totais; histórico sem expiração; apagar histórico ao desinstalar; destino da configuração ainda pendente |
| C15 | Resposta D19 | Usuário adiciona domínios de estudo e personaliza domínios bloqueados; listas têm finalidades distintas; não contar qualquer uso do Brave |

Referências a IDs já respondidos são rastreabilidade; consultar o estado exato em `DECISIONS.md`. Avisos, saída/recuperação, calendário das janelas, limites/adjacência, exclusão da pausa do foco, única conta e ativação inicial têm respostas explícitas.

As rotas reais de jogos, a expansão de `www.`, a lista completa de processos do sistema e as métricas de foco não estão totalmente especificadas. Não promover exemplos a defaults nem prometer cobertura completa de sites pelo hosts.

## Dependências de aceite

- RF01–RF06 dependem da semântica de tempo e avisos.
- RF07–RF11 dependem da proteção e identificação precisa de processos.
- RF12–RF15 e RNF04 dependem de recuperação segura e preservação do hosts.
- RF16–RF21 dependem das regras de pausa e contabilização.
- RF22–RF24 refletem as mesmas regras aprovadas; não devem criar outra fonte de verdade na interface.

Consulte [TEST_PLAN.md](TEST_PLAN.md) para os cenários e [DELIVERY_PLAN.md](DELIVERY_PLAN.md) para a ordem das entregas.

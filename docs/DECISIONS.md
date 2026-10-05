# Decisões, divergências e perguntas

Fonte: [escopo](Focus%20Blocker_%20escopo%20do%20projeto.md) e respostas explícitas do usuário nesta conversa em 2026-10-05. Propostas técnicas são possibilidades para revisão, não alterações do escopo.

## Decisões já declaradas

Windows 10/11; Python 3.12+; bloqueio leve; múltiplas janelas em JSON; processos por executável/pasta/padrão de linha de comando; safelist prioritária; sites via hosts; Brave sem DNS seguro; espera de pausa de 60 s e liberação por 15 min; bandeja + CustomTkinter; SQLite local; instalador com auto-start elevado. Fontes: §§1–5, 7, 9–10.

As divergências de avisos e recuperação foram respondidas abaixo. Exemplos de dados e mecanismos técnicos ainda possuem detalhes pendentes; esta síntese não os fecha silenciosamente.

## Perguntas já enviadas ao usuário

1. **D01:** prevalecem avisos aos 5 e 1 minuto, apesar da tabela que diz 2–5 minutos?
2. **D02/D03:** Sair libera imediatamente? Após crash, recuperar automaticamente sem reabrir, ou aceitar limpeza na próxima inicialização?
3. **D04/D05/D06/D07:** janela de segunda 22:00–02:00 inclui terça até 02:00? Foco conta todo o dia ou só em janela? Quais apps contam? Instalação para uma conta Windows ou várias?

Respondidos D01–D05, D07–D08 e o fluxo de D13; D06, D09, D11–D12 e D16 têm respostas de produto com detalhes ainda pendentes. O conjunto documental não fecha os comportamentos ainda pendentes para implementação.

## Decisões respondidas em 2026-10-05

| ID | Resposta explícita do usuário | Consequência |
| --- | --- | --- |
| D01 | Sim, avisos aos 5 e 1 minuto | RF05 prevalece sobre a expressão 2–5 min da tabela inicial |
| D02 | Sair libera | Menu Sair encerra com limpeza dos bloqueios; nenhuma fricção adicional foi solicitada |
| D03 | Após falha, limpar ao reabrir | Recuperação diferida aprovada; hosts pode permanecer bloqueado até a próxima inicialização. Não há watchdog ou recuperação independente aprovados |
| D04 | Sim: segunda 22:00–02:00 inclui terça até 02:00; segunda=0 até domingo=6 | Dias selecionados designam início da janela; o trecho após meia-noite mantém o vínculo; contrato numérico aprovado |
| D05 | Foco apenas nas horas bloqueadas; não conta enquanto em pausa, que é descanso | Só creditar dentro da janela e fora da pausa. A referência ao método Pomodoro descreve a intenção de descanso; não definiu ciclos automáticos adicionais |
| D06 | Brave, IDEs, Codex, Claude e ChatGPT; deve ser possível adicionar apps de estudo na aplicação | Lista de apps de estudo editável pela UI confirmada. Executáveis reais, IDEs específicas e uso via navegador/terminal ainda a identificar |
| D07 | Única conta Windows | Não implementar suporte a várias contas como requisito; preservar identificação da conta e cuidado com hosts global |
| D13 | Escolha do usuário; sim, configurar antes de ativar | Começar sem horários ativos, apresentar listas do escopo como sugestões e ativar só após escolher/salvar horários e listas. Não ativar os horários de exemplo automaticamente |
| D09 | Sim, adotar as regras propostas de pausa | Pedido só durante bloqueio; espera mantém bloqueio; cancelamento não conta; liberação de 15 min após espera; fora da janela não retomar bloqueio. Pedidos repetidos, reinício e suspensão ainda pendentes |
| D11 | Sim às regras de estatísticas; apagar histórico ao desinstalar | Guardar só dados necessários aos totais; histórico sem expiração até desinstalar. Preservação/exclusão da configuração não foi explicitamente respondida |
| D12 | Sim à semana de segunda a domingo e calendário local do Windows | Calendário fechado; duração observada, suspensão e mudanças de relógio ainda exigem detalhamento |
| D16 | Sim, uma tentativa por processo efetivamente encerrado, sem visitas a sites | Não contar falha de encerramento nem acesso web; identidade/deduplicação ainda a detalhar |
| D08 | Sim às regras propostas de limites e união | Intervalos com início incluído/fim excluído; início igual ao fim inválido; unir janelas adjacentes além das sobrepostas |
| D19 — produto respondido | Contar por sites: usuário adiciona domínios considerados estudo e personaliza sites bloqueados | Manter lista de estudo distinta da lista de bloqueio; contar Brave em primeiro plano somente quando domínio for elegível, dentro da janela e fora da pausa. Mecanismo de identificar domínio e política de subdomínios ainda a definir |
| D17 — leitura respondida | Sim, preservar e informar erro de JSON inválido/corrompido | Interromper inicialização com erro, sem substituir configurações; exigir correção. Demais políticas de persistência continuam distintas |
| D20 | Salvar como janela desativada | `days: []` é válido e não bloqueia; ausência de `days` usa todos os dias, conforme RF01 |

**Ajuste explícito do escopo em D03:** a frase de §3 sobre não ficar bloqueado para sempre passa a ser interpretada conforme a recuperação ao reabrir de §8, escolhida pelo usuário. A documentação não promete liberação automática após crash. O original foi preservado para rastreabilidade.

## Registro de pendências

| ID | Lacuna / pergunta | Fonte e impacto | Quem decide |
| --- | --- | --- | --- |
| D01 — fechado | Avisos exatamente 5/1 min | Resposta do usuário; corrige divergência entre §1 e RF05 | Usuário, 2026-10-05 |
| D02 — fechado | Sair libera bloqueios | Resposta do usuário; cleanup de encerramento normal | Usuário, 2026-10-05 |
| D03 — fechado | Após crash, limpar ao reabrir | Resposta do usuário; recuperação diferida, sem garantia independente | Usuário, 2026-10-05 |
| D04 — fechado | Dia de início; segunda=0 até domingo=6 | RF01–02 e respostas | Usuário, 2026-10-05 |
| D05 — fechado | Só nos horários de bloqueio e fora da pausa | RF20 e respostas; pausa é descanso | Usuário, 2026-10-05 |
| D06 — parcial | Apps de estudo editáveis: Brave, IDEs, Codex, Claude e ChatGPT; falta identificação real; Brave segue domínios de D19 | RF20, RF24 e respostas; não inventar nomes de executáveis | Usuário/equipe |
| D07 — fechado | Única conta Windows | Resposta do usuário; identidade elevada/mutex ainda são detalhes técnicos | Usuário, 2026-10-05 |
| D08 — fechado | Início incluído/fim excluído; igualdade inválida; unir adjacentes | RF01–04 e resposta | Usuário, 2026-10-05 |
| D09 — parcial | Regras respondidas acima; falta pedidos repetidos, fim da janela durante espera, reinício/suspensão e atribuição diária | RF16–19; transições e dados | Usuário/equipe |
| D10 | Como evitar avisos repetidos? Avisar ao retomar pausa só se haverá bloqueio? Avisos perdidos por suspensão/edição/relógio são recuperados? Aviso de retorno depende de jogo aberto? | RF05–06/18 e §8 | Usuário para comportamento; Backend para mecanismo |
| D11 — parcial | Só dados para totais, sem expiração, apagar histórico ao desinstalar; granularidade técnica e exclusão manual/exportação não definidas | RF19–21 e resposta | Banco propõe granularidade; usuário decide funcionalidades adicionais |
| D12 — parcial | Semana segunda–domingo, calendário local; falta medição após suspensão/atraso/mudança de relógio | RF20–21 e resposta | Banco/Backend propõem medição |
| D13 — fluxo fechado | Configurar antes de ativar, sem horários ativos; listas sugeridas | JSON §5 é exemplo; sugestões §6 precisam de validação; desenho dos controles ainda a detalhar | Usuário para fluxo; equipe para propostas de UI |
| D14 | Safelist de sistema completa, identificação por nome/caminho e possibilidade de editar/remover proteções? | RF10; prioridade definida, conteúdo e governança incompletos | Usuário aprova política; Backend propõe identificação |
| D15 | Padrão cmdline é substring literal ou regex? Case sensitivity? Expandir variáveis/atalhos/junctions em pastas? Qual tratamento de acesso negado? | RF07–09, §6–7; proteção contra falso positivo | Usuário para regra; Backend para normalização e falhas |
| D16 — parcial | Processo encerrado com sucesso; visitas web não contam; falta identidade/deduplicação técnica | RF11/21 e resposta | Banco/Backend |
| D17 — parcial | JSON inválido interrompe com erro e arquivo intacto, confirmado; substituição atômica escolhida para fase 1. Migrações/SQLite, backup hosts e configuração/backups na desinstalação ainda pendentes | RF15, §§5/10, D11 e resposta de 2026-10-05; durabilidade | Usuário para política visível; equipe para mecanismos |
| D18 | Versões/arquiteturas Windows/Brave de validação, hardware de referência, método de CPU/RAM, instalador e assinatura? | §§1/3/9–10/13; entrega e critérios medíveis | Usuário para público-alvo; equipe propõe matriz |
| D19 — mecanismo pendente | Regra por domínios editáveis aprovada; como identificar domínio da aba ativa? Correspondência exata ou com subdomínios? Como tratar domínio ausente e conflito estudo/bloqueio? | Respostas do usuário; amplia RF20 originalmente baseado só em processo | Equipe propõe mecanismo; usuário aprova comportamentos ainda ambíguos |
| D20 — fechado | Dias vazios desativam a janela sem excluí-la | Resposta do usuário ao iniciar desenvolvimento | Usuário, 2026-10-05 |

### Perguntas respondidas e detalhamento futuro

As perguntas enviadas nesta sessão foram respondidas e consolidadas acima. D19 aprova lista de domínios de estudo editável e personalização de sites bloqueados, sem estabelecer domínios iniciais obrigatórios. Não assumir análise de títulos, extensão, histórico de navegação, API local ou mudança na política de dados locais. A escolha do mecanismo e os demais detalhes abertos serão tratados antes das fases dependentes.

## Escolhas técnicas da fase 1

Desenvolvimento autorizado pelo usuário em 2026-10-05. O Maestro definiu as APIs em [PHASE1_CONTRACT.md](PHASE1_CONTRACT.md), biblioteca padrão e `unittest`, sem dependências externas para esta fase. Configuração valida somente `windows` e preserva campos adicionais para evolução, sem executá-los como regras de bloqueio. `windows` é obrigatório; dias ausentes usam todos; dias vazios desativam conforme D20. Gravação usa temporário no diretório de destino e substituição atômica. Identificação da conta via APPDATA sem fallback oculto.

CLI de diagnóstico: status por padrão; criação explícita sem sobrescrever; horários ISO locais sem fuso para consulta; `--at` não combinado com modo contínuo; retorno 0 sucesso/Ctrl+C, 1 erro operacional/configuração, 2 argumento inválido. São escolhas de implementação desta etapa, não afirmações de que bloqueadores/GUI estejam prontos.

## Contradições e limites que não podem ser ocultados

- **Recuperação, resolvida por D03:** um processo encerrado abruptamente não consegue executar a limpeza. O usuário escolheu limpar ao reabrir; não se exige mecanismo independente. Encerramento normal continua exigindo cleanup, sem pressupor que `atexit` cubra crash.
- **Cobertura dos sites:** o escopo reconhece que hosts não aceita curingas. Os domínios são candidatos à validação, incluindo abreviações `www.`; não são garantia de bloquear toda reprodução ou tráfego existente. Proxy DNS permanece fora do escopo.
- **Ciclo de 5 s:** esperar até 2 s por processo na mesma thread pode consumir o intervalo quando vários processos precisam ser encerrados. A estratégia de execução exige desenho e medição, preservando a proteção e o fluxo do escopo.
- **Dados de exemplo:** a árvore `data/` não substitui o destino instalado em APPDATA; o JSON mostrado não contém todos os sites, launchers nem a opção de sempre avisar. O contrato final ainda depende de defaults e revisão.
- **Sistema versus usuário:** D07 definiu única conta; hosts atua na máquina e APPDATA aponta a uma conta. O instalador ainda precisa resolver corretamente a identidade elevada e o mutex, sem ampliar para várias contas.
- **Brave e estatísticas, detalhe adicional aprovado:** D19 exige distinguir domínios de estudo; o desenho de §7 que observa somente processo em primeiro plano é insuficiente. A lista de estudo não é lista de liberação durante bloqueio e não deve sobrescrever hosts implicitamente. Classificação, representação JSON, identificação da aba ativa e tratamento de conflitos precisam de proposta e revisão antes da fase 6.

## Como fechar uma decisão

Registrar a resposta explícita, data e origem; atualizar os documentos impactados; só então liberar as tarefas dependentes. Se for apenas recomendação da equipe, manter marcada como proposta. Uma decisão que altera o escopo deve ser identificada como alteração, com o trecho substituído explicado aqui; preservar o documento original nesta etapa.

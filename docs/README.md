# Documentação de desenvolvimento — Focus Blocker

Status: fases 1/2, editor CLI, painel/configuração gráfica, controle explícito do motor, bandeja e guarda de instância gráfica. Evidências e limites atuais no log; fase 5 completa e MVP original ainda pendentes. Ver [instruções de execução](../README.md).

## Fonte e autoridade

- [Escopo original](Focus%20Blocker_%20escopo%20do%20projeto.md): fonte dos requisitos e das decisões já declaradas pelo usuário. Preservado nesta tarefa.
- Regras de trabalho: `C:/Users/vinic/.codex/AGENTS.md`, consultado pelo Maestro. Commits locais por unidade concluída, sem push; registro em `DEVELOPMENT_LOG.md` no mesmo commit.
- Os documentos abaixo detalham o escopo. Não aprovam silenciosamente soluções para ambiguidades ou novos requisitos.
- **Confirmado pelo escopo** indica conteúdo explícito da fonte. **Proposta técnica** indica recomendação para revisão. **Pendente** indica informação que ainda exige resposta ou validação. Uma proposta não deve ser implementada como decisão aprovada.
- O exemplo de JSON da seção 5 e as listas de partida da seção 6 não equivalem a uma configuração inicial completa e validada.

## Guia de leitura

| Documento | Uso |
| --- | --- |
| [REQUIREMENTS.md](REQUIREMENTS.md) | RF01–RF24, requisitos não funcionais, critérios observáveis e rastreabilidade |
| [DECISIONS.md](DECISIONS.md) | Divergências, perguntas ao usuário e decisões técnicas ainda não aprovadas |
| [USER_ANSWERS.md](USER_ANSWERS.md) | Canal local de perguntas/respostas; usuário preenche aqui, Maestro preserva e consolida decisões |
| [ARCHITECTURE_BACKEND.md](ARCHITECTURE_BACKEND.md) | Núcleo, agendamento, bloqueadores, comunicação e recuperação |
| [UI_FLOWS.md](UI_FLOWS.md) | Bandeja, abas, pausa, configuração e feedback ao usuário |
| [DATA_MODEL.md](DATA_MODEL.md) | JSON, estatísticas locais em SQLite e lacunas do contrato de dados |
| [DELIVERY_PLAN.md](DELIVERY_PLAN.md) | Sete fases do escopo, dependências, responsáveis e condições para iniciar |
| [TEST_PLAN.md](TEST_PLAN.md) | Validação das regras, integração Windows, casos de falha e entrega |
| [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md) | Estado real do projeto e ponto de retomada |
| [PHASE1_CONTRACT.md](PHASE1_CONTRACT.md) | APIs e limites da primeira implementação |
| [PHASE2_CONTRACT.md](PHASE2_CONTRACT.md) | Proteções, regras conjuntas, adaptador e modo de aplicação de processos |
| [CONFIG_EDITOR_CONTRACT.md](CONFIG_EDITOR_CONTRACT.md) | Rascunho, edição pela CLI, salvamento e conflitos externos |
| [GUI_EDITOR_CONTRACT.md](GUI_EDITOR_CONTRACT.md) | Editor gráfico, sessão de edição, consulta da agenda e limites de validação nativa |
| [CONFIG_EVOLUTION_CONTRACT.md](CONFIG_EVOLUTION_CONTRACT.md) | Painel semanal, duplicação, busca e importação/exportação do rascunho |
| [CONFIG_DIFF_CONTRACT.md](CONFIG_DIFF_CONTRACT.md) | Comparação de alterações pendentes GUI/CLI, índices e limites de apresentação |
| [REVIEW_NAVIGATION_CONTRACT.md](REVIEW_NAVIGATION_CONTRACT.md) | Navegação dos apontamentos às categorias/linhas originais sem editar dados |
| [RULE_LIST_VIEW_CONTRACT.md](RULE_LIST_VIEW_CONTRACT.md) | Busca e ordenação visual das regras com cadastro/índices originais preservados |
| [PROCESS_GUI_CONTRACT.md](PROCESS_GUI_CONTRACT.md) | Motor gráfico: início/parada, worker, snapshots, recarga e saída ordenada |
| [TRAY_CONTRACT.md](TRAY_CONTRACT.md) | Bandeja explícita, fila de comandos Tk e uma GUI por configuração/sessão |
| [INITIAL_SETUP_CONTRACT.md](INITIAL_SETUP_CONTRACT.md) | Primeira configuração gráfica, sugestões opt-in e criação exclusiva ao Salvar |

## Coordenação da equipe

Agentes identificados por `maestri list`: Maestro, Backend, Frontend e Banco de dados. Na etapa documental, cada especialista produziu seu documento. Na fase 1, Backend entregou agendador; Banco, JSON; Frontend, CLI/integração. Maestro definiu tipos, verificou a agenda independentemente, revisou a unidade e integrou documentação/commit.

Na fase 2, Backend mantém bloqueador/adaptador; Banco, JSON tipado; Frontend, CLI; Maestro, contratos/revisão/integração. Antes de iniciar implementação posterior, consultar log/decisões; não interpretar ausência de resposta como autorização para escolher comportamento de produto.

No editor CLI independente, Backend mantém `ConfigDraft`; Banco, snapshots/persistência; Frontend, menu e flags; Maestro, integração, documentação e commit único. A unidade foi complementada pelo editor gráfico, painel semanal/portabilidade, controle de processos e bandeja. Backend entregou controlador/guarda, Banco presenters/integração com JSON, Frontend lifecycle/widgets e Maestro revisão/integração. Avisos/pausa e aceite visual da fase 5 continuam pendentes.

A pedido do usuário, novas perguntas ficam em USER_ANSWERS, sem formulários/mensagens Maestri para colher respostas. Ler esse arquivo antes de cada etapa; preservar o texto preenchido, acrescentar perguntas com novos IDs e consolidar somente respostas explícitas em DECISIONS. Relatórios dos agentes não são respostas do usuário.

## Limites desta documentação

O projeto possui núcleo de agenda/configuração, editores de terminal/gráfico, aplicação de regras de processos por CLI e GUI, bandeja explícita e guarda gráfica. A suíte integrada inclui widgets nativos com controlador simulado; não substitui inspeção visual/DPI. Não há bloqueador de sites, avisos/pausa, schema SQLite ou instalador. Testes/resultados ficam em TEST_PLAN/DEVELOPMENT_LOG; catálogo de proteção não comprova reconhecimento universal de aplicativos. Versões Windows alvo, sites/Brave, desempenho e recuperação do hosts exigem validação própria.

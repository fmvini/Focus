# Documentação de desenvolvimento — Focus Blocker

Status: fases 1/2 e editor interativo de horários/processos por CLI; etapas restantes e limites de validação no log. Ver [instruções de execução](../README.md).

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

## Coordenação da equipe

Agentes identificados por `maestri list`: Maestro, Backend, Frontend e Banco de dados. Na etapa documental, cada especialista produziu seu documento. Na fase 1, Backend entregou agendador; Banco, JSON; Frontend, CLI/integração. Maestro definiu tipos, verificou a agenda independentemente, revisou a unidade e integrou documentação/commit.

Na fase 2, Backend mantém bloqueador/adaptador; Banco, JSON tipado; Frontend, CLI; Maestro, contratos/revisão/integração. Antes de iniciar implementação posterior, consultar log/decisões; não interpretar ausência de resposta como autorização para escolher comportamento de produto.

No editor independente, Backend mantém `ConfigDraft`; Banco, snapshots/persistência; Frontend, menu e flags; Maestro, integração, documentação e commit único. A unidade complementa as fases 1/2 e prepara a configuração da fase 5, sem entregar GUI/bandeja.

A pedido do usuário, novas perguntas ficam em USER_ANSWERS, sem formulários/mensagens Maestri para colher respostas. Ler esse arquivo antes de cada etapa; preservar o texto preenchido, acrescentar perguntas com novos IDs e consolidar somente respostas explícitas em DECISIONS. Relatórios dos agentes não são respostas do usuário.

## Limites desta documentação

O projeto possui núcleo de agenda/configuração, editor interativo de horários/processos e aplicação de regras de processos por CLI. Não há bloqueador de sites, avisos/pausa, GUI, schema SQLite ou instalador. Testes/resultados ficam em TEST_PLAN/DEVELOPMENT_LOG; catálogo de proteção não comprova reconhecimento universal de aplicativos. Versões Windows alvo, sites/Brave, desempenho e recuperação do hosts exigem validação própria.

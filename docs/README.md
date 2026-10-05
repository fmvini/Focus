# Documentação de desenvolvimento — Focus Blocker

Status: fase 1 implementada — JSON, agendador e CLI; fases posteriores e detalhes técnicos em aberto. Ver [instruções de execução](../README.md).

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
| [ARCHITECTURE_BACKEND.md](ARCHITECTURE_BACKEND.md) | Núcleo, agendamento, bloqueadores, comunicação e recuperação |
| [UI_FLOWS.md](UI_FLOWS.md) | Bandeja, abas, pausa, configuração e feedback ao usuário |
| [DATA_MODEL.md](DATA_MODEL.md) | JSON, estatísticas locais em SQLite e lacunas do contrato de dados |
| [DELIVERY_PLAN.md](DELIVERY_PLAN.md) | Sete fases do escopo, dependências, responsáveis e condições para iniciar |
| [TEST_PLAN.md](TEST_PLAN.md) | Validação das regras, integração Windows, casos de falha e entrega |
| [DEVELOPMENT_LOG.md](DEVELOPMENT_LOG.md) | Estado real do projeto e ponto de retomada |
| [PHASE1_CONTRACT.md](PHASE1_CONTRACT.md) | APIs e limites da primeira implementação |

## Coordenação da equipe

Agentes identificados por `maestri list`: Maestro, Backend, Frontend e Banco de dados. Na etapa documental, cada especialista produziu seu documento. Na fase 1, Backend entregou agendador; Banco, JSON; Frontend, CLI/integração. Maestro definiu tipos, verificou a agenda independentemente, revisou a unidade e integrou documentação/commit.

Para desenvolvimento posterior, a proposta de divisão está no plano de entrega. Antes de iniciar implementação, consultar o log e as decisões pendentes. Não interpretar ausência de resposta como autorização para escolher comportamento de produto.

## Limites desta documentação

O projeto agora possui núcleo de agenda/configuração e CLI, com 75 testes executáveis da fase 1. Não há bloqueadores de processos/sites, GUI, schema SQLite ou instalador. A validação dessa fase não comprova cobertura de sites, integração Brave, desempenho ou recuperação do hosts; esses critérios serão verificados nas entregas correspondentes.

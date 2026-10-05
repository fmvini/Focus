# Plano de entrega e coordenação

Base: sete fases da seção 11 do [escopo](Focus%20Blocker_%20escopo%20do%20projeto.md). Estado atual: documentação em análise; todas as fases de software ainda não iniciadas. Não há estimativa de prazo ou esforço aprovada.

## Preparação documental

- Maestro consolida o escopo, a rastreabilidade, as perguntas e a revisão dos três documentos especialistas.
- Backend documenta núcleo, bloqueadores, contratos internos e recuperação em `ARCHITECTURE_BACKEND.md`.
- Frontend documenta bandeja, janela e fluxos em `UI_FLOWS.md`.
- Banco de dados documenta JSON/SQLite e contabilização em `DATA_MODEL.md`.
- As questões do usuário ficam centralizadas em `DECISIONS.md`; especialistas não fecham regras de negócio por conta própria.

## Entregas do software

A atribuição e o detalhamento abaixo são **proposta de organização da equipe**, alinhada às fases existentes; não autorizam iniciar implementação nesta tarefa documental.

| Fase | Entrega do escopo | Responsável proposto e colaboração | Dependências para fechar | Critério de pronto |
| --- | --- | --- | --- | --- |
| 1 | Agendador, JSON e testes | Backend: agendamento; Banco: contrato/persistência; Frontend: revisão do contrato | D04, D08, D13, D17; fronteira de pausa em D09 | Janelas, dias, meia-noite e sobreposição verificados; configuração válida preservada; inválida tratada conforme decisão |
| 2 | Bloqueio de processos | Backend; Banco: definição de eventos; Frontend: surfacing de erros | Fase 1; D14–D16 | Launchers/jogos elegíveis encerram, reabertura é detectada e protegidos ficam intactos |
| 3 | Bloqueio de sites | Backend; Frontend: alertas/onboarding | Fase 1; D03, D07, D13, D17 | Hosts modificado só no bloco do app; backup e flush; Brave verificado durante/fora da janela; garantia de recuperação validada |
| 4 | Avisos e pausa | Backend: transições; Frontend: contagem/cancelamento; Banco: registros | Fases 1–3; D01–D02, D09–D10, D16 | Avisos definidos; espera cancelável; 15 min liberados; retorno e persistência de eventos consistentes |
| 5 | Bandeja e configuração | Frontend; Backend: comandos/snapshots; Banco: gravação | Fases 1–4; D06, D13–D15 | Cinco abas e menu; edição prevista sem JSON manual; estados e falhas refletem o núcleo |
| 6 | Estatísticas | Banco: esquema/agregações; Backend: coleta; Frontend: visualização | Fases 1–5; detalhes pendentes D06, D09, D11–D12, D16–D17; regra/mecanismo Brave D19 | Totais coerentes; foco só nas janelas e fora da pausa; Brave segundo regra aprovada; ociosidade/suspensão validadas |
| 7 | Instalador e auto-start | Backend: build/tarefa/cleanup; Frontend: instalação/configuração Brave; Banco: dados instalados | Fases 1–6; D03, D07, D17–D18 | Instalar, iniciar elevado no login e desinstalar limpo em Windows alvo; validar mutex e RNFs |

A definição de eventos de pausa/tentativas deve ocorrer antes da fase 4, embora a tela final de estatísticas esteja na fase 6. O trabalho de preparação dos contratos pode ocorrer antes da UI, sem considerar a funcionalidade entregue.

## Dependências entre agentes

| Interface de trabalho | Alinhamento necessário antes de codificar |
| --- | --- |
| Backend ↔ Banco | Dias/horários, contrato de JSON, gravações, eventos de pausa/tentativa, tempo de foco e concorrência SQLite |
| Backend ↔ Frontend | Estados e comandos, cancelamento, momento de aplicar mudanças, erros visíveis e atualização de bandeja/janela |
| Banco ↔ Frontend | Campos editáveis, validações, agregações e calendário semanal |
| Maestro ↔ equipe | Decisões do usuário, conflitos entre documentos, delimitação de tarefas e revisão da unidade concluída |

## Condições de conclusão de cada fase

1. Regras que afetam a fase respondidas e refletidas nos documentos.
2. Implementação da unidade completa; sem afirmar que sugestões estão aprovadas.
3. Validação relevante realizada conforme `TEST_PLAN.md`, com resultados reais e limites relatados.
4. Revisão de diff/status; somente arquivos da unidade incluídos.
5. `DEVELOPMENT_LOG.md` atualizado antes da conclusão e no mesmo commit da implementação.
6. Um commit local coerente. Testes acompanhantes não recebem commit próprio. Sem push automático.

Maestro integra cada unidade; em trabalho compartilhado, evitar commits concorrentes e edição simultânea dos mesmos arquivos. Essa coordenação é uma proposta operacional, não uma mudança na arquitetura da aplicação.

## Retomada

O calendário, os limites/adjacência e a ativação inicial já têm respostas em `DECISIONS.md`. Fechar validação/persistência para a fase 1; em paralelo, propor identificação de domínio ativo e contrato da lista editável de estudo no Brave (D19), necessário à fase 6. Revisar contratos especialistas antes de implementá-los. A tarefa atual é documental; nenhuma fase de software foi iniciada.

# Plano de entrega e coordenação

Base: sete fases da seção 11 do [escopo](Focus%20Blocker_%20escopo%20do%20projeto.md). Desenvolvimento autorizado em 2026-10-05; fase 1 concluída com CLI e 75 testes, fases 2–7 pendentes. Não há estimativa de prazo ou esforço aprovada.

## Preparação documental

- Maestro consolida o escopo, a rastreabilidade, as perguntas e a revisão dos três documentos especialistas.
- Backend documenta núcleo, bloqueadores, contratos internos e recuperação em `ARCHITECTURE_BACKEND.md`.
- Frontend documenta bandeja, janela e fluxos em `UI_FLOWS.md`.
- Banco de dados documenta JSON/SQLite e contabilização em `DATA_MODEL.md`.
- As questões do usuário ficam centralizadas em `DECISIONS.md`; especialistas não fecham regras de negócio por conta própria.

## Entregas do software

A fase 1 foi distribuída aos três agentes pelo Maestro; as atribuições das fases posteriores continuam como proposta de organização. O usuário autorizou iniciar o desenvolvimento, preservando as decisões e limites registrados.

| Fase | Entrega do escopo | Responsável proposto e colaboração | Dependências para fechar | Critério de pronto |
| --- | --- | --- | --- | --- |
| 1 | Agendador, JSON e testes | Backend: agenda; Banco: JSON; Frontend: CLI e integração; Maestro: referência independente/revisão | D04/D08/D13/D20 e leitura D17 respondidos; contratos definidos em PHASE1_CONTRACT; pausa fica na fase 4 | Janelas/dias/meia-noite/sobreposição/adjacência; gravação preserva dados; JSON inválido interrompe com erro |
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

Consultar `DEVELOPMENT_LOG.md` para o resultado da fase 1. Antes da fase 2, resolver a proteção de processos (D14) e correspondência de cmdline/pastas (D15). Para a fase 6, propor identificação do domínio ativo e contrato da lista editável de estudo no Brave (D19); não atribuir foco a qualquer página aberta.

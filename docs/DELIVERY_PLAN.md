# Plano de entrega e coordenação

Base: sete fases da seção 11 do [escopo](Focus%20Blocker_%20escopo%20do%20projeto.md). Desenvolvimento autorizado em 2026-10-05; fase 1 concluída e implementação da fase 2 integrada por CLI, com evidências/limites no log. Fases 3–7 pendentes. Não há estimativa de prazo ou esforço aprovada.

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
| 2 | Bloqueio de processos por CLI implementado | Backend: adaptador/guardas; Banco: JSON; Frontend: aplicação/erros; Maestro: integração/revisão | D14/D15 respondidos; D16 evento em memória | Matcher, ciclo e confirmação testados com doubles; contexto Windows verificado por leitura. Encerramentos reais/jogos e cobertura Windows alvo ainda exigem aceite dedicado; catálogo não certifica proteção universal |
| 3 | Bloqueio de sites | Backend; Frontend: alertas/onboarding | Fase 1; D03, D07, D13, D17 | Hosts modificado só no bloco do app; backup e flush; Brave verificado durante/fora da janela; garantia de recuperação validada |
| 4 | Avisos e pausa | Backend: transições; Frontend: contagem/cancelamento; Banco: registros | Fases 1–3; D01–D02, D09–D10, D16 | Avisos definidos; espera cancelável; 15 min liberados; retorno e persistência de eventos consistentes |
| 5 | Bandeja e configuração | Frontend; Backend: comandos/snapshots; Banco: gravação | Fases 1–4; D06, D13–D15 | Cinco abas e menu; edição prevista sem JSON manual; estados e falhas refletem o núcleo |
| 6 | Estatísticas | Banco: esquema/agregações; Backend: coleta; Frontend: visualização | Fases 1–5; detalhes pendentes D06, D09, D11–D12, D16–D17; regra/mecanismo Brave D19 | Totais coerentes; foco só nas janelas e fora da pausa; Brave segundo regra aprovada; ociosidade/suspensão validadas |
| 7 | Instalador e auto-start | Backend: build/tarefa/cleanup; Frontend: instalação/configuração Brave; Banco: dados instalados | Fases 1–6; D03, D07, D17–D18 | Instalar, iniciar elevado no login e desinstalar limpo em Windows alvo; validar mutex e RNFs |

A definição de eventos de pausa/tentativas deve ocorrer antes da fase 4, embora a tela final de estatísticas esteja na fase 6. O trabalho de preparação dos contratos pode ocorrer antes da UI, sem considerar a funcionalidade entregue.

## Unidade complementar — editor de configuração

Enquanto Q-HOSTS-01–05 permanecem sem resposta, foi concluído o editor CLI independente de horários/processos conforme [CONFIG_EDITOR_CONTRACT.md](CONFIG_EDITOR_CONTRACT.md). Complementa as fases 1/2 sem depender de hosts, pausa ou medição de foco. Backend: rascunho validado; Banco: snapshots e conflitos; Frontend: `--edit-config`; Maestro: integração, docs e commit.

Continuidade: editor gráfico `--gui` implementado conforme [GUI_EDITOR_CONTRACT.md](GUI_EDITOR_CONTRACT.md), reutilizando rascunho/repositório e acrescentando sessão com baseline/alterações pendentes. Controle do bloqueador integrado conforme [PROCESS_GUI_CONTRACT.md](PROCESS_GUI_CONTRACT.md), seguido de bandeja explícita Mostrar/Parar/Sair e guarda gráfica conforme [TRAY_CONTRACT.md](TRAY_CONTRACT.md). Pausa, estados completos da bandeja e campos futuros continuam na fase 5; a fase completa não está concluída. Inspeção visual/DPI ainda pendente; smoke tests/resultados atuais no log.

## Dependências entre agentes

Unidade complementar em 2026-10-11: painel semanal, duplicação de horários,
busca e portabilidade JSON, conforme [contrato](CONFIG_EVOLUTION_CONTRACT.md).
Backend mantém cálculo puro/duplicação; Banco mantém importação/exportação
de rascunho; Frontend integra quatro abas; Maestro revisa e valida a unidade.
Resultados e pendências reais estão no log; esta unidade não conclui a fase 5.

Unidade seguinte concluída: controle gráfico de processos. Backend manteve
worker/snapshots/gates; Banco presenter puro e testes com JSON real; Frontend
comandos/polling/saída e lifecycle de callbacks; Maestro contrato, integração,
documentação e commit. Motor começa parado e não aplica rascunhos pendentes.

Continuação bandeja/instância: Backend mantém guarda Windows de handles;
Banco mantém mailbox limitada e ensaios entre subprocessos; Frontend adapta
pystray e lifecycle Tk; Maestro dependências, revisão, aceites e commit.

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

Consultar `DEVELOPMENT_LOG.md` para resultados atuais. Primeira configuração gráfica reutiliza o editor com rascunho sem arquivo e sugestões opt-in, conforme `INITIAL_SETUP_CONTRACT.md`. Próximo aceite: conferir primeira abertura, `--gui` e menu/retorno da bandeja no Windows, incluindo DPI, rolagem em 880×660 e diagnósticos; captura automatizada voltou a falhar por timeout. Encerramento real de alvo descartável e preservação fora da janela foram ensaiados, sem comprovar jogos reais, todas as versões Windows ou catálogo universal. Runtime Python 3.12 permanece pendente. Próxima evolução: responder Q-PAUSE-01/02 e Q-WARN-01/02 em `USER_ANSWERS.md` antes de comportamentos dependentes; manter motor explicitamente iniciado e shutdown ordenado. Para sites, fechar Q-HOSTS-01–05; validar primeiro com arquivos isolados. Para fase 6, fechar domínio ativo/lista de estudo Brave (D19); não atribuir foco a qualquer página.

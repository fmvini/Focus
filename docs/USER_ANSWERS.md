# Perguntas e respostas do usuário

Este é o canal de esclarecimentos do projeto. O Maestro escreve perguntas aqui; o usuário preenche **Resposta do usuário** diretamente no arquivo. Não é necessário responder pelos formulários/mensagens do Maestri.

## Como usar e preservar respostas

- Escreva abaixo de **Resposta do usuário** e salve o arquivo. Respostas podem ser texto livre; não é necessário escolher uma sugestão.
- Campo vazio significa **não respondido**, nunca aprovação. Sugestão da equipe não é decisão do usuário.
- O Maestro deve ler este arquivo antes de cada etapa, preservar integralmente as respostas e acrescentar perguntas novas sem sobrescrever campos já preenchidos. Se algo estiver ambíguo, criar uma pergunta complementar com novo ID.
- Depois de conferir uma resposta, o Maestro atualiza seu status e registra a decisão em `DECISIONS.md`, com referência ao ID daqui. Não reescrever a resposta original para substituí-la por uma interpretação.
- Relatórios dos agentes não devem ser colados nos campos de resposta. Eles ficam no log/contratos apropriados.
- Arquivo local em `docs/`, acompanhado no Git, para recuperar versões anteriores registradas por commits.

## Decisões já confirmadas — não precisam ser respondidas novamente

Registro consolidado em [DECISIONS.md](DECISIONS.md). As confirmações finais da fase 2 foram recebidas separadamente, depois de uma resposta misturada com relatório de agente:

| ID | Confirmação explícita | Estado |
| --- | --- | --- |
| D14 | Sim às proteções obrigatórias e lista adicional editável; preservar processo com verificação insegura | Registrado |
| D14 — ferramentas | VS Code, IntelliJ, PyCharm, terminal e Codex | Reconfirmado e registrado |
| D15 | Sim ao nome completo sem caixa, pastas/subpastas absolutas com variáveis e cmdline executável + trecho literal obrigatório; links/junctions incertos preservados | Registrado |
| D15 — trecho | Sim, ignorar maiúsculas/minúsculas dentro de cada argumento, sem juntar argumentos separados | Reconfirmado e registrado |

As decisões anteriores D01–D13/D16–D20 mantêm o estado detalhado em DECISIONS; algumas têm detalhes futuros pendentes. Não presumir que a existência de um ID significa que todos os seus detalhes foram respondidos.

## Perguntas para a próxima etapa — bloqueio de sites

Não impedem o commit da implementação de processos já validada. Devem ser respondidas antes dos comportamentos dependentes da fase 3. As sugestões abaixo estão **sem aprovação**.

### Q-HOSTS-01 — Domínios e subdomínios

**Status:** aguardando resposta.

O hosts exige cada domínio concreto; cadastrar `youtube.com` não abrange automaticamente todos os seus subdomínios. Você prefere bloquear somente os domínios cadastrados ou acrescentar também a variante `www.` automaticamente? Outros subdomínios continuariam exigindo cadastro explícito. A lista inicial continuará sendo escolhida por você, conforme D13.

**Sugestão da equipe:** somente os domínios cadastrados, com a UI futura permitindo adicionar cada variante desejada.

**Resposta do usuário:**


### Q-HOSTS-02 — Bloco próprio danificado

**Status:** aguardando resposta.

Se os marcadores do Focus no hosts estiverem incompletos, duplicados ou alterados por outra ferramenta, o app pode interromper a alteração, mostrar o erro e preservar o arquivo para correção, em vez de tentar adivinhar quais linhas apagar?

**Sugestão da equipe:** preservar e informar o erro; nenhuma restauração automática do arquivo inteiro.

**Resposta do usuário:**


### Q-HOSTS-03 — Falha de bloqueio ou liberação

**Status:** aguardando resposta.

Se não for possível escrever o hosts ou atualizar o cache DNS, o app deve continuar bloqueando processos e mostrar que o bloqueio de sites falhou, ou parar a aplicação de todos os novos bloqueios até corrigir o erro? Ao sair, se a limpeza do hosts falhar, pode encerrar com erro explícito informando que sites podem permanecer bloqueados até a correção/reabertura?

**Sugestão da equipe:** manter os processos conforme a agenda, informar falha parcial e nunca indicar sites liberados sem confirmação; na saída, comunicar a falha de limpeza.

**Resposta do usuário:**


### Q-HOSTS-04 — Backup existente

**Status:** aguardando resposta.

Pode haver um único backup inicial do hosts, guardado no diretório local do Focus, sem sobrescrever uma cópia já existente? Se esse backup estiver ilegível ou incompleto antes de uma nova alteração, prefere interromper e pedir correção ou permitir criar outra cópia preservando a anterior? O backup não será usado para substituir automaticamente o hosts inteiro, pois isso poderia apagar alterações de outras ferramentas.

**Sugestão da equipe:** preservar a cópia existente e interromper se não for possível verificar o backup; definir a recuperação explicitamente.

**Resposta do usuário:**


### Q-HOSTS-05 — Orientação para o Brave

**Status:** aguardando resposta.

Na fase 3, ainda sem interface gráfica, pode haver uma orientação pela CLI para desativar o DNS seguro do Brave, explicando que abas/conexões já abertas podem exigir recarregamento? A fase 5 apresentaria essa orientação na interface. Isso não encerrará o Brave, que é protegido.

**Sugestão da equipe:** orientação na CLI agora e na interface depois; configuração do navegador pelo próprio usuário.

**Resposta do usuário:**


## Pendências das etapas posteriores

Pausas/avisos (D09/D10), medição de foco/relógio (D12), domínio ativo do Brave (D19), instalador/dados na desinstalação (D17/D18) serão convertidos em perguntas aqui quando sua etapa começar. Não preencher lacunas com decisões inventadas.

# Arquitetura do backend — Focus Blocker

Documento de referência para implementação, ainda sem código. Fontes: [Focus Blocker: escopo do projeto](<Focus Blocker_ escopo do projeto.md>) e [decisões registradas pelo Maestro](DECISIONS.md), com respostas explícitas do usuário em 2026-10-05. As referências a seção e RF apontam para o escopo; os IDs D apontam para respostas e detalhes pendentes no registro central. Este documento incorpora respostas sem alterar o original nem aprovar soluções para outras lacunas.

## 1. Classificação e alcance

- **Requisito explícito (R):** comportamento ou decisão escrito no escopo, com seção/RF citados.
- **Decisão confirmada (C):** resposta explícita registrada em `DECISIONS.md`, citada pelo ID. Consultar ali o estado atual: alguns IDs têm comportamento de produto respondido e mecanismo técnico ainda pendente.
- **Derivação (D):** consequência conceitual de requisitos citados; não equivale à aprovação de um mecanismo técnico. Quando admite interpretações, a dúvida permanece registrada.
- **Proposta técnica não aprovada (T):** alternativa para implementação; não deve ser tratada como arquitetura confirmada.
- **Decisão pendente (P):** lacuna, conflito ou escolha ainda não resolvida. Os identificadores locais P01–P12 agrupam questões para o Maestro, sem substituir os IDs de `DECISIONS.md`. P01 foi fechada por D03; P07 perdeu a divergência de minutos por D01, mas conserva outras lacunas.
- **Fato técnico externo:** comportamento documentado de uma dependência, com fonte oficial. Uma biblioteca permitir algo não torna seu uso uma decisão do projeto.

“Backend” designa o núcleo local e seus adaptadores de sistema operacional, configuração e estatísticas. Os contratos descritos são internos ao processo; não são endpoints, API HTTP, serviço remoto ou esquema definitivo de classes. Os caminhos da seção 4 do escopo são a estrutura prevista, não evidência de módulos já implementados. Não se declara aqui nenhuma funcionalidade como pronta.

## 2. Arquitetura confirmada e limites

| Tema | Requisito explícito | Referência |
| --- | --- | --- |
| Plataforma e linguagem | Windows 10/11; Python 3.12+ | Seção 1 |
| Modelo de execução | Um processo elevado; núcleo em thread de fundo; bandeja `pystray` em thread própria; janela CustomTkinter sob demanda | Seção 4 |
| Comunicação | Objeto de estado compartilhado protegido por lock | Seção 4 |
| Instância | Uma única instância, com mutex | Seção 3 |
| Cadência | Cálculo de bloqueio a cada 5 s; varredura de processos durante bloqueio a cada 5 s | RF04, RF11; seção 7 |
| Persistência | Configuração JSON; estatísticas SQLite; dados do usuário em `%APPDATA%\FocusBlocker` | Seções 4, 5, 7 e 10 |
| Privilégios e inicialização | Iniciar elevado com o Windows, sem UAC em cada login; instalação cria tarefa de logon com privilégios elevados | Seções 3 e 10 |
| Bloqueio leve | Pausa com fricção; mudança de relógio aceita | Seções 1 e 8 |
| Dados e rede | Todos os dados locais, sem internet nem conta | Seção 3 |
| Recursos | CPU abaixo de 1% e RAM abaixo de 80 MB em repouso | Seção 3 |

**C — Consolidação:** D04 usa dia de início para janela noturna; D05 limita foco aos horários de bloqueio; D06 permite editar apps de estudo (Brave, IDEs, Codex, Claude e ChatGPT, processos ainda a identificar); D07 define única conta Windows; D13 define configuração inicial por escolha do usuário. D09 restringe pedido de pausa ao bloqueio, mantém bloqueio durante espera, exclui cancelamento da contagem e impede retomar fora da janela. D11 define dados mínimos, histórico sem expiração e exclusão do histórico na desinstalação; D12 usa calendário local e semana segunda–domingo; D16 conta processos efetivamente encerrados, sem acessos web. Detalhes ainda não respondidos continuam pendentes.

**C — Respostas incorporadas:** avisos aos 5 e 1 minuto prevalecem sobre “2 a 5 min” (D01); Sair libera os bloqueios, sem fricção adicional solicitada (D02); após crash, limpar ao reabrir, aceitando recuperação diferida sem watchdog exigido (D03). Essas decisões não definem as políticas de erro de cleanup, tempo durante suspensão ou outras pendências.

**R — Limites:** proteção por listas de processos e arquivo `hosts`; Brave com DNS seguro desativado; demais ferramentas e itens fora das listas liberados (seções 1, 6 e 9). Proxy DNS/curinga, modo rígido anti-burla, nuvem, exceções por canal e outros dispositivos ficam fora do escopo atual (seção 12). Serviço SYSTEM + UI aparece apenas como possibilidade futura, não como arquitetura aprovada (seção 4).

**D — Alcance da liberação:** parar a varredura permite abrir apps; encerrar um jogo não é reversível automaticamente. RF17 não manda reiniciar processos encerrados. Reabertura automática seria comportamento adicional e precisaria de decisão.

**P12 — Medição:** o escopo não define método, máquina, duração ou se “repouso” inclui janela aberta. Os limites de recursos são metas a verificar, não resultados já medidos.

## 3. Responsabilidades dos módulos previstos

| Módulo previsto | Responsabilidade confirmada | Fronteira conceitual e o que falta definir |
| --- | --- | --- |
| `main.py` | Iniciar as partes, mutex e cleanup (seção 4); limpeza inicial e normal (seção 8); Sair libera e crash recupera ao reabrir (D02/D03) | Ordem completa de inicialização, reação à segunda instância e a falhas, política de término e alcance do mutex: P10/P11 |
| `core/config.py` | Carregar/salvar `config.json` e validar (seção 4); dar suporte às edições de RF01/RF24 | Regras completas de validação, valores iniciais, atualização durante bloqueio e recuperação de arquivo inválido: P05/P07/P08 |
| `core/scheduler.py` | Janelas, meia-noite, união de sobreposições, pausa e estado (RF01–RF04, RF16–RF18; seção 4) | Semântica de dias, bordas de intervalos, relógios e combinação pausa/janela: P02/P06 |
| `core/proc_blocker.py` | Inspecionar processos com `psutil`; safelist antes de regras por nome, pasta e cmdline; encerrar e contabilizar (RF07–RF11; seção 7) | Normalização, identificação segura, critérios incompletos e definição de tentativa: P04/P05/P09 |
| `core/site_blocker.py` | Backup, bloco próprio no `hosts`, remoção própria, flush DNS (RF12–RF15); limpeza ao Sair/reabrir (D02/D03) | Escrita segura, marcadores danificados, concorrência externa e falhas parciais: P08/P10 |
| `core/notifier.py` | Toasts Windows de início; aviso de retomada cujo canal ainda não foi especificado (RF05/RF06/RF18; seção 4) | Tempos 5/1 confirmados; canal de retomada, supressão/deduplicação e avisos perdidos: P07 |
| `core/stats.py` | Primeiro plano, ociosidade, foco por dia/semana/total, pausas e tentativas em SQLite (RF19–RF21; seção 7) | Contratos de gravação/consulta, fronteiras temporais, esquema e erros: P02/P09/P10 |
| `ui/tray.py` | Estado e comandos Abrir/Pausar/Sair; contagem regressiva da pausa (RF17/RF22) | Protocolo de comando e apresentação de falhas: P03/P10 |
| `ui/window.py` | Abas e edição de horários e listas (RF23/RF24) | Integração Tkinter, aplicação de config e edição de cmdline/safelist: P03/P05/P08 |
| `installer/build.bat` e `installer/setup.iss` | PyInstaller, Inno Setup, tarefa elevada e desinstalação que limpa `hosts` (seções 4 e 10) | Identidade de usuário, opções completas da tarefa e coordenação com app em execução: P11 |

**R:** o núcleo coordena o ciclo da seção 7: relógio/configuração, expiração de pausa, avaliação de janela, avisos, aplicação/remoção de sites, varredura quando bloqueando e atualização de ícone/estatísticas.

**T — Separação sugerida:** manter decisões de agendamento e correspondência de regras separadas dos efeitos de encerrar processos, escrever arquivos e emitir avisos. Essa divisão facilita verificar requisitos sem tocar o sistema operacional, mas as interfaces concretas ainda precisam de aprovação.

## 4. Contratos conceituais internos

Os conteúdos mínimos abaixo são uma **D** das responsabilidades do escopo. São descrições de intenção e resultado; não fixam nomes de funções, tipos Python, filas, assinaturas, exceções ou esquema SQL. Os detalhes adicionais estão identificados como **T** ou **P**.

| Interação interna | Entrada conceitual | Resultado/efeito exigido pelo escopo | Base e pendências |
| --- | --- | --- | --- |
| Configuração → núcleo/agendador | Janelas, dias, avisos, pausa, sites, regras de processos, safelist e apps de dev | Disponibilizar configuração carregada/validada; persistir edições | Seções 4/5; RF01/RF24. Aplicação das mudanças e falhas: P08 |
| Núcleo → agendador | Instante atual, janelas e situação da pausa | Determinar bloqueio atual e vencimento da pausa; considerar meia-noite e união | RF02–RF04/RF18; seção 7. Relógios e bordas: P02/P06 |
| Bandeja → coordenação da pausa | Pedido de pausa ou cancelamento da espera | Espera cancelável de 60 s; depois liberação de 15 min | RF16/RF17. Elegibilidade e repetição: P06 |
| Núcleo → bloqueador de processos | Estado de bloqueio e regras/proteções | Varredura; ignorar protegidos; encerrar correspondências elegíveis | RF07–RF11; seção 7. Semântica de regras e erros: P04/P05/P10 |
| Núcleo/lifecycle → bloqueador de sites | Intenção de aplicar domínios ou remover bloco próprio | Backup antes da primeira alteração; escrita/remoção própria; flush após mudança | RF12–RF15; seção 8; D02/D03. Resultado parcial e reparo: P08/P10 |
| Agendamento/núcleo → notificações | Início de janela próximo; presença de jogo/launcher ou opção de sempre avisar; retomada de pausa | Toast para RF05/RF06; aviso RF18 com canal pendente | Identificação de jogo/launcher, gatilhos e exceções: P07 |
| Núcleo/bloqueador → estatísticas | Observação de primeiro plano e input; pausa; tentativa bloqueada | Soma de foco segundo RF20; registros e consultas de RF19/RF21 | Seção 7. Momento do registro e dados precisos: P09 |
| Núcleo → bandeja/janela | Estado e contagens; erro de `hosts` | Exibir livre/bloqueando/pausado, regressiva e alerta de `hosts` | RF17/RF22; seção 8. Threading e fidelidade ao efeito real: P03/P10 |
| Interface → configuração/estatísticas | Edições autorizadas pelas telas; pedido de resumo | Salvar listas/janelas e apresentar métricas locais | RF01/RF21/RF23/RF24. Semântica de consultas/edições: P08/P09 |
| Lifecycle → partes internas | Iniciar ou encerrar a aplicação | Inicializar, limpar bloco antigo e reavaliar; Sair libera; crash recupera ao reabrir | Seções 4/8; D02/D03. Ordem, prazos operacionais e falhas: P10/P11 |

**T — Estado compartilhado sugerido:** separar intenção do agendador, situação da pausa, tempo restante, resultado observado do `hosts` e erros por componente. Um booleano “bloqueando” não prova que todos os efeitos ocorreram. Campos, responsáveis pelas escritas e quando a UI recebe confirmação estão pendentes (P03/P10).

**T — Resultado de operação sugerido:** distinguir sucesso, ausência de mudança e falha parcial. No bloqueio de processos, separar protegido, sem correspondência, indisponível para inspeção, encerrado e falha ao encerrar. No `hosts`, separar escrita/remoção e flush DNS. Essas categorias não são um enum aprovado nem novos estados visuais de RF22.

**T — Comandos sugeridos:** UI solicita ações ao núcleo; o núcleo publica uma visão consistente do estado. Identificadores de pedido e versão de configuração poderiam evitar que resultados antigos sobrescrevam uma edição mais recente. Protocolo e transporte internos: P03/P08.

## 5. Estados e transições

### 5.1 Estados derivados

| Estado conceitual | Classificação e base | Significado e limite |
| --- | --- | --- |
| Livre | R: RF22; seção 7 | Fora do bloqueio, garantir ausência do bloco próprio no `hosts` |
| Bloqueando | R: RF22; RF11/RF12; seção 7 | Garantir sites e executar varreduras; não significa que toda operação teve sucesso |
| Pausado | R: RF17/RF22 | Sites e apps liberados por 15 min, com contagem regressiva |
| Espera de pausa | D: RF16/RF17 | Pedido em contagem cancelável de 60 s; a liberação só ocorre após a espera. Nome de estado interno não aprovado |
| Inicialização e encerramento | D: seções 4/8 | Etapas de lifecycle, não estados adicionais aprovados para o ícone |
| Aviso próximo | D: RF05/RF18 | Evento de notificação; o escopo não exige um estado de bloqueio separado |

**D:** a espera é distinta da pausa concedida. RF17 não autoriza liberação imediata ao clicar. A agenda continua sendo avaliada por RF04; o escopo não define como apresentar a espera nem o que fazer se a janela terminar durante ela (P06).

### 5.2 Transições com apoio no escopo

| Origem/evento | Transição/ação descrita | Referência | Lacuna que permanece |
| --- | --- | --- | --- |
| Aplicação inicia | Limpar bloco antigo; reavaliar agenda; recuperar bloqueio residual após crash ao reabrir | Seção 8; D03 | Ordem perante config/mutex, falha de limpeza e retomada de pausa anterior: P06/P08/P10/P11 |
| PC inicia no meio de janela | Aplicar bloqueio imediatamente, sem aviso | Seção 8 | O que conta como “imediato” diante do ciclo de 5 s e da inicialização: P12 |
| Livre; entrada em janela | Adicionar sites e varrer processos | RF04/RF11/RF12; seção 7 | Bordas e falhas parciais: P06/P10 |
| Bloqueando; saída de janela | Remover apenas bloco próprio e limpar cache após mudança | RF13/RF14; seção 7 | Prioridade quando há pausa/espera ou edição simultânea: P06/P08 |
| Pedido de Pausar | Só durante bloqueio: começar espera cancelável de 60 s mantendo bloqueio | RF16; D09 | Cliques repetidos: P06 |
| Espera; cancelamento | Cancelar pedido, sem incrementar pausas | RF16; D09 | Resultado quando a agenda mudou durante a espera: P06 |
| Espera completa | Liberar sites/apps e ficar pausado por 15 min | RF17; seção 7 | Falha na remoção do `hosts`, momento de iniciar os 15 min e janela já encerrada: P06/P10 |
| Pausa perto do fim | Aviso de 1 min antes da retomada | RF18 | Se RF06 também condiciona esse aviso; suspensão e ausência de janela futura: P07 |
| Pausa vence | Retomar somente se houver janela ativa; fora dela manter livre | RF18; D09 | Suspensão/reinício e pedidos repetidos: P02/P06 |
| Suspensão/hibernação termina | Próximo ciclo reavalia | Seção 8 | Se suspensão consome espera/pausa e como tratar avisos perdidos: P02/P07 |
| Relógio muda | Alteração aceita no bloqueio leve | Seção 8 | Efeito em duração da pausa, duplicação de avisos e estatísticas: P02/P07/P09 |
| Menu Sair / encerramento normal | Liberar bloqueios e encerrar com limpeza do `hosts`; sem fricção adicional solicitada | Seções 4/8; D02 | Ordenação entre parar núcleo, limpar e liberar mutex; falha de limpeza: P10/P11 |
| Crash/término abrupto | Limpar ao reabrir; recuperação diferida aceita, sem watchdog exigido | Seção 8; D03 | Não há promessa de liberação automática enquanto o app estiver encerrado; falha no novo cleanup: P08/P10 |

### 5.3 Regras de calendário ainda pendentes

**R:** janelas possuem início, fim e dias; padrão todos os dias (RF01). Cruzam meia-noite (RF02) e sobreposições se unem (RF03).

**C — D04/D08:** dia selecionado é o de início; segunda 22:00–02:00 inclui terça até 02:00; segunda=0 até domingo=6; início incluído/fim excluído; igualdade inválida; unir adjacentes e sobrepostas. **P06:** restam instante de aviso após união, espera quando janela termina, pedidos repetidos e interrupções.

**T:** expandir janelas em ocorrências datadas e unir intervalos antes de avaliar bloqueio/avisos é uma alternativa para RF02/RF03. Depende de resolver P06; não fixa aqui horizonte de cálculo, fuso ou convenção de dias.

## 6. Invariantes e correspondência de processos

### 6.1 Invariantes exigidos

1. **R:** safelist tem prioridade sobre nome, pasta e cmdline. IDEs, terminais, navegadores e processos do sistema nunca devem ser encerrados (RF10; seções 7/8).
2. **R:** a seleção de alvo pode ocorrer por nome, caminho dentro de pasta ou padrão contido na cmdline (RF07–RF09). A varredura descrita usa `pid`, `name`, `exe`, `cmdline` (seção 7).
3. **R:** para o Minecraft em Java, a lista inicial cita `javaw.exe` somente quando a cmdline contém `.minecraft`; bloquear todo `javaw.exe` pelo nome derrubaria IDEs Java (seção 6; risco da seção 13). Não transformar esse exemplo em regra genérica de bloqueio de Java.
4. **R:** processos reabertos são encerrados novamente, com varredura a cada 5 s durante bloqueio (RF11; seção 8).
5. **R:** sequência prevista: `terminate()`, espera de 2 s e `kill()` se necessário; contabilizar uma tentativa bloqueada (seção 7).
6. **D:** um processo protegido continua protegido mesmo se estiver dentro de pasta bloqueada ou contiver padrão configurado. A correspondência de bloqueio não autoriza ignorar RF10.

**Fato técnico externo:** no Windows, `psutil.terminate()` é alias de `kill()`, que usa `TerminateProcess`. A sequência do escopo não garante encerramento gracioso nem salvamento do jogo. Isso limita a interpretação da sequência, sem substituí-la por outra solução. [Documentação oficial do psutil — terminate/kill](https://psutil.readthedocs.io/stable/index.html#psutil.Process.terminate)

### 6.2 Proteção incompleta e identidade

**P04:** o JSON da seção 5 mostra alguns executáveis protegidos; não enumera todos os processos das categorias de RF10 nem define como identificá-los. Também não define se a UI pode retirar proteção obrigatória, como proteger o próprio Focus Blocker ou como proceder quando nome/caminho não puderem ser lidos. O exemplo de safelist não prova a garantia “nunca encerrar processos do sistema”.

**T:** prever proteção obrigatória além de exceções editáveis; não encerrar quando não for possível verificar a proteção; conferir a identidade do processo e a proteção novamente antes do efeito. Critérios, abrangência e tratamento de dados ausentes exigem decisão, não são regras já aprovadas.

**Fato técnico externo:** psutil documenta `NoSuchProcess`, `AccessDenied` e `TimeoutExpired`. `terminate()`/`kill()` possuem verificação preventiva de reutilização de PID; isso não torna eternamente válidos os dados lidos antes da ação. [Documentação oficial do psutil — processos e exceções](https://psutil.readthedocs.io/stable/index.html#process-class)

**C — D16:** tentativa é um processo efetivamente encerrado, sem contar falhas ou visitas web. **P09:** identidade/deduplicação entre varreduras e múltiplas regras ainda precisam de mecanismo definido; não duplicar o evento por `terminate` seguido de `kill`.

### 6.3 Nomes, pastas e padrões

| Regra | Requisito explícito | Decisão pendente | Proposta técnica não aprovada |
| --- | --- | --- | --- |
| Nome | Encerrar por nome de executável (RF07) | Igualdade, sensibilidade a maiúsculas, aceitação de caminho em campo `.exe`, nome vazio e conflito com proteção (P04/P05) | Comparação por nome completo normalizado, sem substring ou glob implícito |
| Pasta | Caminho do processo dentro de pasta bloqueada (RF08) | Subpastas, caminho relativo, variáveis de ambiente, identidade de usuário, links/junctions, UNC, pasta inexistente e acesso negado (P05/P11) | Normalizar caminhos e comparar componentes; uma simples comparação de prefixo poderia confundir `C:\Jogos` com `C:\JogosLegitimos`. Política de resolução de links deve ser explícita |
| Cmdline | Linha de comando contém padrão (RF09) | Caixa, substring literal versus regex/glob, inspeção de cada argumento versus linha reconstruída, aspas, padrão vazio e restrição por executável (P05) | Padrões literais não vazios, sem regex/glob implícitos; permitir restrição de executável somente se aprovada e refletida no modelo |
| Minecraft Java | `javaw.exe` somente com `.minecraft` na cmdline (seção 6) | Como representar a conjunção no JSON que hoje só exemplifica lista de strings `block_cmdline`; falso positivo fora do jogo (P05) | Regra conjunta de executável e padrão, sujeita à proteção de RF10 e à aprovação do formato |

**P05:** a lista inicial contém `...\Steam\steamapps\common` e `%LOCALAPPDATA%\Roblox\Versions` (seção 6). A primeira forma não é caminho resolvido; a segunda depende do usuário. Não inventar instalações. D06 confirmou edição dos apps de estudo; edição de padrões cmdline/safelist ainda pendente. D13 exige escolhas antes de ativar, sem horários iniciais ativos.

**T:** impedir configurações que bloqueiem genericamente `javaw.exe` e padrões vazios seria uma proteção contra falsos positivos. Como recusar, informar ou corrigir essas entradas permanece pendente; não aprovar sozinho essa validação.

**P12:** esperar até 2 s por alvo, sequencialmente, pode estender a varredura além de 5 s. A cadência de RF04/RF11 não determina se o intervalo é entre inícios ou após cada ciclo. Esperas coletivas, orçamento por ciclo e execução separada são alternativas técnicas, não decisões.

## 7. Invariantes e aplicação do `hosts`

### 7.1 Obrigações confirmadas

- **R:** ao entrar em janela, adicionar domínios apontando para `127.0.0.1` e `::1` (RF12).
- **R:** remover apenas as linhas do app, identificadas por `# FOCUS-BLOCKER-START` e `# FOCUS-BLOCKER-END`, ao sair (RF13).
- **R:** executar `ipconfig /flushdns` depois de cada mudança (RF14).
- **R:** fazer backup antes da primeira alteração (RF15).
- **R:** limpar bloco antigo ao iniciar, limpar no encerramento normal e na desinstalação (seções 8/10).
- **C:** Sair libera (D02); após crash, a limpeza é feita ao reabrir, com recuperação diferida aceita (D03).
- **R:** quando `hosts` estiver somente leitura ou o antivírus impedir a edição, registrar erro e mostrar alerta na bandeja (seção 8).

**D — Preservação:** limpeza normal não equivale a restaurar o arquivo inteiro do backup. RF13 exige remover somente linhas próprias; restaurar uma cópia antiga poderia desfazer alterações de terceiros. O backup não define sozinho um procedimento aprovado de restauração.

**D — Pré-condição:** editar sem ter feito o backup da primeira alteração contraria RF15. Se o backup falhar, não é possível declarar esse requisito atendido; reação da aplicação e forma de comunicar a falha permanecem em P08/P10.

**D — Sem mudança:** RF14 relaciona flush a mudança, não exige reescrever e executar flush a cada ciclo. A seção 7 manda “garantir” sites/limpeza; idempotência é uma **T** de implementação coerente com esse fluxo, não algoritmo já definido.

### 7.2 Limites e decisões de integridade

**P08:** não estão definidos caminho e política de backup, significado de “primeira alteração” após reinstalação, retenção, codificação/finais de linha do arquivo, procedimento de escrita, preservação de permissões, verificação pós-escrita ou concorrência com outras ferramentas. O lock da seção 4 protege estado entre threads do app; não coordena editores externos.

**P08:** marcadores ausentes, duplicados, sem par, aninhados ou arquivo truncado não possuem política de reparo. Sem delimitação confiável, não presumir que todo conteúdo restante pertence ao app. Excluir por domínio fora do bloco também poderia remover linha de terceiro, contrariando RF13.

**T:** comparar conteúdo desejado com o existente; preservar o conteúdo externo; serializar efeitos do app; validar o bloco; escrever de forma resistente a interrupção; verificar resultado; reportar separadamente edição e flush. Técnica de substituição, rollback, tratamento de edição externa e permissões precisa de validação no Windows e aprovação.

**P10:** uma escrita pode funcionar e o flush falhar, ou processos podem ser encerrados enquanto sites continuam liberados. O escopo não estabelece atomicidade entre esses efeitos, retentativas, rollback ou regra de estado visual. Não declarar “liberado” ou “bloqueado com sucesso” apenas pela intenção do agendador.

### 7.3 Limites do bloqueio de sites

**R:** `hosts` não aceita curinga; cada subdomínio precisa estar listado, e listas incompletas podem deixar carregamento parcial (seção 6; seção 13). A lista é ponto de partida a validar, não cobertura comprovada. `www.` e `m.` aparecem abreviados na seção 6; não são domínios completos prontos para gravação (P05).

**R:** desativar DNS seguro no Brave é passo de instalação; conexões já abertas podem continuar até recarregar. Flush e aviso opcional para fechar abas são as mitigações descritas (seções 8/9). Não há autorização para encerrar Brave: RF10 protege navegadores.

**D:** adicionar um domínio não impede todas as conexões já estabelecidas nem valida a cobertura de um site. A referência não promete bloqueio integral de streaming, todas as alternativas de resolução ou subdomínios desconhecidos.

**P05:** falta fechar regras de entrada de domínios (URL versus hostname, espaços, duplicatas, caixa e internacionalização) e efeitos de domínios compartilhados sobre ferramentas permitidas. A seção 5 exemplifica só YouTube/Netflix, enquanto as seções 1/6 abrangem nove serviços; não usar o exemplo JSON como lista completa definitiva.

## 8. Cleanup, falhas e lifecycle

### 8.1 Garantia possível com o desenho descrito

**R, com interpretação fechada por C:** a seção 3 originalmente exige que, se o app fechar ou travar, o `hosts` não fique bloqueado para sempre; a seção 8 prevê limpeza no próximo início e no encerramento normal. D03 aprova explicitamente a interpretação de recuperação ao reabrir: o `hosts` pode permanecer bloqueado até a próxima inicialização, sem garantia independente após crash. D02 confirma que Sair libera. A decisão atual mantém processo único (seção 4).

**Fato técnico externo:** `atexit` executa handlers no término normal do interpretador; não executa em erro interno fatal, `os._exit()` ou término por sinal não tratado. Python 3.12 também impede criar nova thread em handler de saída. Assim, não é uma garantia geral de recuperação após crash. [Python 3.12 — atexit](https://docs.python.org/3.12/library/atexit.html)

**D — Limite central, aceito em D03:** se o único processo morrer ou ficar travado sem executar cleanup, ele não pode executar sua própria limpeza naquele momento. Auto-start no logon não significa reinício imediato após falha. O estado residual pode persistir até reabrir; a referência não promete desbloqueio autônomo nem prazo independente de recuperação.

**P01 — Fechada por D03:** recuperação diferida é a escolha explícita. Watchdog, serviço ou tarefa extra de recuperação não são exigidos nem aprovados. Não reabrir essa decisão como pré-condição da implementação. Procedimentos operacionais para erro de limpeza, escrita interrompida e travamento ainda em execução permanecem em P08/P10/P11; D03 não especifica seus mecanismos.

### 8.2 Sequenciamento a decidir

**T — Inicialização sugerida:** resolver identidade/diretório e privilégios; adquirir mutex; preparar recuperação; limpar bloco antigo; carregar/validar configuração; iniciar partes e reavaliar imediatamente. A ordem entre carregamento e limpeza precisa ser definida para config inválida não impedir recuperação. P08/P10/P11 permanecem abertos. O resultado de limpeza ao reabrir é confirmado por D03, mas não esse sequenciamento.

**T — Exclusão mútua de efeitos:** uma segunda instância deveria ser impedida de limpar o bloco usado pela primeira. Adquirir exclusividade antes de editar `hosts` é uma solução sugerida, não ordem especificada pelo escopo. Nome/escopo do mutex e comunicação entre instâncias não estão definidos (P11).

**C — Sair libera:** D02 exige liberação dos bloqueios ao encerrar pelo menu, sem fricção adicional solicitada. Isso implica cessar encerramentos de processos; não exige reabrir apps já encerrados.

**T — Encerramento sugerido:** impedir novos pedidos e reaplicação de bloqueio; parar o ciclo; limpar bloco próprio e executar flush quando houver mudança; finalizar persistência/UI; liberar mutex. Cleanup repetível e uma tentativa explícita antes do `atexit` poderiam reduzir corridas. Prazos operacionais, cancelamento de operações, falha ao limpar e finalização de threads não foram aprovados (P10/P11).

**P11:** fechar a janela de configuração é o mesmo que Sair ou apenas ocultá-la? O escopo oferece menu Sair e janela sob demanda, mas não define esse gesto. Logoff/desligamento do Windows, desinstalação com app ativo e término de uma thread sem terminar o processo também carecem de política. Não presumir que falha só do núcleo aciona `atexit`.

### 8.3 Erros: obrigação e proposta de resposta

| Situação | Obrigação explícita | Resposta proposta, ainda não aprovada / decisão pendente |
| --- | --- | --- |
| `hosts` somente leitura/antivírus | Registrar erro e alertar na bandeja (seção 8) | Diferenciar etapa falha e efeito remanescente; periodicidade de alerta e retentativa: P10 |
| Backup, escrita, remoção ou flush falha | RF12–RF15 continuam sendo requisitos; resposta não definida | Expor resultado parcial, evitar declarar sucesso, definir recuperação: P08/P10 |
| Processo desaparece entre leitura e ação | Não definido | Tratar desaparecimento sem derrubar ciclo; decidir contagem: P09/P10 |
| Inspeção/encerramento com acesso negado | RF10 continua obrigatório; resposta não definida | Preservar proteção, registrar falha por alvo, continuar alvos seguros: P04/P10 |
| Config ausente, malformada ou inválida | Validação prevista na seção 4; resposta não definida | Não substituir silenciosamente por exemplos; definir defaults, conservação de dados e recuperação: P08 |
| SQLite indisponível/corrompido ou gravação falha | Dados locais e métricas de RF19–RF21; resposta não definida | Separar erro de estatísticas do efeito de bloqueio; definir retenção de eventos e perda tolerável: P09/P10 |
| Toast, bandeja ou janela falha | Interface e avisos previstos em RF05/RF18/RF22/RF23; resposta não definida | Decidir fallback e se o núcleo continua; não presumir outro canal: P03/P07/P10 |
| Núcleo trava ou thread termina | Seção 8; D03 confirma recuperação ao reabrir após falha | Tratamento de falha de thread com processo ainda vivo não está detalhado; monitoramento interno seria proposta: P10. Não exigir watchdog externo |
| Elevação/tarefa/mutex falha | Seções 3/10 exigem execução elevada e única | Definir mensagem, impedimento de execução parcial e recuperação: P11 |

**P10:** “registrar erro” não define arquivo, formato, retenção ou exposição de cmdline/caminhos. O destino dos logs não está especificado. Evitar inventar telemetria ou envio remoto, pois a seção 3 exige dados locais e ausência de internet/conta.

## 9. Relógios, suspensão e estatísticas

**R:** o núcleo lê relógio/config a cada ciclo; relógio alterado é aceito; acordar de suspensão/hibernação leva à reavaliação no próximo ciclo (seções 7/8). Espera de 60 s e pausa de 15 min são durações de RF16/RF17.

**P02:** não estão definidos fuso dos horários, mudança de fuso/horário de verão, relógio usado para durações, se suspensão consome espera/pausa, nem persistência dos prazos ao reiniciar. Aceitar mudança do relógio na agenda não responde como medir durações.

**Fato técnico externo:** `time.monotonic()` não retrocede e não é afetado por atualizações do relógio do sistema; só diferenças entre leituras têm significado. A documentação também alerta que `sleep()` pode durar mais que o pedido. Não usar número de ciclos como relógio exato. [Python 3.12 — time](https://docs.python.org/3.12/library/time.html#time.monotonic)

**Fato técnico externo:** o Windows documenta que `QueryPerformanceCounter` inclui tempo em suspensão/hibernação. Isso não autoriza decidir que a pausa do produto deva expirar durante suspensão, nem afirmar genericamente que todo relógio monotônico exclui suspensão. A implementação escolhida no runtime deve ser verificada. [Microsoft — contadores de tempo](https://learn.microsoft.com/en-us/windows/win32/sysinfo/acquiring-high-resolution-time-stamps#general-faq)

**T:** usar hora civil para janelas e relógio de duração separado para espera/pausa/cadência; comparar prazos em vez de subtrair 5 s por tick; reavaliar após retorno e descartar efeitos de avaliação antiga. Consumo ou preservação da pausa durante suspensão continua dependente de P02.

**R — Foco:** medir app de dev em primeiro plano e ausência de ociosidade; mais de 5 min sem input pausa a contagem (RF20). Seção 7 descreve amostra a cada 5 s, soma de 5 s ao dia e gravação em `focus_log`, `pauses`, `blocked_attempts`. RF19 manda registrar cada pausa e RF21 exige resumos diários, semanais, totais, pausas e tentativas.

**C — D05/D09/D12:** foco só nas janelas e fora da pausa de descanso; cancelamento não conta pausa; semana local segunda–domingo. **P09:** troca de app entre amostras, falhas de observação, meia-noite, retrocesso de data e recuperação após reinício ainda precisam de definição. Não atribuir longo intervalo suspenso a foco por extrapolação. Soma fixa de 5 s é o fluxo explícito; medição de duração real é proposta a conciliar.

**T:** amostrar sem recuperar “foco perdido” durante suspensão ou ciclos atrasados; identificar eventos de pausa concedida e tentativas com resultado. Precisão, deduplicação, persistência e esquema pertencem à decisão conjunta com o responsável pelos dados, sem definir colunas neste documento.

**C/P — D19:** foco no Brave depende dos domínios de estudo que o usuário adiciona; sites bloqueados também são personalizáveis. Medir só processo em primeiro plano não distingue páginas. Propor fonte do domínio da aba ativa e contrato com dados/UI, preservando dados mínimos/locais. Extensão, coleta de URLs, API local e alterações de arquitetura não foram escolhidas. Subdomínios, falha de identificação e conflito entre listas continuam pendentes.

## 10. Concorrência e threading da interface

**R:** núcleo em fundo, bandeja em thread própria, estado com lock e CustomTkinter sob demanda (seção 4). A seção não atribui explicitamente a janela à thread principal nem descreve entrega de comandos.

**Fato técnico externo:** Tkinter associa o interpretador Tcl à thread que criou `Tk`. Chamadas vindas de outra thread dependem da fila de eventos; sem loop processando eventos podem falhar, e algumas funções só operam na thread criadora. Handlers longos bloqueiam a UI. Um lock de aplicação não elimina essas restrições. [Python 3.12 — threading do Tkinter](https://docs.python.org/3.12/library/tkinter.html#threading-model)

**Fato técnico externo:** `pystray.Icon.run()` é bloqueante, mas a documentação permite executá-lo fora da thread principal quando o alvo é somente Windows. Isso é compatível com a decisão do escopo; não determina como a janela será criada. [pystray — criação do ícone](https://pystray.readthedocs.io/en/latest/usage.html#creating-a-system-tray-icon)

**T — Integração sugerida:** manter criação/manipulação de widgets e loop Tk na thread principal; núcleo e callbacks da bandeja enviam pedidos/dados, consumidos na thread da UI. Uma raiz oculta persistente com janela exibida sob demanda é alternativa a avaliar. Filas, uso de timers da UI, política de ocultar/destruir e cadência de contagem regressiva não estão aprovados (P03).

**T — Lock:** manter trechos curtos para publicar/copiar estado; fazer esperas de processo, arquivos, DNS, toasts e consultas fora do lock. Definir responsável por cada escrita e descarte de resultados obsoletos. O escopo não define essa granularidade nem permite concluir que compartilhar o estado autoriza modificar widgets de qualquer thread.

**Fato técnico externo:** `sqlite3.connect()` usa `check_same_thread=True` por padrão. Usar a conexão em outra thread gera erro; desativar a checagem pode exigir serialização de escritas. O lock do estado não decide a propriedade da conexão. [Python 3.12 — sqlite3.connect](https://docs.python.org/3.12/library/sqlite3.html#sqlite3.connect)

**P03/P09:** definir onde vivem conexão e consultas SQLite e como a janela obtém resumos sem bloquear Tk. Um responsável único pelas operações de dados ou conexões distintas são propostas possíveis, sujeitas ao contrato com o responsável pelos dados.

## 11. Avisos, dependências e implantação

### 11.1 Avisos confirmados e eventos pendentes

**C — D01:** avisos aos 5 e 1 minuto são a resposta explícita do usuário. RF05 prevalece sobre “2 a 5 min” da seção 1, conforme `DECISIONS.md`; seção 5, seção 7 e fase 4 também apresentam 5/1. A divergência está resolvida e não deve ser devolvida como pergunta aberta. **P07:** configurabilidade dos valores e demais políticas de eventos ainda não foram fechadas.

**R:** RF06 condiciona aviso à presença de jogo ou launcher, com opção de sempre avisar. RF18 exige aviso 1 min antes de retomada; iniciar PC no meio da janela dispensa aviso (seção 8).

**P07:** RF06 se aplica também à retomada? Como distinguir launcher/jogo de outros apps adicionados? O JSON não mostra a opção “sempre avisar”. Qual comportamento ao iniciar entre limiares, pular um limiar por atraso/suspensão, alterar janela, unir sobreposições, repetir hora ou expirar pausa fora de janela? RF18 e o texto “No fim: avisa 1 min antes e retoma” da seção 7 não detalham o gatilho operacional.

**T:** disparar por cruzamento de limiar com registro de ocorrência/aviso para evitar repetição a cada ciclo. Política de aviso atrasado e deduplicação após retrocesso do relógio dependem de P07; não são requisitos fechados.

### 11.2 Dependências explicitadas

| Dependência/facilidade | Uso previsto no escopo | Limite de decisão |
| --- | --- | --- |
| `psutil` | Inspeção e encerramento de processos | Versão, proteção, correspondências e exceções: P04/P05/P10 |
| `pystray` e `Pillow` | Bandeja; bibliotecas listadas na seção 4 | Versões e criação/atualização do ícone não detalhadas |
| `customtkinter` | Janela de configuração | Integração com threading: P03 |
| `pywin32` | Janela em primeiro plano e `GetLastInputInfo` | Erros, sessão do usuário e precisão das amostras: P09/P11 |
| `win11toast` | Toasts Windows | Versão e verificação Windows 10/11 ainda não dadas; P07/P12 |
| `sqlite3` da biblioteca padrão | Estatísticas locais | Schema, transações e propriedade das conexões: P09 |
| `hosts` e `ipconfig /flushdns` | Bloqueio por nomes e limpeza de cache; Sair libera e recuperação após crash ao reabrir (D02/D03) | Privilégios, integridade e efeito parcial: P08/P10/P11 |
| PyInstaller | `.exe` com `--noconsole --uac-admin` | Configuração de build e validação de distribuição não concluídas |
| Inno Setup e Agendador do Windows | Instalador; tarefa de logon com `/rl highest`; remoção e cleanup | Comando completo, conta, sessão e condições da tarefa: P11 |

**R:** bibliotecas da seção 4 e ferramentas da seção 10 constituem as escolhas nomeadas. Não há versões fixadas, instalação realizada ou dependência adicional aprovada neste documento.

**P11:** `%APPDATA%\FocusBlocker` é o local de dados definido na seção 10; `data/config.json` e `data/stats.db` aparecem na árvore da seção 4. Falta definir uso de `data/` no desenvolvimento/distribuição, usuário proprietário, identidade da tarefa elevada e resolução de `%LOCALAPPDATA%`. Não presumir que elevar sob outra conta mantenha os dados/pastas do usuário pretendido.

**P11:** a linha exemplificada de `schtasks` não fecha credenciais, execução interativa, condições, política de reinício ou tratamento de falha. Não documentar conta SYSTEM, recuperação automática após crash ou comportamento para todos os usuários como já decidido.

**C — D07/D11:** única conta Windows; desinstalação apaga histórico. A identidade correta da conta elevada, o escopo técnico do mutex e o destino da configuração/backups na desinstalação continuam pendentes; não ampliar para várias contas.

**R:** seção 13 aponta possível estranhamento do antivírus, assinatura ou exceção como possibilidades. Assinatura, fornecedor, certificados e exceções não estão aprovados nem asseguram ausência de bloqueio.

### 11.3 Validação futura, sem alegar execução

**R:** as fases da seção 11 pedem agenda testada (meia-noite/sobreposição), jogos fechando com IDEs intactas, Brave bloqueado/livre, avisos/pausa, edição pela UI, estatísticas e instalador que desinstala limpo.

**T:** transformar decisões pendentes em critérios verificáveis antes da implementação: proteção contra regra ampla e cmdline ausente; pasta vizinha e variável de usuário; preservação de linhas externas/marcador quebrado; erro de backup/flush; duas instâncias; crash sem reabrir; suspensão durante pausa; mudança de relógio; Tk aberto a partir da bandeja; núcleo atrasado por vários alvos. Esses cenários são sugestões de validação, não testes executados nem novos requisitos aceitos.

## 12. Decisões e perguntas para devolução ao Maestro

Estas perguntas são itens de coordenação para o Maestro, não solicitações enviadas ao usuário. O documento deve continuar com as lacunas explícitas até existir decisão autorizada.

| ID | Prioridade | Pergunta/decisão necessária | Sugestão não aprovada |
| --- | --- | --- | --- |
| P01 | Fechada por D03 | Recuperação após crash ao reabrir; bloco residual pode permanecer até esse momento | Não exigir watchdog nem prometer cleanup autônomo; mecanismos de erro permanecem em P08/P10/P11 |
| P04 | Crítica | Como garantir proteção de todas as categorias de RF10, inclusive com dados inacessíveis e listas editáveis? Como proteger o próprio app? | Proteção obrigatória e ausência de encerramento quando proteção não puder ser verificada |
| P05 | Alta | Qual semântica exata de nomes/pastas/cmdline? Como representar `javaw.exe` + `.minecraft`, resolver caminhos iniciais e domínios abreviados? Quais listas são editáveis? | Correspondência explícita, comparação de componentes de caminho e validações contra regras amplas, após aprovação |
| P02 | Alta | Qual relógio mede espera/pausa? Suspensão consome duração? Qual fuso/reação a mudança de hora? Prazos sobrevivem a reinício? | Separar hora civil de duração, sem escolher política de suspensão implicitamente |
| P06 | Alta; parcial D04/D08/D09 | Calendário, bordas e adjacência respondidos; pausa só em bloqueio, sem contagem cancelada ou retomada fora de janela. Restam espera com janela encerrada, pedidos repetidos e reinício/suspensão | Manter respostas; fechar somente as lacunas restantes |
| P07 | Alta; minutos fechados por D01 | Avisos confirmados em 5/1 min. São configuráveis? RF06 vale na retomada? Como tratar limiar perdido, deduplicação e identificação de jogo/launcher? | Fechar políticas de eventos mantendo D01; não perguntar novamente quais minutos prevalecem |
| P03 | Alta | Qual thread cria Tk, como bandeja solicita abertura, como UI obtém resultados, e quem escreve estado? | Tk na principal, pedidos/dados consumidos pela UI, sem efeitos demorados sob lock |
| P08 | Alta | Quais validações/defaults de config e quando edições entram em vigor? Como gravar/recuperar backup e `hosts` com marcador danificado/edição externa? | Operações idempotentes, preservação externa e protocolo de gravação a validar |
| P10 | Alta | Como representar efeito parcial e comunicar erro sem declarar sucesso indevido? Onde registrar erros, quando repetir e como lidar com falha de thread? | Separar intenção/resultado/erro; políticas locais por componente |
| P11 | Alta | Qual conta/sessão/tarefa elevada, alcance do mutex, ordem de startup/saída, gesto de fechar janela e desinstalação com app ativo? | Coordenar exclusividade antes de efeitos e fechar lifecycle com identidade explícita |
| P09 | Média; parcial D05/D09/D11/D12/D16 | Produtos de estudo editáveis, foco só no horário, semana local segunda–domingo, pausa efetivada e processo encerrado estão definidos; restam medição, deduplicação e contrato SQLite | Dados mínimos para totais; não inventar schema |
| P12 | Média | Como comprovar cadência de 5 s, “imediato” ao iniciar, recursos em repouso e compatibilidade de versões? | Critérios de medição e validação no Windows definidos antes de declarar conformidade |

**Estado desta referência:** arquitetura explícita e respostas do usuário consolidadas; contratos conceituais rastreados; mecanismos não definidos permanecem propostas. Antes de converter em contratos de código, fechar os detalhes da fase correspondente e consultar `DECISIONS.md`, sem reabrir decisões já respondidas.

Fontes externas consultadas em 2026-10-05 são documentação oficial de dependências/plataforma, usadas apenas para avaliar viabilidade e limites. Seus links acompanham as afirmações correspondentes; não substituem aprovação de requisitos.

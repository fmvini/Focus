# Modelo de dados do Focus Blocker

**Implementação atual:** configuração da agenda e quatro listas tipadas de processos em `core/config.py`/`core/models.py`. Ver [PHASE1_CONTRACT.md](PHASE1_CONTRACT.md) e [PHASE2_CONTRACT.md](PHASE2_CONTRACT.md), que prevalecem sobre propostas históricas abaixo. Tabelas SQLite continuam conceituais, sem banco/schema criado.

## Contrato efetivo da fase 2

`AppConfig` acrescenta `block_exes`, `block_folders`, `safelist_exes` e `block_cmdline`, mantendo `windows`/`extra`. Os quatro campos ausentes equivalem a listas vazias; gravação explícita emite as quatro listas. Nenhuma sugestão de bloqueio é ativada. Outros campos raiz continuam preservados e opacos. Colisões de `extra` com campos tipados são erro.

Nomes exigem `.exe` completo sem diretório/wildcard/espaços externos. Pastas são absolutas Windows após expansão de `%VAR%` conhecida, conservando a entrada original no JSON; parsing não verifica instalação. O adaptador precisa resolver destinos antes de efeitos. Cmdline agora exige objetos com exatamente `executable` e `contains`, trecho não vazio/sem controles, e aplica conjunção literal sem caixa dentro de cada argumento. Strings legadas geram erro explícito e arquivo intacto; não são migradas por inferência.

Eventos de encerramento confirmado ficam somente em memória, com identidade PID+create_time e instante observado de confirmação, deduplicados por execução. Não incluem cmdline completa e não constituem tabela SQLite ou histórico persistente. Confirmação pendente pode ser reconciliada depois sem novo encerramento; falhas, protegidos e desaparecimento anterior à solicitação não geram tentativa. Esquema/agregações continuam na fase 6.

## 1. Status e fonte de verdade

Este documento registra o que consta em `docs/Focus Blocker_ escopo do projeto.md` e identifica lacunas para revisão pelo Maestro. Não aprova schema, defaults adicionais, políticas de dados ou alterações de escopo. Não contém SQL nem implementação.

**Consolidação pelo Maestro, 2026-10-05:** respostas em [DECISIONS.md](DECISIONS.md) confirmam avisos 5/1 min, saída/recuperação, calendário, foco e configuração inicial. D14/D15 fecharam política de proteção e correspondência; nomes de campos/representação conjunta são escolhas técnicas em PHASE2_CONTRACT. Schema SQLite e mecanismo do domínio ativo (D19) continuam pendentes.

As classificações usadas são:

- **Requisito explícito:** decisão ou comportamento presente no escopo, com referência à seção ou RF.
- **Proposta técnica não aprovada:** alternativa para avaliação; não constitui contrato de implementação.
- **Decisão pendente:** definição ausente, ambígua ou conflitante no escopo; depende de esclarecimento.

Os exemplos JSON da seção 5 demonstram a representação prevista, mas não tornam todos os seus valores defaults definitivos. Os campos SQLite abaixo são exclusivamente conceituais.

## 2. Persistência e localização confirmadas

| Item | Requisito explícito | Referência |
| --- | --- | --- |
| Configuração | Janelas salvas em JSON; `core/config.py` carrega, salva e valida `config.json`. | Seções 1, 4 e 5 |
| Estatísticas | SQLite, com tabelas denominadas `focus_log`, `pauses` e `blocked_attempts`. | Seções 4 e 7, fluxo Estatísticas |
| Dados do usuário | Diretório `%APPDATA%\FocusBlocker`. | Seção 10, item 4 |
| Localidade dos dados | Todos os dados locais, sem internet nem conta. | Seção 3 |
| Instância e estado compartilhado | Uma única instância via mutex; um processo elevado com estado compartilhado protegido por lock. | Seções 3 e 4 |

**Decisão pendente:** a árvore da seção 4 ilustra `data/config.json` e `data/stats.db`; a seção 10 fixa o diretório dos dados do usuário. Não há definição expressa da resolução dos caminhos em desenvolvimento, do usuário cujo APPDATA é usado na execução elevada, nem de subdiretórios no local instalado. A localização APPDATA está confirmada; a resolução concreta desses arquivos ainda precisa ser alinhada.

## 3. Contrato JSON descrito no escopo

O contrato confirmado aqui é a estrutura apresentada na seção 5, vinculada aos comportamentos dos RF. O escopo não fornece um schema formal que determine obrigatoriedade de cada chave, rejeição de chaves desconhecidas, limites de tamanho, tratamento de tipos inválidos ou compatibilidade entre versões.

| Campo e representação na seção 5 | Significado confirmado e referência | Valores, defaults e lacunas |
| --- | --- | --- |
| `windows`: lista de objetos | Janelas editáveis; cruzamento de meia-noite; unir sobrepostas e adjacentes. RF01–RF03; D08. | D13: começar sem horários ativos e escolher antes de ativar. Exemplos 08:00–12:00/14:00–18:00 não são defaults. Quantidade máxima pendente. |
| `windows[].start`, `windows[].end`: textos como `08:00` | D08: início incluído/fim excluído; igualdade inválida. RF01 e seção 5. | Representação `HH:MM`; gramática completa/segundos ainda a formalizar. |
| `windows[].days`: lista de números como `[0,1,2,3,4,5,6]` | RF01: todos por padrão se ausentes; D04: dia inicial, segunda=0 até domingo=6. D20: lista vazia desativa. | Fase 1 exige inteiros únicos 0–6 (sem bool); ver PHASE1_CONTRACT. |
| `warn_minutes`: lista numérica `[5,1]` | Avisos 5 e 1 minuto antes. RF05, seção 5 e D01. | D01 confirmou esses tempos, superando “2 a 5 min” da seção 1. Ser editável ou fixo e aceitar outros valores: pendente. |
| `pause.wait_seconds`: número `60` | Espera cancelável de 60 segundos. RF16. | Comportamento explícito, não apenas exemplo. Possibilidade de alteração pela configuração: pendente. |
| `pause.duration_minutes`: número `15` | Liberação de sites e apps por 15 minutos. RF17. | Comportamento explícito, não apenas exemplo. Possibilidade de alteração pela configuração: pendente. |
| `sites`: objeto com nomes de sites associados a listas de textos | Domínios para bloquear no hosts; edição de domínios pela UI. RF12–RF14 e RF24. | YouTube e Netflix ilustram o JSON. A seção 1 inclui outros serviços; a seção 6 chama os domínios de ponto de partida a validar. Não é uma lista definitiva validada. |
| `block_exes`: lista de textos | Bloqueio por nome do executável. RF07. | Fase 2: nome completo `.exe` sem caixa; ausente/vazio não bloqueia. Usuário escolhe a lista. |
| `block_folders`: lista de textos | Bloqueio por caminho dentro das pastas. RF08. | D15: absoluta/subpastas/variáveis; destino incerto preservado. Caminhos de exemplo não são instalações assumidas. |
| `block_cmdline`: originalmente lista de textos | Bloqueio por padrão contido na linha de comando. RF09. | Fase 2 substitui por objetos executable+contains obrigatórios, literal sem caixa por argumento (D15). Forma antiga rejeitada, arquivo preservado. |
| `safelist_exes`: lista de textos | Proteção prioritária; RF10; seções 7 e 8. | D14: adicional editável complementa base obrigatória; lista vazia não remove proteção. Cobertura universal de catálogo não comprovada. |
| `dev_apps`: lista de textos | Apps elegíveis em primeiro plano com usuário ativo, nas janelas e fora da pausa (D05); lista editável (D06). | Brave, IDEs, Codex, Claude e ChatGPT; executáveis/uso via terminal pendentes. Brave exige domínio de estudo de D19; fonte/contrato ainda a definir. |

**Requisito explícito:** RF06 permite configurar o aviso para sempre aparecer, em vez de aparecer somente com jogo ou launcher aberto. **Decisão pendente:** a seção 5 não possui chave correspondente. Não foi inventado um nome para essa chave.

**Requisito explícito:** RF24 permite editar domínios, executáveis e pastas. **Decisão pendente:** a seção 11, fase 5, fala em “tudo editável”; o alcance da edição de pausa, avisos, safelist, padrões de linha de comando e apps de dev não está detalhado.

### Validação sugerida — proposta técnica não aprovada

- Validar estrutura, tipos, horários e referências antes de publicar. Fases 1/2 adotam erro interrompendo execução e arquivo intacto, sem usar snapshot anterior após recarga inválida (D17); a proposta histórica de manter última configuração não foi adotada.
- Definir normalização de nomes de executáveis, caminhos e domínios sem ampliar regras de bloqueio de forma implícita. Distinguir entrada original de valor normalizado se isso for necessário para a UI.
- Exigir domínios concretos no formato acordado: o escopo declara que hosts não aceita curingas (seção 6). Abreviações como `www.` nessa seção precisam de expansão confirmada, não de cópia literal ou interpretação silenciosa.
- Verificar a relação entre regras bloqueadas e safelist preservando sua prioridade explícita. O modo de informar conflitos permanece pendente.
- Não substituir valores ausentes por exemplos da seção 5. Política de defaults, recuperação de JSON inválido e formato versionado dependem de aprovação.

## 4. SQLite: tabelas conceituais, sem schema aprovado

**Requisito explícito:** os nomes das três tabelas constam na seção 7. Não há definição de colunas, tipos SQL, chaves, índices, granularidade dos registros, relações ou versão do schema.

**Proposta técnica não aprovada:** os campos candidatos abaixo servem para discutir rastreabilidade e contabilização. Não representam tabelas existentes nem um modelo autorizado. Nenhum campo ou índice desta seção está confirmado pelo escopo.

### `focus_log` — proposta de registros de intervalo

| Campo candidato — proposta | Finalidade e decisão ainda necessária |
| --- | --- |
| `id` | Identificador interno; formato e geração pendentes. |
| `started_at`, `ended_at` | Limites do intervalo observado; representação temporal, fuso e tratamento de intervalo aberto pendentes. |
| `credited_seconds` | Segundos de foco atribuídos; depende da política de amostragem, ociosidade e suspensão. |
| `app_name` | Nome do app elegível, se for necessário guardar esse detalhe. Necessidade e privacidade pendentes. |
| `close_reason` | Motivo conceitual de encerramento, como troca de app ou interrupção; enumeração e necessidade pendentes. |

**Proposta de índices não aprovada:** índice pelo início do intervalo para consultas por período; índice por app e período somente se houver consulta aprovada que o justifique. Chave interna e unicidade dependem da granularidade escolhida.

**Decisão pendente:** escolher entre amostras de 5 segundos, intervalos consolidados ou agregados diários. RF21 exige totais, mas não exige histórico por aplicativo. A proposta por intervalo não autoriza armazenar detalhes adicionais. Data de agregação e totais derivados só podem ser definidos após a política de calendário.

### `pauses` — proposta de histórico de ciclo de pausa

| Campo candidato — proposta | Finalidade e decisão ainda necessária |
| --- | --- |
| `id` | Identificador de uma solicitação/ciclo; significado exato pendente. |
| `requested_at` | Início da espera; persistir solicitações ainda não efetivadas é pendente. |
| `released_at`, `scheduled_end_at`, `finished_at` | Início efetivo da liberação, fim previsto e fim observado; tipos e semântica pendentes. |
| `status` | Diferenciar espera, cancelamento, liberação e conclusão/interrupção, se aprovado. Estados finais e contagem pendentes. |
| `finish_reason` | Possível distinção entre término normal, encerramento e recuperação; necessidade pendente. |

**Proposta de índices não aprovada:** início efetivo da liberação para relatórios; status apenas se necessário para recuperação. Relação com `focus_log` e limites de ciclos simultâneos não estão aprovados.

**Requisito e resposta D09:** registrar pausa efetivada; cancelamento da espera não conta. **Decisão pendente:** atribuição diária e tratamento de pausa interrompida por fechamento/suspensão. O histórico proposto não implica restaurar pausa após reinício.

### `blocked_attempts` — proposta de eventos de bloqueio

| Campo candidato — proposta | Finalidade e decisão ainda necessária |
| --- | --- |
| `id` | Identificador persistente do evento; unicidade pendente. |
| `occurred_at` | Momento de observação ou de encerramento; escolha pendente. |
| `process_name` | Nome do processo; necessidade de persistência e normalização pendentes. |
| `process_instance_key` | Identidade candidata para deduplicação; PID isolado não deve ser assumido como identidade definitiva. Composição e persistência pendentes. |
| `matched_rule_kind` | Possível categoria nome/pasta/linha de comando; não implica guardar o conteúdo da regra. Necessidade pendente. |
| `outcome` | Possível distinção entre encerramento e falha; quais resultados contam é pendente. |

**Proposta de índices não aprovada:** momento do evento para relatórios; eventual unicidade por instância e episódio somente após aprovar deduplicação. Não há índice, chave única ou período de deduplicação definido.

**Requisito e resposta D16:** uma tentativa corresponde a um processo efetivamente encerrado; falhas de encerramento e visitas a sites não contam. RF11 exige encerrar novamente se reabrir. **Decisão pendente:** identidade/deduplicação entre observações e regras múltiplas. D11 limita persistência aos dados necessários aos totais; não guardar linha de comando completa como detalhe adicional.

### Versão do schema — proposta técnica não aprovada

Propor um marcador persistido de versão para detectar compatibilidade antes de ler ou migrar o banco. Local do marcador, versão inicial, sequência de versões e relação com eventual versão do JSON são decisões pendentes. Não foi escolhido número de versão nem mecanismo de migração.

## 5. Contabilização e consistência

### Comportamentos explícitos

- Foco exige app de dev em primeiro plano e usuário não ocioso; mais de 5 minutos sem input pausa a contagem (RF20).
- O fluxo de estatísticas observa a cada 5 segundos e soma 5 segundos ao dia se as condições forem atendidas (seção 7).
- A tela apresenta horas por dia, semana e total, número de pausas e tentativas bloqueadas (RF21).
- Janelas que cruzam meia-noite são suportadas e sobreposições são unidas (RF02–RF03).
- Após suspensão/hibernação, o próximo ciclo reavalia; alterações do relógio são aceitas (seção 8). Isso não define como atribuir estatísticas nessas situações.

### Casos que exigem decisão

| Caso | Lacuna e impacto | Sugestão técnica não aprovada |
| --- | --- | --- |
| Janela `22:00–02:00` em dias selecionados | D04: dia de início, segunda=0 até domingo=6; segunda inclui terça até 02:00. | Expansão de intervalos é mecanismo proposto, preservando a regra aprovada. |
| Foco atravessando meia-noite | RF21 pede totais diários, sem definir fuso, limites ou atribuição de amostras que atravessam o dia. | Considerar divisão no limite do dia civil aprovado, sem duplicar segundos. |
| Semana | D12 confirmou segunda a domingo e calendário local do Windows; períodos parciais e mudanças de fuso ainda precisam de tratamento técnico. | Agregar créditos diários segundo a regra aprovada. |
| Suspensão, hibernação e ciclos atrasados | Somar o intervalo do relógio poderia creditar tempo não observado; somar 5 segundos ao acordar pode ter atribuição ambígua. | Considerar excluir lacunas não observadas e reiniciar a amostragem ao retomar; não escolher sozinho a regra do primeiro ciclo. |
| Ociosidade | Não está definido se os primeiros 5 minutos sem input contam, se haverá desconto retroativo, nem o instante preciso de corte entre ciclos. | Especificar limite e tratamento das amostras limítrofes antes de definir `credited_seconds`. |
| Foco fora da janela ou durante pausa | D05: só nas janelas e fora da pausa de descanso. | Aplicar as duas condições; não creditar descanso mesmo com app elegível aberto. |
| Horários iguais (`start == end`) | D08: inválidos. | Mensagem de validação ainda a detalhar, sem interpretar como 24 h. |
| Limites, sobreposição e janelas contíguas | D08: início incluído/fim excluído; unir sobrepostas e adjacentes. | Mecanismo de união a propor conforme contrato aprovado. |
| Relógio/fuso alterado | Aceitar alteração para bloqueio não resolve datas retroativas, duração negativa, repetição de períodos ou mudança de fuso no histórico. | Considerar instantes em UTC para referência e relógio monotônico para duração observada; política de dia local e fuso histórico pendente. |
| Repetição da tentativa bloqueada | D16 exige um processo efetivamente encerrado por tentativa; não duplicar por múltiplas regras/operações. Identidade técnica ainda pendente. | Identificação por instância/episódio como proposta; reabertura encerrada é novo evento. |
| Tentativas de sites | D16 exclui visitas a sites da contagem. | Não implementar histórico de navegação para essa métrica. |
| Pausa no fim de uma janela | D09 confirmou não retomar bloqueio fora da janela; fim durante espera continua pendente. | Registrar fim da pausa separado da avaliação de janela é mecanismo proposto. |
| Reinício, falha ou edição de config | Não há política de recuperação de intervalo aberto, pausa ativa, créditos ainda não gravados ou troca de `dev_apps` no meio de amostra. | Considerar registrar transições e interromper intervalos incertos, sem creditar automaticamente tempo de ausência. |

### Invariantes sugeridos — todos propostas não aprovadas

- Créditos não negativos e sem contagem dupla de intervalos; D05 exclui foco durante pausa, independentemente do app aberto.
- Totais diários, semanais e gerais calculados a partir da mesma fonte de créditos e da mesma política temporal. Retenção pode mudar o significado de “total”; isso precisa ser definido.
- Contagens de pausas e tentativas baseadas em eventos elegíveis definidos, sem multiplicar registros por operações internas ou leituras repetidas.
- Identificadores estáveis para repetir uma gravação sem duplicar créditos/eventos, se houver recuperação ou tentativas de escrita.
- Alterações relacionadas gravadas de forma transacional; ordem de persistência e atualização do estado compartilhado ainda precisa ser definida. Não há garantia aprovada de atomicidade entre JSON, SQLite e hosts.

## 6. Gravação segura e concorrência

**Requisitos explícitos:** mutex de instância única (seção 3), lock no estado compartilhado entre partes do processo (seção 4) e validação em `core/config.py` (seção 4). Esses requisitos não especificam o protocolo de gravação em disco.

**Propostas técnicas não aprovadas:**

- Salvar JSON em arquivo temporário no mesmo diretório, validar e substituir o arquivo de destino de forma atômica; avaliar durabilidade e recuperação de temporário após falha. Não assumir que lock em memória protege o arquivo de edições externas.
- Serializar gravações SQLite por um responsável definido, ou por conexões e transações coordenadas. Dono das conexões, estratégia entre threads, filas, limites de espera e repetição após conflito permanecem pendentes.
- Avaliar modo de journal e configurações de durabilidade; não assumir WAL como decidido. A escolha precisa considerar backup, arquivos auxiliares e comportamento em falha.
- Publicar para o núcleo uma configuração validada com revisão identificável, evitando mistura de valores de revisões diferentes durante um ciclo. Formato da revisão e precedência entre UI e edição externa são pendentes.
- Em erro de gravação, preservar dados anteriores e sinalizar falha; política de retry, perda máxima aceitável e limites de fila precisam de decisão. O alerta explícito da seção 8 trata falhas no hosts, não define tratamento de falhas de JSON/SQLite.

## 7. Migrações, backup e retenção: decisões pendentes

| Tema | Confirmado | Pendente / proposta para avaliação |
| --- | --- | --- |
| Migração do banco | SQLite previsto; sem política de migrações. | Versão, ordem, transações, recuperação após falha e compatibilidade com versões anteriores. Proposta: recusar escrita em schema incompatível e migrar somente com estratégia validada. |
| Evolução do JSON | Modelo da seção 5. | Versionamento, campos novos/ausentes, chaves desconhecidas e preservação de configurações antigas. |
| Backup do hosts | Antes da primeira alteração, RF15. | Local, retenção e restauração desse backup não detalhados. Essa exigência não equivale a backup de config ou estatísticas. |
| Backup de config/banco | Não especificado. | Necessidade, frequência, destino local, cópia consistente com banco ativo, rotação e restauração. Proposta: avaliar cópia consistente e validação de restauração, se backup for aprovado. |
| Retenção de estatísticas | D11: só dados necessários aos totais; histórico sem expiração até desinstalar. | Granularidade e crescimento; exclusão manual/exportação não aprovadas. |
| Desinstalação | Remover tarefa e limpar hosts, seção 10; D11: apagar histórico. | Configuração e backups não receberam política explícita de exclusão/preservação. |

## 8. Privacidade e multiusuário

**Requisito explícito:** dados locais, sem internet nem conta (seção 3); armazenamento no APPDATA (seção 10). Isso não define criptografia, permissões de acesso, dados sensíveis armazenáveis nem isolamento entre usuários Windows.

**Proposta técnica não aprovada:** coletar apenas o necessário aos totais aprovados. Evitar persistir títulos de janela, URLs visitadas, linha de comando completa e caminhos pessoais se não forem necessários. Nomes de apps também podem revelar hábitos; aprovação de detalhe por aplicativo e retenção é pendente. Nenhum desses conteúdos adicionais tem persistência exigida pelo escopo, e não há schema aprovado que a defina.

**Decisão respondida D07:** uso por uma única conta Windows. Suporte a várias contas não é requisito. Os riscos abaixo permanecem relevantes para identificar corretamente a conta elevada e evitar conflito com instâncias externas.

**Decisões pendentes:**

- Qual usuário Windows possui os arquivos ao iniciar elevado, especialmente quando a elevação envolve outro usuário? Como resolver APPDATA e permissões sem misturar históricos?
- O mutex é por usuário, por sessão ou por máquina? “Uma única instância” não estabelece esse alcance.
- Como coordenar sessões simultâneas, auto-start e regras de usuários diferentes ao editar o mesmo hosts? O escopo não define precedência nem suporte a esse cenário. Isso é um risco de isolamento a avaliar, não uma funcionalidade aprovada.
- Quais sessões/processos entram nas estatísticas e no bloqueio? A varredura descrita não especifica filtro de usuário ou sessão.
- Config, banco e backups precisam de proteção contra leitura por outros usuários? Criptografia, permissões, exportação e exclusão não estão definidos; não há proposta de sincronização ou conta.

## 9. Perguntas prioritárias para o Maestro

1. **Calendário e janelas, respondido:** D04/D08 fixaram dia de início, segunda=0 até domingo=6, início incluído/fim excluído, igualdade inválida e união de adjacentes. Restam validações formais e aplicação de edição.
2. **Crédito de foco, parcial:** D05 exclui fora da janela e pausa; D12 fixa semana local segunda–domingo. Restam amostras limítrofes de ociosidade, meia-noite, atrasos, suspensão e relógio/fuso.
3. **Tentativas bloqueadas:** D16 definiu um processo efetivamente encerrado por tentativa, sem visitas web ou falhas. Como implementar identidade/deduplicação apesar de múltiplas regras/varreduras?
4. **Pausas:** D09 exclui cancelamento e conta pausa efetivada. Como atribuir dia, tratar interrupções e decidir persistência/restauração após reinício ou suspensão?
5. **Defaults e JSON:** quais listas/janelas iniciais são definitivas? Pausa e avisos são fixos ou editáveis? D01 já confirmou avisos aos 5/1 min; como representar a opção de RF06? Quais regras de validação e comportamento de campos ausentes/inválidos são aprovados?
6. **Granularidade e privacidade:** D11 aprovou só dados necessários aos totais e histórico sem expiração; escolher proposta de granularidade mínima sem detalhes pessoais desnecessários.
7. **Localização e identidade:** D07 confirmou única conta. De qual usuário é APPDATA na execução elevada? Qual o alcance do mutex e como impedir conflito no hosts?
8. **Schema e consistência:** quais campos/índices conceituais serão aprovados, onde registrar versão e como garantir transações, recuperação e compatibilidade? Qual perda de dados em falha é aceitável?
9. **Backup e ciclo de vida:** haverá backup de JSON/SQLite? D11 mandou apagar histórico na desinstalação; como tratar configuração e backups?

As respostas registradas em `DECISIONS.md` prevalecem sobre perguntas já respondidas. Nenhuma lacuna remanescente foi fechada unilateralmente.

## 10. Uso qualificado do Brave: pendência de contrato

D19 confirmou regra por sites: usuário adiciona domínios considerados estudo e personaliza quais bloquear. O processo em primeiro plano não distingue páginas sozinho. A lista de domínios de estudo precisa de representação própria, diferente de `sites` de bloqueio; nome da chave, formato, subdomínios e conflitos ainda a definir. Não há domínios iniciais obrigatórios aprovados. Guardar navegação completa não foi autorizado; manter dados mínimos de D11.

Proposta técnica não aprovada: obter apenas o domínio elegível da aba ativa para decidir crédito, sem persistir URL completa ou histórico. Fonte desse domínio, validade temporal, falha de leitura e formato de mensagens/JSON ainda precisam de desenho e revisão; nenhuma integração foi escolhida.

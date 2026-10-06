# Focus Blocker — Fluxos de interface

**Implementação atual:** CLI em `main.py`, diagnóstico por padrão e aplicação explícita de processos via `--watch --apply-processes`, com recarga/erros/Ctrl+C e resultados confirmados/pendentes separados. Nenhuma bandeja ou janela gráfica implementada; edição ainda via JSON. Fluxos abaixo continuam referência para a fase 5. Ver [execução](../README.md) e [contrato da fase 2](PHASE2_CONTRACT.md). D14/D15 foram respondidos; propostas históricas de proteção/correspondência abaixo devem ser lidas à luz desse contrato.

## 1. Finalidade, fonte e classificação

Documento de referência para a interface, sem implementação. Fonte dos requisitos: [Focus Blocker: escopo do projeto](Focus%20Blocker_%20escopo%20do%20projeto.md), especialmente seções 1–11. A documentação não comprova que as funcionalidades já estejam implementadas.

**Consolidação pelo Maestro, 2026-10-05:** respostas explícitas em [DECISIONS.md](DECISIONS.md) confirmam avisos 5/1 min, Sair com liberação, recuperação ao reabrir, dia inicial da janela noturna, foco só nos horários de bloqueio, uma conta Windows e configuração inicial escolhida pelo usuário. D06 exige edição dos apps de estudo na aplicação: Brave, IDEs, Codex, Claude e ChatGPT. As demais propostas e pendências abaixo continuam abertas.

As descrições usam três classificações:

- **Requisito explícito:** conteúdo definido no escopo, acompanhado de seção e/ou RF.
- **Proposta técnica não aprovada:** sugestão para avaliação pelo Maestro; não constitui comportamento obrigatório ou decisão de produto.
- **Decisão pendente:** lacuna ou divergência que exige definição; este documento não a resolve.

Não estão definidos aqui visual, cores, desenho de ícones, disposição de controles, textos de mensagens ou novas telas. Os nomes do menu e das abas reproduzem RF22 e RF23. As tabelas de estados são organização documental dos fluxos, não uma nova arquitetura aprovada.

## 2. Bandeja e abas confirmadas

| Elemento | Requisito explícito | Referência | Decisão pendente |
| --- | --- | --- | --- |
| Bandeja | Ícone com estados bloqueando, livre e pausado; menu Abrir, Pausar e Sair. | RF22; seção 1 | Aparência dos estados, gesto de abertura e habilitação das ações em cada estado. |
| Abrir | Há janela de configuração aberta sob demanda. | RF22; seção 4 | Foco de janela já aberta, comportamento ao fechar a janela e aba inicial. |
| Horários | Cadastrar, editar e remover janelas com início, fim e dias; padrão de dias: todos. | RF01; RF23 | Formato de entrada, controles, confirmação de remoção e salvamento. |
| Sites | Adicionar/remover domínios pela interface. | RF23–RF24 | Edição dos agrupamentos por serviço e apresentação das listas iniciais. |
| Jogos/Apps | Adicionar/remover executáveis e pastas pela interface. | RF23–RF24 | Edição de padrões de linha de comando e safelist; regras para nomes e caminhos. |
| Estatísticas | Horas por dia, semana local segunda–domingo e total; pausas e processos efetivamente encerrados. | RF21; RF23; D12/D16 | Seleção de períodos, atualização e apresentação. |
| Configurações | Aba com esse nome. | RF23 | Campos e opções nela disponíveis; RF23 não os enumera. |

**Requisito explícito:** a fase 5 tem como critério “Tudo editável sem tocar no JSON” (seção 11). RF24 enumera domínios, executáveis e pastas, enquanto a seção 5 também contém `dev_apps`, `safelist_exes`, `block_cmdline`, avisos e parâmetros de pausa. **Decisão pendente:** delimitar o significado de “Tudo” e a localização de cada edição. A frase não define sozinha controles, validações ou quais parâmetros devem ser ajustáveis.

## 3. Estados e transições

### 3.1 Estados descritos pelo escopo

| Situação | Requisito explícito | Referência | Limites da definição |
| --- | --- | --- | --- |
| Bloqueando | Durante janela de bloqueio, garantir os domínios no `hosts` e varrer processos; reencerrar processos que reabram a cada 5s. | RF04; RF07–RF12; seção 7 | Tratamento visual de falha parcial não definido. |
| Livre | Fora das janelas, garantir `hosts` limpo das linhas do app; ícone indica livre. | RF13; RF22; seção 7 | Disponibilidade de Pausar fora de bloqueio não definida. |
| Espera de pausa | Pausar inicia contagem de 60s, cancelável; remoção do bloqueio ocorre aos 60s. | RF16–RF17; seção 7, Pausa | RF22 não lista espera como quarto estado do ícone; local da contagem e do cancelamento não definido. |
| Pausado | Após a espera, liberar sites e apps por 15 min e apresentar contagem regressiva no ícone. | RF17; RF22 | Formato, precisão e frequência de atualização do indicador não definidos. |

**Requisito explícito:** o fluxo retira o bloqueio aos 60s, não ao clique em Pausar (seção 7, Pausa). **Decisão pendente:** se a janela termina durante a espera, o tratamento da solicitação de pausa e o estado apresentado não são definidos. Espera é uma etapa confirmada do fluxo; sua representação como estado separado do núcleo não está estabelecida.

### 3.2 Transições confirmadas e fronteiras pendentes

| Origem/evento | Resultado explícito | Referência | Decisão pendente |
| --- | --- | --- | --- |
| Entrada em janela | Aplicar bloqueio de sites e processos e atualizar ícone/estatísticas no ciclo do núcleo. | RF04; RF07–RF14; RF22; seção 7 | Relação visual entre início da aplicação e confirmação de sucesso. |
| Saída de janela | Remover apenas as linhas do app do `hosts` e limpar cache de DNS após a mudança. | RF13–RF14; seção 7 | Apresentação se a remoção ou limpeza de DNS falhar. |
| Clique em Pausar | Iniciar espera cancelável de 60s. | RF16 | Solicitações repetidas e estados em que o comando está disponível. |
| Cancelamento da espera | A espera pode ser cancelada. | RF16 | Retorno visual e eventual registro de cancelamento nas estatísticas. |
| Espera completa | Liberar sites e apps por 15 min; apresentar contagem regressiva no ícone. | RF17; seção 7 | Tratamento se não houver mais janela ativa. |
| Um minuto antes do fim da pausa | Avisar antes da retomada. | RF18 | Condição de jogo/launcher aberto, meio do aviso e caso sem janela ativa. |
| Fim da pausa | Retomar se houver janela ativa; fora dela manter livre. | RF18; D09 | Aviso quando não haverá retorno e interrupções ainda pendentes. |

**Decisão respondida D09:** Pausar só pode ser pedido durante bloqueio; a espera mantém bloqueio; cancelamento não conta pausa. Ao vencer a pausa, só retomar se houver janela ativa; fora dela manter livre. Pedidos repetidos, janela terminar durante espera, reinício e suspensão ainda precisam de detalhamento.

## 4. Fluxos de operação

### 4.1 Inicialização, abertura e retomada do computador

**Requisitos explícitos:**

1. A inicialização limpa qualquer bloco antigo no `hosts` e reavalia o horário (seção 8).
2. Se o PC for ligado no meio de uma janela, o bloqueio vale imediatamente, sem aviso prévio (seção 8).
3. O núcleo consulta relógio e configuração a cada 5s, aplica o estado e atualiza ícone e estatísticas (RF04; seção 7).
4. A janela de configuração é aberta sob demanda; a bandeja oferece Abrir (RF22; seção 4).
5. Ao acordar de suspensão/hibernação, o próximo ciclo reavalia (seção 8).

**Decisões pendentes:** apresentação durante inicialização/limpeza, recuperação de erro, restauração de pausa após reinício e tratamento de abertura repetida. O escopo não exige mostrar automaticamente uma janela de boas-vindas.

### 4.2 Avisos antes do bloqueio

**Requisitos explícitos:** RF05 exige notificação do Windows 5 min e 1 min antes do início da janela. RF06 condiciona o aviso à existência de jogo ou launcher aberto e permite configurar para sempre avisar. A seção 5 exemplifica `warn_minutes: [5, 1]`.

**Decisões pendentes:**

- **Resolvido pelo usuário em D01:** prevalecem avisos aos 5 e 1 minuto. A expressão “2 a 5 min” da seção 1 fica superada por essa resposta.
- RF06 não define como reconhecer jogo/launcher aberto diante de regras de pasta, linha de comando e safelist.
- Não há definição de reaviso, deduplicação, passagem sobre o instante do aviso entre ciclos, sobreposição de janelas ou alteração do relógio/configuração.
- RF05 especifica notificação do Windows para início de janela; RF18 não especifica o meio do aviso de retomada nem se RF06 o condiciona.
- Textos, ações da notificação e edição dos tempos de aviso não estão definidos.

**Proposta técnica não aprovada:** usar o início da janela efetiva após união de sobreposições para avaliar avisos e evitar avisos duplicados do mesmo início. Depende da definição das regras acima.

### 4.3 Pausa com fricção

**Requisitos explícitos:**

1. A pessoa aciona Pausar na bandeja (RF16; RF22).
2. Começa uma contagem de 60s, cancelável (RF16).
3. Aos 60s, o fluxo remove o bloqueio e libera sites e apps por 15 min (RF17; seção 7).
4. O ícone apresenta contagem regressiva durante a pausa (RF17).
5. Há aviso 1 min antes da retomada e retomada ao fim (RF18).
6. Cada pausa é registrada nas estatísticas (RF19).

**D09 confirmado:** pedido só durante bloqueio; espera mantém bloqueio; cancelamento não conta; 15 min após espera; não retomar fora da janela. **Decisões pendentes:** onde exibir/cancelar a espera; se fechar a janela cancela; solicitações repetidas; fim da janela durante espera; encerramento/reinício/suspensão; atribuição diária de pausa.

**Proposta técnica não aprovada:** manter a indicação do estado efetivo de bloqueio durante a espera e acrescentar informação de espera cancelável. Não implica cor, novo ícone, texto, tela ou controle aprovado.

### 4.4 Sair e fechamento da janela

**Requisitos explícitos e decisões respondidas:** há ação Sair no menu (RF22); o encerramento normal limpa o `hosts`, e a inicialização limpa bloco antigo (seção 8). Em D02, o usuário confirmou que Sair libera os bloqueios. Em D03, escolheu recuperação após falha somente ao reabrir; o hosts pode permanecer bloqueado até isso acontecer. Essa decisão ajusta a garantia mais ampla da seção 3.

**Decisões pendentes:**

- D02 já definiu que Sair libera; detalhes de feedback e falha de limpeza continuam pendentes. Nenhuma fricção adicional foi solicitada.
- O que acontece se a limpeza do `hosts` falhar durante a saída?
- Como fechar a janela de configuração se relaciona com Sair e permanência na bandeja?
- Como tratar edição não salva, espera e pausa em andamento no encerramento?

Sair com liberação e recuperação ao reabrir estão definidos em D02–D03. Não há recuperação automática independente exigida; não informar que o hosts será liberado imediatamente após crash.

**Proposta técnica não aprovada:** distinguir fechamento da janela e encerramento do processo. A política de Sair com liberação foi aprovada; textos, feedback e política de fechar apenas a janela ainda não foram definidos.

## 5. Edição e validação de configurações

### 5.1 Horários

**Requisitos explícitos:** criar, editar e remover janelas com início, fim e dias da semana; todos os dias são o padrão (RF01). Janelas podem cruzar meia-noite (RF02), e sobreposições são unidas (RF03). Os horários são salvos em JSON (seção 1); a seção 5 usa `windows`, `start`, `end` e `days`. A arquitetura atribui carga, gravação e validação a `core/config.py` (seção 4).

**Decisões respondidas D04/D08:** dia selecionado é o de início; segunda=0 até domingo=6; segunda 22:00–02:00 inclui terça até 02:00; início incluído/fim excluído; igualdade inválida; unir adjacentes. **Pendentes:** seleção vazia de dias, formato de entrada, união apenas no cálculo ou também na lista editável e momento de aplicar edição durante bloqueio.

**Proposta técnica não aprovada:** validar a entrada antes de gravar e indicar os campos inválidos, preservando a edição para correção. A definição das regras de validade precede a especificação desse retorno. Um horário final anterior ao inicial não pode ser rejeitado apenas por essa relação, pois RF02 permite cruzar meia-noite.

### 5.2 Sites, executáveis e pastas

**Requisitos explícitos:** adicionar/remover domínios, `.exe` e pastas pela interface (RF24); bloqueio por nome, caminho dentro de pasta e padrão em linha de comando (RF07–RF09). O `hosts` não aceita curinga; subdomínios precisam de entradas individuais (seção 6). As listas de domínios da seção 6 são ponto de partida a validar na prática, não garantia de cobertura completa.

**Decisões pendentes:**

- Domínio com protocolo, caminho, porta, curinga, caixa diferente ou duplicação: rejeitar, normalizar ou pedir correção?
- Entradas abreviadas como `www.` na seção 6: quais nomes completos entram na configuração inicial?
- Executável: aceitar apenas nome ou também caminho? Como tratar duplicações e diferenças de caixa?
- Pasta inexistente, caminho relativo, variável como `%LOCALAPPDATA%` ou trecho ilustrativo como `...`: quais formatos serão aceitos e como serão resolvidos?
- Remoção, cancelamento, salvamento, feedback de erro e aplicação durante bloqueio: qual o contrato?

**Proposta técnica não aprovada:** distinguir domínios de URLs na validação, explicitar a limitação de curinga e evitar gravar entradas inválidas segundo regras aprovadas. Seletores de arquivos/pastas e confirmação de remoção são possibilidades não aprovadas.

### 5.3 `dev_apps`, safelist e linha de comando

| Configuração | Requisito explícito | Lacuna de interface | Proposta técnica não aprovada |
| --- | --- | --- | --- |
| `dev_apps` | RF20 e D06: lista de estudo editável, incluindo Brave, IDEs, Codex, Claude e ChatGPT. D05 limita foco às janelas e exclui pausa. | Controles/identificação real pendentes; Brave exige domínios de estudo editáveis (D19), com mecanismo ainda a definir. | Escolha e validação dos executáveis sem inferir nomes a partir da marca. |
| `safelist_exes` | RF10 protege IDEs, terminais, navegadores e processos do sistema; seção 7 ignora safelist antes de verificar bloqueio; seção 8 confirma prioridade. | Não está definido se a proteção é totalmente editável, se há entradas obrigatórias ou como lidar com conflitos apresentados na UI. | Apresentar a prioridade da proteção quando uma regra de bloqueio coincidir; preservar proteções obrigatórias conforme definição futura. |
| `block_cmdline` | RF09 exige padrão na linha de comando; seção 6 restringe `javaw.exe` do Minecraft a linha contendo `.minecraft` e alerta que bloquear por nome derrubaria IDEs Java. | RF24 não enumera sua edição; não define sintaxe, comparação, associação entre nome e padrão ou tratamento de padrão vazio. | Oferecer edição somente após definir o modelo de regra e sua validação; explicar impacto da correspondência. |

**Decisão pendente:** a seção 5 exemplifica lista de strings `block_cmdline`, enquanto a seção 6 descreve condição envolvendo `javaw.exe` e `.minecraft`. Não está definido como representar essa associação. A UI não deve assumir regex, curinga ou operadores inexistentes no escopo.

**Decisão pendente:** estar em `dev_apps` não é descrito como inclusão automática na safelist. Não equiparar as listas sem aprovação.

### 5.4 Salvamento, parâmetros e erros de configuração

**Requisito explícito:** há carga/gravação/validação de JSON em `core/config.py` (seções 4–5), configuração para sempre avisar (RF06) e parâmetro de espera de 60s/duração de 15 min no modelo (seção 5).

**Decisões pendentes:** salvamento automático ou explícito; aplicação imediata ou diferida; descarte de edição; falha de gravação; configuração inválida na inicialização; limites dos campos. A presença de `warn_minutes` e `pause` no JSON não aprova sua edição livre na UI nem substitui os valores exigidos por RF05/RF16/RF17.

**Proposta técnica não aprovada:** validar no componente de configuração, mostrar retorno específico à edição e considerar gravação concluída somente após confirmação. Preservar a configuração anterior em caso de falha é sugestão a avaliar, não política aprovada pelo escopo.

## 6. Alertas de erros e limitações

| Ocorrência | Requisito explícito | Decisão pendente / proposta |
| --- | --- | --- |
| `hosts` somente leitura ou bloqueado por antivírus | Registrar erro e mostrar alerta na bandeja. | Seção 8. **Decisão pendente:** canal exato do alerta, duração, repetição, ações e indicação do estado efetivo quando só parte do bloqueio funcionar. |
| Conexões já abertas no Brave | Podem continuar até recarregar; mitigação indicada: limpar DNS e, opcionalmente, avisar para fechar abas. | Seção 8; RF14. Avisar para fechar abas é opcional no escopo; momento, canal e texto não definidos. |
| Domínios incompletos | Site pode carregar parcialmente; listas exigem validação prática. | Seções 6 e 13. **Proposta técnica não aprovada:** disponibilizar orientação para ajuste da lista, sem prometer cobertura completa. |
| Falha ao salvar, carregar config, limpar DNS, encerrar processo ou acessar estatísticas | Não há fluxo de alerta de interface especificado para essas falhas. | **Decisão pendente:** severidade, registro, recuperação, tentativas e apresentação. **Proposta técnica não aprovada:** diferenciar erro de entrada de falha operacional com retorno acionável. |

RF22 define estados do ícone, mas não define um estado de erro. Não presumir cor, ícone adicional, diálogo, toast ou tratamento automático. Em particular, o alerta de bandeja da seção 8 não aprova por si só uma notificação do Windows para toda falha.

## 7. Onboarding do Brave

**Requisitos explícitos — passo de instalação, seção 9:**

1. Acessar `brave://settings/security` e desativar **Usar DNS seguro**.
2. Opcionalmente, desativar Brave News e conteúdo da página de nova guia.
3. Abrir `youtube.com` durante uma janela e confirmar o bloqueio.

**Requisito explícito:** conexões já existentes podem continuar até recarregar (seção 8), e todas as mudanças no `hosts` exigem limpeza de cache de DNS (RF14).

**Decisões pendentes:** onde apresentar as instruções (instalador, janela ou outro local), se haverá reapresentação, como a pessoa informa o resultado do teste e o que fazer se ele falhar. O escopo não exige assistente, nova aba, tela de onboarding, detecção automática de DNS seguro ou alteração automática do Brave.

**Proposta técnica não aprovada:** oferecer instruções locais acessíveis novamente e orientar o teste considerando conexões abertas. Trata-se de orientação de produto a aprovar; não exige introduzir nova tela. As instruções acima reproduzem o escopo, sem verificação externa da versão atual do navegador.

## 8. Interação entre interface e núcleo

**Arquitetura explícita — seção 4:** processo único elevado; núcleo em thread de fundo com loop de 5s; `pystray` em thread própria; janela CustomTkinter sob demanda; estado compartilhado protegido por lock. A separação em serviço + UI é possibilidade futura, não arquitetura atual.

**Fluxo explícito — seção 7:** núcleo lê relógio/configuração, verifica vencimento da pausa, calcula janela, dispara avisos, garante `hosts`/varre processos conforme estado, atualiza ícone e estatísticas. A safelist precede correspondências de bloqueio. Estatísticas somam 5s quando app de desenvolvimento está em primeiro plano e usuário não está ocioso; RF20 define ociosidade acima de 5 min sem input.

**Decisões pendentes:**

- Contrato para pedidos da UI (salvar, pausar, cancelar e sair), confirmação, erros e latência de aplicação.
- Quais dados compartilhados representam tempo restante, espera, falhas e configuração efetiva.
- Como atualizar bandeja/janela com segurança entre threads e como manter consistência durante edição.
- Persistência da espera/pausa e tratamento de alterações de configuração durante bloqueio.

**Propostas técnicas não aprovadas:** refletir na interface o estado confirmado pelo núcleo; devolver resultado de comandos e gravações; encaminhar atualizações ao contexto de execução apropriado da UI. Não ficam aprovados fila, eventos, polling adicional, APIs, campos de estado ou novos módulos. O loop de 5s não define a frequência de atualização da contagem no ícone.

## 9. Critérios de aceite UX rastreáveis

Os critérios abaixo traduzem somente requisitos explícitos em verificações futuras. Não registram testes executados. Onde houver divergência ou regra ausente, o resultado depende da decisão indicada; propostas não integram os critérios obrigatórios.

| ID | Verificação | Referência | Dependência/limite |
| --- | --- | --- | --- |
| UX01 | Bandeja apresenta estados bloqueando, livre e pausado e menu Abrir, Pausar, Sair. | RF22 | Visual e política de habilitação pendentes. |
| UX02 | Janela oferece Horários, Sites, Jogos/Apps, Estatísticas e Configurações. | RF23 | Não exige layout ou campos adicionais. |
| UX03 | É possível cadastrar, editar e remover início, fim e dias; o padrão é todos os dias. | RF01 | Regras de entrada e salvamento pendentes. |
| UX04 | Dia de início na janela noturna, segunda=0; unir sobrepostas/adjacentes; início incluído/fim excluído; igualdade inválida. | RF01–RF03; D04/D08 | Apresentação da união pendente. |
| UX05 | Domínios, executáveis e pastas podem ser adicionados/removidos; apps de estudo também podem ser adicionados na aplicação. | RF24; D06 | Edição de safelist/cmdline e controles específicos pendentes. |
| UX06 | Avisos de início são notificações do Windows em 5 min e 1 min; sem jogo/launcher aberto, só aparecem na configuração de sempre avisar. | RF05–RF06; D01 | Tempos confirmados; reconhecimento de jogo/launcher ainda pendente. |
| UX07 | Acionar Pausar inicia espera de 60s que pode ser cancelada; liberação por pausa ocorre após a espera completa. | RF16–RF17; seção 7 | Local do cancelamento e fronteiras com o fim da janela pendentes. |
| UX08 | Pausa libera sites e apps por 15 min, com contagem regressiva no ícone. | RF17 | Formato/frequência e solicitações repetidas pendentes. |
| UX09 | Com janela ainda ativa, há aviso 1 min antes do fim da pausa e retomada ao término; fora da janela não retomar. | RF18; D09 | Meio/condicional do aviso pendentes. |
| UX10 | Pausa efetivada conta; cancelamento não. Estatísticas apresenta horas por dia, semana segunda–domingo e total, pausas e processos efetivamente encerrados. | RF19; RF21; D09/D12/D16 | Calendário local; atribuição diária e deduplicação técnica pendentes. |
| UX11 | App de estudo/dev em primeiro plano só nas janelas e fora da pausa; ociosidade >5 min interrompe; Brave só em domínio de estudo cadastrado. | RF20; D05–D06/D19 | Identificação real e mecanismo do domínio ativo pendentes. |
| UX12 | Durante bloqueio, processos correspondentes são encerrados/reencerrados, preservando safelist; sites são liberados ao sair da janela com remoção apenas das linhas do app. | RF07–RF14; seção 7 | Verificação integrada de resultado percebido; cobertura de domínios e erros não garante bloqueio completo. |
| UX13 | `hosts` somente leitura ou bloqueado por antivírus resulta em registro de erro e alerta na bandeja. | Seção 8 | Não prescreve formato nem novo estado do ícone. |
| UX14 | Orientação de instalação inclui desativar DNS seguro no Brave e testar YouTube durante janela; Brave News/nova guia são opcionais. | Seção 9 | Canal de orientação e retorno do teste pendentes. |
| UX15 | Inicialização no meio da janela aplica bloqueio sem aviso prévio; após suspensão o próximo ciclo reavalia. | Seção 8; RF04 | Apresentação durante retomada pendente. |
| UX16 | Sair libera os bloqueios; inicialização limpa bloco antigo e reavalia, inclusive após crash. | Seção 8; D02–D03 | Recuperação ao reabrir aprovada; falha de limpeza e feedback pendentes. |

Não há critério aprovado para cores, textos, navegação por teclado, responsividade da janela, escolha de aba inicial, confirmações ou mensagens de validação. A definição desses aspectos deve permanecer separada da conformidade com os RF existentes.

## 10. Perguntas prioritárias para o Maestro

As perguntas são encaminhamentos ao Maestro para consolidação; não representam decisões tomadas nem solicitação direta ao usuário neste trabalho.

1. **Edição e proteção:** D06 já confirmou edição dos apps de estudo. “Tudo editável” (seção 11) também inclui safelist, `block_cmdline`, tempos de aviso e pausa? Em quais abas? Quais proteções de RF10 são obrigatórias e não removíveis?
2. **Modelo/validação de cmdline:** padrões são substrings simples? Como associar `javaw.exe` a `.minecraft` sem ampliar o bloqueio a outros apps? Quais entradas e conflitos serão rejeitados ou permitidos (RF09–RF10; seções 5–6)?
3. **Saída, parcialmente respondida:** Sair libera, e crash é recuperado ao reabrir (D02–D03). Como tratar falha de limpeza? Fechar a janela mantém o processo na bandeja? O que ocorre com edição não salva e pausa/espera (RF22; seção 8)?
4. **Fronteiras da pausa, parcialmente respondidas:** D09 confirmou elegibilidade durante bloqueio, espera bloqueada, cancelamento sem contagem e ausência de retomada fora da janela. Como tratar fim da janela durante espera, pedidos repetidos, reinício/suspensão e atribuição diária?
5. **Indicadores:** onde ficam a contagem de 60s e seu cancelamento? Como o ícone apresenta os 15 min regressivos e com qual frequência? Como indicar falha parcial sem confundir horário de bloqueio com bloqueio aplicado (RF16–RF17; RF22; seção 8)?
6. **Avisos, parcialmente respondidos:** D01 confirmou 5/1 min. RF06 também se aplica à retomada? Como reconhecer jogo/launcher e evitar duplicatas após sobreposição, edição ou salto de relógio (RF03; RF05–RF06; RF18)?
7. **Configuração e validação:** D04/D08 fecharam dias, meia-noite, limites/adjacência e igualdade inválida; D13 exige configurar antes de ativar, sem horários iniciais ativos e listas sugeridas. Restam salvar/aplicar/cancelar após primeiro uso, dias vazios, domínios, duplicações, pastas/variáveis e falhas de gravação/leitura.
8. **Brave e alertas:** onde orientar instalação e reteste? Como tratar falha no teste e conexões abertas? Qual canal, duração e repetição do alerta obrigatório de erro no `hosts` (seções 8–9)?
9. **Contrato UI/núcleo e estatísticas:** como confirmar comandos e refletir erros/estado efetivo entre threads? D09/D12/D16 definiram cancelamento sem contagem, semana segunda–domingo local e tentativa por processo encerrado; restam períodos selecionáveis, atribuição diária e deduplicação.

Antes de transformar propostas em critérios obrigatórios, consolidar respostas em `DECISIONS.md` e nos documentos impactados. Consultar o registro central para distinguir perguntas respondidas de pendências. O escopo original permanece preservado.

## 11. Primeiro uso e qualificação do Brave

**D13 confirmado:** iniciar sem horários ativos, apresentar listas como sugestões, escolher/salvar horários e listas antes de ativar bloqueios. Não há wizard, layout ou texto aprovado; esses detalhes são propostas de UI a elaborar.

**D19 confirmado para produto:** usuário adiciona domínios considerados estudo e personaliza quais sites bloquear. A UI deve permitir essas duas finalidades, sem promover domínio de estudo a liberação automática. Aba/controles, normalização, subdomínios e tratamento de conflitos ainda a definir. Não há lista inicial obrigatória aprovada. D05 exclui descanso dos totais; identificar domínio da aba ativa permanece decisão técnica.

# Proposta de protocolo de desempenho

Data: 2026-10-13. Base de referência: `79607c9`.

**Status: proposta técnica, sem aprovação D18. Nenhum RNF está aceito por
este documento.** A preparação documental original não executou benchmark ou
suíte nativa; execuções posteriores do coletor estão registradas separadamente.
Todas as matrizes, cargas, durações, quantidades de repetições e escolhas de
instrumentação abaixo são propostas para revisão; não são critérios de aceite
aprovados. Um subconjunto agora tem [coletor implementado](PERFORMANCE_COLLECTOR.md),
testes e [ensaios exploratórios](PERFORMANCE_COLLECTOR_RESULTS.md). Esta proposta
completa, incluindo sessões longas e artefato distribuído, não foi executada.
Ensaios exploratórios dentro do desenvolvimento autorizado devem identificar
suas condições e limites; não exigem fechar D18 para produzir uma medição,
mas não podem declarar RNF01 aceito antes dessa definição.

## Rastreabilidade e decisões em aberto

[REQUIREMENTS.md](REQUIREMENTS.md) registra RNF01: CPU abaixo de 1% e RAM abaixo
de 80 MB em repouso. [DECISIONS.md](DECISIONS.md), D18, ainda deixa em aberto
hardware de referência, método de CPU/RAM e matriz de versões/arquiteturas.
Também é necessário escolher qual estado do motor constitui repouso, quais
processos do produto entram na conta e qual estatística será comparada aos
limites. Não interpretar MB como MiB ou escolher a normalização de CPU depois
de conhecer o resultado.

[USER_ANSWERS.md](USER_ANSWERS.md) estabelece que resposta vazia não é aprovação.
Este arquivo não fecha decisões de sites, pausa, avisos, instalador ou Brave.
[TEST_PLAN.md](TEST_PLAN.md) prevê medição do executável distribuído e sessões
longas, com carga de referência pendente. Medir o intérprete de desenvolvimento
ou um controlador falso não substitui essa evidência.

[GUI_PERFORMANCE.md](GUI_PERFORMANCE.md) preserva medições exploratórias
anteriores: amostra única, raiz oculta, motor/bandeja simulados e CPU normalizada
por um núcleo. O render histórico mudou de `app.render` para `app.render_rules`;
esses tempos não permitem comparação estrita. Manter esses registros separados
dos futuros dados deste protocolo, sem retroativamente declarar RNF01 aceito.

## Ambiente e perímetro propostos — sem aprovação D18

Registrar antes da execução: commit completo, diff e hashes das fontes,
identificador/hash do coletor, comando e argumentos exatos, caminho do runtime,
versões Python/Tk/CustomTkinter/psutil/Pillow/pystray e hash do artefato, quando
houver distribuição. Congelar fonte e coletor durante uma comparação.

Registrar Windows edição/build/arquitetura, desktop interativo ou sandbox/RDP,
privilégio, CPU modelo/núcleos físicos/processadores lógicos, afinidade, limites
de VM/job, RAM física e disponível em bytes, armazenamento, plano de energia,
alimentação/bateria, monitores/resolução/DPI, tema e geometria efetiva.
Hardware disponível é ambiente observado, não hardware mínimo aprovado.

**Matriz de ambiente proposta, sem aprovação D18:**

| Série proposta | Ambiente a registrar | Alcance |
| --- | --- | --- |
| Desenvolvimento | Windows 10 e Windows 11 AMD64; Python 3.12.14 e 3.14.6 em séries separadas | Exploração nas versões já usadas pelo projeto; não define suporte final |
| Distribuição futura | Executável distribuído em hardware/Windows de referência a escolher em D18 | Necessário para futura avaliação do produto; artefato e coletor ainda a definir |
| Outras arquiteturas/Brave | Células pendentes de D18 e das funcionalidades correspondentes | Não presumir cobertura nem adicionar ensaio de navegador nesta unidade |

Propor CPU/RAM do PID do app, incluindo suas threads, como série principal.
Identificar processos por PID + create_time; registrar separadamente coletor,
launcher e eventuais filhos do produto. Na distribuição, conferir a árvore real
do empacotamento: excluir o launcher só se comprovadamente externo ao produto.
Se houver múltiplos PIDs, publicar contadores por PID e a soma de CPU; soma de
working sets pode contar páginas compartilhadas mais de uma vez. O perímetro e
a regra de memória agregada precisam de decisão prévia, sem escolha oportunista.

## CPU: contadores e dois denominadores

Guardar `cpu_times().user` e `.system` acumulados, em segundos, e marcas
`perf_counter_ns()` monotônicas no coletor. Para o mesmo conjunto de PIDs e um
intervalo válido, definir:

```text
delta_cpu_s = soma[(user_fim - user_inicio) + (system_fim - system_inicio)]
delta_wall_s = (mono_fim_ns - mono_inicio_ns) / 1_000_000_000
cpu_pct_1_logico = 100 * delta_cpu_s / delta_wall_s
cpu_pct_total_maquina = cpu_pct_1_logico / N_logicos_maquina
cpu_pct_capacidade_disponivel = cpu_pct_1_logico / N_logicos_disponiveis
```

O primeiro percentual usa um processador lógico ocupado como 100% e pode
superar 100% com várias threads. A segunda medida normaliza pelo número de
processadores lógicos da máquina; não pelo número de núcleos físicos. A terceira
só é publicada se afinidade/restrições efetivas forem conhecidas. Se uma quota
não puder ser representada por essa contagem, registrar a restrição e deixar
essa coluna indisponível. Não chamar uma VM restrita de capacidade total do host.
Essa normalização por tempo não mede capacidade computacional ponderada por
frequência ou diferenças entre núcleos.

Exemplo aritmético, sem medição: 0,6 s de CPU em 60 s de parede equivale a 1%
de um processador lógico e 0,125% de uma máquina com oito lógicos. O intervalo
do exemplo não é duração de ensaio aprovada. D18 deve escolher qual denominador
vale para RNF01; o relatório conservará ambos.

Propor coleta externa ao PID medido, com ordenação constante de leituras.
Guardar início/fim da leitura e seu custo; usar a marca intermediária da leitura
de CPU como timestamp da amostra. Calcular intervalos reais, sem assumir que o
agendamento ocorreu pontualmente. Usar delta dos contadores, sem depender do
primeiro resultado de `cpu_percent()` ou misturar CPU global com CPU do app.
CPU global pode ser controle ambiental separado. Não subtrair a CPU de outra
execução como suposto overhead. Quantização e deltas zero não significam custo
nulo; registrar resolução observada e aumentar duração apenas em nova série
identificada. Não somar novamente as threads ao contador do próprio processo.

## RAM: bytes, MB, MiB e contador Windows

Preservar inteiros em bytes. Exibir também `MB = bytes / 1_000_000` e
`MiB = bytes / 1_048_576`, com arredondamento apenas na apresentação.
80 MB decimais são 80.000.000 bytes, aproximadamente 76,294 MiB;
80 MiB são 83.886.080 bytes. A conversão não decide o significado aprovado
de RAM em RNF01, nem altera seu limite.

No backend Windows do [psutil 7.2.2](https://github.com/giampaolo/psutil/blob/release-7.2.2/psutil/_pswindows.py#L738),
`memory_info().rss` corresponde ao working set e `vms` ao PagefileUsage.
A documentação de [PROCESS_MEMORY_COUNTERS_EX](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters_ex)
define working set atual e pico em bytes e PrivateUsage como memória privada
comprometida. PagefileUsage não deve ser interpretado como bytes atualmente
gravados no arquivo de paginação.

**Escolha de medição proposta, sem aprovação D18:** registrar `rss`/`wset`,
`peak_wset`, `private` e `vms`/`pagefile`, se disponíveis na versão usada,
mantendo nomes originais e indisponibilidades explícitas. Working set é a série
principal exploratória para continuidade com GUI_PERFORMANCE; memória privada
comprometida é série complementar, não substituição silenciosa. USS opcional
pertence a coleta separada se seu custo interferir na amostragem. Não equiparar
essas séries à coluna padrão de memória do Gerenciador de Tarefas sem registrar
qual coluna/contador foi selecionado.

Publicar memória absoluta, baseline após imports, após build e após ações.
Delta sobre baseline ajuda a investigação, mas não é RAM total do produto.
Separar pico amostrado dentro de uma fase de `peak_wset` lifetime: o pico lifetime
pode ter ocorrido no build e não pode ser atribuído ao idle. Não forçar coleta
de lixo, esvaziar working set ou induzir pressão de memória para atingir limite.

## Carga proposta — sem aprovação D18

Para continuidade, propor `R_N` com **N = 0, 100 ou 1000 regras**, todas em
`block_exes`: nomes ASCII de largura fixa `qa-0000.exe` até `qa-(N-1).exe`,
formatando o índice com quatro dígitos. `windows: []`, demais listas vazias,
sem extras, consulta vazia, ordem Cadastro e seleção desligada. N é quantidade
de regras, não quantidade de processos. Não criar processos para preencher N.
Guardar JSON exato, tamanho em bytes, SHA256 e receita de geração antes do run;
os dados ficam em diretório exclusivo da fixture, fora da configuração do usuário.

Essa carga simples não representa automaticamente um cadastro real. Como
extensão proposta separada, `M_100`/`M_1000` distribuiria igualmente o total
pelas quatro categorias de regras, com manifest contendo nomes, pastas absolutas,
cmdline e comprimentos exatos. Duplicatas, Unicode, extras JSON, horários e
seleção ativa seriam extensões com IDs próprios, sem mudar `R_N` no meio da série.
Não afirmar limite de cadastro, carga mínima aprovada ou alcance universal.

Conferir universo completo N, página inicial, quantidade de páginas e no máximo
25 rows de regras projetadas, conforme implementação atual. Registrar também
contagem de horários/widgets e cardinalidade final de cada consulta. Paginação
não limita o modelo nem elimina o custo de filtrar/ordenar o universo.

## Matriz de estado proposta — sem aprovação D18

Cruzar inicialmente cada carga `R_N` proposta com as quatro primeiras células
abaixo. Ensaios de ações/query são fases separadas do idle, com seus próprios
marcadores. Estados futuros não são declarados executáveis ou autorizados agora.

| ID proposto | Interface/bandeja | Motor | Interpretação |
| --- | --- | --- | --- |
| G-P | GUI visível 880×660, Jogos / Apps, bandeja real pronta | Controlador real parado; nenhum start | Custo do app aberto sem ciclos de bloqueio |
| T-P | Ocultação pelo fluxo real de bandeja, ícone pronto, menu fechado | Controlador real parado | GUI ainda existe e polling continua; ocultar não é destruir |
| G-F | Mesma GUI visível e bandeja real | Controlador fake com snapshot running estável | Custo do estado apresentado; fake sem worker/scan não mede custo do motor |
| T-F | Mesma ocultação e bandeja real | Mesmo fake da célula G-F | Custo da apresentação na bandeja; não prova comportamento de worker real |
| H-F, referência opcional | Raiz oculta diretamente, bandeja fake | Fake sem worker | Compatibilidade exploratória com o histórico; não comparar como T-P/T-F |
| G-R/T-R, futuro | GUI/bandeja real em estados registrados | Motor real: fora da janela e janela ativa em séries distintas | Scan/cadência/carga do SO; depende de planejamento e autorização próprios |

Identificar classe/hash e semântica do fake. Propor snapshot estável sem IO,
enumeração, terminate/kill ou thread; contar chamadas para comprovar o perímetro.
Um futuro worker com adaptador sintético seria outra célula, com cardinalidade,
agenda e periodicidade próprias: não renomear o fake estático como motor ativo.

Para motor real futuro, registrar separadamente N regras, quantidade de processos
enumerados, candidatos/reinspeções, duração/atraso de ciclos e resultado do scan.
O ciclo de 5 s é comportamento existente, não duração de benchmark aprovada.
Começar por estado sem efeitos e depois propor alvos descartáveis específicos;
nenhum efeito sobre hosts ou aplicativos do usuário está autorizado aqui.
Agenda, alvos e eventuais encerramentos não devem entrar no agregado de idle
sem identificação. Memória/CPU dos alvos é carga externa, não custo do app.

## Durações e repetições propostas — sem aprovação D18

Propor cinco repetições independentes por célula, cada uma em processo novo.
Alternar a ordem das cargas de forma determinística e registrar ordem/seed.
Baseline pós-import, build e estabilização ficam fora da janela de idle.
Propor warmup de 30 s de mainloop no estado escolhido, seguido de 120 s de
idle com amostras externas a cada 1 s; guardar duração efetiva e atrasos.
Não simular idle com sleep na thread Tk. Bandeja deve estar pronta e a busca
sem pending/timer antes da fase. Erro NIM_ADD torna a célula de bandeja inválida,
sem fallback para bandeja fake ou skip tratado como sucesso.

Esses tempos propostos permitem observar polling e reduzir o peso de contadores
quantizados; não bastam para demonstrar estabilidade de sessões longas.
Propor extensão separada de 60 min, em cinco processos independentes, com
amostragem a cada 5 s e estado constante. Registrar tendência de working set,
memória privada, handles e threads; crescimento sozinho não prova vazamento.
As durações, frequências e repetições dessa extensão também estão sem aprovação D18.

Para ações, propor série separada com cinco processos novos e dez tentativas
por ação por processo, restaurando explicitamente estado/consulta/página entre
tentativas. Um warmup de cada ação fica marcado e fora do agregado de ações;
guardar suas medidas também. Build ocorre uma vez por processo e não possui
warmup do próprio build. Processo novo não garante cache de disco frio: registrar
cache conhecido/desconhecido, sem purgar caches ou chamar essa série de cold boot.

## Fronteiras de timing propostas — sem aprovação D18

Usar relógio monotônico de alta resolução e CPU do processo, com endpoints
idênticos entre versões. Preparação da fixture/imports/carregamento da sessão
ficam medidos à parte, com exclusões declaradas. Propor as seguintes séries:

| Métrica proposta | Início | Fim e limites |
| --- | --- | --- |
| Build widgets | Imediatamente antes de `_build_app` | Retorno da fábrica; inclui o render inicial e demais trabalho síncrono |
| Build até layout | Mesmo início | Após passagem de `update_idletasks`; registrar endpoint e custo separadamente |
| Render completo | Antes de `app.render()` | Retorno; layout adicional em coluna própria |
| Render regras | Antes de `app.render_rules()` | Retorno; layout adicional em coluna própria; não equiparar a render completo |
| Projeção | Antes de `render_rule_projection(página)` | Retorno e layout, sem confundir com cálculo do universo lógico |
| Query fim a fim | Imediatamente antes da última escrita efetiva na consulta | Projeção correspondente à revisão final concluída, pending falso e layout processado |
| Query trabalho | Entrada do render final até retorno/layout | Custo da reconstrução; espera/agendamento excluídos e publicados separadamente |

Uma passagem de layout não garante pixels apresentados pelo compositor. Não
usar `update()` irrestrito como endpoint sem declarar os callbacks processados:
ele pode consumir timers/polling e introduzir reentrância. Propor observadores
externos/reversíveis no harness, sem mudanças em produção ou patch para retirar
o debounce. Guardar callbacks e revisões de consulta para vincular cada fim ao
último valor escrito; callback cancelado não produz amostra válida de conclusão.

O debounce **atual** é um `after(200, ...)`, conforme
[RULE_SEARCH_DEBOUNCE_CONTRACT.md](RULE_SEARCH_DEBOUNCE_CONTRACT.md).
200 ms é atraso solicitado ao event loop, não latência medida, limite de resposta
ou duração de render. Guardar timestamp da escrita, prazo solicitado, início
real do callback, entrada/saída do render e layout. A latência observada inclui
espera, atraso do loop e reconstrução; não deduzir o total subtraindo 200 ms.

**Perfis de query propostos, sem aprovação D18:** consulta unitária `qa-00`,
rajada `q` → `qa` → `qa-` → `qa-0` → `qa-00` com intervalo solicitado de 50 ms,
e mesmas escritas espaçadas com intervalo solicitado de 500 ms. Registrar
intervalos reais, render count, query final e resultados. Não pressupor um
render por rajada quando o loop esteve ocupado; não agendar todas as escritas
numa única chamada síncrona e chamar isso de digitação real. Clear/Escape e
review com filtro incluinte/excluinte são ações separadas com destino/página
registrados, sem flush intermediário que transforme o trabalho medido.

## Registro bruto proposto e análise

Propor manifest JSON e amostras CSV/JSONL UTF-8 locais por run, gravados fora
das fronteiras de timing quando possível. O formato ainda será implementado;
não inventar resultados. Conservar stdout/stderr, erros Tk e runs inválidos.

| Registro proposto | Campos mínimos |
| --- | --- |
| Manifest | protocol_version, run_id, status=proposta_sem_aprovacao_D18, base/hash/diff, ambiente, comandos, coletor/hash, PID/create_time/perímetro, carga/hash, estado, ordem, repetições/durações propostas e efetivas |
| Amostra | run_id, fase, seq, mono_ns, read_start/end_ns, user_s, system_s, rss_bytes, peak_wset_bytes, private_bytes, vms_bytes, CPU global de controle, RAM disponível, erro/indisponibilidade |
| Evento | fase início/fim, consulta/revisão, prazo/start de callback, render start/end, layout fim, página, universo/rows, estado motor/bandeja e contadores de chamadas/efeitos |
| Encerramento | duração, exit code, PIDs/threads restantes, timers owned, bgerrors, hashes finais de JSON/fontes, remoção de fixtures ou motivo de preservação |

Timestamp civil com timezone serve à rastreabilidade; duração vem do monotônico.
Dados de processos reais futuros devem ser contagens/IDs de fixture, sem dumps
de cmdlines pessoais. Guardar precisão original; não transformar erro de acesso,
amostra ausente ou timeout em zero. Se o PID terminar entre leituras, marcar o
intervalo incompleto; não reaproveitar contadores de outro processo.

Por run, calcular CPU média com deltas dos endpoints válidos de idle;
resumir também intervalos e memória com mediana, mínimo, máximo amostrado e
duração. Entre runs, publicar cada valor e a mediana/faixa; timings de ações
incluem mediana, máximo e p95 com método explícito (nearest rank). Tentativas
no mesmo processo não são repetições independentes; cinco builds não sustentam
um p95 estável de startup. Não juntar runtimes/cargas/estados/fases, escolher
somente o melhor run ou remover outliers sem causa registrada. A estatística
para aceite permanece pendente de D18, mesmo se números ficarem abaixo dos limites.

## Controles, teardown e continuidade propostos

Executar futuramente um cenário por vez, sem benchmark ou suíte nativa
concorrente. Registrar atividade de fundo e interrupções; não desativar serviços,
antivírus ou mudar prioridade/afinidade para melhorar números. Impedir suspensão
somente por mecanismo registrado; suspensão/RDP/alteração de energia durante
fase gera run inválido preservado e repetição adicional identificada.

Separar idle de menus abertos, modais, confirmações, seleção, digitação e Save.
Antes/depois, conferir modelo/universo, baseline, dirty/history e SHA256 do JSON,
além de zero IO/efeitos do fake. Mudança necessária de fixture ocorre entre
runs. Conferir fonte/hash estável e registrar qualquer desvio metodológico.

Propor fechamento pelo lifecycle normal do app, stop de motor/bandeja e
cancelamento dos timers pertencentes à fixture, sem wait/join no callback Tk.
O supervisor externo pode aguardar término; propor timeout de 90 s por teardown,
sem aprovação D18. Se expirar, registrar falha antes de eventual cleanup do
processo dedicado, revalidando PID/create_time/exe e diretório exclusivo.
Conferir saída do launcher/app/filhos próprios, threads encerradas, ausência de
bgerrors/timers owned e remoção apenas das fixtures verificadas. Conservar
evidências brutas; nunca encerrar PIDs ou excluir caminhos de terceiros.

Próximo passo: estender o coletor exploratório com geometria estabilizada,
repetições/estados e latência de busca, mantendo contadores/endpoints e limites
registrados. Para aceite final, consolidar
D18 com o usuário (hardware, matriz, repouso/carga, CPU, memória/perímetro,
estatística e artefato) pelo canal [USER_ANSWERS.md](USER_ANSWERS.md).
Resultados futuros devem relatar
desvios e limitações; este documento não altera RNF01, não conclui aceite
visual/DPI e não fecha respostas vazias de outras funcionalidades.

# Medição de custo da interface

## Antes da atualização condicional — 2026-10-13

Base `7d3ad6d`. Uma execução por cenário, em processos novos, sem suíte de
testes concorrente. Configuração JSON UUID isolada, executáveis únicos
`qa-N.exe`, janela 880×660 oculta, light/blue, ordem Cadastro, busca vazia e
seleção desligada. Controlador e bandeja simulados; nenhum motor real.

Snapshot e helper registered tiveram uma chamada cada. Build/reconstrução
incluem criação de widgets e processamento de layout/Tk; preparação do JSON
e carregamento da sessão ficaram fora desses tempos. Repouso: cinco segundos
de mainloop com polling normal. CPU user+system e RSS medidos somente pelo
`psutil.Process(os.getpid())` do intérprete de QA.

| Regras | Snapshot ms | Helper ms | Build s | Render s | CPU build/render s | RSS build/idle MiB | CPU idle s | Idle % de um núcleo |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 0,057 | 0,012 | 1,015 | 0,101 | 1,000 / 0,094 | 62,36 / 62,37 | 0,375 | 7,49% |
| 100 | 0,070 | 0,030 | 4,359 | 3,434 | 3,938 / 3,094 | 73,08 / 75,13 | 0,406 | 8,11% |
| 1000 | 0,369 | 0,184 | 30,538 | 35,648 | 28,250 / 33,516 | 187,32 / 195,31 | 0,375 | 7,50% |

Repouso wall: 5,004 / 5,012 / 5,002 s. Pico lifetime Windows: 62,37 / 75,13 /
195,33 MiB; baseline após imports aproximadamente 45 MiB. Todos os processos
terminaram dentro de 90 segundos e suas fixtures foram removidas.

Ambiente: Python 3.14.6 AMD64, Windows 10.0.19045, Tk 8.6.15, CustomTkinter
6.0.0, psutil 7.2.2, Pillow 12.3.0. Pystray 0.19.5 instalado, mas não iniciado.
Máquina reporta quatro núcleos físicos/oito lógicos e 9,88 GiB de RAM.

## Após atualização condicional — 2026-10-13

Produção congelada GUI_IDLE_UPDATES sobre `7d3ad6d`, com o mesmo protocolo e
ambiente. Repetidos somente os cenários 0/100, sem testes concorrentes ou nova
execução de 1000. Uma amostra por cenário; CPU/RSS do próprio PID.

| Regras | Build s | Render s | Snapshot ms | Helper ms | CPU idle s | Idle % de um núcleo | RSS idle MiB |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 0,934 | 0,0649 | 0,0492 | 0,0131 | 0,046875 | 0,937% | 62,71 |
| 100 | 3,916 | 3,149 | 0,0616 | 0,0265 | 0,015625 | 0,312% | 75,09 |

Repouso wall: 5,004 / 5,006 s. CPU build/render: 0,859375 / 0,0625 s e
3,484375 / 2,90625 s. RSS após build 62,71 / 73,52 MiB; pico 62,72 / 75,10 MiB.
Processos encerrados com exit 0 e fixtures removidas; nenhum timeout.

Nesta amostra, CPU idle caiu 87,5% / 96,15%; resolução/quantização e uma única
observação impedem tratar isso como garantia estatística. RSS ficou próximo
do anterior. Render de 100 regras continua aproximadamente 3,15 s; a alteração
não resolve o custo da materialização de listas extensas. Não extrapolar o
resultado posterior para 1000 regras, seleção ativa, motor real ou RNF01.

## Após paginação visual — 2026-10-13

Uma execução final do cenário 1000, fonte RULE_PAGINATION congelada sobre
`795c794`, mesmo ambiente/dataset/configuração/880×660/seleção desligada.
SHA256 de `ui/config_gui.py`:
`1BAB4F60A1689F6D9403134FDB8B2BDB32FE1C78B89F5EA50681FE3FD252827F`.

| Medida | Antes, 1000 regras | Após paginação, 1000 regras |
| --- | ---: | ---: |
| Construção s | 30,538 | 2,089431 |
| Render s | 35,648 (`app.render`) | 1,049138 (`app.render_rules`) |
| RSS idle MiB | 195,31 | 66,773438 |
| CPU idle de um núcleo | 7,50% | 0,311850% |

**Desvio explícito:** o script anterior renderizava toda a app
(`app.render` + updates); o atual usou `app.render_rules` + os mesmos updates,
por instrução inicial incorreta do Maestro. A correção chegou após o processo
terminar; não houve repetição. Os tempos de render não são comparação estrita.
Construção e demais condições mantiveram o protocolo anterior. Uma amostra
não é garantia estatística nem aceite RNF01/visual/DPI.

Snapshot 0,282300 ms/helper 0,272600 ms; CPU build/render 1,890625/0,953125 s.
RSS após build 66,222656 MiB, pico lifetime 66,777344 MiB. Idle wall 5,010428 s,
CPU 0,015625 s (quantização relevante). Nenhum timeout/erro/stderr.

Invariantes conferidos: FULLindices/modelo **1000**, página 0 de **40**, somente
**25** rows materializadas (índices 0–24), modelo tipado/bytes intactos, dirty
false, controller/tray starts zero e bgerrors vazios. Processo/launcher
encerrados e fixture UUID removida. Não medir seleção ativa ou motor real.

## Interpretação consolidada e limites

- Nesta amostra, snapshot/helper são sub-ms; criação/reconstrução dos widgets
  domina o custo de listas extensas. Com 1000 regras, o custo é relevante para
  a capacidade de resposta da thread Tk. Não demonstra vazamento de memória.
- Idle não aumentou visivelmente com a quantidade de regras no modo seleção
  desligado. Não extrapolar para seleção ativa, bloqueador real ou bandeja.
- Percentual acima usa um núcleo como 100%, não a capacidade total da máquina.
  RNF01 e definição do cenário de repouso/hardware continuam pendentes; estes
  números não constituem aceite de CPU <1%/RAM <80 MB.
- Uma amostra, raiz oculta, imports de QA e resolução dos contadores limitam
  comparações. Sem medição de pintura, foco físico, DPI ou acessibilidade.
- Instrumentação fake independente confirmou inicialmente 39 `configure` em
  três polls sem mudança (13/poll). A atualização condicional elimina setters
  repetidos de texto/estado. Essa alteração sozinha não reduz a quantidade de
  widgets; a paginação posterior limita a projeção a 25 linhas.

## Continuidade

Atualização condicional e paginação visual de 25 limitam trabalho repetido e
quantidade de widgets, preservando o universo completo. A implementação/QA
da paginação tem [contrato próprio](RULE_PAGINATION_CONTRACT.md). Modelos e
snapshots continuam proporcionais à quantidade de dados; páginas não limitam
configuração nem garantem latência/RSS. Aceite visual/DPI e RNF01 do app real
continuam pendentes.

O [coletor exploratório](PERFORMANCE_COLLECTOR.md) foi implementado e seus
[resultados](PERFORMANCE_COLLECTOR_RESULTS.md) preservam raw, cobertura CPU,
invariantes e saída do PID. Geometria síncrona e warmup variaram; não comparar
estritamente seus timings com os históricos acima. Os
[resultados v2](PERFORMANCE_GEOMETRY_RESULTS.md) registram renders reais no mainloop
com geometria confirmada nas fronteiras e espera after_idle separada; build e
raiz oculta continuam não comparáveis. Duas repetições por runtime mostraram
variação CPU dentro do mesmo runtime, sem causa demonstrada. Próxima medição deve seguir
[PERFORMANCE_PROTOCOL.md](PERFORMANCE_PROTOCOL.md),
registrando fontes/dados brutos e desvios. Matriz, cargas, durações e método de
aceite continuam propostas de D18; ensaios curtos não executam a matriz completa.
Q-PERF-01/02 em [USER_ANSWERS.md](USER_ANSWERS.md) tratam ambiente/repouso e
significado dos limites para aceite final, sem impedir investigação exploratória.

A [medição de busca](PERFORMANCE_QUERY_RESULTS.md) separa setter/debounce/render/
after_idle e reset vazio real antes do idle. Usa R_N1000, programaticamente,
sem representar teclado físico ou pintura. Custo por chamada e CPU idle
observados exigem diagnóstico separado antes de alterar produção ou polling.

Os [controles de idle](PERFORMANCE_IDLE_DIAGNOSTIC.md) observaram CPU alto
também sem query no período curto; warmup30/idle15 reduziu os valores, com
picos posteriores. Perfil separado localiza CPU na thread Tk em um ensaio,
sem atribuir função nativa ou aceitar RNF01. Polling/produção permanecem iguais.

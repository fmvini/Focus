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

## Interpretação e limites

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
  repetidos de texto/estado; não resolve a materialização de listas extensas.

## Continuidade

Medição posterior 0/100 concluída com o mesmo protocolo. Para listas extensas,
uma próxima unidade deve
avaliar renderização progressiva cancelável preservando todos os resultados
da seleção, índices originais, contextos obsoletos recusados e navegação pela
revisão. Nenhuma política de paginação/limite foi implementada nesta medição.

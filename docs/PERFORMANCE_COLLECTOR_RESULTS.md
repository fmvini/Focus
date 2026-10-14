# Resultados exploratórios do coletor

Data: 2026-10-13, Windows 10.0.19045 AMD64. Produção em `79607c9`,
base documental `6aa53c6`; ferramentas novas ainda sem commit durante os runs.
Cada manifesto conserva HEAD/status e hashes dos arquivos realmente usados.
Execuções do Maestro, sequenciais, sem GUI/benchmark/suíte nativa concorrente.
**Não há aceite RNF01, visual/DPI ou garantia estatística.**

## Ambiente e método

Máquina reportou quatro núcleos físicos/oito lógicos. Python 3.14.6 e 3.12.14,
CustomTkinter 6.0.0, psutil 7.2.2, Pillow 12.3.0, pystray 0.19.5.
Versões, memória total/disponível e executáveis ficam nos manifestos/reports;
afinidade do alvo fica em `summary.json.identity.affinity`. Plano de energia,
escala Windows, monitor e quotas não
medidos. A versão do supervisor é separada da versão do worker.

R_N contém executáveis sintéticos distintos e demais listas/agenda vazias.
Motor parado, busca vazia, ordem Cadastro, seleção desligada, projeção de até
25 regras. Perfis conforme [guia](PERFORMANCE_COLLECTOR.md): H-F oculto/fake,
G-P janela visível/bandeja real pronta, T-P oculto pelo fluxo da bandeja real.
O controlador dos perfis reais tem gate que impede iniciar o motor.

Intervalo solicitado de 0,25 s. CPU abaixo usa delta user+system dividido pela
cobertura efetiva entre leituras válidas inteiras no idle, não pelo tempo
solicitado. A coluna total divide pelo número de processadores lógicos (oito).
RSS é o máximo amostrado do working set em MiB; bytes/MB, commit privado e
pico lifetime estão separados no resumo bruto. Zero CPU observado pode resultar
da quantização do contador e não significa custo nulo.

## Fonte final

Estes três runs usam a fonte final do coletor, incluindo retenção na preparação,
Ctrl+C/publicação, nome UUID comum e versões Python/executável no worker.
Os 65 testes com doubles passaram nesta fonte em Python 3.14.6/2,336 s e
3.12.14/2,215 s, sem skips; nenhuma GUI foi importada pelos testes.

| Run em `.qa/performance/` | Python | Perfil/regras | Warmup / idle solicitado s | Cobertura CPU s | CPU lógico % | CPU total % | RSS máximo MiB |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| `run-da6e9b1e7e474bd0910c34c154b02769` | 3.14.6 | G-P/100 | 30 / 10 | 9,782798 | 3,194383 | 0,399298 | 60,289063 |
| `run-247800ac890447e58d283a4ffb44fc8d` | 3.12.14 | G-P/100 | 30 / 10 | 9,782215 | 0,319457 | 0,039932 | 60,464844 |
| `run-a91460c2137c4add90d4c7c59b95e430` | 3.12.14 | T-P/100 | 0,5 / 3 | 2,759302 | 0,000000 | 0,000000 | 59,582031 |

Todos publicaram ready/report/raw/summary completos, exit=0, errors=[],
closed=true, tray_alive=false e after_info=[]. Invariantes de bytes/modelo
tipado/draft/baseline/history/FULL/projeção e zero starts passaram; fonte e
fixture conservaram hashes. O supervisor comprovou separadamente a ausência
do PID/create_time medido após a saída do launcher. Nenhum cleanup forçado
foi necessário nesses runs. `ok=true` valida o ensaio, não aprova desempenho.

## Ensaios anteriores durante a implementação

Mantidos para rastreabilidade; não atribuir estas execuções à fonte final.
Os cinco primeiros precedem as correções de retenção/UUID; os três seguintes
usam essas correções, mas precedem o acréscimo de versão Python/executável ao
report do worker. Parâmetros e hashes exatos permanecem em cada manifesto.

| Run em `.qa/performance/` | Python | Perfil/regras | Warmup / idle s | Cobertura CPU s | CPU lógico % | RSS máximo MiB |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `run-900b9b3abdee429aa96cab66ca870da6` | 3.14.6 | H-F/100 | 0,5 / 3 | 2,760067 | 0,566109 | 54,593750 |
| `run-dbd3f2d03a144219a179030c7f47d4ec` | 3.14.6 | H-F/0 | 0,5 / 3 | 2,760520 | 0,566017 | 50,488281 |
| `run-60253741ceb94b818b9307304739f79b` | 3.14.6 | H-F/1000 | 0,5 / 3 | 2,760237 | 1,698224 | 54,925781 |
| `run-da1f5b373cd8404d985a281d416c4f19` | 3.14.6 | G-P/100 | 0,5 / 3 | 2,759551 | 50,959376 | 59,832031 |
| `run-14d5e4e964c3408ba3d70bc1f72bcf7a` | 3.14.6 | T-P/100 | 0,5 / 3 | 2,774691 | 0,000000 | 59,296875 |
| `run-f38045c97c6841a180a245f6dc5a9e4b` | 3.14.6 | H-F/100 | 0,5 / 3 | 2,760562 | 0,566008 | 59,101563 |
| `run-22508fda8cc8486ea22bd0014e8534e4` | 3.12.14 | H-F/100 | 0,5 / 3 | 2,760170 | 0,566088 | 56,699219 |
| `run-9b706e679aed49ca97cfdd826467e345` | 3.14.6 | G-P/100 | 5 / 5 | 4,766076 | 11,802161 | 60,402344 |

Os resumos desses runs também reportaram sucesso e invariantes preservadas.
O consumo visível caiu nas amostras com aquecimento maior, mas a diferença
entre runtimes permanece. São observações únicas, com duração/versões da
ferramenta diferentes; não demonstram causa, estabilização ou regressão do app.
Investigar com repetições e séries temporais antes de mudar polling/timers.

## Limites e continuidade

As fronteiras síncronas de build/render reportaram geometria efetiva 200×200,
embora tenham solicitado 1000×740/880×660. Depois do mainloop, G-P/T-P prontos
reportaram 880×660; H-F reportou 200×200. `update_idletasks` não comprovou
geometria estabilizada ou pintura. Timings brutos são endpoints observados,
não tempos aprovados de render em 880×660; não comparar estritamente com
[medições históricas](GUI_PERFORMANCE.md) ou entre perfis.

Artefatos completos ficam nos diretórios acima, ignorados pelo Git. Logs
adicionais em `.qa/collector-*.log`; não houve remoção desses dados brutos.
As primeiras tentativas fake do Frontend deixaram nove diretórios
`.qa/perf-worker-fake-*` e diretórios Temp com falha WinError 5; os testes
finais usam mkdir padrão e limpam suas próprias fixtures. Resíduos anteriores
não foram removidos nem tiveram ACL alterada; parte dos Temp tem atribuição
apenas temporal, não identidade comprovada.

Próximos ensaios: estabilizar/verificar geometria no mainloop antes dos
timings comparáveis; investigar CPU visível por série temporal e repetições
com warmup explícito; ampliar cargas/estados/latência de busca e sessão longa.
Executável distribuído, hardware/matriz e interpretação dos limites dependem
da consolidação D18/Q-PERF-01/02 para aceite final. Roteiro visual permanece
sem aprovação: [tentativas](GUI_ACCEPTANCE_RESULTS.md).

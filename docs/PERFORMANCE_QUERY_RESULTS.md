# Latência programática da busca — resultados exploratórios

Data: 2026-10-14, America/Sao_Paulo. Base `9596d71`, produção `79607c9`
inalterada. [Contrato](PERFORMANCE_QUERY_CONTRACT.md) e [CLI](PERFORMANCE_COLLECTOR.md).
**Não é aceite RNF01, visual/DPI, pintura ou teclado físico.**

## Fonte, ambiente e validação

113 testes aprovados/zero skips pelo Maestro: Python 3.14.6/3,778 s e
3.12.14/3,943 s; 28 worker, 20 métricas, 19 artefatos, 19 supervisor,
20 query puros e 7 probe/integração. Testes com doubles, sem GUI nativa.
Backend validou separadamente seus 20 puros nos dois runtimes. Frontend/Banco
revisaram hooks/eventos/invariantes somente por leitura; Backend reconferiu
supervisor final depois das correções, sem rerun ou benchmark atribuído à revisão.

O supervisor inicialmente aceitava ready sem modo/schema e pacotes com só
declaração ok. Fonte final exige schema inteiro1, modo antes do sampler,
eventos completos, checks de dados, resumo idêntico ao recálculo puro,
reset posterior à observação final e revisão crescente. Falhas são preservadas.
Regressões cobrem evidências ausentes/adulteradas, schema bool/float,
cancel/stale/consumed callback, restauro exato/idempotente, swallowed Tk error
e getters que esgotam prazo antes de set/render.

SHA256 finais:
- `tools/perf_query.py`: `C67AFAD22C2EC4D7BA239C8CB3D1AF48F3D8F58366FF064C285FC128E1B8F032`.
- `tools/perf_query_probe.py`: `F00371F625B10CAA906159FB853B410367F20CA68896E111A07D9F68F8AAE031`.
- `tools/perf_gui_worker.py`: `58E0339FC3122CB906142B0F5C601BD96DAEBDF9DEA1D19266C1B6A39AF09606`.
- `tools/measure_gui.py`: `AE0C91C5571235C97A9D42ECD889591C11CC2447C5E5202838705BEB7034924A`.

Windows 10.0.19045 AMD64, quatro núcleos físicos/oito lógicos, Tk 8.6.15,
CustomTkinter 6.0.0, psutil 7.2.2, Pillow 12.3.0, pystray 0.19.5.
Executáveis/versões e afinidade (summary.identity) conservados nos artefatos.
DPI, plano de energia, quotas e atividade de fundo não controlados/medidos.
Uma GUI por vez, sem benchmark/suíte nativa/captura concorrente.

Doze runs sequenciais: seis antes de endurecer o supervisor e seis com fonte
final. Worker/probe/helper iguais nas duas etapas; os seis manifestos iniciais
diferem da entrega somente em `tools/measure_gui.py`. Não são doze repetições
equivalentes, nem comparação de runtimes controlada. Todos G-P/R_N1000,
warmup1/idle3 s, intervalo0,25 s, startup60/finish30 s. Bandeja real pronta,
motor parado, geometria v2 confirmada; query/reset antes de ready/warmup/idle.
Timings de preparação versão2 e eventos query versão1 são schemas distintos.

## Série final

Valores em ms, seis casas decimais. Última escrita→observação inclui setter,
debounce real, chamada de render e espera até after_idle/instrumentação.
Primeira escrita→observação também inclui as escritas/esperas intermediárias.
Reset vazio é uma ação distinta pelo debounce real; nunca flush/clear/update.

| Modo | Python | Última→observação ms | Primeira→observação ms | Renders | Reset ms | Run em `.qa/performance/` |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| single | 3.14 | 915.835700 | 915.835700 | 1 | 1289.973800 | `run-aff302f1d7ca47d9b3b4424dab5636e5` |
| single | 3.12 | 920.956700 | 920.956700 | 1 | 1309.326100 | `run-17230154352743a5a439b6d1c8795a42` |
| burst | 3.14 | 841.898000 | 1191.058800 | 1 | 1194.142100 | `run-85415c71fbd046699bb857213c8bae66` |
| burst | 3.12 | 820.155900 | 1160.657000 | 1 | 1215.553700 | `run-41bdf1a68b524a6cb4ab326cb74d369b` |
| spaced | 3.14 | 1236.818100 | 6045.131400 | 5 | 1210.702400 | `run-bc4483e742914f5c9a63f541a2f4d04a` |
| spaced | 3.12 | 1161.778400 | 5606.034000 | 5 | 1205.358700 | `run-e96493e956014b56b34e2d0aa74e1117` |

### Decomposição da busca

Listas seguem ordem das escritas/renders. `—` indica callback cancelado ou
ausência de gap; não é duração zero. Chamada de setter inclui trace síncrono;
não isola custo exclusivo do trace. Espera do callback começa no retorno do
registro do timer. after_idle não prova pintura nem CPU exclusiva de layout.

| Modo/Python | Setter ms por escrita | Espera callback ms | Chamada render ms | Espera after_idle ms | Gaps efetivos ms |
| --- | --- | --- | --- | --- | --- |
| single/3.14 | 113.561900 | 200.076500 | 592.651200 | 9.459200 | — |
| single/3.12 | 113.236800 | 200.066800 | 595.335500 | 12.162100 | — |
| burst/3.14 | 122.037600, 0.433300, 0.261700, 0.427000, 0.198700 | —, —, —, —, 200.038400 | 633.628300 | 7.967800 | 74.378700, 50.956300, 50.366000, 50.300200 |
| burst/3.12 | 112.768100, 0.350500, 0.224800, 0.217700, 0.268900 | —, —, —, —, 200.060000 | 611.862300 | 8.011300 | 75.383100, 51.063900, 50.335000, 50.158000 |
| spaced/3.14 | 105.328300, 111.334500, 162.840000, 111.781000, 110.083400 | 200.126600, 497.824800, 610.184700, 527.251400, 510.360500 | 618.255200, 702.715900, 579.685700, 577.381600, 608.680800 | 120.887100, 173.914200, 119.748900, 119.296800, 7.665000 | 820.383600, 1201.068700, 1190.502900, 1105.074300 |
| spaced/3.12 | 123.630700, 112.507400, 108.707700, 106.889600, 116.096900 | 200.097000, 482.982300, 492.317100, 462.429900, 478.933200 | 584.526600, 574.037100, 584.604100, 608.678600, 557.587400 | 121.081900, 119.176900, 117.341300, 126.102800, 9.110600 | 785.634600, 1057.461200, 1077.797300, 1071.627100 |

Burst pediu 50 ms e observou quatro gaps de aproximadamente50–75 ms; quatro
timers foram cancelados e o último render concluiu. Spaced pediu500 ms,
observou gaps de aproximadamente786–1201 ms e cinco renders. As primeiras
quatro observações spaced já pertenciam a revisões suplantadas: preservadas
como superseded, sem finalizar a sequência. Contagem1/5 é resultado destes
runs, não requisito ou garantia. 200 ms é atraso solicitado, nunca limite de
latência. Esperas do callback spaced superam200 ms em vários passos.

### Idle depois do reset

CPU é delta user+system sobre cobertura real; total divide por8. RSS é pico
amostrado de working set em MiB. Cada run tem20 amostras raw/12 válidas no idle.

| Modo/Python | Cobertura s | CPU lógico % | CPU total % | RSS MiB |
| --- | ---: | ---: | ---: | ---: |
| single/3.14 | 2.760297 | 49.247426 | 6.155928 | 61.851562 |
| single/3.12 | 2.760797 | 54.332140 | 6.791517 | 60.382812 |
| burst/3.14 | 2.759543 | 47.562227 | 5.945278 | 61.464844 |
| burst/3.12 | 2.759768 | 45.859834 | 5.732479 | 60.355469 |
| spaced/3.14 | 2.760310 | 50.379305 | 6.297413 | 62.718750 |
| spaced/3.12 | 2.758548 | 48.145808 | 6.018226 | 60.687500 |

CPU observado45,86–54,33% de um lógico depois do reset exige diagnóstico.
Idle3 s/warmup1 s não demonstra estado estabilizado, persistência do custo,
causa, regressão de produto ou equivalência com os runs históricos R_N100.
Não somar tempo de query ao denominador idle, nem atribuir CPU a Tk/polling,
ao runtime ou a um método específico sem medir atividade separadamente.

## Etapa anterior preservada

Supervisor anterior ao refreeze; worker/probe/helper já finais. Report/eventos
foram recalculados depois, sem transformar hashes antigos em fontes finais.

| Modo/Python | Última→observação ms | Renders | CPU lógico % | Run |
| --- | ---: | ---: | ---: | --- |
| single/3.14 | 1241.069800 | 1 | 54.906699 | `run-979a61a1b50241ebb82149d60ada1947` |
| single/3.12 | 1042.566500 | 1 | 54.333471 | `run-6d5fa982777041d3ada76882dbe39dd1` |
| burst/3.14 | 1078.834300 | 1 | 44.148354 | `run-23e86f7c9dc74e58a1c0d7943e8b9452` |
| burst/3.12 | 860.392000 | 1 | 60.526714 | `run-637824a44b404cec8ce276f446be8201` |
| spaced/3.14 | 1275.056100 | 5 | 50.350002 | `run-47d0aa26b29647b484ad3e1a2baf7fb2` |
| spaced/3.12 | 1235.202100 | 5 | 42.217620 | `run-0d6fe9a562f246b0a2c55eb3b913091c` |

## Integridade, evidência e continuidade

Oito artefatos por run, retidos/ignorados pelo Git. SHA dos bytes R_N intacto,
fontes estáveis durante cada execução; manifestos finais coincidem com todas
as fontes entregues. Eventos/resumos puros recalculados e latências/oráculo
conferidos. Banco recalculou independentemente os24 resumos e CPU/RSS do raw,
sem importar helper/GUI ou executar scripts Root, sem divergência a seis casas.
Query final qa-00: FULL100/índices0..99/page0/4 páginas/25 rows;
reset vazio: FULL1000/40 páginas/25 rows, pendingfalse/timerNone. R_N só contém
strings; não representa extras tipados/Unicode ou teclado físico.

Identidades draft/baseline, igualdade tipada, stacks Undo/Redo vazios, clean,
bytes e zero starts preservados. Hooks restaurados/auditorias concluídas antes
do ready; nenhum IO/hash/model copy/publicação dentro de query/reset. Todos
exit0/errors[]/closed/trayfalse/timers[]/QA callbacks0/PID medido ausente.
Geometria lógica/bruta880×660 é amostrada nas fronteiras, sem inferência DPI.

Próximo diagnóstico: separar custo do setter/invalidação, render e atividade
idle pós-reset com fonte/carga/estado equivalentes, medir série temporal e
overhead antes de alterar polling/produção. Repetições/durações/cargas e D18
continuam propostas; aceite final requer respostas Q-PERF e artefato distribuído.
Aceite visual continua em [registro próprio](GUI_ACCEPTANCE_RESULTS.md).

Continuação: [controles e diagnóstico](PERFORMANCE_IDLE_DIAGNOSTIC.md)
registram CPU alto também sem query no idle curto e contrastes com warmup30 s.
Não alteram esta série histórica nem atribuem o custo exclusivamente à busca.

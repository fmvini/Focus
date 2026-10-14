# Controles de CPU e diagnóstico do idle

2026-10-14, base `8bdff2c`, produção/dependências inalteradas. Continuação de
[QUERY_RESULTS](PERFORMANCE_QUERY_RESULTS.md). Exploração, sem RNF01/visual.

## Controles sem profiler

G-P1000, geometria v2 confirmada, bandeja pronta, motor parado, sampler0,25 s.
Quatro runs com warmup30/idle15 s e dois sem query com warmup1/idle3 s.
Ordem: none3.14, single/reset3.14, single/reset3.12, none3.12; depois os dois
curtos none. Uma amostra por condição; sem randomização/repetições controladas.
Mesma fonte do coletor/produção e fixture R_N1000; oito artefatos/run.
CPU é user+system dividido pela cobertura real, total dividido por8; RSS em MiB.

| Modo/Python | Warmup/idle s | Raw/idle válidas | Cobertura s | CPU lógico % | CPU total % | RSS MiB | Run `.qa/performance/` |
| --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| none-314 | 30/15 | 184/60 | 14.796453 | 2.006393 | 0.250799 | 60.910156 | `run-5b7da3a2a2ec4a71972c2ce5005836b8` |
| single-314 | 30/15 | 184/59 | 14.550824 | 0.214764 | 0.026846 | 62.445312 | `run-8716167c502f4425a1545c8f410a2ada` |
| single-312 | 30/15 | 184/60 | 14.821257 | 4.427762 | 0.553470 | 61.253906 | `run-1ba2579f3d594edfa1a4062733b9be2f` |
| none-312 | 30/15 | 184/60 | 14.799473 | 0.105578 | 0.013197 | 60.644531 | `run-75d20577631047148197c3275fd9a3d4` |
| none-314 | 1/3 | 20/12 | 2.761121 | 57.721129 | 7.215141 | 60.480469 | `run-6f575af42abe4cb1a9bb80c444dca295` |
| none-312 | 1/3 | 20/12 | 2.771576 | 52.429549 | 6.553694 | 60.929688 | `run-39dfff6587704a7f9cb180731f0419ba` |

Os dois controles curtos **sem query** também observaram52–58% de um lógico.
O fenômeno não é exclusivo da busca/reset. Nos quatro longos, CPU0,106–4,428%
e direção do contraste none/single muda entre runtimes; não demonstra custo
persistente de meio núcleo, causa ou otimização necessária no debounce.
Não inferir equivalência estatística/ausência de custo a partir desses controles.

## Recortes dos dados brutos

Intervalos de5 s desde ready_ns até idle_begin_ns (preparação/publicação/warmup),
e três bins no idle. ready_ns antecede a publicação; não é marker exato do
início de warmup. Somente leituras inteiras dentro de cada bin; cobertura é
primeiro/último midpoint, fronteiras excluídas, sem interpolar ou somar bins
para reconstruir o delta completo. Valores são CPU lógico%, não tempo de render.

| Modo/Python | Ready→idle s | 0–5 | 5–10 | 10–15 | 15–20 | 20–25 | 25–30 | Idle0–5 | Idle5–10 | Idle10–15 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| none-314 | 30.081301 | 52.333803 | 14.427429 | 0.327888 | 0.983040 | 0.000000 | 12.781899 | 0.655607 | 0.655720 | 4.921000 |
| single-314 | 30.047132 | 52.333723 | 13.119419 | 0.327741 | 0.327958 | 0.655544 | 11.404005 | 0.327903 | 0.345752 | 0.000000 |
| single-312 | 30.043748 | 58.962788 | 16.392082 | 0.655389 | 13.764592 | 21.951954 | 2.294869 | 0.327372 | 0.653818 | 12.783740 |
| none-312 | 30.149231 | 57.026727 | 14.185018 | 0.327430 | 0.327872 | 12.448331 | 0.327208 | 0.000000 | 0.000000 | 0.327726 |

Nos quatro runs, os primeiros5 s após ready têm52–59%; os seguintes5 s,
13–16%; depois aparecem recortes baixos e picos posteriores. Isso localiza
variação temporal, sem provar layout estabilizado, tarefa nativa específica ou
causa. Não declarar30 s universalmente suficientes nem omitir os picos.

## Diagnóstico cProfile separado

Receita experimental local `.qa/profile_gui_idle.py`, não CLI distribuída;
fonte e hashes retidos em diagnostic_manifest.json. Instância Worker dedicada,
fixture própria, overrides apenas begin_idle/end_idle da instância; nenhuma
alteração de app/classes/timers. enable depois do marker idle, disable antes
do marker end; profiler/dump fora do caminho padrão. Exceções/markers incompletos
mantêm perfil inválido/parcial. `complete` exige report.ok/markers ordenados,
mas não exige stats: pode haver records[]/calls0/wallNone com lifecycle completo.
Para atribuir funções, exigir também registros e tempos disponíveis; os três
observados têm stats. Caminhos de falha/sem stats foram lidos, não ensaiados.

Perfil usa tempo decorrido e inclui overhead; `total_calls_wall_s` soma tempos
próprios perfilados, não representa span idle nem CPU. Não somar cumulativos
aninhados. Profilers não são benchmarks, conforme
[documentação Python](https://docs.python.org/3.14/library/profile.html).
O timer padrão usa perf_counter em
[CPython3.14.6](https://github.com/python/cpython/blob/v3.14.6/Modules/_lsprof.c).
`thread_time_ns` mede user+system da thread atual, separado do processo e do
tempo decorrido, conforme [API](https://docs.python.org/3.14/library/time.html#time.thread_time_ns).
Brackets before-enable/after-disable não são endpoints exatos do profiler.

Três execuções single/reset, Python3.14.6, artefatos próprios em
`.qa/idle-diagnostics/`; não têm samples.jsonl/summary externos nem a mesma
estrutura de oito artefatos dos controles. Não comparar quantitativamente
CPU/latência com runs sem profiler ou usar profiler para aceitar RNF01.

| Etapa | Warmup/idle s | Span trace s | Chamadas | Soma própria wall s | CPU thread s | Run |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| Antes de contador thread | 1.0/3.0 | 3.018634 | 5736 | 0.044725 | indisponível | `run-2633343e535e4d959947a900a384a5c4` |
| Fonte final | 1.0/3.0 | 3.000184 | 5722 | 0.026606 | 1.656250 | `run-26034b074eb14327ac8a2f7c93c58fdf` |
| Fonte final | 30.0/10.0 | 10.003915 | 18356 | 0.096497 | 0.687500 | `run-a77c525ab3c84bc6b08e341b61df8080` |

Fonte final da receita SHA256
`7B80D6AFFE1C6058BCB8FCB6AEB30937F68EE09833667B2B7899F864915D9ADF`.
O primeiro manifesto difere somente na receita, antes do contador thread;
todos os arquivos tools/ui/core permanecem iguais. Fonte final inclui validade,
brackets, erros, stats ausentes e delta da thread; nenhum perfil parcial foi
observado nesses três runs.

No short final, poll_status12/DPI30/appearance99/textbox45, sem render_rules,
render ou mainloop registrados na janela cProfile. Poll cumulativo0,003673 s;
CPU thread1,656250 s em span3,000184 s, soma própria0,026606 s. No long,
CPU thread0,687500 s em10,003915 s, soma própria0,096497 s.
Mainloop C já estava aberto antes de enable; atividade entre callbacks,
trabalho nativo/overhead e threads da bandeja não são atribuídos por esse
perfil. **Não subtrair wall de CPU para declarar custo de Tcl/Windows.**
A janela short localiza CPU na thread Tk neste ensaio instrumentado, sem
atribuir uma função. Escala, composição/driver, energia, atividade de fundo e
overhead não controlados; contraste short/long não é par estatístico.

Todos os controles/profiles concluíram lifecycle, dados/hashes/history/zero
starts e timers preservados. Controles confirmam saída do PID externamente;
profiles somente exit0/report closed/trayfalse, sem supervisor externo nem
prova equivalente de identidade/saída de filho. Evidências locais conservadas.
Banco recalculou independentemente tabelas dos seis controles,36 bins e três
profiles, incluindo hashes/markers/contadores, sem divergência. Revisão somente
leitura; execuções e validação de receita atribuídas ao Maestro.

## Próxima unidade

Antes de alterar polling/render, medir externamente CPU por TID nativo da
thread Tk com PID/create_time/TID/birth conferidos, cobertura e erros explícitos.
Isso localiza tempo; não atribui função. Para atribuição, desenhar amostragem de
stacks nativas/estados running-ready-wait com perímetro e overhead definidos.
WPR existe neste host; nenhum trace ETW/WPR foi iniciado. A eventual captura
deve limitar perímetro dedicado e conservar desconhecidos/amostras perdidas,
sem confundir espera com CPU ou coletar processos alheios como parte deste ensaio.
Proposta de hooks por instância permanece desenho, não implementação/aceite.
Manter produção,200/250 ms, D18 e respostas USER_ANSWERS intactos.

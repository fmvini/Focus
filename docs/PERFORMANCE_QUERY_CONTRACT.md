# Latência programática da busca — contrato exploratório

Base `9596d71`; produção permanece inalterada. Subconjunto de
[PERFORMANCE_PROTOCOL.md](PERFORMANCE_PROTOCOL.md), sem aceite RNF01/visual.

## Escopo e fases

`--query` aceita none (default), single, burst e spaced. Query só é autorizada
no perfil G-P; outros perfis recusam antes de criar run/GUI. R_N 0/100/1000,
motor parado, geometria v2 confirmada, bandeja pronta. none conserva caminho
atual sem hooks. Execução: preparação/render/perfil → query → reset vazio por
debounce real → ready → warmup → idle → fechamento. Não misturar CPU idle com
query. Orçamento cooperativo de 30 s por sequência/reset, subordinado ao
startup-timeout externo. Falha preserva parcial e impede ready/idle.

single escreve qa-00; burst/spaced escrevem q, qa, qa-, qa-0, qa-00 em callbacks
distintos, primeira escrita sem espera e demais after50/after500 desde retorno
da escrita anterior. Registrar gaps efetivos; atraso do loop pode mudar número
de renders. É alteração programática da StringVar, não teclado/foco/caret
físicos. Reset escreve vazio em outro turno e espera o debounce original.
Não usar clear/flush/update/update_idletasks/sleep como fallback.

## Eventos em memória e vínculos

`query_schema_version=1` identifica pacotes/report/ready; é independente de
`timing_schema_version=2` dos renders de preparação. `query_mode` no ready
identifica a sequência concluída antes do warmup.

Hooks reversíveis por instância em after/after_cancel/render_rules; capturar
somente after200 agendado dentro do escopo da escrita StringVar.set. Confirmar
handle/revision/ticket ao retorno; ambiguidade ou ausência invalida. Delegar
callback/cancel/render originais exatamente uma vez, sem modificar 200 ms.
Callbacks recusados por fechamento/cancelamento/ticket/consumo obsoleto não
delegam nem consultam Tk, preservando a recusa que o callback nativo faria.
Ticket pertence ao agendamento: render_rules incrementa ticket ao cancelar;
não exigir ticket constante após render. Não substituir trace_add original.
Não afirmar medida exclusiva do trace: set_call inclui setter/trace síncronos.

Escritas: seq/query/begin_ns/set_return_ns, revision/ticket/timer_id,
schedule_begin_ns/schedule_return_ns/delay_ms, callback_enter_ns/cancelled_ns.
Renders: write_seq/revision/query/ticket_original, start_ns/return_ns,
observation_ns/settled/pending/timer_id, full_indices/rows/page/page_count.
Timing de chamada exclui getters; observação after_idle inclui espera e
instrumentação e não comprova pixels. Observar revision/query/contexto final,
pending=false/timer=None. Observação antiga não encerra sequência atual.
Registrar renders intermediários sem exigir 1/5 renders por padrão.

Guardas token/fase/handle/closed antes de getters; callbacks de observação
owned e deadline absoluto. Restaurar atributos/overrides exatamente na saída
normal, erro e fechamento. Sem IO, hashing, cópia/comparação de modelo ou
publicação JSON em todo intervalo query/reset; eventos ficam em memória.

## Invariantes e responsáveis

Oráculo independente fora do timing: final qa-00 produz FULL=min(N,100),
índices originais0..FULL-1, page0, page_count=max(1,ceil(FULL/25)) e rows=min25.
Demais textos dos planos correspondem a todas as N regras; reset restaura
universoN. Bytes/config/draft/baseline/history vazio preservados, dirty/is_new
false, seleção0, motor starts0; R_N de strings não comprova extras/Unicode.

Backend: somente tools/perf_query.py/tests/test_perf_query.py, stdlib puro.
API query_plan(mode) retorna tuple de QueryStep(query, delay_ms), incluindo
reset interno; summarize_query(writes, renders, mode, rules) valida vínculos,
ordem/tipos/cancel/supersession/partial e computa intervalos/latências, com
ok/errors/insufficient, sem clock/IO/GUI ou mutar entradas. Resumo aceita
observações intermediárias superseded; sucesso exige observação final correta.
Frontend: revisão estática dos hooks/fases; Banco: revisão de oráculos/eventos.
Maestro: probe stdlib em tools/perf_query_probe.py e testes correspondentes,
integração worker/supervisor/testes/docs e ensaios nativos sequenciais.

Produção/dependências não editadas; fake/pure tests nos dois runtimes, freeze
antes do native, artefatos exclusivos/hashes/invariantes/teardown existentes
preservados. Implementação/testes/log formam um commit local conjunto.

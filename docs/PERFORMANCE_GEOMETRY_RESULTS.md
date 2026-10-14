# Geometria e timings do coletor v2

Data: 2026-10-13, America/Sao_Paulo. Base `513fdc4`, produção `79607c9`
inalterada. Fonte final congelada antes dos ensaios; cada manifesto conserva
HEAD/status e hashes dos arquivos usados, ainda sem commit durante a execução.
**Ensaios exploratórios, sem aceite visual/DPI ou RNF01.**

## Correção e validação

Renders antes do mainloop observavam 200×200 apesar do pedido 880×660.
A versão 2 espera geometria lógica CTk 880×660, janela normal/mapeada e
cliente Tk bruto positivo/estável em duas observações separadas por 50 ms.
Cada render ocorre em callback distinto e revalida antes, no retorno e na
observação posterior por after_idle. Build conserva startup observado;
H-F continua oculto/não confirmado, sem mapeamento para obter números.
T-P mede renders na preparação visível e depois oculta pelo fluxo real.

CPU/RAM externos e invariantes continuam iguais. duration_ns mede a chamada;
layout_duration_ns=None nos renders, layout_wait_ns é espera do loop até
observação, incluindo getters/instrumentação. Esse endpoint não comprova
pintura nem CPU exclusiva de layout; não comparar com update_idletasks v1.
Watchdog usa margem restante desde return+10 s e não preempta operação
síncrona. Erro de cancelamento invalida callbacks e bloqueia ready/idle,
mantendo fechamento e report inválido. Contrato e uso no
[guia](PERFORMANCE_COLLECTOR.md).

Fonte final: **82 testes aprovados/zero skips** pelo Maestro em Python
3.14.6/3,249 s e 3.12.14/3,299 s. São 28 worker, 20 métricas, 19 artefatos
e 15 supervisor, sem import/execução GUI pelos testes. Regressões novas
cobrem mapping/geometria atrasada/oscilação/cliente escalado, timeout,
resize/unmap nas fronteiras, after_idle starvation, callbacks consumidos ou
obsoletos, fechamento e warmup0; cancelamento com erro, getters/registro
consumindo prazo e arredondamento do restante. Backend/Banco reconferiram
as correções finais somente por leitura, sem achados pendentes.

SHA256 worker: `4495468BEA61704DD0612D6AAF7953C74CCB54D78742E41A47C0895B4946A67D`.
SHA256 teste: `2E0FDF1DAEA661D9F7AA8850A02AF3BF073F88EDC7B060B214C9C61DD9A16AB0`.
Todos os manifestos dos sete runs coincidem com as fontes entregues.

## Ambiente e série executada

Windows 10.0.19045 AMD64, quatro núcleos físicos/oito lógicos, Tk 8.6.15,
CustomTkinter 6.0.0, psutil 7.2.2, Pillow 12.3.0, pystray 0.19.5.
Versões/executáveis separados por supervisor/worker nos artefatos. DPI/escala
Windows, plano de energia e quotas não medidos; atividade de fundo não
controlada nem registrada por coletor global. Motor parado, gate impede start,
busca vazia/ordem Cadastro/seleção desligada, R_N sintético com demais listas
e agenda vazias. Um processo por cenário, sem GUI/benchmark/suíte nativa
concorrente; revisões estáticas dos agentes ocorreram durante parte da série.

Intervalo solicitado 0,25 s. H-F1000 e T-P100: warmup1/idle3 s. G-P100:
warmup30/idle15 s, duas execuções por runtime, intercaladas 3.14/3.12.
São ensaios curtos; não executam as cinco repetições/120 s ou sessão longa
propostas para D18. Cobertura CPU usa midpoints das leituras válidas inteiras
no idle; percentual total divide por oito. RSS é máximo amostrado em MiB,
não commit privado ou pico lifetime; bytes/MB e demais contadores ficam no raw.

| Run em `.qa/performance/` | Python | Perfil/regras | Cobertura CPU s | CPU lógico % | CPU total % | RSS máximo MiB |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `run-2c6e7ee38f5a448aa07f21ba1b8af787` | 3.14.6 | H-F/1000 | 2,758419 | 0,000000 | 0,000000 | 54,730469 |
| `run-fedd304602c6480981c8f222e9a61b3f` | 3.12.14 | H-F/1000 | 2,760136 | 1,698286 | 0,212286 | 52,308594 |
| `run-44be01b325954e22aee36012651d791c` | 3.14.6 | T-P/100 | 2,758100 | 0,000000 | 0,000000 | 59,265625 |
| `run-fa786bbcf2a54296a81384fc18ad580e` | 3.14.6 | G-P/100 | 14,797591 | 0,000000 | 0,000000 | 60,480469 |
| `run-bb666f7132b541da8c7837529e50b2de` | 3.12.14 | G-P/100 | 14,799312 | 4,962224 | 0,620278 | 61,101562 |
| `run-9cd4eebbc98a49518ad3e74c7d75fa18` | 3.14.6 | G-P/100 | 14,795022 | 0,316830 | 0,039604 | 60,988281 |
| `run-785c0d96e5964d6182ee7c2a0bcaf8f1` | 3.12.14 | G-P/100 | 14,807456 | 0,316563 | 0,039570 | 61,117188 |

Todos: ok=true, exit0, errors=[], closed=true, tray_alive=false,
after_info=[], qa_callbacks_pending=0, invariantes true/zero starts,
hashes fixture/fonte preservados e PID/create_time medido ausente após saída
do launcher. Sem cleanup forçado nesses runs. Artefatos completos em cada
diretório; logs auxiliares `.qa/geometry-*.log`. Dados brutos conservados,
ignorados pelo Git. ok valida ensaio/ferramenta, não aprova desempenho.

## Geometria observada e endpoints

G-P/T-P: gate confirmed e cliente bruto 880×660 nas três fronteiras dos dois
renders, getter lógico 880×660, state normal/mapped=true. T-P ready/idle
withdrawn/unmapped depois dos renders. H-F permaneceu withdrawn/unmapped e
200×200; gate not_required, geometry_verified/comparable false. Build de
todos observado 200×200/withdrawn/unmapped e não comparável. Valor Tk scaling
não foi convertido em escala Windows ou aceite DPI.

| Cenário | Render completo: chamada s | Espera observação s | Render regras: chamada s | Espera observação s |
| --- | ---: | ---: | ---: | ---: |
| geometry-hf1000-314 | 0,598308 | 0,008004 | 0,587329 | 0,001743 |
| geometry-hf1000-312 | 0,599708 | 0,008047 | 0,572977 | 0,002265 |
| geometry-tp100-314 | 0,823507 | 0,016833 | 0,655689 | 0,011045 |
| geometry-gp100-a-314 | 0,797936 | 0,030498 | 0,723236 | 0,008633 |
| geometry-gp100-a-312 | 0,688785 | 0,170294 | 0,597868 | 0,007241 |
| geometry-gp100-b-314 | 0,754380 | 0,016861 | 0,573832 | 0,005716 |
| geometry-gp100-b-312 | 0,768358 | 0,053988 | 0,571623 | 0,007987 |

Fronteiras confirmadas são elegíveis apenas a comparações com mesmas dimensões,
endpoints/versões/estado; não garantem estabilidade global ou apresentação de
pixels. Tempos visíveis não são custo de idle na bandeja e não são latência de
busca. Renders ocultos e build não entram em comparação com render confirmado.
[Dados da primeira implementação](PERFORMANCE_COLLECTOR_RESULTS.md) permanecem
separados, sem promover seus timings antigos à semântica v2.

## Variação CPU e continuidade

Em G-P/100, 3.14 observou 0% e 0,316830% lógico; 3.12 observou 4,962224%
e 0,316563%. A variação dentro de 3.12 supera a diferença das segundas
execuções entre runtimes. Não sustenta atribuir o pico ao runtime, ao tamanho
da janela ou somente ao startup. Zero pode refletir quantização do contador,
não custo nulo. Duas observações não são garantia estatística nem critério RNF.

Recortes auxiliares de 5 s do idle preservam cobertura própria entre leituras,
sem chamar essa taxa de CPU instantânea ou decomposição completa do idle:

| Run visível | Faixa solicitada desde idle s | Cobertura entre leituras s | CPU lógico % |
| --- | --- | ---: | ---: |
| `run-fa786bbcf2a54296a81384fc18ad580e` | 0–5 | 4,765485 | 0,000000 |
| `run-fa786bbcf2a54296a81384fc18ad580e` | 5–10 | 4,766062 | 0,000000 |
| `run-fa786bbcf2a54296a81384fc18ad580e` | 10–15 | 4,764511 | 0,000000 |
| `run-bb666f7132b541da8c7837529e50b2de` | 0–5 | 4,767044 | 0,000000 |
| `run-bb666f7132b541da8c7837529e50b2de` | 5–10 | 4,766953 | 12,783324 |
| `run-bb666f7132b541da8c7837529e50b2de` | 10–15 | 4,763927 | 2,623886 |
| `run-9cd4eebbc98a49518ad3e74c7d75fa18` | 0–5 | 4,763321 | 0,656055 |
| `run-9cd4eebbc98a49518ad3e74c7d75fa18` | 5–10 | 4,764714 | 0,327932 |
| `run-9cd4eebbc98a49518ad3e74c7d75fa18` | 10–15 | 4,764719 | 0,000000 |
| `run-785c0d96e5964d6182ee7c2a0bcaf8f1` | 0–5 | 4,765693 | 0,000000 |
| `run-785c0d96e5964d6182ee7c2a0bcaf8f1` | 5–10 | 4,767112 | 0,000000 |
| `run-785c0d96e5964d6182ee7c2a0bcaf8f1` | 10–15 | 4,771925 | 0,982308 |

As lacunas nas fronteiras entre recortes não entram nesses deltas; o resumo
original é a métrica do idle coberto inteiro. O pico variável requer perfil
diagnóstico separado, com overhead/atividade de fundo registrados, antes de
propor otimização de polling/Tk. Não houve modificação do app por esta amostra.
Próximas extensões: latência de busca e sessão longa, preservando endpoints e
raw; consolidar D18/Q-PERF-01/02 antes do aceite no artefato distribuído.
Aceite visual/DPI continua sem aprovação; esta unidade não repetiu captura
nem executou roteiro visual: [registro anterior](GUI_ACCEPTANCE_RESULTS.md).

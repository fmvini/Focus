# Coletor exploratório de GUI

Ferramenta de QA externa, conforme [contrato](PERFORMANCE_COLLECTOR_CONTRACT.md)
e [protocolo proposto](PERFORMANCE_PROTOCOL.md). Não altera a execução normal
do Focus nem aprova RNF01. Usa psutil e dependências gráficas já instaladas.

## Executar

Na raiz do projeto, executar um cenário por vez, sem outra GUI/benchmark/suíte
nativa concorrente. Os defaults curtos servem à exploração, não às cinco
repetições/120 s de idle propostas no protocolo completo.

```powershell
.\.venv\Scripts\python.exe -B -m tools.measure_gui --rules 100 --profile H-F --warmup 2 --idle 10 --interval 1
.\.venv\Scripts\python.exe -B -m tools.measure_gui --rules 100 --profile G-P --warmup 2 --idle 10 --interval 1
.\.venv\Scripts\python.exe -B -m tools.measure_gui --rules 100 --profile T-P --warmup 2 --idle 10 --interval 1
```

`--rules` aceita 0/100/1000; `--warmup` aceita zero, demais durações devem ser
positivas e finitas. `--startup-timeout` padrão 60 s; `--finish-timeout` padrão
90 s é margem adicional depois de ready/warmup/idle. `--runtime` escolhe o
intérprete do worker; por padrão usa o mesmo intérprete do supervisor.
`--output` é um pai de runs dentro de `.qa`, nunca um diretório do usuário.
Cada chamada cria um `run-<UUID>` exclusivo; não sobrescreve ensaios anteriores.

O supervisor imprime summary JSON e retorna 0 somente para run válido; erro,
timeout, identidade/fixture/fonte alterada, dados insuficientes ou teardown
incompleto retornam 1. `ok=true` significa ferramenta/ensaio válido, não
desempenho aprovado. Ao falhar, conservar o diretório indicado e seus erros.
Ctrl+C durante preparação/coleta invalida o run, preserva evidências quando
o diretório já foi registrado e retorna 130. A curta seção final de publicação
e cleanup protege SIGINT para evitar perda de raw/summary por um segundo
Ctrl+C; o handler anterior é restaurado. Fora da thread principal essa proteção
de sinal não é instalada; o uso documentado é o CLI na thread principal.
SIGINT nessa seção é descartado, não adiado: ele não marca `interrupted`
sozinho. Nas fases interrompíveis, a interrupção capturada é registrada.

## Perfis e efeitos

| Perfil | Interface | Controlador |
| --- | --- | --- |
| H-F | Raiz oculta diretamente, bandeja fake | Idle sem worker; referência exploratória |
| G-P | GUI visível em 880×660, bandeja real pronta | Controlador real parado, protegido por gate de start |
| T-P | Ocultação pelo fluxo real de bandeja | Mesmo controlador parado com gate |

O gate registra/recusa start sem delegar ao controlador. Perfis reais precisam
de Shell/desktop acessível: falha `NIM_ADD` invalida o run, sem trocar por fake.
Não interagir com o app durante a medição; alteração de vista/modelo invalida
suas invariantes. Não há enumeração ou encerramento de alvos, hosts, APPDATA,
Save ou mudança de dependências. O único encerramento forçado possível é de
worker/launcher dedicados após falha, com identidade/parent conferidos e run
invalidado; encerramento natural do PID medido é comprovado separadamente.

## Artefatos e interpretação

| Arquivo no run | Conteúdo |
| --- | --- |
| `config.json` | R_N sintético, agenda/listas extras vazias |
| `manifest.json` | Parâmetros, comando, versão/source hashes, ambiente e perímetro do supervisor |
| `ready.json` | PID/create_time, perfil pronto, versões/tempo/geometria inicial disponíveis |
| `samples.jsonl` | CPU user/system, memória em bytes, timestamps da leitura e erros por amostra |
| `report.json` | Idle, timings, ambiente do worker, invariantes e teardown |
| `summary.json` | Validade, saída do alvo, hashes finais, cobertura CPU real e estatísticas de memória |
| `stdout.log`, `stderr.log` | Saída completa do worker, inclusive falhas |

Writers usam publicação completa/exclusiva; arquivos em `.qa` não entram no
Git. Não apagar os dados brutos para conservar apenas o resumo. Manifesto
registra a versão de desenvolvimento/diff: uma fonte ainda sem commit fica
explicitamente identificada por hashes.

Somente leituras inteiras dentro do idle entram nas métricas. CPU usa os
midpoints do primeiro/último IO válido, e o resumo conserva cobertura e fração
do período. Não usa a duração solicitada como denominador. Leituras inválidas,
mistura de identidades, regressões de contadores ou dados indisponíveis ficam
explícitos; zero não substitui erro. CPU por processador lógico e por total da
máquina são colunas distintas; afinidade é metadado, quotas efetivas podem
permanecer desconhecidas.

Memória conserva bytes, MB e MiB; working set atual e pico amostrado não são
pico lifetime ou commit privado. Instrumentação/modelos de QA fazem parte do
PID medido e podem afetar seu RSS. Nenhuma coleta de USS ou subtração de overhead.

Build usa o tamanho inicial do app (1000×740); renders completo/de regras são
medidos depois de ajustar 880×660. Início, retorno, layout e instrumentação
ficam separados. `update_idletasks` não prova pintura/compositor. Comparações
precisam repetir os mesmos endpoints e condições, sem juntar build com render.
Dimensões acima são **solicitadas**, não garantia da geometria efetiva na
fronteira síncrona. Nos primeiros runs, os timings reportaram 200×200 antes
de consumir eventos do mainloop; G-P/T-P prontos reportaram 880×660. H-F
permaneceu com geometria reportada 200×200. Esses desvios impedem atribuir seus
tempos a renderização estabilizada em 880×660 ou comparar raízes ocultas com
janela visível como se fossem a mesma condição.
Query/latência de debounce, longa duração, motor real, fake running, outras
cargas/estados e executável distribuído ficam para extensões próprias.

Esta implementação conserva um subconjunto do protocolo. DPI/monitor/plano
de energia/job/quota não são inferidos a partir da geometria ou plataforma;
registrar contexto conhecido e limitações ao publicar resultados. Metadados
de versões do supervisor e worker são separados quando runtimes diferem.
No aceite final, consolidar D18/Q-PERF-01/02 antes de interpretar limites.

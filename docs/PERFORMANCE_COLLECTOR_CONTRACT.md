# Coletor exploratório — primeira implementação

Base: `6aa53c6`, produção funcional `79607c9`. Unidade de ferramenta de QA,
sem alteração do app, dependências ou critérios RNF01. Referência:
[PERFORMANCE_PROTOCOL.md](PERFORMANCE_PROTOCOL.md).

## Perímetro desta versão

Supervisor externo `python -B -m tools.measure_gui`: uma carga por execução,
R_N com 0/100/1000 executáveis sintéticos; diretório UUID exclusivo sob `.qa`.
Perfis H-F (raiz oculta/bandeja fake/controlador idle sem worker), G-P
(janela visível e bandeja real pronta, motor parado) e T-P (ocultação pelo
fluxo real de bandeja, motor parado). Nenhum início de bloqueador, leitura de
processos do usuário, hosts, configuração APPDATA ou efeitos em alvos.

Warmup/idle/intervalo configuráveis e registrados. Defaults exploratórios
curtos, sem representar a matriz/repetições propostas para aceite. Não inclui
query, seleção ativa, motor real, distribuição, longa duração ou aceite visual.
Construção/render completo/render de regras têm endpoints separados;
`update_idletasks` é somente layout, sem prova de pixels apresentados.

## Divisão e interfaces congeláveis

- Backend: `tools/perf_metrics.py`, `tests/test_perf_metrics.py`.
  `ProcessSampler(pid, create_time).read()` retorna dict bruto com `ok`,
  `pid`, `create_time`, `read_start_ns`, `read_end_ns`, `mono_ns`,
  `user_s`, `system_s`, `rss_bytes`, `peak_wset_bytes`, `private_bytes`,
  `vms_bytes`; contadores indisponíveis são None. Identidade é revalidada
  antes/depois; erro gera registro `ok=False` com motivo, sem zeros falsos.
  `summarize(samples, begin_ns, end_ns, logical_cpus)` considera leituras
  inteiramente dentro de idle, publica cobertura real, deltas CPU, ambos
  percentuais, RAM absoluta/MB/MiB, pico amostrado separado do lifetime,
  erros e insuficiência explícitos. Nenhum resultado de aceite RNF01.
- Banco: `tools/perf_artifacts.py`, `tests/test_perf_artifacts.py`.
  `create_run(workspace, out_parent=None)` cria pasta exclusiva `run-<UUID>`
  sob `.qa/performance` (ou pai dentro de `.qa` explicitado). Verificar
  resolução, links/junctions e containment antes da escrita.
  `make_fixture(run_dir, rules)` retorna config.json R_N validável.
  `write_json(path, data)` e `write_jsonl(path, records)` usam criação
  exclusiva UTF-8; `file_sha256(path)` calcula bytes reais. Sem overwrite.
- Frontend: `tools/perf_gui_worker.py`, `tests/test_perf_gui_worker.py`.
  CLI interna `--run-dir --rules --profile --warmup --idle`.
  Carrega config.json real; controlador nunca inicia worker/bloqueador.
  Produz ready.json após build, com `pid`/`create_time`; report.json ao fim,
  com `ok`, `profile`, `idle_begin_ns`/`idle_end_ns`, `timings`, `invariants`,
  `errors`, `closed`, `tray_alive`, `after_info`, dados de geometria/Tk e
  identidade. Fronteiras monotônicas; eventos/diagnósticos fora de idle.
  Mainloop normal durante idle; sem sleep/join na thread Tk. Bandeja real
  precisa ready; falha/timeout invalida perfil, sem fallback silencioso.
  Stop/destroy pelo lifecycle do app; wait de bandeja apenas após mainloop.
- Maestro: `tools/__init__.py`, `tools/measure_gui.py`,
  `tests/test_measure_gui.py`, integração/documentação/commit conjunto.

Supervisor aguarda ready, amostra somente PID/create_time do worker e
conserva manifest inicial, samples.jsonl, report.json, summary.json,
stdout/stderr e falhas. Fonte/hash/diff, intérprete/versões, parâmetros,
perímetro e metadados desconhecidos ficam explícitos. Só resume após worker
encerrado; não mistura startup/ações/teardown com idle. Cleanup forçado de
processo dedicado é registrado como falha, nunca sucesso.

## Validação e continuidade

Agentes não rodam GUI/native/benchmark em paralelo. Testes de suas interfaces
usam entradas/contadores/subprocessos simulados; Maestro roda smoke real e
ensaios curtos após freeze. Preservar bytes/modelo/baseline/history, universo
N/projeção25, zero starts e ausência de erros/timers ao terminar.
Esta versão implementa um subconjunto exploratório, sem declarar o protocolo
inteiro executado ou redefinir D18. Testes, ferramenta e log no mesmo commit.

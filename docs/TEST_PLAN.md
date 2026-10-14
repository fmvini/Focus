# Plano de validação

Fonte: [escopo](Focus%20Blocker_%20escopo%20do%20projeto.md), [requisitos](REQUIREMENTS.md) e [decisões](DECISIONS.md). Fases 1/2: 206 testes OK em Python 3.14.6/psutil 7.2.2 por `.venv/Scripts/python.exe -B -m unittest discover -s tests` (10,542 s). Sintaxe 3.12 dos 18 arquivos Python conferida; runtime 3.12 ainda não executado. Encerramentos reais e fases posteriores continuam pendentes.

## Busca programática e reset real — 2026-10-14

- [Contrato](PERFORMANCE_QUERY_CONTRACT.md) e [resultados](PERFORMANCE_QUERY_RESULTS.md).
  Query G-P single/burst/spaced, eventos vinculados à revisão/ticket original,
  observação after_idle e reset vazio pelo debounce original antes de ready/idle.
- Maestro: **113 testes aprovados/zero skips** em Python3.14.6/3,778 s e
  3.12.14/3,943 s: 28 worker/20 métricas/19 artefatos/19 supervisor/20 query
  puros/7 probe e integração. Nenhuma GUI importada/executada pelos doubles.
  Regressões: cancel/stale/consumed, ambiguidade/restauro, swallowed Tk error,
  prazo após instrumentação, ready modo/schema e prova completa/recalculada.
- Doze runs G-P1000 sequenciais, seis na fonte final e seis anteriores à
  correção do supervisor. Worker/probe/helper iguais; anteriores diferem somente
  no supervisor. Todos query/reset/invariantes/hashes/teardown/PID ausente OK.
  Warmup1/idle3/interval0,25; últimas latências0,82–1,24 s e CPU idle45,86–54,33%
  lógico na série final. Não demonstram causa, estado estabilizado ou RNF01.
- Frontend/Banco/Backend revisaram fontes finais somente por leitura; suites
  e native atribuídos ao Maestro. Produção/dependências intactas; suíte completa
  do produto não repetida (última842/841/um skip em ambos runtimes).
- Nova sessão visual isolada: duas capturas timeout e encerramento normal
  por prazo; diagnóstico start200×200. Sem imagem, interação física ou aceite
  visual/DPI. Registro em [GUI_ACCEPTANCE_RESULTS.md](GUI_ACCEPTANCE_RESULTS.md).

## Geometria e timings v2 do coletor — 2026-10-13

- Worker mede renders em callbacks distintos do mainloop; gate de duas
  observações CTk lógico880×660/cliente bruto estável, revalidação nas fronteiras,
  after_idle com espera separada e deadline monotônico/watchdog restante.
  Build e H-F não promovidos a geometria confirmada. T-P renderiza antes de ocultar.
- **82 testes/82 aprovados/zero skips**, Maestro na fonte final: Python
  3.14.6/3,249 s e 3.12.14/3,299 s. 28 worker, 20 métricas, 19 artefatos,
  15 supervisor. Novos fake cobrem atraso/instabilidade/timeout/escala raw,
  resize/unmap, starvation/fechamento, stale/consumed callbacks e cancelamento
  com erro impedindo ready/idle; getter/registro lento e margem restante.
- Sete ensaios sequenciais reais em [RESULTS](PERFORMANCE_GEOMETRY_RESULTS.md):
  H-F1000 nos dois runtimes, T-P100 em 3.14 e dois G-P100 por runtime com
  warmup30/idle15 s. Todos válidos, hashes/invariantes/zero starts preservados,
  closed/tray/timers/callbacks corretos e PID medido ausente. G-P/T-P tiveram
  cliente880×660/mapped nas três fronteiras; H-F/build200×200 não comparáveis.
- Backend/Banco revisões finais somente leitura sem achados P2 pendentes;
  root verificou artefatos/hashes/endpoints. CPU varia dentro do mesmo runtime;
  não conclui causa/RNF01. Produto/dependências intactos, suíte completa não
  repetida (última842/841/um skip nos dois runtimes). Nenhuma captura nova ou
  aprovação visual/DPI/teclado/leitor de tela nesta unidade.

## Coletor exploratório e nova tentativa visual — 2026-10-13

- [Contrato](PERFORMANCE_COLLECTOR_CONTRACT.md), [CLI](PERFORMANCE_COLLECTOR.md)
  e [resultados](PERFORMANCE_COLLECTOR_RESULTS.md): supervisor externo, métricas,
  artefatos exclusivos e worker lazy, sem mudança na produção/dependências.
- Fonte final: **65 testes aprovados, zero skips** em Python 3.14.6/2,336 s e
  3.12.14/2,215 s. São 20 métricas, 19 artefatos, 11 worker e 15 supervisor;
  doubles sem import/execução GUI. Cobrem identidade/corridas, contadores e
  cobertura idle, tipos/bytes/guardas/publicação, lifecycle fake, falhas de
  preparação/metadados/stat, Ctrl+C, retenção SIGINT e prova separada de saída.
- Onze ensaios reais preservados por estágio de fonte, incluindo H-F 0/100/1000,
  G-P100 e T-P100. Três na fonte final: G-P100 com 30 s de warmup/10 s idle nos
  dois runtimes e T-P100 em 3.12 com 0,5/3 s. Todos válidos, invariantes/hash
  preservados; fontes finais provaram ausência do PID medido/timers/bandeja.
  Não são onze repetições equivalentes nem aceite RNF01. Geometria síncrona
  200×200 e variação CPU visível impedem alegar estabilização/comparação estrita.
- Nova tentativa visual teve duas capturas com timeout. Probe isolado encerrou
  pelo lifecycle com descarte automático de QA, destino ausente preservado;
  não comprova interação física, retorno da bandeja ou casos visuais/DPI.
- Backend/Banco revisões estáticas finais sem P2/P3 pendentes; suites/ensaios
  integrados atribuídos ao Maestro. Suíte completa do produto não repetida:
  produção permanece `79607c9`, última evidência 842/841/um skip nos dois runtimes.

## Preparação de aceite visual e desempenho — 2026-10-13

- [GUI_ACCEPTANCE.md](GUI_ACCEPTANCE.md) define 13 casos, critérios de cortes/foco/contraste/alcance, oito ambientes reais/simulados e fixtures ausente/vazio/25/26/60/1000. Matriz visual ainda sem aprovação; simulação CTk não equivale a escala Windows.
- Receita de cinco JSONs validada em Python 3.14.6 e 3.12.14, sem abrir GUI: parser/manifesto SHA256, Unicode/espaços/tipos, duplicatas, dias `(6,0)` e destino ausente preservados. Nome inválido, reutilização e destino fora de QA recusados sem escrita/sobrescrita. Execução integral do pipe PowerShell não ensaiada; fonte extraída da receita executada em cada runtime.
- [GUI_ACCEPTANCE_RESULTS.md](GUI_ACCEPTANCE_RESULTS.md) registra uma janela real de primeiro uso com controlador sem bloqueador, 880×660 e arquivo ausente. Duas capturas falharam por timeout; UIA retornou principalmente painéis/imagens, sem confirmar foco útil. Clique sem geometria e tentativa de fechamento não completaram o fluxo; cleanup externo somente dos processos do probe, sem prova de teardown normal. Nenhum caso visual/DPI foi aprovado.
- [PERFORMANCE_PROTOCOL.md](PERFORMANCE_PROTOCOL.md) mantém cargas/estados/repetições como proposta, diferencia denominadores CPU e contadores RAM, endpoints de build/render/query e dados brutos. Na unidade documental original, coletor ainda não implementado e nenhum benchmark novo; a implementação posterior está registrada acima, sem aceite RNF01. Q-PERF-01/02 em USER_ANSWERS detalham D18 para aceite final.
- Produção/testes existentes não alterados nesta unidade; não se repetiu a suíte completa. Última evidência funcional permanece 842 testes/841 aprovados/um skip nos dois runtimes sobre `79607c9`.

## Evidência da busca com reconstrução diferida — 2026-10-13

Contrato em [RULE_SEARCH_DEBOUNCE_CONTRACT.md](RULE_SEARCH_DEBOUNCE_CONTRACT.md).

- Cinco fake/dois native novos cobrem rajada com uma reconstrução, tokens e callbacks antigos antes de Tk, seleção FULL invalidada imediatamente, modelo atual lido uma vez sem IO, JSON tipado/history/baseline/bytes, clear/review/ordem/categoria/modelo sem projeção duplicada, modal/retry/picker/prompts/saída cancelada e cancelamento owned no teardown.
- Frontend confirmou equivalência AST dos 121 fake/48 native legados normalizando somente o helper de consulta com flush, com oráculos preservados. Backend, Frontend e Banco revisaram a fonte congelada somente por leitura, sem achados funcionais; não executaram suítes nesta revisão.
- Primeiro run Maestro no sandbox, Python 3.14.6: 842 descobertos, 840 aprovados, uma falha `NIM_ADD` do ícone real e um skip conhecido, 191,815 s. Os 14 testes de bandeja passaram fora do sandbox em 0,343 s, sem alterar fonte ou suprimir erro.
- Suítes completas finais Maestro no desktop Windows AMD64: **842 descobertos, 841 aprovados e um skip conhecido** symlink/WinError 1314 em ambos runtimes, Python 3.14.6/172,998 s e Python 3.12.14/200,123 s. Cinquenta nativeGUI e ícone real aprovados; implementação/testes permaneceram congelados.
- AST 3.12/UTF-8 dos 76 arquivos e links locais conferidos. Nenhum benchmark ou captura novo; janelas ocultas não concluem aceite visual/DPI/RNF01. Os testes usam arquivos isolados e controladores simulados.

## Evidência da paginação visual — 2026-10-13

- Helper frozen: 14 novos/14 view existentes aprovados nos dois runtimes, 0,439 s/0,889 s. Limites 0/25/26/50/51/1000, offsets/clamp/lookup/duplicatas/reconstrução/tipos/frozen/source/pureza/lazy.
- Banco quatro integrações com JSON/sessão/helpers reais aprovadas nos dois runtimes, 0,954 s/0,843 s. Seleção de índices entre páginas e AllFULL não fica limitada ao slice visual, uma edição Undo/Redo, ordem/tipos/extras/baseline/bytes/Save/conflito/importreload preservados.
- GUI final: seis fake/três native novos verificam universo completo/projeção25, seleção crosspage e remoção offpage/AllFULL, índices originais/duplicatas, epochs e callbacks antigos, prompt/reentrância, revisão distante e filtro incluinte preservado, layout/ownedscroll/bgerrors. Quick9 nos dois runtimes 19,722 s/20,621 s; compatibilidade140 15,851 s/15,826 s. Após ajuste somente de hint, um fake final nos dois runtimes 0,032 s. Backend/Banco revisão estática final sem achados pendentes.
- Suíte completa final Maestro: **835 descobertos, 834 aprovados e um skip conhecido** symlink/WinError 1314 nos dois runtimes Windows AMD64: Python 3.14.6/265,365 s e Python 3.12.14/285,585 s. Quarenta e oito nativeGUI, ícone real e guardas passaram. AST 3.12/UTF-8 nos 76 arquivos, links e diff conferidos.
- Medição única 1000, sem QA concorrente: modelo/universo1000, 40 páginas/25 widgets, bytes/dirty/controlador preservados; construção2,089 s e RSS idle66,773 MiB. Render usou render_rules, baseline render completo: não comparar estritamente esses tempos. Protocolo/limites em [GUI_PERFORMANCE.md](GUI_PERFORMANCE.md), comportamento em [RULE_PAGINATION_CONTRACT.md](RULE_PAGINATION_CONTRACT.md). HiddenRoot/amostra única não constituem aceite visual/DPI ou RNF01.

## Evidência da atualização condicional de widgets — 2026-10-13

- Três fake/dois native novos cobrem três polls estáveis sem configure em todos os widgets após sync, agenda/runtime/mailbox avaliados três vezes, mudanças reais de texto/estado, histórico/revisão/modal/picker/selecting/confirming, runtime/error/aliveclosing e toolbar de seleção ativa. Preservam identidade/modelo/history/baseline/bytes/geração/seleção/timer; CTk real verifica cget/teardown sem bgerrors.
- Frontend final: 133 GUI/mainfake e somente dois novos native aprovados nos dois runtimes, Python 3.14.6/11,943 s e Python 3.12.14/11,870 s, zero skips. Backend/Banco estáticos sem achados; Backend normalizou setters novos/removendo helper e confirmou restante AST idêntico ao HEAD anterior.
- Medição comparativa com fontes congeladas concluída, sem suites concorrentes: idle 0/100 de 7,49%/8,11% para 0,937%/0,312% de um núcleo; RSS próximo. Uma amostra/quantização, sem garantia estatística/RNF01; 1000 não repetido. Metodologia/dados/limites em [GUI_PERFORMANCE.md](GUI_PERFORMANCE.md).
- Suíte completa final Maestro: **808 descobertos, 807 aprovados e um skip conhecido** symlink/WinError 1314 nos dois runtimes Windows AMD64: Python 3.14.6/199,132 s e Python 3.12.14/229,239 s. Quarenta e cinco nativeGUI, ícone real e guardas passaram. AST 3.12/UTF-8 nos 73 arquivos, links e diff conferidos.

## Evidência da integridade das ações individuais — 2026-10-13

- Sete fake/três native novos verificam contextos capturados no render, snapshots compartilhados, identidade/modelo tipado/vista/geração, callbacks antigos após render/import/reload/history, Apply antes de getter Tk e recarga guardada sem IO. Remoção confere contexto antes/depois do prompt; cancelamento/reentrância/erro liberam a flag sem alterar dados. Dois casos verificam Editar/Cancelar e Remover individual com um Undo durante seleção em lote.
- Fontes finais após correção de closure ACTION/BULK: Frontend dez aprovados nos dois runtimes, 25,351 s/26,713 s; Banco dez, 24,686 s/23,771 s; Backend quatro essenciais, 5,048 s/5,623 s. Revisões finais sem achados. Maestro dez novos, 18,754 s/17,718 s.
- Primeira suíte completa encontrou dois erros de fixtures legadas que chamavam edit_rule durante picker ativo, agora recusado. Simulações ajustadas para confirmar a recusa e construir modal substituto externo diretamente; dois testes aprovados nos dois runtimes, 2,556 s/2,600 s. Produção não alterada nesse ajuste.
- Suíte completa final Maestro: **803 descobertos, 802 aprovados e um skip conhecido** symlink/WinError 1314 nos dois runtimes Windows AMD64: Python 3.14.6/225,621 s e Python 3.12.14/262,128 s. Quarenta e três nativeGUI, ícone real e guardas passaram. AST 3.12/UTF-8 nos 73 arquivos, links dos 27 documentos e diff conferidos.
- Raízes ocultas/controlador-tray fake/fixtures isoladas; não comprovam visual/DPI/foco físico/acessibilidade. Nenhum processo/hosts/configuração do usuário afetado.

## Evidência da remoção em lote — 2026-10-12

- Quinze novos core testam quatro listas/posições/duplicatas, one-shot/falha tardia/causa/interrupção, tipos/faixa/campo, vazio sem serializer/revalidação preservando redo, atomicidade/uma edição, source/typedextras/pureza/import lazy. Com 35 regressões, 50 aprovados nos dois runtimes, 0,880 s/1,270 s. Quatro integrações com JSON/helper/sessão reais cobrem sort/filter/dup/Save/UndoRedo/conflict/import/reload; 0,217 s/0,197 s.
- Oito fake/três native novos verificam modo/view/reset/contexto/oldcallbacks, offviewport, contador sem render, cancel/reentrância/14 mudanças durante prompt, uma operação/uma edição, noIO/bytes/conflito/guardas/teardown. Regressão de polling confere zero configure redundante e mudança disabled/enabled uma vez. Erro de teste `invoke` inexistente foi corrigido para `toggle`; nenhuma exceção suprimida.
- Fonte final: Frontend 124 GUI/main/três native nos dois runtimes, 119,048 s/116,961 s; Backend revisão sem achados, 13 em 3.14/112,058 s e nova regressão polling em 3.12/0,041 s; Banco 11 nos dois runtimes, 112,393 s/111,544 s, sem achados. Seleções anteriores não equivalem ao último ajuste.
- Suíte completa final Maestro: **793 descobertos, 792 aprovados e um skip conhecido** symlink/WinError 1314 nos dois runtimes Windows AMD64: Python 3.14.6/213,791 s e Python 3.12.14/231,287 s. Quarenta nativeGUI, ícone real e guardas passaram. AST 3.12/UTF-8 nos 73 arquivos e links/diff conferidos. Sem efeitos em processos/hosts/configuração do usuário; widgets ocultos não comprovam visual/DPI/acessibilidade.

## Evidência da busca pelo teclado — 2026-10-12

- Quatro fake/três native novos verificam quatro categorias/query/ordem, APIs públicas de foco/seleção, ausência de timer/render ao focar, limpeza única por trace/empty no-op, índices originais/duplicatas/CRUD, histórico/redo/baseline/bytes/revisão/motor preservados, guards antes de Tk e Escape separado do formulário.
- Uma asserção legada do rótulo anterior falhou nas execuções inicialmente importadas. Foi ajustada ao texto aprovado, sem alterar produção/nativos. Frontend: 113 GUI/main finais aprovados em 3.14/6,567 s e 3.12/6,512 s; 37 nativos das fontes inalteradas também aprovados. Backend/Banco revisaram sem achados e aprovaram 25/25 e 54/54 nos dois runtimes.
- Suíte completa final Maestro: **763 descobertos, 762 aprovados e um skip conhecido** symlink/WinError 1314 nos dois runtimes Windows AMD64: Python 3.14.6/173,387 s e Python 3.12.14/200,022 s. Trinta e sete nativeGUI, ícone real e guardas passaram. AST 3.12/UTF-8 nos 71 arquivos e links/diff conferidos. Sem efeitos em processos/hosts/configuração do usuário; widgets ocultos não comprovam visual/DPI/foco físico/acessibilidade.

## Evidência dos atalhos de dias e edição fiel — 2026-10-12

- Seis fakeGUI/três nativeGUI novos cobrem presets locais, cancelamento/Escape, novo/desativado, Apply inválido e retry, dias retidos/novos/remoção/toggle, no-op em `(6, 0)` preservando redo/dirty/extras tipados, única edição Undo/Redo, horário editado e conflito externo, callbacks antigos recusados antes de Tk/finish_edit, teardown sem bgerrors.
- Frontend congelou fontes e confirmou 143 GUI/main/native em 3.14/117,879 s. Agentes atingiram cota antes dos relatórios finais; não atribuir QA/revisão incompleta a eles.
- Suíte completa Maestro: **756 descobertos, 755 aprovados e um skip conhecido** symlink/WinError 1314 nos dois runtimes Windows AMD64: Python 3.14.6/227,984 s e Python 3.12.14/240,553 s. Trinta e quatro nativeGUI, ícone real e guardas passaram. AST 3.12/UTF-8 nos 71 arquivos e diff conferidos. Sem encerramento de processos do usuário/hosts; widgets ocultos não aceitam visual/DPI/acessibilidade.

## Evidência da ordenação visual das regras — 2026-10-12

- Helper: 14 testes aprovados nos dois runtimes, 0,222 s/0,639 s; quatro integrações de sessão/JSON reais, 0,182 s/0,141 s. Verificam índices originais, empates/duplicatas/casefold, cmdline/pastas literais, tipos/ordens/filtro/imutabilidade/pureza/lazy, CRUD por índice retornado, Undo/Redo, Save com cadastro original, import/reload e conflitos externos.
- Cinco fakeGUI/três nativeGUI novos verificam ordens/categorias/busca, CRUD da segunda duplicata, preferência da sessão, noIO/dados/history/motor, navegação mantendo ordem, guards, canvas real/row-owned scroll cancelado e layout do controle ao lado da busca. Frontend: 134 GUI/main/native nos dois runtimes, 87,015 s/86,196 s, zero skips; 31 nativeGUI.
- Suíte completa: **747 descobertos, 746 aprovados e um skip conhecido** symlink/WinError 1314 nos dois runtimes Windows AMD64: Python 3.14.6/147,755 s e Python 3.12.14/167,510 s. Trinta e um nativeGUI, ícone real e guardas passaram. Fontes congeladas; AST 3.12/UTF-8 nos 71 arquivos e links/diff conferidos. Nenhum processo/hosts/configuração do usuário afetado; visual/DPI/acessibilidade permanece pendente.

## Evidência da navegação da revisão — 2026-10-12

- Dez novos testes helper verificam prefixo antes do filtro, ordinais/índices originais, cinco categorias, múltiplos apontamentos do mesmo item, metadata inválida, candidato fora de faixa, tipos/limites/frozen/pureza/lazy. Com nove reviewer, 19 aprovados nos dois runtimes em 0,645 s/1,298 s.
- Sete fakeGUI/quatro nativeGUI novos verificam seleção explícita, filtros/duplicatas/mapa original/CRUD, escolhas antigas com mesmo label/quantidade/índice, import/reload/history, guardas/noIO/no mudança de dados, scroll real até item25 e cancelamento antes de rerender/destroy/saída. Frontend: 126 GUI/main/native aprovados em 61,771 s/62,241 s, zero skips; vinte e oito nativeGUI.
- Suíte completa: **721 descobertos, 720 aprovados e um skip conhecido** symlink/WinError 1314 em ambos runtimes Windows AMD64. Python 3.14.6: 128,213 s; Python 3.12.14: 152,385 s. Vinte e oito nativeGUI, ícone real e guardas passaram. AST 3.12/UTF-8 nos 68 arquivos e links/diff conferidos.
- Backend revisou fonte congelada sem achados e passou os 30 helper/reviewer/navfake/navnative nos dois runtimes (10,425 s/27,063 s). Uma única reconstrução da lista por navegação é assertada nos testes fake/nativos.
- Uso do canvas interno CTk 6.0.0 está isolado no adaptador e deve ser revalidado em upgrade; fallback orienta rolagem manual. Nenhum processo/hosts/configuração do usuário afetado. Widgets ocultos não comprovam visual/DPI/acessibilidade.

## Evidência da comparação de alterações — 2026-10-12

- Suíte completa `-B -m unittest discover -s tests`: **700 descobertos, 699 aprovados e um skip conhecido** symlink/WinError 1314 em ambos runtimes Windows AMD64. Python 3.14.6: 172,667 s; Python 3.12.14: 186,035 s. Vinte e quatro nativeGUI, ícone real e guardas passaram, sem supressão de falhas. AST 3.12/UTF-8 nos 66 arquivos e links locais/diff conferidos.
- 64 testes novos: 32 diff (tipos/dados exatos, offsets/opcodes, bordas/duplicatas/no-op, 992 reconstruções nos dois sentidos, frozen/defensive/pureza/lazy), 18 presenter (índices humanos, criação vazia/0 itens, extras privados, controles/espaços/literais, limites/truncamento/excedentes), sete fakeGUI/quatro nativeGUI (modal readonly/resizable/scroll, captura/baseline, próximos previews/history/save/import/reload, novo arquivo, guardas/conflito/saída/after/bgerrors) e três CLI (sem read/save extra, conflito externo e história/baseline em subprocesso).
- Revisão Banco GUI/CLI sem achados: 113 testes relevantes aprovados nos dois runtimes (11,077 s/15,314 s). Frontend selecionou 115 GUI/main/native, todos aprovados em 131,989 s/132,484 s. Maestro CLI/presenter/núcleo: 85 aprovados em 4,021 s. Fontes permaneceram congeladas durante integração.
- Benchmark puro Backend: sete amostras, inputs pré-alocados, troca central em 2000 regras uniformes. Antes 1480,65 ms; após preservar bordas iguais, mediana 0,664 ms em 3.14.6 e 0,403 ms em 3.12.14. Não mede renderTk/RSS nem garante limite de tempo; miolo residual repetitivo ainda pode custar quadraticamente. Nenhum fallback aproximado.
- Nenhum processo/hosts/configuração do usuário afetado; fixtures UUID próprias. Widgets ocultos/seletores fake não substituem visual/DPI/acessibilidade/interação do seletor nativo.

## Evidência das correções do editor e runtime 3.12 — 2026-10-11

- Suíte integrada em ambos runtimes: **636 descobertos, 635 aprovados e um skip conhecido** symlink/WinError 1314. Python 3.14.6: 79,903 s; Python 3.12.14: 103,041 s, Windows AMD64. Vinte nativeGUI/ícone real/guardas passaram. Carregamento explícito dos `test_*.py` com exceção apenas de `test_config_diff.py`, ainda em implementação; todas as unidades já integradas foram executadas.
- Quinze novos testes comparison/history/session cobrem tipos JSON aninhados, dict reorder, listas ordenadas, no-op/branch, Undo/Redo, baseline/import/save/conflito/falha/retry e comparação sem IO/serialização/revalidação ambiental. Dez novos GUI (seis fake/quatro nativos) cobrem tipo importado/dirty/prompt/save, pasta com retorno após fechar/substituir modal/root, falha/retry e ready durante/depois de todos os seletores.
- Fixture nativeGUI inicializa CTk por `update` antes de agendar destruição, mantendo asserts de bgerrors/after. Duas falhas intermitentes anteriores foram repetidas três vezes cada e passaram; as suítes integradas passaram sem suprimir erro ou adicionar skip.
- Python 3.12.14 foi provisionado dentro de `.qa/`, sem alterar registro/PATH, conforme [documentação do uv](https://docs.astral.sh/uv/concepts/python-versions/). As dependências vêm do mesmo `requirements.txt`; `.venv` continua em 3.14.6. Reprodução no PowerShell, a partir da raiz:

```powershell
uv python install 3.12.14 --install-dir .qa\python --cache-dir .qa\cache --no-bin --no-registry --no-config
uv venv .qa\venv312 --python .qa\python\cpython-3.12.14-windows-x86_64-none\python.exe --no-python-downloads --no-project --no-config --cache-dir .qa\cache
uv pip install --python .qa\venv312\Scripts\python.exe -r requirements.txt --cache-dir .qa\cache --link-mode copy --no-config
.qa\venv312\Scripts\python.exe -B -m unittest discover -s tests
```

- Nenhum processo/hosts/configuração do usuário alterado. QA usa fixtures UUID próprias e controladores/adaptadores fake, salvo smoke isolado do ícone/mutexes. Runtime 3.12 comprovado para esses testes; interação visual/DPI permanece pendente.

## Evidência da revisão pela CLI — 2026-10-11

- Oito testes novos verificam `--review` somente leitura, contagens/índices humanos, apontamentos informativos com retorno 0, JSON inválido/ausente sem recuperação, modos incompatíveis antes de IO/import, caminho padrão/callback, interrupção e import lazy em subprocesso sem GUI/psutil/controller. Saída cp1252 com caminho Unicode retorna erro explícito 1, preservando JSON UTF-8. Seleção relevante de 79 testes passou em 3,122 s; revisão independente Backend concluída e achado de encoding corrigido.
- Suíte completa: 610 descobertos, 608 aprovados, um skip conhecido e um erro no smoke nativo de fechamento em 64,432 s. O erro CTk/mainloop já foi reproduzido na revisão Frontend e não envolve dispatch/reviewer CLI; correção e nova validação completa serão registradas no lote de seletores. Nenhum erro foi suprimido ou convertido em skip.
- Arquivos/configuração/processos/hosts do usuário intactos; runtime 3.12 e visual/DPI permanecem pendentes.

## Evidência do histórico de edição — 2026-10-11

- Suíte completa escalada: **603 descobertos, 602 aprovados, um skip** symlink/WinError 1314, 47,046 s. Dezesseis nativeGUI e ícone real passaram; AST 3.12/UTF-8 nos 58 arquivos e links/diff conferidos.
- Nove testes history verificam restauração de CRUD/lotes/sugestões, limite de 50, branching/no-op/inválidos, cópias defensivas, revalidação de variável de pasta/restauração falha atômica, save/dirty/baseline/import/reload e pureza. Cinco GUI e nativeGUI em 880×660 verificam botões/atalhos/foco, seletor/modal/saída, erro e atualizações da revisão.
- Integração CLI real em subprocesso usa menu 6/7 com JSON isolado: sair após restaurar não grava; Save aplica versão escolhida; Reload limpa histórico. Não há persistência do histórico, threads ou efeitos em processos/hosts. Runtime 3.12 e visual/DPI pendentes.

## Evidência da revisão do rascunho — 2026-10-11

- Suíte completa escalada: **587 descobertos, 586 aprovados e um skip** symlink/WinError 1314, 42,744 s. Quinze nativeGUI e ícone real passaram; AST 3.12/UTF-8 nos 57 arquivos e links/diff conferidos.
- Nove testes reviewer: índices/ordem original, duplicatas casefold das quatro listas/horários com dias reordenados, pares literais sem trim/alias de pasta presumido, proteções obrigatórias/adicionais, Java por nome, contagens cadastradas, invalid input, frozen/pureza/import lazy e catálogo idêntico ao motor.
- Dois fluxos GUI e nativeGUI readonly/scroll em 880×660 verificam atualização do rascunho sem IO, limites de detalhes/lista longa e ausência de bloqueio de Save/Iniciar por apontamentos. Regressões de motor/adapter e dispatch/lazy passaram. Não consulta processos ou instalações; runtime 3.12 e visual/DPI permanecem pendentes.

## Evidência do fim da agenda — 2026-10-11

- Suíte completa fora do sandbox: **575 descobertos, 574 aprovados, um skip** de symlink/WinError 1314, 41,137 s. Quatorze nativeGUI e ícone real passaram em Python 3.14.6/Windows; AST 3.12/UTF-8 nos 54 arquivos conferidos.
- Oito testes em `test_schedule_end` verificam limite exclusivo/subminuto, noites, união/adjacência/gap de um minuto, domingo/segunda com união de mais de 24h, virada anual/bissexto, cobertura contínua, generator one-shot e rejeição de timezone. Referência independente por minuto: 12 cenários fixos/aleatórios determinísticos, amostras em toda a semana.
- Dois fluxos GUI e nativeGUI em 880×660 verificam baseline versus rascunho/save, agenda inativa/contínua/nova, noite e motor parado. Nenhum encerramento real; retorno é previsão da agenda carregada. Runtime 3.12 e visual/DPI pendentes.

## Evidência da seleção de executáveis — 2026-10-11

- Suíte completa escalada no desktop Windows: **564 descobertos, 563 aprovados e um skip** symlink/WinError 1314, 39,227 s, Python 3.14.6. Treze nativeGUI e ícone real passaram.
- `tests/test_executable_selection.py`: sete testes de lote/ordem, extras/regras/duplicatas preservados, dedup casefold entre pastas, proteção independente, inválidos e campos/tipos rejeitados atomicamente, iterable one-shot/falha com causa e ausência de IO/resolução/execução.
- Cinco fluxos novos em `tests/test_config_gui.py`: multisseleção só draft até Save, cancelamento sem alteração de feedback, categorias suportadas/duplicatas, lote inválido/erro de diálogo, modal/reentrância/Iniciar/saída e categoria capturada antes de eventos internos.
- NativeGUI adicional usa CTk real em 880×660, retorno de diálogo simulado e sessão/JSON reais: inclusão sem gravação, botão desabilitado em cmdline, proteção adicional e Save. Teardown after vazio/bgerrors vazios. Interação real com o diálogo do Windows e visual/DPI não automatizados.
- Sintaxe Python 3.12/UTF-8 nos 53 arquivos Python, links locais e diff conferidos. Runtime 3.12 pendente. Nenhum executável selecionado foi lido ou executado, nenhum processo/hosts do usuário afetado.

## Evidência da primeira configuração — 2026-10-11

- Suíte completa fora do sandbox: `.venv/Scripts/python.exe -B -m unittest discover -s tests`, **551 descobertos, 550 aprovados e um skip conhecido** de symlink/WinError 1314, 38,140 s. Python 3.14.6/Windows 10; doze nativeGUI e smoke de bandeja real passaram.
- `tests/test_initial_setup.py`: 22 testes de catálogo literal do §6/frozen, seleção individual/vazia/repetida, ordem do catálogo, dedup casefold, extras/duplicatas preservados, Java conjunto, iterable one-shot/falha atômica e import/função sem IO/psutil/Tk.
- `tests/test_initial_setup_integration.py`: 14 testes com arquivos reais. Abrir não cria diretórios/JSON; salvar vazio ou completo, import/export somente draft, agenda salva vazia antes de publicar, recarga estrita, erro/concorrente mantidos. Corridas reais no rename Windows e link preservam bytes externos; fsync/publicação falhos limpam temporário e permitem retry; escritor posterior não é adotado como baseline.
- GUI: sete novos fluxos simulados, três mainGUI e dois nativeGUI de primeira configuração. Somente FileNotFoundError de leitura permite for_new, lstat recusa existente/erro/link; sugestões desmarcadas, criação via Save/Ctrl+S/saída confirmada, start somente após salvar/confirmar, cancelamento/tray/discard sem JSON. Widgets reais em 880×660, bgerrors vazios/after vazio no teardown, motor/bandeja injetados.
- Sintaxe 3.12/UTF-8 nos 52 arquivos Python e links locais/diff conferidos. Runtime 3.12, inspeção visual/DPI continuam pendentes; janelas de testes ficam ocultas. Nenhum processo/hosts do usuário afetado.
- Primitivos de publicação são compartilhados com exportação, cuja cobertura de escrita/flush/cleanup/aliases segue passando. Runtime POSIX/FAT/exFAT real e crash adversarial não ensaiados; veja limites no [contrato](INITIAL_SETUP_CONTRACT.md).

## Evidência de bandeja e instância — 2026-10-11

- Suíte final fora do sandbox: `.venv/Scripts/python.exe -B -m unittest discover -s tests`, **503 descobertos, 502 aprovados e um ignorado**, 30,474 s. Python 3.14.6/Windows 10 build 19045; psutil 7.2.2, CustomTkinter 6.0.0, pystray 0.19.5 e Pillow 12.3.0. Skip conhecido: symlink/WinError 1314.
- `tests/test_instance_guard.py`: 33 testes de lifecycle, aliases, concorrência, ctypes/last-error/HANDLE e quatro mutexes reais. `tests/test_instance_guard_integration.py`: seis subprocessos reais, incluindo recuperação após saída abrupta. `tests/test_tray_commands.py`: 13 testes de mailbox, coalescência e corridas. Fixtures UUID e bytes de configuração preservados.
- `tests/test_windows_tray.py`: 14 testes, incluindo startup/stop concorrentes, callbacks tardios, falhas de fábrica/threads, setup interrompido antes de ready, BOOL ADD false sem ready e recriação após Explorer via API falsa. Smoke real passou com ADD aceito, ready/stop e ambas as threads encerradas; não abre menu nem inicia motor. No desktop isolado do sandbox, o Shell recusou ADD: falha explícita, cleanup completo, sem skip. O smoke precisa de desktop Windows que aceite o ícone.
- GUI atual: 41 fluxos simulados, 13 mainGUI e dez smoke tests CustomTkinter reais com motor/bandeja falsos. Cobrem ocultar somente após ready, timeout de 10 s/erro/restauração, cancelamento preservando execução e saída esperando ambos os workers. after info vazio e bgerrors assertados vazios; nenhum wait/join em callback.
- Entrada real `main.py --gui` recusou guarda concorrente da mesma configuração com retorno 1, sem criar janela/motor nem alterar JSON. Testes não encerram aplicativos do usuário; o aceite adicional de processos dedicados está descrito abaixo.
- Sintaxe Python 3.12/UTF-8 validada nos 49 arquivos Python, links locais e diff conferidos. Runtime Python 3.12, menu por interação, visual/DPI e reinício real do Explorer não executados. Nova tentativa de captura falhou duas vezes; smoke nativo não substitui inspeção visual.
- APIs, implementação dependente de internals pystray e limites em [TRAY_CONTRACT.md](TRAY_CONTRACT.md).

## Evidência do controle gráfico — 2026-10-11

Aceite nativo adicional na retomada: Python 3.14.6, Windows 10 build 19045,
ProcessController e adaptador psutil padrão, JSON isolado. Duas instâncias
descartáveis de uma cópia de `System32/ping.exe` com nome UUID no workspace,
somente localhost, launcher já encerrado antes do scan e somente esse nome
na lista de bloqueio (sem pastas/cmdline). Dentro da janela, alvo encerrou com
evento confirmado; fora dela permaneceu vivo/sem eventos. Salvar agenda ativa
e solicitar stop antes do próximo ciclo preservou o segundo alvo. Cleanup
conferiu PID/create_time/exe e removeu apenas fixtures. Nenhum aplicativo do
usuário ou hosts alterado. Esse ensaio não comprova jogos, Windows 11, GUI
Iniciar por interação, catálogo universal ou todas as condições de timing.

Captura visual novamente tentada pelo Computer Use com janela visível e JSON
isolado, regras vazias/motor parado. Duas tentativas com reseleção falharam em
`window capture timed out: timed out waiting on channel`. Sem interação visual;
execução QA encerrada pelo caminho exclusivo da fixture.

- Suíte completa no `.venv`: **426 descobertos, 425 aprovados e 1 ignorado**,
  37,077 s, Python 3.14.6/Windows, psutil 7.2.2 e CustomTkinter 6.0.0. Skip:
  symlink por WinError 1314. Oito smoke tests nativos passaram sem bgerrors.
- `tests/test_process_controller.py`: 27 testes de import/construção lazy,
  concorrência de start, snapshots, parada nas fronteiras, gates antigos,
  cadência/slots, retry, falhas e relatório parcial. ProcessBlocker real com
  adaptador falso verifica gates antes de terminate e kill.
- `tests/test_process_controller_config.py`: nove testes com load_config padrão
  e arquivos isolados; recarga válida/inválida/removida, rascunho versus save,
  conflito externo e retry sem reabrir gates anteriores.
- `tests/test_runtime_presenter.py`: 16 testes puros de estados/botões,
  contagem de eventos/status, erro/relatório parcial, última agenda preservada,
  diagnósticos ausentes/longos/multilinha, truncamento e import sem IO/widgets.
- GUI: 35 fluxos simulados com JSON real, dez testes de dispatch/saída de
  mainloop e oito smoke tests reais. Cobrem confirmação/dirty/modal, início,
  parar sem join, retry só depois de worker morto, saída/cancelamento/conflito,
  detail rolável e teardown. Callbacks de modal/linhas são cancelados sem
  remover polling da raiz; after info vazio na saída e bgerrors assertados vazios.
- Nenhum hosts ou processo do usuário alterado pelos testes; bloqueadores
  injetados. QA abriu janela com configuração isolada, regras vazias e motor
  parado; captura falhou duas vezes por timeout. Inspeção visual/DPI/rolagem,
  encerramentos Windows reais e runtime 3.12 permanecem pendentes.
- Comando, APIs e limites em [PROCESS_GUI_CONTRACT.md](PROCESS_GUI_CONTRACT.md).
- Sintaxe Python 3.12/UTF-8 válida nos 42 arquivos Python; links locais e diff
  conferidos. Runtime executado permanece 3.14.6.

## Evidência do editor gráfico — 2026-10-09

- Suíte final: **306 testes descobertos, 304 aprovados e 2 ignorados**, 11,390 s em Python 3.14.6. Os dois ignorados são smoke tests nativos, pois CustomTkinter não está instalado no ambiente de validação.
- `tests/test_config_session.py`: 11 testes com configuração/repositório reais; salvamento, consultas do baseline, dias vazios, extras, conflitos, arquivo removido, recarga inválida, falhas/retry e escritor posterior ao replace.
- `tests/test_config_gui_main.py`: oito testes de flags/importações/dispatch, erro de dependência, configuração inválida e Ctrl+C, sem importar bloqueadores ou abrir janela real.
- `tests/test_config_gui.py`: 12 testes de callbacks com widgets simulados e JSON real: CRUD, validação/correção, seleção de pastas, categorias, cmdline literal, conflito, recarga, saída e cancelamento de callbacks pendentes. Não comprovam renderização/compatibilidade nativa dos widgets.
- `tests/test_config_gui_native.py`: dois smoke tests opcionais, com widgets CustomTkinter reais e janelas ocultas, preparados para serem executados após instalar as dependências. Ainda não executados nesta entrega.
- Sintaxe Python 3.12 conferida em 33 arquivos; runtime executado continua 3.14.6. `git diff --check`, UTF-8 e links locais conferidos. Nenhum hosts, perfil do usuário ou processo real foi alterado pelos testes.
- Instalação impedida pelo bloqueio de rede do ambiente; helper de Computer Use indisponível (native pipe não encontrado). Abrir `--gui` no Windows após instalar dependências para validar layout, DPI e interação nativa. Limites e comandos em [GUI_EDITOR_CONTRACT.md](GUI_EDITOR_CONTRACT.md).

## Evidência do editor independente — 2026-10-08

- Suíte completa com as fases 1/2 e editor: **273 testes OK**, 18,358 s, Python 3.14.6, na conferência final do Maestro após os três relatórios. Frontend confirmou independentemente 273 testes em 18,507 s e os sete testes de flags/importações com `ui.config_cli` previamente importado. Sintaxe Python 3.12 verificada por `ast.parse(feature_version=(3, 12))` em 27 arquivos; runtime 3.12 ainda não executado. UTF-8/links locais conferidos.
- `tests/test_config_editor.py`: CRUD de janelas/quatro listas, dias/índices estritos, iteração de dias com falha, erro sem mutação, ordem/duplicatas, extras/cópias defensivas e ausência de IO.
- `tests/test_config_repository.py`: mesma leitura capturada/validada, UTF-8/JSON inválido, chaves duplicadas/constantes inválidas, roundtrip, conflitos inclusive remoção/formatação, segunda conferência após fsync, falhas de escrita/flush/replace/cleanup e baseline próprio após escritor posterior.
- `tests/test_config_cli.py` e `tests/test_config_editor_main.py`: menus/índices humanos, CRUD, validação, salvar/retry, conflito/reload, baseline após salvar, EOF/Ctrl+C e flags/lazy import sem bloqueadores. Doubles exercitam as fronteiras do frontend; testes de integração abaixo usam módulos reais.
- `tests/test_config_editor_integration.py`: cinco sessões com JSON/agenda reais, três via subprocess. Incluem janela noturna, regra conjunta, dias vazios, extras, EOF sem salvar, conflito externo seguido de recarga e falha real de publicação injetada seguida de retry com rascunho preservado.
- Arquivos de teste isolados no workspace; nenhum hosts, perfil do usuário ou processo real alterado. GUI/bandeja não são validadas nesta entrega. Comparação de bytes não elimina a pequena corrida entre conferência e replace, conforme [contrato](CONFIG_EDITOR_CONTRACT.md).

## Evidência da fase 2

- `tests/test_process_config.py`: listas promovidas/defaults vazios, nomes/pastas/variáveis, regras conjuntas/legado rejeitado, extras/bytes preservados e falhas antes de gravação.
- `tests/test_proc_blocker.py` e `tests/test_process_adapter.py`: fronteira de SO falsa; proteção antes de regras, helpers/ancestrais vivos/órfãos, acesso negado, destinos, PID reutilizado e metadados alterados antes de efeitos. Descoberta leve não autoriza ação; candidatos são reinspecionados completamente.
- Espera coletiva limitada, pending confirmado fora da janela sem nova enumeração/efeito, uma tentativa por identidade confirmada, falhas/desaparecimento prévio sem evento, relatório parcial entregue uma vez, Ctrl+C e ciclos concorrentes recusados.
- `tests/test_process_main.py`: flag explícito, lazy import, relógio fresco, recarga/erro sem snapshot antigo, prazos/atrasos, pending separado de sucesso e relatórios parciais. `tests/test_phase2_integration.py` integra JSON/agenda/CLI/bloqueador real com adaptador falso.
- `tests/test_process_wait_integration.py`: wait_procs instalado com handles falsos, sem processos do sistema; confirmação/negado/alive/interrupt/reuso de identidade.
- Integração **somente por leitura** no Windows build 10.0.19045: contexto próprio passou após corrigir ancestral do Explorer já ausente. Aproximadamente 293 processos; descoberta vazia 0,910 s, por nome sintético 0,923 s, por pasta workspace 1,243 s, com terminate/kill impedidos: zero chamadas/eventos. Antes da otimização, uma varredura completa de 291 registros levou 21,899 s.
- Essas amostras não comprovam RNF01, cadência sob muitos alvos, elevação, jogos reais, classificação universal do catálogo, Windows 11 ou instalador. Nenhum teste alterou hosts ou encerrou aplicativo do usuário.

## Evidência da fase 1

Testes em `tests/test_config.py`, `tests/test_scheduler.py`, `tests/test_scheduler_reference.py`, `tests/test_main.py` e `tests/test_phase1_integration.py`. Há comparação independente do calendário, validação/roundtrip, falhas de fsync/replace com original preservado, consultas via subprocess e watch com recarga/Ctrl+C controlados. Nenhum teste altera hosts, encerra processos ou usa o perfil real. Sintaxe 3.12 verificada; runtime validado foi 3.14.6.

## Resultados esperados já esclarecidos pelo usuário

- Avisos aos 5 e 1 minuto; Sair libera; crash recupera ao reabrir, podendo manter bloqueio antes disso (D01–D03).
- Segunda 22:00–02:00 inclui terça até 02:00, segunda=0 até domingo=6; início incluído/fim excluído; igualdade inválida; unir adjacentes. Foco fora das janelas e durante pausa não conta; lista de estudo editável; única conta Windows (D04–D08).
- Pausa só durante bloqueio; espera mantém bloqueio; cancelamento não conta; nenhuma retomada fora de janela (D09).
- Semana local segunda–domingo; uma tentativa por processo encerrado com sucesso, sem visitas web; dados mínimos para totais, sem expiração, histórico apagado na desinstalação (D11/D12/D16).
- Configuração inicial escolhida pelo usuário antes de ativar; sem horários ativos e com listas sugeridas (D13).

## Estratégia proposta

- Validar agendamento e contabilização com relógio/entrada controlados, sem tocar em processos reais ou hosts.
- Para regras de processo e hosts, primeiro usar entradas e arquivos isolados; só depois integração Windows com alvos de teste autorizados.
- Usar ambiente Windows dedicado para encerramento de processos, hosts, privilégio elevado, tarefa agendada e desinstalação. Registrar versão Windows/Brave, privilégios e estado do DNS seguro.
- Medir desempenho do executável distribuído. Não prometer RNF de CPU/RAM com base em teste unitário.
- Fase 1 usa unittest da biblioteca padrão; ferramentas/ambientes de integração das fases posteriores ainda a definir.

## Cenários por área

| Grupo | Cenários essenciais | Rastreabilidade | Decisões necessárias |
| --- | --- | --- | --- |
| Agendamento | Antes/início/dentro/fim de janela; múltiplas janelas; dias não selecionados; virada de semana e meia-noite; sobreposição; intervalos adjacentes; início=fim | RF01–04 | D04, D08 |
| Relógio e retomada | Iniciar no meio da janela aplica imediatamente; suspender/acordar dentro/fora; mudar relógio; evitar tempo fictício de foco | C04–05, RF20 | D09–D12 |
| JSON | Criar/editar/excluir e reabrir; validação de horas/dias/listas; arquivo ausente/inválido; falha de gravação e mudanças simultâneas | RF01/24, C02 | D13, D17 |
| Processos | Nome/pasta/cmdline; regras combinadas; `javaw.exe` com e sem `.minecraft`; safelist prioritária; prefixo parecido fora da pasta; processo que desaparece; acesso negado; reabertura; terminate sem sucesso | RF07–11, C03 | D14–D16 |
| Hosts | Backup antes da primeira escrita; IPv4/IPv6; entrar/sair; ciclos repetidos sem duplicar; preservar entradas externas; alteração externa durante bloqueio; marcador ausente/corrompido; somente leitura; falha de DNS flush | RF12–15, C06 | D03, D17 |
| Recuperação | Sair normal; encerrar abruptamente processo; reiniciar app; reiniciar Windows; desinstalar durante bloqueio; falha de cleanup | RNF04, C04, C08 | D02–D03, D07, D17 |
| Avisos | 5/1 min se confirmados; jogo/launcher aberto ou ausente; modo sempre avisar; sobreposição sem duplicar; loop atravessa instante do aviso; suspensão/edição/relógio | RF05–06 | D01, D10, D13 |
| Pausa | Espera 60 s; cancelar; pedido repetido; liberação de sites/processos por 15 min; aviso 1 min antes; janela termina durante espera/pausa; retomada; reabrir/suspender durante pausa | RF16–19 | D09–D10 |
| Foco | App elegível em primeiro plano; outro app; ociosidade abaixo/exatamente/acima de 5 min; retomada de input; atraso/suspensão; troca de dia/semana; pausa e horário livre | RF20–21 | D05–D06, D12 |
| Brave e foco | Domínio cadastrado como estudo versus não cadastrado; adicionar/remover lista; não contar fora da janela nem na pausa; troca de aba ativa | RF20; D19 | Identificação da aba/domínio, subdomínios e conflitos ainda a definir |
| Métricas | Total diário/semanal/geral; pausa cancelada/iniciada; processo bloqueado/reaberto; falha ao encerrar; não contar múltiplas regras para um evento segundo definição aprovada | RF19/21, C03 | D09, D11–D12, D16 |
| UI | Abrir/fechar janela repetidamente; manter bandeja; estados coerentes; cinco abas; listas/horários editáveis; cancelamento; falha visível sem travar UI | RF22–24, C01/C06 | D02, D06, D09, D13–D15 |
| Instalação | Instalador completo; dados em APPDATA; login elevado sem UAC por login; segunda instância; desinstalação remove tarefa e bloco do hosts | RNF02–03, C02/C08 | D03, D07, D17–D18 |
| Recursos | CPU/RAM em repouso; núcleo de 5 s com muitos processos; UI aberta/fechada; sessões longas sem crescimento indevido | RNF01, RF04/11 | D18; carga de referência pendente |

## Validação dos sites no Brave

Confirmado: nove serviços-alvo, DNS seguro desligado, hosts sem curinga e possível persistência de conexões já abertas. Fonte: §§1, 6, 8–9.

Para cada serviço, registrar domínios exatos testados, janela ativa/inativa, aba nova ou conexão preexistente e resultado de acesso/reprodução. Conferir liberação após janela/pausa e acesso a ferramentas livres previstas no escopo. Não considerar `www.` um hostname completo nem inferir bloqueio de subdomínio apenas por bloquear domínio raiz.

As listas são ponto de partida. Cobertura parcial deve ser relatada como limitação; não classificar um bloqueio como completo com base apenas no hosts correto. O critério final para conteúdo parcialmente disponível precisa de definição do usuário e evidência prática.

## Registro de resultado por entrega

Proposta: registrar cenário, requisito, ambiente, configuração relevante, resultado esperado, resultado observado e limitação. Evitar copiar dados pessoais ou cmdlines completas para relatórios sem política aprovada (D11).

Testes acompanham o mesmo commit da implementação correspondente. Não criar commits exclusivos por adicionar, modificar ou executar testes. Documentos de planejamento não substituem a execução.

## Painel e portabilidade — validação em 2026-10-11

- Prévia semanal: união/clipping diário, domingo anterior, meia-noite,
  adjacência/sobreposição, desativados e comparação independente por minuto.
- Duplicação: cópia independente, índices inválidos e preservação do rascunho.
- Importação/exportação: validação completa, extras/Unicode/cmdline, baseline
  preservado, conflitos depois de importar, aliases, falhas e limpeza.
  Corrida de publicação exercitada com `os.rename` real no Windows;
  ramo hard link também exercitado no filesystem local, sem runtime POSIX.
- GUI: prévia versus agenda salva, orientação para desativados/safelist sem
  alvos, busca com índices originais, seletores cancelados, importação
  confirmada, exportação sem salvar o ativo, modal e regressões de saída.
- Suíte completa em Python 3.14.6: **359 descobertos, 353 aprovados e 6
  ignorados**, 24,940 s. Cinco smoke tests gráficos sem CustomTkinter;
  um teste de symlinks sem privilégio Windows (WinError 1314).
  Sintaxe Python 3.12 conferida em 37 arquivos; runtime 3.12 pendente.
- Inspeção visual/DPI/rolagem em 880×660, FAT/exFAT real e runtime POSIX
  não executados. Testes não modificaram hosts nem encerraram aplicativos.

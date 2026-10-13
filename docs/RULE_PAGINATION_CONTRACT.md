# Contrato — paginação visual de regras

Unidade autorizada em 2026-10-13 após `795c794`, baseada no custo documentado
em [GUI_PERFORMANCE.md](GUI_PERFORMANCE.md). Implementação concluída e suíte
integrada final aprovada nos dois runtimes.

## Escopo e interface

- Quatro categorias de regras, busca e ordenação existentes. Página de **25**
  resultados, sem limite de configuração nem alteração de ordem/dados salvos.
- Pager compacto Anterior / Página X de Y · itens a–b de M / Próxima abaixo
  da lista, oculto quando houver no máximo uma página. Preservar busca/ordem,
  modo de seleção, janela mínima 880×660 e footer.
- Sem novos timers, virtualização de canvas, debounce, alterações de motor ou
  persistência. Custo ainda proporcional à página; 25 não promete RNF01.

## Helper puro

`ui.rule_pagination` importa somente biblioteca padrão:

- `RulePage` frozen: `page`, `page_count`, `total`, `start`, `stop`, `indices`.
- `rule_page(indices: tuple[int, ...], page: int = 0, *, size: int = 25)`.
- `rule_page_for_index(indices: tuple[int, ...], index: int, *, size: int = 25)`
  retorna página do primeiro índice correspondente ou `None` se ausente.
- `indices` é a tupla completa ordenada do helper de view. Ordem e duplicatas
  são preservadas; nunca converter posição visual em índice original.
- Inteiros estritos, bool recusado; índices/page não-negativos e size positivo.
  Tipos inválidos: TypeError; valores negativos/size zero: ValueError.
  Página além do fim é ajustada à última. Vazio: page 0, page_count 1, start e
  stop 0. Start/stop são offsets zero-based, stop exclusivo.
- Resultado frozen/tuple, fonte intacta, sem configuração/validação ambiental,
  IO, Tk, runtime, relógio ou serialização.

## Universo lógico e projeção

- Capturar uma vez field/query/order, draft owner, snapshot independente
  tipado, geração lógica e **full_indices**. A seleção é subset desses índices.
- Projeção contém somente page_indices, mapa de rows/checkboxes e geração de
  binding. Trocar página preserva universo/seleção, mas destrói bindings antigos,
  cancela scroll/highlight owned e recusa callbacks antigos antes de Tk.
- Categoria/filtro/ordem/model change/import/reload/history/refresh lógico
  reiniciam página e seleção, mesmo retornando a dados iguais. Diferenciar
  explicitamente reconstrução lógica de reconstrução da projeção.
- Contador N selecionadas/M resultados considera todo o universo. Hint explica
  que Selecionar exibidas abrange todas as páginas. Novos checkboxes refletem
  seleção existente, sem materializar widgets offpage.

## Guardas e operações

- Checkbox/CRUD exige contexto lógico atual, índice original, geração da
  projeção e identidade row/map/variable antes de getter/ação. Não reutilizar
  callback antigo depois de ida/volta à página com dados iguais.
- Lote valida universo completo/seleção/faixa/owner/snapshot tipado/geração
  antes/depois do prompt. Identidade de widgets é conferida somente onde há
  projeção materializada; não exigir rows offpage. Capturar tupla selecionada
  e época/projeção presente para recusar alteração durante confirmação.
- Shared confirmation flag bloqueia troca de página/reentrância. Cancelar ou
  retorno obsoleto preserva dados/history. Uma chamada remove_rules para todo
  o lote, uma edição Undo/Redo, Save explícito e conflito existentes.
- Snapshot compartilhado, sem cópia por row. Sem adotar arquivo externo em
  navegação. Formulários/contextos individuais e lifecycle já corrigidos ficam.
- Review navega pelo índice ORIGINAL: localizar sua posição no universo
  ordenado, revelar página antes de um único render/destaque/scroll. Preservar
  ordem; limpar filtro quando necessário. Mesma vista pode mudar só projeção,
  mantendo seleção. Completion/scroll revalida review/projeção/mapa antes Tk.

Se o filtro atual já incluir o alvo, preservar consulta e seleção e revelar
somente a página. Limpar filtro apenas quando necessário para revelar o índice.

## Ownership e aceite

- Backend: somente `ui/rule_pagination.py`, `tests/test_rule_pagination.py`.
- Banco: somente `tests/test_rule_pagination_integration.py`.
- Frontend: somente GUI e seus dois testes. Maestro docs/full/commit conjunto.
- APIs cedo, freeze explícito antes de importações/QA dos colegas. Nenhum
  commit exclusivamente de teste ou progresso intermediário.
- Cobrir limites 0/25/26/50/51/1000, páginas/sort/filter/duplicatas, lookup,
  seleção crosspage/AllFULL/offpage/oneUndo/Save, oldcallbacks e mudanças no
  prompt, revisão distante, logical reset versus page preservation, layout e
  timers/bgerrors. QA nos dois runtimes; roots ocultas não aceitam visual/DPI.
- Após QA final quieta, medição isolada de 1000 com mesmo protocolo anterior,
  uma construção/render/5s idle e limite 90s. Root autoriza janela antes de
  medir; depois suíte completa e commit funcional. Nenhum motor real/captura.

## Evidência final

Helper e integrações passaram nos dois runtimes; nove fluxos GUI novos e
compatibilidade selecionada também. Suíte completa final: 835 descobertos,
834 aprovados e um skip conhecido de symlink/WinError 1314, Python
3.14.6/265,365 s e 3.12.14/285,585 s, incluindo 48 smoke GUI nativos.
Medição isolada de 1000 preservou modelo/universo completo, 40 páginas e
25 linhas materializadas. Construção 2,089 s e RSS idle 66,773 MiB nessa
amostra; o render usou chamada diferente da baseline, explicitada em
[GUI_PERFORMANCE.md](GUI_PERFORMANCE.md). Não constitui aceite visual/DPI
ou RNF01.

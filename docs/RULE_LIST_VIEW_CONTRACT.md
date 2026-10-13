# Contrato — ordenação visual das regras

Evolução de interface em 2026-10-12, após navegação dos apontamentos.
Ordenar/filtrar modifica somente a apresentação de Jogos / Apps, preservando
cadastro, JSON, histórico, baseline, matching do motor e índices originais.

## Helper puro

- `ui/rule_list_view.py`: `rule_view_indices(config: AppConfig, field: str,
  query: str = '', order: str = 'registered') -> tuple[int, ...]`.
- Fields: block_exes, block_folders, safelist_exes e block_cmdline; exclui
  windows. Ordem registered preserva cadastro. name_asc/name_desc ordenam
  nomes por casefold; cmdline usa par executable/contains. Empates mantêm
  ordem original, inclusive descendente; duplicatas não são removidas.
- Busca mantém semântica existente: query.strip().casefold(); strings
  literais nas três listas simples e executable + separador de linha +
  contains em cmdline. Pastas não são expandidas/resolvidas.
- Retorna índices originais, não novos objetos/regras nem posições visuais.
  Config/query/field/order com tipo errado levantam TypeError; field/order
  desconhecidos levantam ValueError. Espera modelos tipados, sem revalidar
  schema/ambiente, acessar extras ou efetuar IO/discovery/runtime.
- Dependências somente biblioteca padrão e core.models; não importa GUI,
  validador ou controlador/bloqueador. Entradas permanecem intactas.

## GUI e integração

- Controle **Ordem visual**: Cadastro (padrão), Nome A–Z e Nome Z–A. Estado
  somente da sessão, sem novo campo de configuração ou Save automático.
- Busca e ordenação se combinam; trocar categoria ou ordem recalcula view.
  Mensagens distintas continuam para lista vazia e busca sem resultados.
- Editar/Remover usam índice original do helper. Mapa de navegação mantém
  (field, índice original); Ir para item respeita ordem atual e limpa somente
  busca. Reconstrução cancela callbacks/highlight de linhas antigas, sem
  invalidar revisão/dados somente por alteração da apresentação.
- Modal/seletor/saída guardam o controle; Iniciar/Salvar/history não são
  acionados. CRUD/import/reload/Undo/Redo recalculam índices da versão atual.
- Controle compacto deve preservar área da lista em 880×660. Widgets ocultos
  validam estado/teardown, não inspeção visual/DPI.

O helper sempre retorna o universo completo. A projeção GUI em páginas de 25
é definida em [RULE_PAGINATION_CONTRACT.md](RULE_PAGINATION_CONTRACT.md), sem
truncar resultados nem converter índices. Navegação da revisão revela a página
correspondente ao índice original; seleção em lote continua abrangendo todas.

Backend: helper/testes. Frontend: GUI/testes fake+nativos. Banco: integração
com sessão/JSON em arquivo de testes exclusivo, sem GUI durante edição.
Maestro: revisão, documentação, suíte e commit funcional conjunto. Testes
acompanham implementação; não gerar commit próprio.

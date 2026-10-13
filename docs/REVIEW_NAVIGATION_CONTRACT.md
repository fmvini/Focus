# Contrato — navegação dos apontamentos da revisão

Evolução de interface em 2026-10-12, após a comparação GUI/CLI integrada.
Apontamentos continuam informativos; navegar não corrige, salva ou altera
horários/regras, histórico, baseline ou estado do motor.

## Links e apresentação

- `ui/review_navigation.py`: `ReviewLink(ordinal, field, index, label)` frozen
  e `review_links(report: ConfigReview, limit: int = 10) -> tuple`.
- Considera o prefixo `report.items[:limit]`, igual aos apontamentos exibidos
  na revisão. Somente depois filtra itens sem índice ou com metadata inválida;
  não oferece um link para texto que ficou fora do prefixo.
- Ordinal do apontamento e índice original da lista são zero-based internos.
  Rótulo humano `Apontamento N · Categoria · item M`; a numeração do texto
  da revisão acompanha o ordinal. Ordem e múltiplos apontamentos do mesmo
  item são preservados, sem dedup/casefold ou conteúdo privado adicional.
- Campos conhecidos: windows, block_exes, block_folders, safelist_exes e
  block_cmdline. None, campo desconhecido, bool/negativo/não-int não geram
  link. Report errado/limit não-int estrito levanta TypeError; limite negativo
  levanta ValueError. Não valida configuração nem resolve recursos.
- Helper puro sem IO/descoberta/serialização/runtime; depende somente dos
  tipos da revisão e biblioteca padrão.

## Ação na GUI

- Visão geral oferece seletor compacto e botão **Ir para item**, sem navegar
  automaticamente ao renderizar. Ambos ficam desabilitados sem link válido.
- Horário abre Horários; regra abre Jogos / Apps e a categoria correspondente.
  Busca é limpa para revelar o índice original. Destino ganha destaque visual
  e rolagem, mantendo Editar/Remover/Duplicar nos índices originais.
- Não abre formulário automaticamente. A ação respeita modal, seletor e
  saída, valida campo/índice/faixa atuais e descarta escolha obsoleta após
  alterações/reload/import/Undo/Redo; destaque é somente estado da interface.
- Callback de rolagem pertence à linha destacada e é cancelado ao removê-la.
  Destruição da linha/modal/root mantém polling e teardown existentes, sem
  callbacks órfãos, wait/join ou widgets acessados pelo worker.
- CTk 6.0.0 não oferece API pública para rolar até uma linha. Um adaptador
  restrito usa o canvas interno; se indisponível, mantém destaque e orienta
  rolagem manual. Revalidar esse adaptador ao atualizar a dependência.
- Busca não vazia usa seu trace para reconstruir a lista; busca já vazia
  renderiza diretamente. A navegação não constrói a mesma lista duas vezes.
- Regras paginadas são localizadas pela posição do índice original no universo
  completo ordenado. Revelar página antes do destaque/scroll, sem buscar pelo
  texto de duplicatas. Mesma vista muda somente projeção e preserva seleção;
  limpar filtro ou mudar contexto reconstrói logicamente. Detalhes no
  [contrato da paginação](RULE_PAGINATION_CONTRACT.md).

## Propriedade e validação

Banco: helper/testes. Frontend: GUI/testes fake+nativos. Backend: revisão
somente leitura de índices, duplicatas, seleções obsoletas e lifecycle.
Maestro: integração, documentação, suíte e commit conjunto. Não criar commit
exclusivamente de testes ou de progresso intermediário.

Validar todas as categorias, filtros/duplicatas/índices originais, primeira
configuração sem links, escolhas antigas, invalid input, guards e ausência
de IO/mudança de dados. Widgets nativos ocultos não aceitam visual/DPI.

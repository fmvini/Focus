# Contrato — remoção de regras selecionadas em lote

Implementação integrada em 2026-10-12 após a busca por teclado `3cc801b`.
Evidências e limites de QA em [TEST_PLAN.md](TEST_PLAN.md) e no log.

## Núcleo

`ConfigDraft.remove_rules(field: str, indices: Iterable[int]) -> int` remove
posições originais das quatro listas de processos, nunca horários.

- Validar campo mesmo com seleção vazia. Consumir o iterable exatamente uma
  vez; recusar str/bytes/bytearray como coleção de índices. Cada índice deve
  ter tipo int estrito, não negativo e dentro da lista original, antes de
  deduplicar posições. Valores de regras duplicados continuam distintos.
- Falha de iteração, inclusive depois de posições válidas, levanta ConfigError
  com causa e não muda draft, undo ou redo. Campo/índice inválido também não
  muda estado. Não tratar KeyboardInterrupt/SystemExit como erro de configuração.
- Vazio válido retorna zero antes de serialização/revalidação, conservando
  redo. Seleção não vazia constrói sobreviventes na ordem original e chama
  `_accept` uma única vez, validando antes de publicar. Retorno é a quantidade
  de posições distintas removidas. Falha de validação conserva estado.
- Uma remoção real é uma edição Undo/Redo. Outros campos/windows/extras,
  incluindo tipos JSON e ordem, permanecem intactos. Sem IO, descoberta ou motor.

## Interface

- Modo explícito **Selecionar regras**, inicialmente desligado. Fora do modo,
  preservar lista/busca/ordem/footer atuais. Ativo mostra checkbox compacta em
  cada regra e barra de contador/ações; não altera dados ao entrar ou fechar.
- Contador N selecionadas / M exibidas. **Selecionar exibidas** abrange todos
  os resultados da categoria/filtro atual, inclusive fora do viewport. Nunca
  outras categorias ou linhas ocultas pelo filtro. **Limpar seleção** e
  **Fechar seleção** descartam somente estado visual.
- Categoria, consulta, ordem, qualquer rerender ou mudança de modelo limpa
  seleção e incrementa geração. Informar essa política brevemente na barra.
  Checkbox/contador não reconstrói a lista. Zero selecionadas desabilita
  remoção; zero exibidas desabilita seleção em lote.
- Polling de estado não deve reconfigurar checkboxes quando o estado permanece
  igual: CTk redesenha ao receber configure(state), mesmo com valor idêntico.
  Mudanças de disponibilidade continuam atualizando os controles.
- **Remover selecionadas** confirma quantidade distinta e categoria, inclusive
  Proteção adicional, como remoção do rascunho. Cancelar preserva seleção se
  a vista continuar atual. Salvar permanece explícito, com conflito existente.
- Capturar geração da vista/seleção, campo, tupla original selecionada,
  identidade draft e snapshot independente. Conferir guardas, geração,
  conteúdo tipado, faixa e pertencimento à vista antes e depois de askyesno.
  Retorno ao mesmo texto/modelo não revalida callbacks antigos. Checkbox
  também confere geração/mapa/identidade da linha antes de acessar Tk.
- Flag de confirmação em try/finally impede confirmação/remoção reentrante.
  Saída, modal, seletor ou mudança de vista/modelo durante prompt descarta
  remoção sem tocar estado novo. Não esperar workers em callback.
- Barra compacta somente no modo ativo; custo temporário aproximado de 40 px
  da lista, mantendo scroll e footer em raiz mínima 880×660. Default mantém
  lista na linha 4; modo ativo pode deslocá-la ao mostrar a barra. Não prometer
  aceite visual/DPI por testes de raízes ocultas.

## Ownership e QA

Backend: `core/config_editor.py` e novo `tests/test_rule_bulk_remove.py`.
Banco: novo `tests/test_rule_bulk_remove_integration.py`, usando sessão/JSON
reais somente após freeze do núcleo. Frontend: três arquivos GUI/testes.
Maestro: docs/integração/suíte/commit conjunto. Não importar fonte em edição.

Cobrir índices originais/duplicatas/sort/filter, one-shot/falha tardia/tipos,
no-op/redo, atomicidade/único Undo, seleção/reset/cancel/prompt reentrante,
callback antigo/mudança durante confirmação, bytes intactos até Save e
conflito/import/reload, native layout/teardown sem bgerrors nos dois runtimes.

# Contrato — busca de regras pelo teclado

Continuidade autorizada em 2026-10-12 após `8d040af`, independente das perguntas
de sites, pausa e avisos.

- Ctrl+F na janela abre Jogos / Apps e coloca foco na busca da categoria
  atualmente selecionada. Preserva consulta e ordem visual; seleciona o texto
  existente para facilitar substituição. Sem foco diferido/timer novo.
- Escape somente dentro da busca limpa o filtro; não fecha a janela nem
  interfere no Escape dos formulários. Botão Limpar ao lado da entrada oferece
  a mesma ação. Vazio não provoca reconstrução desnecessária.
- Guardas de modal, picker_active, selecting_executables, closing e closed
  impedem atalhos/botão antes de acessar widgets. Não mudar categoria, draft,
  baseline, histórico, bytes ou motor. Salvar continua explícito.
- Limpar filtro reutiliza trace e helper de visualização, mantendo ordem
  e índices originais de regras/CRUD/navegação; uma reconstrução por ação.
  Limpar/Escape continuam síncronos com a busca diferida; consulta vazia
  pendente é resolvida, enquanto vazia estável permanece noop. Ctrl+F apenas
  foca e não antecipa a reconstrução. Ver
  [RULE_SEARCH_DEBOUNCE_CONTRACT.md](RULE_SEARCH_DEBOUNCE_CONTRACT.md).
- Layout compacto na linha da busca, ordem visual permanece ao lado,
  lista e footer preservados na raiz mínima 880×660. Rótulo informa Ctrl+F;
  Escape é documentado, sem ampliar a interface com instruções técnicas.

Frontend possui GUI e dois testes GUI/nativos; Backend e Banco revisam somente
leitura após congelamento, sem retomar lotes antigos. Maestro integra/docs e
commit funcional único. QA fake/native nos dois runtimes verifica comandos,
guardas, categoria/consulta/ordem, filtro/índices, ausência de efeitos e
teardown. Raízes ocultas não comprovam visual/DPI/acessibilidade.

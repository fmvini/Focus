# Contrato — reconstrução da busca após digitação

Unidade retomada em 2026-10-13 após `e314c22`. Implementação e validação
integrada concluídas nos dois runtimes; evidências em [TEST_PLAN.md](TEST_PLAN.md).
O custo observado da projeção de 25 linhas motiva evitar reconstruções por
escritas intermediárias da busca. Não altera configuração, motor ou alcance
da seleção; 200 ms não é garantia de latência ou aceite RNF01.

## Digitação e invalidação

- Trace da consulta usa trailing debounce de 200 ms, com um único `after`
  pertencente à raiz, id rastreado e token monotônico. Reiniciar cancela o
  anterior; callback antigo verifica token/saída antes de qualquer getter/Tk
  e nunca apaga o handle de um agendamento mais novo.
- Cada escrita invalida imediatamente owner/contextos e gerações lógica e
  de projeção, limpa seleção e cancela highlight/scroll owned. A→B→A não
  recupera ações antigas. Não calcular helper/copiar configuração/criar ou
  destruir linhas em cada tecla.
- Últimas linhas podem permanecer, desabilitadas e identificadas como
  `Atualizando busca…`. Pager/checkbox/ações de linha e lote ficam inertes;
  não mostrar a contagem antiga como resultado válido da nova consulta.
  Entry, categoria e ordem continuam disponíveis. Sem novo layout.
- Ao concluir, ler a configuração atual uma vez e reconstruir o universo
  completo e projeção de 25. Não alimentar a vista com snapshot antigo,
  reler arquivo, revalidar ambiente, salvar ou alterar history/dirty/motor.

## Ações explícitas e fronteiras

- Render lógico, categoria/ordem, CRUD/import/reload/history/Save/refresh
  cancelam pendência e constroem uma vez o estado final. Evitar flush de uma
  vista anterior seguido de outro render para a mesma ação.
- Limpar/Escape são síncronos por escopo protegido em try/finally. Vazio
  estável é noop; vazio com busca pendente deve resolver a atualização.
- Review resolve consulta atual/alvo original antes de uma única projeção:
  preserva filtro incluinte, limpa apenas filtro necessário. Não construir
  página 0 antes da página alvo. Ctrl+F somente foco não exige flush.
- Nenhum timer reconstrói sob modal, picker, seleção de executáveis ou
  confirmação. Entrada autorizada em bloqueio resolve antes a pendência,
  ou a suspende com retomada explícita sem reagendamento recorrente.
  Callbacks de rows antigas são recusados; não fazer flush para ressuscitá-los.
- APIs internas: `cancel_rule_search()` preserva pending e invalida ticket;
  `flush_rule_search(*, target_index=None)` sincroniza quando permitido;
  `rule_search_boundary()` suspende em profundidade com try/finally, retomando
  somente na fronteira externa. `rule_confirmation()` recusa resposta se a
  revisão da consulta mudou durante o prompt, inclusive ida e volta; essa
  revisão não muda por render sem escrita na consulta.
- Query forçada durante bloqueio invalida imediatamente confirmações e
  mantém necessidade de refresh. Retorno resolve uma vez o estado atual,
  aproveitando o render já existente quando houver Apply/import/Save.
- Saída aceita cancela timer/invalida token antes de destroy. Cancelar a
  saída ou outra operação não perde a busca nem deixa a vista inerte. Guardas
  precedem getters/Tk; nenhum join/wait, thread nova ou polling de debounce.

## Preservação e aceite

- Universo/índices originais, duplicatas, ordenação estável, seleção FULL,
  dias `(6,0)`, extras JSON tipados, identidade do draft/baseline, bytes,
  Undo/Redo, Save explícito/conflito e cadência do motor continuam existentes.
- Frontend possui somente GUI e dois testes. Backend/Banco revisam após
  freeze, sem importar GUI em edição. Maestro integra/docs/commit conjunto.
- Poucos fluxos fake/native: rajada/último render, token A→B→A e timer antigo,
  seleção invalidada antes de getter, clear vazio-pendente/estável, ações
  explícitas/review sem render duplicado, modelo atual durante espera,
  modal/picker/prompt/saída cancelada e callbacks pós-destroy. Legados que
  simulam digitação precisam concluir o agendamento/flush explicitamente,
  preservando os oráculos de dados e ações síncronas.
- QA nos dois runtimes e suite integrada sobre freeze final. Raízes ocultas
  não comprovam visual/DPI/foco físico; nenhuma captura ou benchmark novo.
  Debounce reduz reconstruções intermediárias, não preempta nem acelera a
  projeção já iniciada. Digitação espaçada pode continuar gerando renders.

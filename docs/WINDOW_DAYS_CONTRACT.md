# Contrato — seleção dos dias no formulário de horários

Unidade autorizada em 2026-10-12, após `ac2bb84`. Melhoria independente das
perguntas abertas sobre sites, pausa e avisos.

## Comportamento

- Todos seleciona os sete dias; Seg–Sex seleciona segunda a sexta, sem inferir
  feriados; Fim de semana seleciona sábado e domingo; Nenhum desmarca todos.
- Atalhos alteram somente os checkboxes do formulário. Adicionar/Aplicar
  alteração continua necessário para atualizar o rascunho. Cancelar, Escape
  e fechar o formulário descartam a seleção local.
- Horário novo mantém seleção inicial de todos os dias e publica dias em
  ordem semanal. Nenhum, quando aplicado, cria/edita um horário desativado.
- Na edição, os dias ainda selecionados preservam a ordem original; dias
  novos são acrescentados em ordem semanal. Exemplo: `(6, 0)` sem mudanças
  permanece `(6, 0)`; retirar domingo resulta em `(0,)`; acrescentar quarta
  resulta em `(6, 0, 2)`. Desmarcar e marcar novamente antes de aplicar conserva
  a ordem dos dias retidos pela seleção final.
- Todos em `(6, 0)` resulta em `(6, 0, 1, 2, 3, 4, 5)`: os atalhos escolhem dias,
  sem prometer reordenar dados existentes. Lista e comparação apresentam
  a ordem preservada.

## Estado e limites

A correção evita a alteração estrutural involuntária causada pela enumeração
semanal dos checkboxes na edição. Não altera igualdade tipada, scheduler,
schema ou parser. Aplicar sem mudança efetiva preserva dirty e histórico,
inclusive redo. Mudança válida continua uma edição; falha mantém formulário
e rascunho anterior. Salvar é explícito, com conflito e baseline existentes.

Callbacks dos atalhos e aplicação devem descartar chamadas de formulário
fechado/substituído ou durante saída antes de acessar Tk/draft. Botões compactos
não alteram a janela mínima de 880×660. Testes com widgets ocultos não comprovam
visual, DPI ou acessibilidade.

## Ownership e validação

- Frontend: `ui/config_gui.py`, `tests/test_config_gui.py`,
  `tests/test_config_gui_native.py`; congelamento explícito antes da integração.
- Backend e Banco: revisão somente leitura e testes existentes finalizados.
- Maestro: documentação, revisão integrada, suíte completa e commit funcional
  conjunto; nenhum commit exclusivamente de testes.

Validar presets/localidade, cancelamento, callbacks obsoletos, novo/desativado,
ordem não semanal, no-op/redo, alteração de horário conservando dias,
Undo/Redo e publicação somente ao Salvar nos runtimes 3.14.6 e 3.12.14.

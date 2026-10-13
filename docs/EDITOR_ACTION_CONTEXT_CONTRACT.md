# Contrato — integridade das ações e formulários individuais

Correção autorizada em 2026-10-12 após `d128a78`, baseada em probes de Backend
e Banco, implementada e validada em 2026-10-13. Core/schema/igualdade permanecem
intactos.

## Falhas confirmadas

- Remover individual usa campo/índice antigo na sessão atual depois de confirmar;
  substituir ou editar o draft durante o prompt pode remover outro item.
- Callbacks Editar/Remover/Duplicar capturados de linhas antigas operam sobre
  novas linhas com o mesmo índice depois de trocar modelo/renderizar.
- Apply dos dois formulários resolve o draft atual e pode sobrescrever um novo
  draft/modelo com campos antigos. Apply de regra cancelada/substituída acessa
  Entry destruída; o formulário de janela já guarda identidade modal, mas não
  identidade/conteúdo do draft.
- Reload da UI não recusa modal e troca o draft sob o formulário aberto.

## Correção

- Capturar contexto no render de cada linha: tipo/campo, índice original,
  geração da lista, identidade da linha/draft e snapshot independente tipado;
  regras também vinculadas à categoria/consulta/ordem da vista. Guardar antes
  de Editar/Remover/Duplicar, rejeitando callback antigo antes de Tk/draft.
- Remover individual revalida contexto, faixa/modelo/vista antes e depois do
  prompt. Confirmação não reentrante com flag try/finally, compartilhada ou
  compatível com a confirmação em lote. Cancelar/falha/contexto alterado não
  removem nem mudam histórico. Erro ConfigError é informado com estado intacto.
- Ambos formulários capturam draft e snapshot antes de criar/preencher diálogo;
  conferir novamente se a criação do diálogo permitir mudança de estado.
  Apply completo verifica flags, identidade modal/draft e configs_equal antes
  de qualquer getter e finish_edit. Formulário atual com modelo alterado deve
  orientar reabrir; callback de formulário fechado/substituído é descartado.
- Reload recusa modal/picker/selecting/saída antes de IO e depois de eventual
  confirmação. Se rascunho mudar durante a confirmação de descarte, preservar
  a versão nova. Não bloquear a leitura de arquivo externo quando o draft em
  memória permanece igual e a recarga foi solicitada validamente.
- Manter novos formulários/CRUD atuais, dias retidos na ordem original,
  validação/erro/retry, uma edição Undo/Redo, salvamento explícito e motor.
  Sem novos timers, persistência, política de bloqueio ou normalização de dados.

O snapshot de configuração é compartilhado pelas linhas da mesma lista, sem
cópia por linha. Contextos de ação individual e seleção em lote usam variáveis
distintas; callbacks capturam seus argumentos na construção. Isso permite
Editar/Remover individualmente também no modo de seleção em lote.

## Ownership e QA

Frontend: somente `ui/config_gui.py`, `tests/test_config_gui.py`,
`tests/test_config_gui_native.py`. Backend/Banco revisam somente leitura após
freeze explícito. Maestro integra/docs/suíte/commit funcional conjunto.

Cobrir callbacks antigos após render/import/reload/UndoRedo com mesmo índice
ou dados iguais; remoção com modelo/vista/identidade alterados durante prompt;
Apply de regra/janela após troca draft ou edição same-draft; cancel/substituição
sem getter Tk; reload guardado sem IO; confirmação reentrante/finally; edição
válida/no-op/ordem dias/history/Save/conflito/bytes. QA fake e CTk oculto nos dois
runtimes, sem motor/captura/processos/hosts reais. Não declarar visual/DPI.

Suíte final Maestro: 803 descobertos, 802 aprovados e um skip conhecido de
symlink nos dois runtimes Windows (Python 3.14.6/225,621 s e 3.12.14/262,128 s).
Quarenta e três testes nativeGUI, ícone real e guardas passaram. Resultados e
limites em [TEST_PLAN.md](TEST_PLAN.md).

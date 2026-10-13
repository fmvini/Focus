# Contrato — atualização de widgets no polling

Unidade autorizada em 2026-10-13 após `7d3ad6d`, motivada pela
[medição da GUI](GUI_PERFORMANCE.md). Corrigir somente setters repetidos de
texto/estado, preservando todas as avaliações e transições existentes.

## Comportamento

- Helper interno usa `widget.cget` público para comparar `text`/`state` atuais
  aos desejados. Chama `configure` uma vez com somente as opções diferentes;
  valores iguais não configuram nem redesenham o widget.
- Sem cache paralelo, memoização de configuração, alteração de schema ou
  supressão de exceções Tk. Outros tipos de opção não entram neste helper.
- Aplicar aos labels da agenda, título runtime, Iniciar/Parar, histórico,
  ordem/navegação da revisão e controles/contador da seleção em lote.
  O cache de detalhe do textbox e a guarda de estado dos checkboxes continuam.
- Cadência de 250 ms, consulta da agenda/controller, mailbox e cálculos de
  guardas continuam executados. Não pular o polling inteiro quando o snapshot
  parece igual: modal/picker/saída/worker/horário também podem mudar.
- Preservar transições de rascunho novo/dirty/history, modal/picker/selecting,
  confirmação, revisão/seleção, idle/running/stopping/error e saída com worker
  vivo. Durante saída ainda apresentar Parando e controles desabilitados.
- Não alterar `command`, `values`, estilos, conteúdo de Entry, renderização
  das listas ou lifecycle. Não acrescentar timers nem executar Tk no worker.

## Ownership e aceite

Frontend altera somente `ui/config_gui.py`, `tests/test_config_gui.py` e
`tests/test_config_gui_native.py`, com freeze explícito antes da integração.
Backend/Banco revisam somente leitura; Maestro docs/full/commit conjunto.

QA de fluxos: três polls iguais não configuram os alvos após sincronização;
toolbar ativa também permanece sem redraw; alteração real de texto/estado
aplica uma vez e novo polling estável não aplica novamente. Preservar modelo,
baseline/history/bytes/índices e noIO/noControllerEffects. CTk oculto confere
valores reais e teardown/bgerrors, sem alegar aceite visual/DPI.

Medição posterior 0/100 concluída sem testes concorrentes: idle 0,937%/0,312%
de um núcleo, RSS próximo do anterior. Uma amostra não garante CPU/RAM nem
substitui RNF01. Suíte final Maestro: 808 descobertos, 807 aprovados e um skip
conhecido nos dois runtimes (3.14.6/199,132 s e 3.12.14/229,239 s).

# Registro da tentativa de inspeção da GUI

Data: 2026-10-13, America/Sao_Paulo. Base de produção: `79607c9`.
**Resultado: inspeção visual/DPI não concluída.** Este registro documenta
uma tentativa diagnóstica; não aprova casos do [roteiro](GUI_ACCEPTANCE.md).

## Ambiente e isolamento

- Windows 10.0.19045 AMD64; Python 3.14.6, CustomTkinter 6.0.0,
  psutil 7.2.2, Pillow 12.3.0 e pystray 0.19.5.
- Probe local `.qa/gui_acceptance_probe.py`, fora do código distribuído,
  usando `_build_app` e `ConfigSession.for_new` com destino
  `.qa/acceptance-new/config.json` realmente ausente. Não foi a execução
  completa de `main.py --gui` nem a receita de fixtures do roteiro.
- Controlador injetado sem worker/bloqueador; `start()` não inicia motor.
  A instância de bandeja real foi construída, mas não se enviou à bandeja.
- Janela `Focus QA — Primeira configuração`, geometria efetiva inicial
  880×660. `tk scaling` reportou 1,3348876577408433. Escala Windows,
  área cliente física, DPI por monitor e aumento de texto **não medidos**;
  não converter o valor Tk em aprovação de uma escala Windows.
- Diagnóstico inicial: destino ausente, modelo e baseline preservados,
  dirty=true esperado no primeiro uso, Undo/Redo=false, zero chamadas
  de start e nenhum erro Tk. Registro local em
  `.qa/acceptance-new/start.json`; esses artefatos de QA não são versionados.

## Observações reais

| Operação | Resultado observado | Limite da evidência |
| --- | --- | --- |
| Construir e localizar janela | Janela retornada por `sky.list_windows`; diagnóstico Tk mediu 880×660 | Não prova pintura, legibilidade, foco ou ausência de cortes |
| Captura inicial | `FrameArrived timed out: timed out waiting on channel` | Nenhuma imagem obtida |
| Atualizar seleção, ativar janela e repetir captura | `window capture timed out: timed out waiting on channel` | Recuperação sem imagem; nenhuma célula DPI aceita |
| Ler UI Automation sem screenshot | Título identificado; árvore composta principalmente de painéis/imagens e controles da moldura; foco reportado como `1 painel` | Não foram obtidos nomes/papéis úteis dos controles CTk nesta leitura; leitor de tela não ensaiado |
| Enviar Ctrl+F | Envio retornou e a árvore mudou; foco continuou reportado como `1 painel` | Não foi possível confirmar foco/caret na busca; nenhum texto foi digitado |
| Clicar Fechar por índice de acessibilidade | `coordinate input geometry is unavailable` | Fechamento por esse caminho não confirmado |
| Tentar Alt+F4 após nova leitura | `user input was detected in this window; call get_window_state before continuing` | Não houve nova tentativa de entrada; encerramento normal não validado |
| Limpar os processos dedicados | PIDs 19636 e 26300 revalidados pelo comando do probe e encerrados; destino continuou ausente | Cleanup externo, sem prova de teardown normal ou contadores finais de memória |

O primeiro cleanup recusou incluir o processo de console auxiliar porque seu
comando não correspondia ao probe. A execução seguinte restringiu-se aos dois
PIDs de Python confirmados; não foram encerrados aplicativos do usuário.
Não houve Save, seleção de sugestões, Apply, remoção de regras, início de
motor, envio à bandeja, captura salva ou benchmark nesta tentativa.

## Estado e retomada

V01 teve somente abertura/diagnóstico parcial. V02–V13 não foram concluídos;
Ctrl+F isolado não aprova V09. A árvore UIA obtida indica uma limitação concreta
da observação automática, sem certificar suporte ou ausência universal de
suporte a tecnologia assistiva. Não se inferiu defeito de layout sem imagem.

Retomar pelo [roteiro](GUI_ACCEPTANCE.md) em sessão que permita observação
direta ou captura funcional. Registrar a escala real antes dos casos e usar
fixtures isoladas, um processo por vez e motor parado. Conferir teclado e
leitor de tela separadamente. Corrigir eventuais defeitos demonstrados em
unidade coerente, com implementação/regressões/log no mesmo commit.

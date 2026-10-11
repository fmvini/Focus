# Contrato — editor gráfico de configuração

Continuidade autorizada em 2026-10-09. Unidade complementar às fases 1/2,
independente das respostas ainda vazias Q-HOSTS-01–05. Implementa edição
gráfica de RF01 e parte de RF24; a fase 5 completa permanece pendente.

## Escopo implementado

Evolução em 2026-10-11: a quarta aba **Visão geral** acrescenta painel semanal
do rascunho e orientação inicial; horários ganham duplicação, regras ganham
busca e Configuração ganha importação/exportação. APIs e comportamento no
[contrato da evolução](CONFIG_EVOLUTION_CONTRACT.md). A janela também controla
um motor de processos por início/parada explícitos, conforme
[contrato do controle gráfico](PROCESS_GUI_CONTRACT.md).
Botão Enviar à bandeja e guarda gráfica por configuração/sessão são definidos
no [contrato de bandeja](TRAY_CONTRACT.md); fechar pelo X continua sair.

- `--gui` abre um JSON existente, com o mesmo `--config`/APPDATA da CLI.
  Destino ausente permite rascunho inicial, criado somente ao Salvar, conforme
  [primeira configuração](INITIAL_SETUP_CONTRACT.md). `--init-config` continua
  disponível pela CLI; arquivo inválido não é substituído. A flag rejeita
  outros modos antes de IO/importações.
- Quatro abas: Visão geral, Horários, Jogos / Apps e Configuração. Janela CustomTkinter na
  thread principal; motor e ícone de bandeja em workers separados. Callbacks
  da bandeja publicam fila limitada; somente polling Tk opera widgets/motor.
- Horários: adicionar/editar/remover; sete checkboxes, todos selecionados por
  padrão. Dias vazios desativam. Mesma validação de horários noturnos,
  igualdade inválida, dias e união já existente no núcleo.
- Quatro categorias de processos: executáveis, pastas, proteção adicional e
  linha de comando. Cmdline mantém executável e trecho juntos, preservando
  espaços do trecho literal. Seletor de pastas opcional. Nenhuma lista
  predefinida ou executável inferido.
- Diálogos aplicam alterações ao rascunho; Cancelar/Escape/fechar o diálogo
  descartam somente os campos desse formulário. Remover exige confirmação.
- Salvar/Ctrl+S publica pelo repositório existente. Erro/conflito preserva
  rascunho e baseline. Recarregar/Ctrl+R lê a versão atual; se houver edição
  pendente, pede confirmação de descarte. Recarga inválida preserva a sessão.
- Fechar a janela com rascunho pendente oferece salvar/descartar/cancelar.
  Falha ao salvar mantém a janela aberta e o motor. Após decidir sair, a GUI
  sinaliza parada e espera motor/ícone por polling antes de destruir a janela.
- Consulta da agenda por timer Tk usa exclusivamente a última versão
  carregada/salva. Não representa confirmação de bloqueio aplicado, nem
  observa automaticamente alterações externas; Recarregar atualiza a leitura.
- Um watcher separado poderá ler o arquivo salvo no próximo ciclo. O editor
  não interrompe nem controla esse watcher, e fechá-lo não encerra o watcher.

## Implementação

`core/config_session.py` contém `ConfigSession`: caminho, snapshot e
`ConfigDraft`; `dirty` compara a configuração editada ao baseline. `save()`
adota somente o snapshot retornado após sucesso; `reload()` só publica a nova
sessão após leitura/validação completas. `agenda_status(now)` retorna estado
e próximo início do baseline, sem efeitos de sistema.

`ui/config_gui.py` importa CustomTkinter/Tk somente na execução de `--gui`.
A fábrica `_build_app` recebe toolkit, diálogos, sessão e controlador opcional
para testar os callbacks com arquivos reais sem dependência gráfica. Abertura
não inicia worker nem importa psutil; Iniciar é explícito. Diagnóstico e editor
CLI continuam com importações independentes. O presenter puro separa estado do
motor, última agenda observada e relatório de encerramentos.

CustomTkinter 6.0.0 é fixado em `requirements.txt`, conforme a versão publicada
no [PyPI](https://pypi.org/project/customtkinter/6.0.0/); widgets seguem a
[documentação oficial](https://customtkinter.tomschimansky.com/documentation/).
Não há mudança de schema, SQLite ou migração. Campos opacos continuam
preservados. Detecção de conflitos por bytes mantém a pequena corrida entre
a conferência final e o replace; não equivale a CAS/lock de escritores externos.

## Validação e limites

- `tests/test_config_session.py`: persistência real, rascunho/baseline,
  consulta de agenda salva, dias vazios, conflitos, remoção, falhas e retry.
- `tests/test_config_gui_main.py`: flag, importações sob demanda, abertura
  sem bloqueadores, erros e parada/espera garantidas na saída do mainloop.
- `tests/test_config_gui.py`: callbacks de CRUD, validação e correção,
  categorias, salvamento, recarga e saída usando widgets simulados com JSON
  e repositório reais. Não valida renderização ou compatibilidade dos widgets.
- `tests/test_config_gui_native.py`: doze smoke tests com CustomTkinter real
  quando instalado, com janelas ocultas; não substituem inspeção visual.

Na retomada de 2026-10-11, as dependências foram instaladas no `.venv` e os doze
smoke tests nativos passaram sem erros de callbacks Tk. Controlador simulado,
sem encerramentos reais. A janela de QA abriu com JSON isolado e alvos vazios,
mas a captura falhou duas vezes por timeout; inspeção visual, DPI e rolagem em
tamanho mínimo continuam pendentes. Não considerar a fase 5 completa entregue.

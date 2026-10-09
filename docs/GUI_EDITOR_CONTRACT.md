# Contrato — editor gráfico de configuração

Continuidade autorizada em 2026-10-09. Unidade complementar às fases 1/2,
independente das respostas ainda vazias Q-HOSTS-01–05. Implementa edição
gráfica de RF01 e parte de RF24; a fase 5 completa permanece pendente.

## Escopo implementado

- `--gui` abre um JSON existente, com o mesmo `--config`/APPDATA da CLI.
  Criação inicial continua explícita em `--init-config`; arquivo inválido
  não é substituído. A flag rejeita outros modos antes de IO/importações.
- Três abas: Horários, Jogos / Apps e Configuração. Janela CustomTkinter na
  thread principal, sem threads de bloqueadores ou bandeja.
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
  Falha ao salvar mantém a janela aberta. Sem bandeja, fechar termina o editor.
- Consulta da agenda a cada segundo usa exclusivamente a última versão
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
A fábrica `_build_app` recebe toolkit, diálogos e sessão para testar os
callbacks com arquivos reais sem dependência gráfica. Diagnóstico, editor
CLI e bloqueador continuam com importações independentes.

CustomTkinter 6.0.0 é fixado em `requirements.txt`, conforme a versão publicada
no [PyPI](https://pypi.org/project/customtkinter/6.0.0/); widgets seguem a
[documentação oficial](https://customtkinter.tomschimansky.com/documentation/).
Não há mudança de schema, SQLite ou migração. Campos opacos continuam
preservados. Detecção de conflitos por bytes mantém a pequena corrida entre
a conferência final e o replace; não equivale a CAS/lock de escritores externos.

## Validação e limites

- `tests/test_config_session.py`: persistência real, rascunho/baseline,
  consulta de agenda salva, dias vazios, conflitos, remoção, falhas e retry.
- `tests/test_config_gui_main.py`: flag, importações sob demanda, ausência
  de bloqueadores e erros de configuração/dependência.
- `tests/test_config_gui.py`: callbacks de CRUD, validação e correção,
  categorias, salvamento, recarga e saída usando widgets simulados com JSON
  e repositório reais. Não valida renderização ou compatibilidade dos widgets.
- `tests/test_config_gui_native.py`: dois smoke tests com CustomTkinter real
  quando instalado, com janelas ocultas; não substituem inspeção visual.

A dependência não pôde ser instalada neste ambiente: downloads do PyPI são
bloqueados. O helper de controle de janelas também estava indisponível. Os
testes nativos foram ignorados; renderização e comportamento nativo ainda
precisam ser verificados no Windows com as dependências instaladas, incluindo
DPI e tamanhos mínimos. Não considerar a fase 5 entregue por esta unidade.

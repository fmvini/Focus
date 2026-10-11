# Contrato — painel semanal e portabilidade da configuração

Unidade autorizada em 2026-10-11 para melhorar funcionalidades e interface,
coordenada pelo Maestro com Backend, Frontend e Banco de dados no Maestri.
Complementa o editor gráfico; os limites de aplicação permanecem no
[contrato gráfico](GUI_EDITOR_CONTRACT.md).

## Painel e edição

- **Visão geral** apresenta a semana atual, de segunda a domingo, com os
  intervalos e minutos planejados por dia e o total semanal do rascunho.
  Sobreposições e adjacências são unidas; trechos noturnos são repartidos no
  dia em que ocorrem, incluindo a continuação do domingo anterior.
  Os controles Semana anterior, Esta semana e Próxima semana permitem
  consultar as mesmas regras recorrentes em outras semanas do calendário.
- Os totais são planejamento em calendário local, sem medição de foco,
  pausa ou confirmação de bloqueio. Alterações não salvas são identificadas.
  A consulta do estado da agenda continua usando o baseline carregado/salvo.
- A orientação inicial indica horários/apps ainda não configurados e oferece
  atalhos para as abas de edição, sem inserir horários ou listas automaticamente.
- **Duplicar** acrescenta uma cópia do horário ao final do rascunho. Não
  ativa uma janela desativada nem salva automaticamente.
- A busca em **Jogos / Apps** filtra a categoria selecionada sem distinguir
  caixa. Editar/remover age sobre o índice original, inclusive com duplicatas;
  filtro sem resultados e categoria vazia recebem mensagens diferentes.

## Importação e exportação

- **Importar JSON** exige confirmação para substituir o rascunho, inclusive
  quando não há alterações pendentes. Validação completa precede a troca.
  O caminho ativo, baseline e arquivo persistido permanecem intactos;
  **Salvar** continua explícito e mantém a detecção de conflitos externos.
- **Exportar JSON** grava uma cópia validada do rascunho em um arquivo novo.
  Arquivos existentes e aliases do arquivo ativo são recusados. A operação
  preserva baseline e alterações pendentes; exportar não equivale a salvar.
- Cancelar seletores não altera a sessão. Falhas de leitura, validação ou
  escrita são apresentadas e preservam o rascunho/configuração ativa.
- Unicode, regras conjuntas de cmdline e campos adicionais são preservados
  pelo mesmo parser/serializador. Nenhum schema novo ou migração é introduzido.
- A cópia é preparada e sincronizada em um temporário no diretório de destino.
  No Windows, `os.rename` publica sem substituir destinos existentes,
  conforme a [documentação Python](https://docs.python.org/3/library/os.html#os.rename).
  Nos demais sistemas, a publicação usa hard link e exige suporte do filesystem;
  uma falha não aciona sobrescrita como alternativa. Não se promete durabilidade
  absoluta após crash, nem há certificação de dispositivos FAT/exFAT nesta suíte.

## APIs e divisão do trabalho

- Backend: `core/agenda_preview.py`, `week_preview(windows, anchor_date)`
  retorna `WeekPreview(start, days, total_minutes)`; cada `DayPreview`
  contém `date`, `intervals` e `minutes`. Intervalos usam `ScheduleInterval`.
  `core/config_editor.py` acrescenta `ConfigDraft.duplicate_window(index)`.
- Banco: `core/config_session.py` acrescenta `import_config(path)` e
  `export_config(path)`; somente a importação altera o rascunho.
  `core/config_portability.py` concentra a publicação exclusiva da cópia.
- Frontend: `ui/config_gui.py` integra painel, duplicação, busca e seletores.
- Maestro: integração, revisão, documentação e commit único com testes.

## Validação

Verificar união diária/semanal, meia-noite, virada da semana, janelas
desativadas, duplicação e índice inválido; importação inválida/Unicode,
exportação sem sobrescrita, falha de escrita e conflito depois de importar;
busca com índices originais, cancelamentos, confirmações e saída com edição.

Resultados efetivamente executados e limites de ambiente ficam no
[registro de desenvolvimento](DEVELOPMENT_LOG.md). Testes simulados de
widgets não certificam renderização, DPI ou interação nativa no Windows.

Resultado integrado de 2026-10-11: 359 descobertos, 353 aprovados e 6 ignorados
(cinco gráficos e um de symlinks); sintaxe Python 3.12 conferida. A restrição
inicial de escrita em `.git/index.lock` foi tratada na retomada com permissão
liberada pelo usuário para o commit local único. Nenhum push realizado.

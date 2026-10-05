# Contrato de implementação — fase 1

Escolhas técnicas do Maestro para a implementação autorizada em 2026-10-05. Regras de produto vinculadas a `DECISIONS.md`; usuário confirmou preservar JSON inválido com erro e salvar dias vazios como janela desativada.

## Fronteiras

Esta fase entrega JSON, agendador e execução de diagnóstico. Não executa encerramento de processos, edição de hosts, notificações ou estatísticas. Bibliotecas externas e interface gráfica entram nas respectivas fases; aqui usar biblioteca padrão Python 3.12+ e `unittest`.

## Tipos compartilhados

`core/models.py`, criado pelo Maestro, define `ScheduleWindow(start: datetime.time, end: datetime.time, days: tuple[int, ...])` e `AppConfig(windows: tuple[ScheduleWindow, ...], extra: dict)`. Horas são civis locais, sem fuso anexado, em precisão de minuto. `days` usa segunda=0 até domingo=6. Configuração valida entradas; agendador recebe os tipos validados.

Campos JSON que não são `windows` serão preservados em `extra` e na gravação, sem aplicar bloqueios nem prometer que estão validados para fases posteriores. Não preencher nomes de executáveis ou caminhos com dados inventados. Uma configuração inicial contém `windows: []`.

## Banco de dados: core/config.py

- `ConfigError`: exceção pública de leitura/validação/gravação.
- `parse_config(data: object) -> AppConfig`: raiz objeto; `windows` lista obrigatória; horários estritos HH:MM, igualdade inválida; dias inteiros únicos 0–6, padrão todos se ausentes. `days: []` desativa. Campos desconhecidos dentro da janela são rejeitados para não perdê-los na gravação; campos adicionais na raiz são preservados.
- `config_to_dict(config: AppConfig) -> dict`: serialização e preservação dos campos extras.
- `load_config(path) -> AppConfig`: ler UTF-8/JSON, rejeitar chaves duplicadas; erros claros; não sobrescrever inválido. Inicialização falha com mensagem e arquivo intacto até correção, conforme resposta do usuário.
- `save_config(path, config) -> None`: validar antes de substituir; escrita temporária no mesmo diretório e substituição atômica; preservar original em falha.
- `default_config_path() -> pathlib.Path`: `%APPDATA%/FocusBlocker/config.json`; ausência de APPDATA é erro, sem fallback silencioso.
- `default_config() -> AppConfig`: nenhuma janela ativa; sem ativar sugestões automaticamente.

## Backend: core/scheduler.py

- `ScheduleInterval(start: datetime.datetime, end: datetime.datetime)`: intervalo efetivo unido.
- `effective_intervals(windows, start_date, end_date) -> tuple[ScheduleInterval, ...]`: incluir ocorrências que intersectem o intervalo de dias inclusivo solicitado, inclusive continuação do dia anterior; unir sobrepostas/adjacentes. Tratar virada de semana e dias pelo início.
- `is_blocking(windows, now: datetime.datetime) -> bool`: início incluído/fim excluído, agenda local, sem pausa nesta fase.
- `next_block_start(windows, now) -> datetime.datetime | None`: próximo início efetivo após agora, sem considerar início de janela interna de um bloco já contínuo; retornar None para agenda vazia ou continuamente bloqueada.

Agendador puro, sem ler relógio real, disco ou Windows. Evitar falsa interrupção ao unir intervalos que cruzem o limite de geração; testar agenda que cobre a semana inteira.

## Frontend: main.py

Diagnóstico da fase 1 por CLI com `--config PATH` opcional (padrão APPDATA), `--init-config` explícito para criar configuração vazia sem sobrescrever existente, `--check`, `--status`, `--at ISO` para consulta reproduzível e `--watch` para reavaliar a cada 5 s até Ctrl+C. Não apresentar estado calculado como bloqueio aplicado ao Windows. Falha deve retornar código não zero com mensagem compreensível e preservar dados. Não criar configurações no perfil real durante testes.

## Propriedade dos arquivos nesta entrega

- Maestro: `core/models.py`, `core/__init__.py`, `tests/__init__.py`, `tests/test_scheduler_reference.py`, `.gitignore`, README e documentação/commit final.
- Banco: `core/config.py`, `tests/test_config.py`.
- Backend: `core/scheduler.py`, `tests/test_scheduler.py`.
- Frontend: `main.py`, `tests/test_main.py`, `tests/test_phase1_integration.py`.

Especialistas não alteram arquivos de outro responsável, docs ou Git. Relatam dúvidas ao Maestro. Todos os testes e arquivos da fase integrarão um único commit local quando a unidade estiver validada.

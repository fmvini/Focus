# Contrato — editor de configuração independente

Escolha técnica do Maestro em 2026-10-08 para o desenvolvimento autorizado.
Complementa as fases 1/2 e prepara a edição prevista em RF01/RF24; não entrega
a bandeja/GUI da fase 5. Não depende das decisões abertas de sites, pausa ou
medição de foco. Regras de produto permanecem em DECISIONS/USER_ANSWERS.

## Entrega

`--edit-config` abre um editor local interativo pela CLI para um JSON existente.
Permite listar/adicionar/alterar/remover horários e editar as quatro listas de
processos já tipadas, sem editar JSON manualmente. Alterações ficam em um
rascunho até Salvar; Sair descarta o rascunho. A criação inicial continua
explícita em `--init-config`. O editor não importa nem instancia bloqueadores,
não toca hosts, não cria estatísticas e não ativa um loop de aplicação.

Se outro processo estiver aplicando a configuração, ele poderá observar o novo
JSON no próximo ciclo. Não oferecer promessa de isolamento em relação a esse
processo. Dias vazios desativam; todos os dias são padrão para um novo horário.
Safelist adicional não remove proteções obrigatórias. Cmdline exige executável
e trecho literal juntos, com validação já existente. Não preencher sugestões
ou alterar campos opacos como sites/dev_apps/pausa.

## APIs e responsáveis

### Banco de dados — core/config_repository.py

- `ConfigConflictError(ConfigError)`: arquivo alterado/removido desde a leitura.
- `ConfigSnapshot`: dataclass congelado, campos `config: AppConfig`,
  `contents: bytes` (bytes exatos da leitura).
- `read_snapshot(path) -> ConfigSnapshot`: validar a mesma leitura capturada,
  incluindo UTF-8 estrito, chaves duplicadas e constantes JSON inválidas, sem
  reabrir para validar uma versão diferente. Pode reutilizar helpers de config.
- `save_snapshot(path, config, snapshot) -> ConfigSnapshot`: validar/serializar
  antes de efeitos, comparar bytes atuais com snapshot; detectar alteração ou
  remoção e preservar destino. Reusar gravação temporária/fsync/replace da fase
  1, com uma conferência adicional imediatamente antes do replace. Sem backup,
  sobrescrita forçada, merge automático ou alteração de políticas de criação.
  Devolver baseline correspondente aos bytes publicados por esta gravação,
  sem adotar bytes de um escritor posterior como se fossem desta gravação.
- Concorrência externa é detectada por comparação, não garantida por CAS do
  sistema operacional. Documentar a pequena corrida entre conferência/replace.
- Banco pode alterar `core/config.py` para extrair/reutilizar parsing e escrita
  sem quebrar APIs existentes; testes em `tests/test_config_repository.py`.

### Backend — core/config_editor.py

- `ConfigDraft(config: AppConfig)` mantém rascunho validado e independente dos
  objetos/extras recebidos; propriedade `config` devolve cópia defensiva.
- `add_window(start: str, end: str, days=None)`; `update_window(index, start,
  end, days=None)`; `remove_window(index)`. Dias None usa todos; iterable de
  inteiros convertido em lista e validado sem converter bool em int.
- `add_rule(field: str, value)`; `update_rule(field, index, value)`;
  `remove_rule(field, index)`. Fields só `block_exes`, `block_folders`,
  `safelist_exes`, `block_cmdline`; cmdline recebe objeto executable/contains.
- Índices são zero-based internos, int estrito, não negativos e dentro da
  lista. Erro levanta ConfigError, mantendo rascunho anterior intacto.
- Validação reutiliza `parse_config/config_to_dict`; preserves extras e ordem;
  não deduplica listas nem infere nomes/caminhos. Sem IO/Windows/relógio.
- Testes em `tests/test_config_editor.py`. Não editar arquivo do Banco.

### Frontend — ui/config_cli.py e main.py

- `run_config_editor(path, *, input_fn=None, output_fn=None) -> int`: defaults
  resolvidos em execução, para doubles. Usa repository para carga/salvamento e
  ConfigDraft para CRUD. Menu em português com índices humanos a partir de 1;
  escolha/lista/validação inválida mostra erro e continua sem gravar.
- Salvar confirma somente após publicação; falha mantém rascunho para nova
  tentativa. Conflito informa recarregar, sem sobrescrever; Recarregar descarta
  rascunho explicitamente. Sair/EOF/Ctrl+C descarta alterações não salvas.
- Entrada de dias: vazio = todos; `nenhum` = lista vazia; números 0–6 separados
  por vírgula. Operações de janela têm campos individuais HH:MM/dias; cmdline
  tem dois prompts; não pedir ao usuário JSON bruto.
- `--edit-config` rejeita combinação com qualquer modo/flag de execução além
  de `--config`, antes de IO. Importação do editor é lazy; diagnóstico existente
  continua sem novas dependências. Códigos: 0 sair normalmente/EOF/Ctrl+C,
  1 falha inicial, 2 flags inválidas. Salvar não encerra o editor.
- Criar `ui/__init__.py` e testes `tests/test_config_cli.py` e
  `tests/test_config_editor_main.py`. Não instalar dependências nem editar docs.

## Integração e aceite

Maestro mantém docs/README/requirements e realiza integração. Especialistas
não fazem commits ou push, nem editam arquivos alheios. Testes acompanhantes
e log ficam no mesmo commit da funcionalidade completa.

Validar CRUD, erros sem efeitos, extras preservados, cópias defensivas,
roundtrip, conflito/remoção externa, falhas de replace e sessão interativa
Salvar/Sair/EOF/Ctrl+C. Usar arquivos UUID isolados no workspace, sem perfil
real ou processos reais. Executar suíte existente além da unidade nova.
CustomTkinter/pystray continuam a stack definida para a futura GUI; não
substituir por outra biblioteca nem alegar validação gráfica nesta entrega.

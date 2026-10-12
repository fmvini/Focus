# Contrato — comparação de alterações pendentes

Evolução de edição em 2026-10-11, independente de sites/pausa/avisos.
Compara o rascunho com a última configuração carregada/salva em memória.
Não relê disco, simula bloqueios, grava, mescla ou contorna conflitos.

## Núcleo e apresentação

- `core/config_diff.py`: `diff_config(baseline: AppConfig | None, draft:
  AppConfig) -> ConfigDiff`, com `ConfigDiff(is_new, changes, extras_changed)`
  e `ConfigChange(field, kind, before_index, after_index, before, after)`.
  Dataclasses frozen, tuple/str sem referências mutáveis às entradas.
- Fields na ordem windows/block_exes/block_folders/safelist_exes/block_cmdline;
  kinds insert/delete/replace. Índices originais zero-based por lado, None
  quando ausente. Prefixo/sufixo exatamente iguais são preservados antes
  de SequenceMatcher sobre o miolo, com autojunk desativado; replace pareia
  posições e mantém sobras como exclusões/inclusões. Ordem, duplicatas,
  caixa, dias e trechos literais são preservados. Reordenar pode aparecer
  como remoção/inclusão; não promete identificar a intenção da edição ou
  produzir o menor script possível.
- Baseline None indica primeiro arquivo, comparando contra configuração
  vazia, mesmo sem itens. Extras usam igualdade JSON tipada compartilhada,
  mas o resultado contém somente um indicador, sem expor seus valores.
- `ui/config_diff_presenter.py`: `DiffView(title, detail)` frozen e
  `format_config_diff(report)`. Português, índices humanos por lado e
  Antes/Depois. Limites explícitos de 100 mudanças/1000 caracteres por
  valor, com aviso de excedentes/truncamento; controles escapados e espaços
  literais preservados. Sem IO, GUI, relógio ou consultas de processos.
- Núcleo/presenter esperam modelos válidos e extras JSON acíclicos; não
  revalidam variáveis de pastas, ambiente ou schema. A validação/persistência
  existente continua responsável por rejeitar conteúdo inválido.

## Acesso e efeitos

- GUI: botão **Ver alterações** em Configuração abre modal de leitura,
  redimensionável e rolável. Fechar/Escape/cancelar preservam rascunho,
  histórico, baseline, bytes e motor. Respeita seletor/modal/saída e os
  callbacks de lifecycle existentes; sem wait/join em callback.
- CLI `--edit-config`: menu **8 ver alterações** imprime o mesmo presenter,
  sem alterar as opções anteriores. Depois de Undo/Redo/Save/Reload, a
  próxima consulta compara as versões atuais da sessão.
- Não há confirmação obrigatória nova ao salvar, nem edição automática.
  Alteração externa pode causar conflito mesmo após a comparação; salvar
  continua verificando bytes pelo repositório. Novo arquivo vazio aparece
  explicitamente como criação pendente.

## Integração

Backend possui núcleo/testes; Banco possui presenter/testes; Frontend possui
GUI/testes GUI; Maestro possui integração CLI, docs, validação e commit
conjunto. Não fazer commits intermediários ou exclusivamente de testes.
Usar somente fixtures UUID, sem processos/hosts/configuração do usuário.
Revisões de código e widgets ocultos não substituem inspeção visual/DPI.

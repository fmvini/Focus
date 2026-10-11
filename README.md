# Focus Blocker

Aplicativo em desenvolvimento para Windows 10/11. Configuração JSON com editores de terminal e gráfico, avaliação de horários e bloqueador de processos com controle pela janela ou CLI. Sites, avisos/pausa, bandeja, estatísticas e instalador continuam nas próximas fases. Widgets nativos foram testados; inspeção visual, DPI e encerramentos reais ainda exigem aceite dedicado.

## Preparar e executar

Requer Python 3.12+. O diagnóstico usa a biblioteca padrão; o bloqueador usa psutil e a janela usa CustomTkinter. Use o Python do ambiente virtual para executar a interface e o bloqueador.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
python main.py --config .\data\config.json --init-config
python main.py --config .\data\config.json --edit-config
python main.py --config .\data\config.json --check
python main.py --config .\data\config.json --status
python main.py --config .\data\config.json --status --at 2026-10-05T09:00:00
python main.py --config .\data\config.json --watch
```

Sem `--config`, o caminho é `%APPDATA%\FocusBlocker\config.json`. A criação é explícita por `--init-config`, sem janela ou regra ativa, e não sobrescreve arquivo existente. `--watch` sozinho consulta a agenda a cada 5 segundos; Ctrl+C encerra. Esses comandos são diagnóstico, sem encerramentos.

Para configurar sem editar JSON, use `--edit-config` depois de criar o arquivo. Exemplo de JSON escolhido apenas para demonstrar uma janela noturna de segunda-feira:

```json
{
  "windows": [
    {"start": "22:00", "end": "02:00", "days": [0]}
  ]
}
```

Segunda=0 até domingo=6; o dia é o de início da janela. Segunda 22:00–02:00 inclui terça até 02:00. Início é incluído e fim excluído; início igual ao fim é inválido. Janelas sobrepostas/adjacentes são unidas. `days: []` desativa; sem `days`, usam-se todos os dias. Arquivo inválido gera erro e é preservado para correção. `--check` valida agenda e regras de processos; outros campos adicionais continuam preservados, sem execução.

## Editar horários e regras

### Editor gráfico

Após instalar as dependências, crie a configuração se ela ainda não existir e abra a janela:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
# Apenas na primeira vez; --init-config recusa sobrescrever um arquivo existente.
.\.venv\Scripts\python.exe main.py --config .\data\config.json --init-config
.\.venv\Scripts\python.exe main.py --config .\data\config.json --gui
```

A aba **Horários** permite adicionar, editar e remover janelas com seleção dos dias da semana. Todos os dias vêm selecionados em um novo horário; desmarcar todos desativa a janela. **Jogos / Apps** reúne executáveis, pastas, proteção adicional e regras conjuntas de linha de comando; pastas também podem ser escolhidas pelo seletor. **Configuração** mostra o arquivo e explica o salvamento.

**Visão geral** mostra os horários planejados da semana atual, de segunda a domingo, com total por dia e por semana. A prévia acompanha o rascunho e identifica alterações não salvas; horários sobrepostos são contados uma vez e trechos após meia-noite aparecem no dia correspondente. Esses totais representam planejamento, sem medição de foco. A tela também orienta o primeiro uso e oferece atalhos para configurar horários e aplicativos.

Em **Horários**, **Duplicar** copia uma janela para ajustar outra faixa rapidamente. Em **Jogos / Apps**, a busca filtra as regras da categoria selecionada. Em **Configuração**, **Importar JSON** substitui o rascunho após confirmação e validação; clique em **Salvar** para publicar. **Exportar JSON** cria uma cópia do rascunho em um arquivo novo, preservando alterações pendentes e recusando sobrescrever arquivos existentes. Ver [contrato desta evolução](docs/CONFIG_EVOLUTION_CONTRACT.md).

**Adicionar/Aplicar alteração** atualiza apenas o rascunho. **Salvar** (Ctrl+S) grava o JSON. **Recarregar** (Ctrl+R) descarta a edição após confirmação. Ao fechar com alterações pendentes, você pode salvar, descartar ou cancelar a saída. Erros preservam o rascunho; conflito externo exige recarga. A consulta da agenda usa a última versão carregada/salva, sem incluir mudanças pendentes e sem reler automaticamente edições externas.

`--gui` combina somente com `--config` e abre com o motor parado. **Iniciar** exige um rascunho sem alterações pendentes e confirmação: aplicativos elegíveis podem ser encerrados sem salvar seu estado. O motor lê o JSON salvo a cada ciclo; edições externas também são observadas. **Parar** impede novas ações, aguarda a chamada em andamento e não reabre aplicativos. Ao fechar, a janela aguarda seu motor terminar; cancelar a saída mantém a execução.

O cabeçalho mostra o estado do motor, a última avaliação da agenda, o último ciclo e encerramentos confirmados, pendências e falhas. Esses dados ficam separados da agenda carregada pelo editor e da prévia do rascunho. JSON inválido/ausente ou erro global interrompe novas ações; corrija a causa e clique em Iniciar novamente quando o worker anterior terminar. Um bloqueador CLI iniciado separadamente continua independente da janela. Sites, pausa, bandeja e estatísticas não fazem parte desta unidade. Ver [contrato do controle gráfico](docs/PROCESS_GUI_CONTRACT.md).

### Editor de terminal

`--edit-config` abre um menu em português para listar, adicionar, alterar e remover horários e regras de processos. As alterações ficam em um rascunho até **Salvar**; **Sair**, EOF ou Ctrl+C descartam o que não foi salvo. Dias: segunda=0 até domingo=6, separados por vírgula; vazio seleciona todos e `nenhum` desativa o horário. Números de itens começam em 1. Regras de cmdline pedem executável e trecho literal em campos separados.

Erros de validação ou gravação mantêm o rascunho para correção/nova tentativa. Se o arquivo mudar ou for removido externamente, salvar informa conflito; **Recarregar** descarta o rascunho e lê a versão atual. Campos adicionais são preservados. A gravação usa temporário, fsync e substituição atômica, com comparação dos bytes antes da preparação e novamente antes da substituição. Há uma pequena corrida entre a última conferência e a substituição; não há lock entre editores externos nem mesclagem automática.

O editor combina somente com `--config` e não inicia bloqueadores. Um `--watch --apply-processes` já em execução poderá ler a configuração salva no próximo ciclo. Sites, apps/domínios de estudo, pausa e avisos ainda não são editáveis por esse menu. A safelist adicional não remove as proteções obrigatórias. Ver [contrato do editor](docs/CONFIG_EDITOR_CONTRACT.md).

## Aplicar bloqueio de processos

Escolha horários e listas por um dos editores ou pelo JSON antes de executar. Use Iniciar na janela ou o comando abaixo. Os campos opcionais `block_exes`, `block_folders`, `safelist_exes` e `block_cmdline` são listas; quando ausentes, ficam vazios. Bandeja continua pendente. Exemplo de regra conjunta, para adicionar ao objeto de configuração somente se você quiser bloquear Minecraft Java:

```json
"block_cmdline": [{"executable": "javaw.exe", "contains": ".minecraft"}]
```

```powershell
.\.venv\Scripts\python.exe main.py --config .\data\config.json --watch --apply-processes
```

Esse comando encerra processos elegíveis somente durante as janelas, usando o relógio real. Não combina com `--at`, `--init-config` ou `--check`; `--apply-processes` exige `--watch`. Configuração é recarregada por ciclo; erro interrompe novas ações, sem substituir o arquivo ou reutilizar configuração antiga. Ciclos usam prazo de 5 s sem sobreposição; inspeções demoradas podem atrasá-los. Ctrl+C para a varredura e não reabre aplicativos encerrados. Sites/hosts não são alterados.

Nomes `.exe` comparam por igualdade sem distinguir caixa. Pastas devem ser absolutas Windows, aceitam `%VAR%` conhecida e incluem subpastas pelo destino resolvido. Links/junctions não verificáveis preservam o processo. Trechos de cmdline são literais sem distinguir caixa, dentro de cada argumento, e exigem o executável correspondente. A antiga lista de strings em `block_cmdline` é rejeitada com erro para correção explícita, sem migração por inferência.

Proteções obrigatórias precedem as listas de bloqueio e não podem ser removidas pela safelist adicional. Incluem o próprio app, ancestrais, Windows/contas de sistema e catálogo de IDEs, terminais, navegadores e ferramentas indicadas. Dados inacessíveis preservam o alvo e geram diagnóstico. O catálogo não reconhece universalmente aplicativos renomeados ou todas as instalações portáteis; inclua ferramentas adicionais em `safelist_exes` antes de bloquear suas pastas. No Windows, encerramento via psutil é forçado; não garante salvar o estado do jogo. Ver [contrato e fontes técnicas](docs/PHASE2_CONTRACT.md).

Somente saída confirmada após solicitação aceita gera evento de tentativa; pedidos pendentes/falhas não contam. Eventos ficam em memória nesta fase, sem SQLite/histórico persistente.

## Verificar

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Testes usam relógios/adaptadores controlados e diretórios isolados; não alteram hosts nem encerram aplicativos do usuário. Ver [documentação de desenvolvimento](docs/README.md), [contratos da fase 1](docs/PHASE1_CONTRACT.md), [fase 2](docs/PHASE2_CONTRACT.md) e [registro de desenvolvimento](docs/DEVELOPMENT_LOG.md).

Os oito smoke tests com widgets nativos são executados quando CustomTkinter está instalado, com janelas ocultas e controlador simulado. Cobrem formulários, busca, importação/exportação, início/parada e limpeza de callbacks. Sem essa dependência, são marcados como ignorados. As dependências foram instaladas e os oito testes passaram neste ambiente; a captura da janela de QA falhou por timeout. A inspeção visual e de DPI deve ser feita abrindo `--gui` no Windows, incluindo a rolagem em 880×660.

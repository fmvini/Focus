# Focus Blocker

Aplicativo em desenvolvimento para Windows 10/11. Configuração JSON, avaliação de horários e bloqueador de processos por CLI. Sites, avisos/pausa, bandeja, interface gráfica, estatísticas e instalador continuam nas próximas fases.

## Preparar e executar

Requer Python 3.12+. O diagnóstico usa a biblioteca padrão; o bloqueador usa psutil, instalado no ambiente virtual do projeto.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
python main.py --config .\data\config.json --init-config
python main.py --config .\data\config.json --check
python main.py --config .\data\config.json --status
python main.py --config .\data\config.json --status --at 2026-10-05T09:00:00
python main.py --config .\data\config.json --watch
```

Sem `--config`, o caminho é `%APPDATA%\FocusBlocker\config.json`. A criação é explícita por `--init-config`, sem janela ou regra ativa, e não sobrescreve arquivo existente. `--watch` sozinho consulta a agenda a cada 5 segundos; Ctrl+C encerra. Esses comandos são diagnóstico, sem encerramentos.

Para configurar, editar o JSON enquanto a interface gráfica ainda não estiver disponível. Exemplo escolhido apenas para demonstrar uma janela noturna de segunda-feira:

```json
{
  "windows": [
    {"start": "22:00", "end": "02:00", "days": [0]}
  ]
}
```

Segunda=0 até domingo=6; o dia é o de início da janela. Segunda 22:00–02:00 inclui terça até 02:00. Início é incluído e fim excluído; início igual ao fim é inválido. Janelas sobrepostas/adjacentes são unidas. `days: []` desativa; sem `days`, usam-se todos os dias. Arquivo inválido gera erro e é preservado para correção. `--check` valida agenda e regras de processos; outros campos adicionais continuam preservados, sem execução.

## Aplicar bloqueio de processos

Escolha horários e listas no JSON antes de executar. Os campos opcionais `block_exes`, `block_folders`, `safelist_exes` e `block_cmdline` são listas; quando ausentes, ficam vazios. A interface para editar essas listas será entregue na fase 5. Exemplo de regra conjunta, para adicionar ao objeto de configuração somente se você quiser bloquear Minecraft Java:

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

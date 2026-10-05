# Focus Blocker

Aplicativo em desenvolvimento para Windows 10/11. A primeira fase entrega configuração JSON e avaliação de horários. Bloqueadores de processos/sites, bandeja, interface gráfica, estatísticas e instalador serão entregues nas fases seguintes.

## Executar a fase 1

Requer Python 3.12+; esta fase usa somente a biblioteca padrão.

```powershell
python main.py --config .\data\config.json --init-config
python main.py --config .\data\config.json --check
python main.py --config .\data\config.json --status
python main.py --config .\data\config.json --status --at 2026-10-05T09:00:00
python main.py --config .\data\config.json --watch
```

Sem `--config`, o caminho é `%APPDATA%\FocusBlocker\config.json`. A criação é explícita por `--init-config`, com nenhuma janela ativa, e não sobrescreve arquivo existente. `--watch` reavalia a agenda a cada 5 segundos; Ctrl+C encerra. Os resultados indicam apenas o estado calculado da agenda nesta fase.

Para configurar, editar o JSON enquanto a interface gráfica ainda não estiver disponível. Exemplo escolhido apenas para demonstrar uma janela noturna de segunda-feira:

```json
{
  "windows": [
    {"start": "22:00", "end": "02:00", "days": [0]}
  ]
}
```

Segunda=0 até domingo=6; o dia é o de início da janela. Segunda 22:00–02:00 inclui terça até 02:00. Início é incluído e fim excluído; início igual ao fim é inválido. Janelas sobrepostas/adjacentes são unidas. `days: []` desativa a janela; sem `days`, usam-se todos os dias. Arquivo inválido gera erro e é preservado para correção. Campos adicionais são preservados, mas ainda não são aplicados nesta fase.

## Verificar

```powershell
python -m unittest discover -s tests -v
```

Testes usam relógios controlados e diretórios temporários; não alteram hosts nem encerram aplicativos. Ver [documentação de desenvolvimento](docs/README.md), [contratos da fase 1](docs/PHASE1_CONTRACT.md) e [registro de desenvolvimento](docs/DEVELOPMENT_LOG.md).

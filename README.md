# Focus Blocker

Aplicativo em desenvolvimento para Windows 10/11. Configuração JSON com editores de terminal e gráfico, avaliação de horários, bloqueador de processos e bandeja com controle pela janela. Sites, avisos/pausa, estatísticas e instalador continuam nas próximas fases. Widgets nativos foram testados; inspeção visual/DPI ainda exige aceite dedicado.

## Preparar e executar

Requer Python 3.12+. O diagnóstico usa a biblioteca padrão; o bloqueador usa psutil e a janela usa CustomTkinter. Use o Python do ambiente virtual para executar a interface e o bloqueador.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
python main.py --config .\data\config.json --init-config
python main.py --config .\data\config.json --edit-config
python main.py --config .\data\config.json --check
python main.py --config .\data\config.json --review
python main.py --config .\data\config.json --status
python main.py --config .\data\config.json --status --at 2026-10-05T09:00:00
python main.py --config .\data\config.json --watch
```

Sem `--config`, o caminho é `%APPDATA%\FocusBlocker\config.json`. Pela CLI, a criação é explícita por `--init-config`, sem janela ou regra ativa, e não sobrescreve arquivo existente. Pela GUI, o arquivo ausente é criado somente ao Salvar. `--watch` sozinho consulta a agenda a cada 5 segundos; Ctrl+C encerra. Esses comandos são diagnóstico, sem encerramentos.

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

Após instalar as dependências, abra a janela:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py --config .\data\config.json --gui
```

A aba **Horários** permite adicionar, editar e remover janelas com seleção dos dias da semana. Todos os dias vêm selecionados em um novo horário; desmarcar todos desativa a janela. **Jogos / Apps** reúne executáveis, pastas, proteção adicional e regras conjuntas de linha de comando; pastas também podem ser escolhidas pelo seletor. **Configuração** mostra o arquivo e explica o salvamento.

Em **Executáveis** ou **Proteção adicional**, **Selecionar .exe…** permite escolher vários arquivos e adicionar os nomes ao rascunho. A regra vale pelo nome em qualquer pasta, não apenas pelo caminho escolhido. O lote inteiro é validado antes da inclusão; nomes equivalentes não são duplicados. Cancelar mantém as regras. Clique em **Salvar** para gravar; selecionar arquivos não os executa nem inicia o motor.

Na primeira execução, se o arquivo estiver ausente, a janela prepara um rascunho vazio. Escolha horários e regras, ou importe um JSON; clique em **Salvar** para criar a configuração. Fechar e descartar deixa o destino ausente. Um arquivo existente inválido é preservado e exige correção. A primeira gravação recusa qualquer destino criado por outra ferramenta enquanto você editava.

As sugestões de jogos e launchers começam desmarcadas. Escolha quais adicionar ao rascunho; elas não detectam instalações nem iniciam o bloqueio. Minecraft Java usa `javaw.exe` junto ao trecho `.minecraft`, preservando a regra conjunta. Depois de salvar, **Iniciar** ainda exige confirmação. Ver [contrato da primeira configuração](docs/INITIAL_SETUP_CONTRACT.md).

**Visão geral** mostra os horários planejados da semana atual, de segunda a domingo, com total por dia e por semana. A prévia acompanha o rascunho e identifica alterações não salvas; horários sobrepostos são contados uma vez e trechos após meia-noite aparecem no dia correspondente. Esses totais representam planejamento, sem medição de foco. A tela também orienta o primeiro uso e oferece atalhos para configurar horários e aplicativos.

A **Revisão do rascunho** aponta horários/regras repetidos, nomes de bloqueio que também são protegidos e a abrangência de `javaw.exe` por nome. Os apontamentos usam somente a configuração; não verificam processos ou instalações, não alteram listas e não impedem salvar ou iniciar. Corrija o que desejar nas abas correspondentes. As demais proteções do motor continuam valendo.

Para localizar um item, escolha um apontamento numerado e clique em **Ir para item**. A interface abre a categoria, limpa a busca e destaca a linha original; use **Editar** se quiser alterá-la. Navegar não grava nem muda o rascunho. Escolhas antigas são recusadas após mudanças na edição. Ver [contrato da navegação](docs/REVIEW_NAVIGATION_CONTRACT.md).

O comando **`--review`** oferece essa revisão para o JSON salvo, sem depender da interface gráfica ou de psutil. Combina somente com `--config`, não altera o arquivo e apresenta todos os apontamentos. Configuração válida retorna 0 mesmo com apontamentos informativos; erros de leitura/validação retornam 1 e argumentos incompatíveis, 2.

Em **Horários**, **Duplicar** copia uma janela para ajustar outra faixa rapidamente. Em **Jogos / Apps**, a busca filtra as regras da categoria selecionada. Em **Configuração**, **Importar JSON** substitui o rascunho após confirmação e validação; clique em **Salvar** para publicar. **Exportar JSON** cria uma cópia do rascunho em um arquivo novo, preservando alterações pendentes e recusando sobrescrever arquivos existentes. Ver [contrato desta evolução](docs/CONFIG_EVOLUTION_CONTRACT.md).

Em **Jogos / Apps → Ordem visual**, escolha Cadastro, Nome A–Z ou Nome Z–A para organizar a lista junto com a busca. Essa preferência vale só nesta janela: não altera a ordem salva, o rascunho ou o motor. Editar, remover e navegar pela revisão continuam atingindo a regra original, inclusive com duplicatas. Ver [contrato da visualização](docs/RULE_LIST_VIEW_CONTRACT.md).

**Desfazer** e **Refazer** restauram até 50 edições do rascunho nesta sessão, incluindo horários, regras, sugestões e seleção de arquivos. Os atalhos são **Ctrl+Z/Ctrl+Y** fora de formulários/campos de texto. **Salvar** mantém o histórico; **Importar** ou **Recarregar** bem-sucedidos o reiniciam. A versão restaurada só é gravada quando você salvar; o histórico não é persistido ao fechar.

Alterações em campos extras preservam a distinção entre valores JSON como `true`, `1` e `1.0` e contam como edição pendente. Seletores de arquivos/pastas mantêm a janela acessível; enviar à bandeja exige concluir a seleção e clicar novamente.

Em **Configuração → Ver alterações**, compare o rascunho com a última versão carregada/salva: inclusões, remoções, Antes/Depois e mudanças em campos extras. O modal permite redimensionar e rolar; a apresentação limita 100 mudanças/1000 caracteres por valor e informa excedentes. A CLI oferece a mesma consulta no menu **8** de `--edit-config`. Consultar não grava nem relê o disco; Salvar continua detectando conflitos externos. Ver [contrato da comparação](docs/CONFIG_DIFF_CONTRACT.md).

**Adicionar/Aplicar alteração** atualiza apenas o rascunho. **Salvar** (Ctrl+S) grava o JSON. **Recarregar** (Ctrl+R) descarta a edição após confirmação. Ao fechar com alterações pendentes, você pode salvar, descartar ou cancelar a saída. Erros preservam o rascunho; conflito externo exige recarga. A consulta da agenda usa a última versão carregada/salva, sem incluir mudanças pendentes e sem reler automaticamente edições externas.

`--gui` combina somente com `--config` e abre com o motor parado. **Iniciar** exige um rascunho sem alterações pendentes e confirmação: aplicativos elegíveis podem ser encerrados sem salvar seu estado. O motor lê o JSON salvo a cada ciclo; edições externas também são observadas. **Parar** impede novas ações, aguarda a chamada em andamento e não reabre aplicativos. Ao fechar, a janela aguarda seu motor terminar; cancelar a saída mantém a execução.

O cabeçalho mostra o estado do motor, a última avaliação da agenda, o último ciclo e encerramentos confirmados, pendências e falhas. Esses dados ficam separados da agenda carregada pelo editor e da prévia do rascunho. JSON inválido/ausente ou erro global interrompe novas ações; corrija a causa e clique em Iniciar novamente quando o worker anterior terminar. Um bloqueador CLI iniciado separadamente continua independente da janela. Sites, pausa e estatísticas não fazem parte desta unidade. Ver [contrato do controle gráfico](docs/PROCESS_GUI_CONTRACT.md).

A consulta da agenda carregada também mostra o **fim da janela em andamento**, considerando a união de horários, a meia-noite e a virada da semana. Se a agenda cobrir a semana inteira sem interrupção, isso aparece como cobertura contínua. A informação segue a configuração carregada/salva, não o rascunho nem uma promessa de reabrir aplicativos.

**Enviar à bandeja** oculta a janela após preparar o ícone, mantendo o rascunho e o motor. O menu oferece **Mostrar Focus**, **Parar motor** e **Sair**; iniciar continua exigindo confirmação na janela. Sair restaura a janela para resolver alterações pendentes; cancelar mantém a execução. Fechar pelo X continua saindo, com parada ordenada. Se a bandeja falhar, a janela permanece visível ou é restaurada.

Uma segunda GUI para o mesmo caminho de configuração informa que já existe uma instância, sem iniciar outro motor. A guarda vale por sessão Windows e caminho resolvido; não coordena CLI, hardlinks ou sessões diferentes. Não há ativação automática da primeira janela. Ver [contrato da bandeja e instância](docs/TRAY_CONTRACT.md).

### Editor de terminal

`--edit-config` abre um menu em português para listar, adicionar, alterar e remover horários e regras de processos. As alterações ficam em um rascunho até **Salvar**; **Sair**, EOF ou Ctrl+C descartam o que não foi salvo. Dias: segunda=0 até domingo=6, separados por vírgula; vazio seleciona todos e `nenhum` desativa o horário. Números de itens começam em 1. Regras de cmdline pedem executável e trecho literal em campos separados.

Erros de validação ou gravação mantêm o rascunho para correção/nova tentativa. Se o arquivo mudar ou for removido externamente, salvar informa conflito; **Recarregar** descarta o rascunho e lê a versão atual. Campos adicionais são preservados. A gravação usa temporário, fsync e substituição atômica, com comparação dos bytes antes da preparação e novamente antes da substituição. Há uma pequena corrida entre a última conferência e a substituição; não há lock entre editores externos nem mesclagem automática.

O editor combina somente com `--config` e não inicia bloqueadores. Um `--watch --apply-processes` já em execução poderá ler a configuração salva no próximo ciclo. Sites, apps/domínios de estudo, pausa e avisos ainda não são editáveis por esse menu. A safelist adicional não remove as proteções obrigatórias. Ver [contrato do editor](docs/CONFIG_EDITOR_CONTRACT.md).

No menu principal, **6 desfazer** e **7 refazer** restauram edições em memória. Salvar continua explícito; Recarregar descarta o rascunho e seu histórico.

## Aplicar bloqueio de processos

Escolha horários e listas por um dos editores ou pelo JSON antes de executar. Use Iniciar na janela ou o comando abaixo. Os campos opcionais `block_exes`, `block_folders`, `safelist_exes` e `block_cmdline` são listas; quando ausentes, ficam vazios. Exemplo de regra conjunta, para adicionar ao objeto de configuração somente se você quiser bloquear Minecraft Java:

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

Os trinta e um smoke tests com widgets nativos são executados quando CustomTkinter está instalado, com janelas ocultas e controlador/bandeja simulados. Cobrem ordenação visual, navegação dos apontamentos, comparação de alterações, histórico, primeira configuração, revisão do rascunho, agenda, seletores, sugestões, formulários, busca, portabilidade, motor, bandeja e limpeza de callbacks. Sem essa dependência, são marcados como ignorados. A suíte completa no Windows teve 747 testes: 746 aprovados e um skip de symlink por permissão, tanto no Python 3.14.6 quanto no Python 3.12.14 isolado em `.qa/`. O smoke de ícone real passou no desktop fora do sandbox; se o Shell recusar NIM_ADD, o teste falha explicitamente. Ver [evidências e reprodução](docs/TEST_PLAN.md). A captura da janela de QA falhou por timeout; inspeção visual e de DPI permanece pendente, incluindo a rolagem em 880×660.

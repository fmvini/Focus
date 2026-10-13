# Roteiro de aceite visual, DPI e acessibilidade do editor

**Base:** `79607c9` — busca com reconstrução diferida. **Preparado em:** 2026-10-13.
**Estado:** roteiro preparado; os casos de aceite abaixo ainda **não concluídos**.
Uma tentativa diagnóstica parcial, com captura indisponível, está registrada
em [GUI_ACCEPTANCE_RESULTS.md](GUI_ACCEPTANCE_RESULTS.md); ela não aprova a matriz.
Executor previsto: Maestro, em uma única sessão coordenada, com aberturas sequenciais e nenhuma GUI/suíte concorrente.

## 1. Escopo e fontes

Inspecionar o editor existente, com motor parado, no tamanho mínimo lógico
880×660: primeira configuração, quatro abas, busca, seleção FULL, páginas,
revisão, teclado/foco, rolagem, diálogos e retorno da bandeja. O processo abre
normalmente em 1000×740; reduzir ao mínimo faz parte do ensaio.

Fontes lidas: [log](DEVELOPMENT_LOG.md), [respostas](USER_ANSWERS.md),
[plano de testes](TEST_PLAN.md), [contrato gráfico](GUI_EDITOR_CONTRACT.md)
e [fluxos](UI_FLOWS.md). Detalhes: [primeiro uso](INITIAL_SETUP_CONTRACT.md),
[busca](RULE_SEARCH_DEBOUNCE_CONTRACT.md), [paginação](RULE_PAGINATION_CONTRACT.md),
[seleção](RULE_BULK_REMOVE_CONTRACT.md), [revisão](REVIEW_NAVIGATION_CONTRACT.md)
e [bandeja](TRAY_CONTRACT.md).

Os contratos atuais prevalecem sobre propostas históricas de UI_FLOWS:
abas **Visão geral / Horários / Jogos / Apps / Configuração**; menu real
**Mostrar Focus / Parar motor / Sair**. Sites, pausa, avisos, estatísticas,
instalador e perguntas vazias de USER_ANSWERS ficam fora deste aceite.
Os critérios de acessibilidade abaixo são verificações técnicas desta unidade,
sem definir novas decisões de produto ou declarar conformidade normativa.

Suítes com widgets ocultos e revisões estáticas anteriores não aprovam qualquer
célula desta matriz. Não fazer benchmark nem usar a espera de 200 ms como
limite de resposta, medição de desempenho ou comprovação de RNF01.

## 2. Preparação reproduzível — execução futura pelo Maestro

### 2.1 Isolamento e fixtures

Conferir `git rev-parse HEAD` e `git status --short`; registrar desvios de
`79607c9`, inclusive mudanças locais. Usar o ambiente existente, sem instalar
ou atualizar dependências durante o aceite. Sempre passar `--config` explícito;
não usar o JSON de APPDATA, `--watch`, `--apply-processes` ou **Iniciar**.
As fixtures principais têm agenda desativada. A fixture suplementar de
integridade contém dias ativos apenas para consulta da agenda; todas as
aberturas mantêm o motor parado e não autorizam **Iniciar**.

O bloco abaixo é uma receita de preparação, separada do aceite visual. Na raiz do repositório, cria
somente uma pasta UUID em `.qa/`, JSONs e arquivos vazios para o seletor.
Não copia nem executa programas. Manter o terminal PowerShell para reutilizar
`$qaVisualRoot`. A criação exclusiva recusa reutilizar uma pasta existente.

```powershell
$qaVisualRoot = Join-Path (Get-Location).Path ('.qa\gui-acceptance-' + [guid]::NewGuid().ToString('N'))
$qaFixtureRecipe = @'
from pathlib import Path
import hashlib
import json
import re
import sys

workspace = Path.cwd().resolve()
qa_parent = workspace / '.qa'
if qa_parent.is_symlink() or qa_parent.is_junction():
    raise SystemExit('A raiz .qa nao pode ser link ou junction')
qa_resolved = qa_parent.resolve()
candidate = Path(sys.argv[1])
if qa_resolved.parent != workspace or candidate.parent != qa_parent:
    raise SystemExit('Destino fora da raiz QA do workspace')
if re.fullmatch(r'gui-acceptance-[0-9a-f]{32}', candidate.name) is None:
    raise SystemExit('Nome de fixture invalido')
root = candidate.resolve()
if root.parent != qa_resolved:
    raise SystemExit('Destino resolvido fora da raiz QA')
root.mkdir(parents=True, exist_ok=False)
tag = root.name.rsplit('-', 1)[1][:8]
games = [f"qa-game-{i:03}-{tag}.exe" for i in range(60)]
games[25] = games[24].upper()  # segunda duplicata: indice 25, item humano 26
games[58] = f"qa-game-058-{tag}-a\u00e7\u00e3o-" + "nome_longo_" * 8 + ".exe"
folders = [str(root / "Pastas com espa\u00e7os e a\u00e7\u00e3o" / f"pasta-{i:03}") for i in range(60)]
safe = [f"qa-safe-{i:03}-{tag}.exe" for i in range(60)]
safe[0] = games[0]  # apontamento de protecao adicional, sem processo real
cmd = [{"executable": f"qa-java-{tag}.exe",
        "contains": f"  perfil-{i:03} --mundo a\u00e7\u00e3o com espa\u00e7os  "} for i in range(60)]
cmd[25] = dict(cmd[24])
cmd[58]["contains"] += "trecho longo com espa\u00e7os e acentua\u00e7\u00e3o " * 6

fixtures = {
    "vazio.json": {"windows": []},
    "limite25.json": {"windows": [], "block_exes": games[:25]},
    "limite26.json": {"windows": [], "block_exes": games[:26]},
    "lista60.json": {
        "windows": [{"start": "22:00", "end": "02:00", "days": []}],
        "block_exes": games, "block_folders": folders,
        "safelist_exes": safe, "block_cmdline": cmd,
        "qa_extra": {"typed": [True, 1, 1.0, "a\u00e7\u00e3o"]},
    },
}
full = [f"qa-full-{i:04}-{tag}.exe" for i in range(1000)]
full[25] = full[24].upper()
full[999] = full[998]
fixtures['integridade1000.json'] = {
    'windows': [{'start': '22:00', 'end': '02:00', 'days': [6, 0]},
                {'start': '08:00', 'end': '09:00', 'days': []}],
    'block_exes': full, 'block_folders': [], 'safelist_exes': [],
    'block_cmdline': [{'executable': f'qa-java-{tag}.exe',
                      'contains': '  perfil a\u00e7\u00e3o literal  '}],
    'qa_extra': {'typed': [True, 1, 1.0, False, 0, 0.0, 'a\u00e7\u00e3o']},
}
manifest = {}
for name, data in fixtures.items():
    path = root / name
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    manifest[name] = {"sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                      "rules": {field: len(data.get(field, [])) for field in
                                ("block_exes", "block_folders", "safelist_exes", "block_cmdline")}}
(root / "seletores").mkdir()
for name in (f"qa-picker-a-{tag}.exe", f"qa-picker-b-{tag}.exe"):
    (root / "seletores" / name).write_bytes(b"")
(root / "Pastas com espa\u00e7os e a\u00e7\u00e3o").mkdir()
(root / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
print(root)
print("Primeiro uso: destino ausente", root / "novo-nao-criado" / "config.json")
'@
$qaFixtureRecipe | .\.venv\Scripts\python.exe -B - $qaVisualRoot
```

Os escapes Unicode no código mantêm o conteúdo acentuado dos JSONs mesmo
quando o pipe do Windows PowerShell usa codificação legada. Não alterar
`$OutputEncoding` nem o ambiente do usuário para preparar as fixtures.

Preparação validada pelo Maestro em Python 3.14.6 e 3.12.14: fonte Python
extraída deste bloco (ASCII), cinco JSONs aceitos pelo parser, hashes do
manifesto, acentos/espaços/tipos, duplicatas e dias `(6,0)` preservados.
Destino novo permaneceu ausente; nome inválido e reutilização foram recusados
sem sobrescrever fixtures. A execução integral do pipe PowerShell e os
comandos de abertura/simulação de GUI não foram ensaiados por essa validação.

| Fixture | Finalidade e oráculo conhecido antes de executar |
| --- | --- |
| `novo-nao-criado/config.json` ausente | Primeiro uso; nenhum arquivo ou diretório deste destino deve surgir antes de Salvar. |
| `vazio.json` | Lista vazia e mensagem sem regras; nenhum pager necessário. |
| `limite25.json` | 25 executáveis; uma página, pager oculto. |
| `limite26.json` | 26 executáveis; duas páginas, faixas 1–25 e 26–26. |
| `lista60.json` | 60 regras em cada categoria; três páginas, faixas 1–25 / 26–50 / 51–60. Duplicata de executável no item original 26 e cmdline com espaços/acentos. |
| `integridade1000.json` | 1000 executáveis, 40 páginas, duplicatas nas fronteiras e extras bool/int/float; horário noturno com dias na ordem `(6,0)` e horário desativado. Motor sempre parado. |
| `seletores/*.exe` | Arquivos vazios apenas para seleção; nenhuma execução. |
| `manifest.json` | Hashes iniciais e quantidades; não é evidência de aceite. |

Preservar os JSONs-base. Para casos com Apply/Save/import, copiar `lista60.json`
para um nome de trabalho exclusivo, como `trabalho-R100.json`, antes de abrir.
Registrar qual cópia foi usada; comparar hashes somente de arquivos que o caso
não autorizou salvar. Reiniciar com cópia nova ao precisar restaurar o cenário.
Antes de copiar/abrir, revalidar raiz/pais resolvidos sem links/junctions;
destino da cópia deve ser novo e estar dentro da pasta UUID criada pelo ensaio.
Não tentar recuperar a fixture modificando arquivo aberto por fora do editor.

### 2.2 Abertura, mínimo e encerramento

```powershell
# Executar um comando por vez; fechar completamente antes de outro.
.\.venv\Scripts\python.exe -B main.py --config (Join-Path $qaVisualRoot 'novo-nao-criado\config.json') --gui
# Nos demais casos, trocar apenas o caminho da fixture/cópia:
.\.venv\Scripts\python.exe -B main.py --config (Join-Path $qaVisualRoot 'lista60.json') --gui
```

Conferir o título **Motor parado**, não acionar Iniciar. Reduzir a janela
restaurada arrastando as bordas até o limite mínimo e mantê-la inteiramente na
área útil do monitor. Não maximizar como condição para passar. Se a escala
impedir que o mínimo caiba na área útil, registrar a incompatibilidade de
ambiente e controles inacessíveis; não reduzir a escala silenciosamente.
O mínimo 880×660 é o valor lógico pedido à CTk, não promessa de 880×660 pixels
físicos. Registrar separadamente tamanho lógico, área cliente física e moldura.
Se a ferramenta não conseguir medir uma unidade, marcar **não medido**.

Ao terminar cada processo, usar X/Sair e resolver o prompt da fixture; aguardar
o retorno do terminal e a remoção do ícone. Não matar processos por nome amplo.
Nenhuma GUI/native/suíte ou outra captura concorre com esta sessão.

### 2.3 Oráculos de dados e limites de observação

Registrar o hash do **arquivo ativo da cópia de trabalho**, não só da fixture
base, antes/depois de cada fluxo sem Save. Não interpretar hash-base intacto
como prova de que a cópia aberta permaneceu intacta. Save explícito autoriza
mudança somente naquela cópia; registrar seu novo hash/baseline e conferir
contagens, ordem, dias e extras tipados no JSON publicado.

Quando houver harness diagnóstico com acesso à sessão, registrar fora de
qualquer timing: `is_new`, dirty, identidade do draft/baseline, comparação
tipada do modelo e `can_undo`/`can_redo` antes/depois. No primeiro uso,
baseline=None e dirty=true são esperados antes de editar. No ensaio apenas
manual, campos de memória não observáveis ficam **não verificados**;
botões/indicadores não provam por si só igualdade tipada ou ausência de IO.

O roteiro visual não cobre atualmente conflito externo ao salvar nem colisão
da primeira gravação. Esses caminhos têm testes funcionais anteriores no
[plano de testes](TEST_PLAN.md), mas a apresentação/interação física dos
respectivos erros continua sem aceite neste roteiro. Guardas de modelo,
history e bytes não serão declaradas aprovadas pela observação de layout.

## 3. Escalas reais e simulação CTk

### 3.1 Windows real

Registrar a escala efetiva em **Configurações do Windows → Sistema → Tela**,
monitor, resolução, área útil e aumento de texto do sistema separadamente.
Executar na escala registrada, com fatores manuais CTk no padrão 1.0. Para cada
mudança de escala, fechar e reabrir o app no monitor escolhido; cumprir eventual
pedido de nova sessão do Windows. Uma mudança apenas em zoom de captura,
resolução, acesso remoto ou ampliação da imagem não comprova DPI real.
Registrar sessão local/remota e escala no lado onde o app efetivamente renderiza.

Se houver dois monitores de escalas distintas, mover a janela entre eles,
restaurar ao mínimo e conferir popups/modais/bandeja. Se não houver, o caso
permanece não executado, sem inferir suporte a DPI por monitor.

### 3.2 Simulação CTk suplementar

Somente se o Maestro incluir essa variante na sessão: usar os setters públicos
abaixo, em processo separado e sequencial. A receita não altera a produção.

```powershell
.\.venv\Scripts\python.exe -B -c 'import sys; import customtkinter as ctk; ctk.set_widget_scaling(float(sys.argv[2])); ctk.set_window_scaling(float(sys.argv[3])); from ui.config_gui import run_config_gui; raise SystemExit(run_config_gui(sys.argv[1]))' (Join-Path $qaVisualRoot 'lista60.json') 1.25 1.25
```

Registrar ambos os fatores e a escala real Windows que continua vigente.
Na CTk instalada, fatores manuais se combinam com o DPI detectado; não chamar
`1.25` de “Windows 125%”. A simulação altera widgets/geometria CTk, sem mudar
por esse comando a escala do Shell, diálogos nativos ou configuração de texto.
Não desabilitar detecção automática de DPI para forçar equivalência. Encerrar
o processo elimina esses setters; a próxima execução normal usa seus padrões.

### 3.3 Matriz de ambiente planejada

Todos os resultados e evidências permanecem vazios até execução real. Usar
novas linhas por runtime/monitor se diferirem. Priorizar as escalas disponíveis;
indisponibilidade deve ficar explícita e não equivale a aprovação.

| ID | Tipo | Windows real | CTk widget / janela | Casos previstos | Resultado | Evidência |
| --- | --- | --- | --- | --- | --- | --- |
| R100 | Real | 100% a verificar | padrão 1.0 / 1.0 | V01–V13 | Não executado | — |
| R125 | Real | 125% a verificar | padrão 1.0 / 1.0 | V01–V13 | Não executado | — |
| R150 | Real | 150% a verificar | padrão 1.0 / 1.0 | V01–V13 | Não executado | — |
| R200 | Real | 200% a verificar | padrão 1.0 / 1.0 | V01–V13, alcance na área útil | Não executado | — |
| RMIX | Real, dois monitores | duas escalas a registrar | padrão 1.0 / 1.0 | V02, V10, V12 | Não executado | — |
| RTEXT | Real, texto ampliado | escala/percentual de texto a registrar | padrão 1.0 / 1.0 | V02, V09, V10 | Não executado | — |
| S125 | Simulação suplementar | escala real a registrar | 1.25 / 1.25 | V02–V06, V10 | Não executado | — |
| S150 | Simulação suplementar | escala real a registrar | 1.50 / 1.50 | V02–V06, V10 | Não executado | — |

## 4. Critérios observáveis

Aplicar os critérios abaixo em cada caso/ambiente pertinente. Uma falha de
acessibilidade fica registrada mesmo quando o mouse permite concluir a ação.
Não inferir aprovação porque a ação possui callback ou passou em teste oculto.

| ID | Observar | Condição para passar esta verificação |
| --- | --- | --- |
| C1 — cortes | Cabeçalho, rodapé, abas, botões, contador, pager, popups, erro e linha longa | Sem sobreposição ou corte que impeça identificar/acionar o controle. Texto essencial legível; conteúdo longo alcançável por rolagem ou campo de edição. Truncamento documentado com aviso não é corte acidental. |
| C2 — foco | Tab/Shift+Tab, Ctrl+F, caret, menus, modal e retorno | Alvo de teclado identificável visualmente; ordem utilizável, sem sumiço inesperado/trava. Entrada mantém digitação durante/após reconstrução. Modal acessível e retorno permite continuar na janela. Registrar controle que não recebe foco. |
| C3 — contraste | Texto principal/secundário/erro, botão normal/hover/desabilitado, seleção e destaque | Informação legível no monitor e estados distinguíveis. Destaque da revisão inclui texto, seleção inclui checkbox/contador; cor sozinha não basta. Avaliação visual é qualitativa: sem medição, não declarar taxa de contraste nem conformidade normativa. |
| C4 — alcance | Primeiro/último item, última página, barra FULL, fim de textos e ações de modal | Todos alcançáveis no mínimo pela rolagem/controles previstos. Avaliar teclado e mouse separadamente; um não compensa falha do outro. Ampliação da janela só serve como diagnóstico após registrar falha no mínimo. |
| C5 — estados | Motor, dirty, busca pendente/concluída, confirmação e bandeja | Mensagem corresponde à situação; contagem antiga não se apresenta como válida durante atualização. Ações antigas inertes, estado retomado ao cancelar, motor permanece parado. |

Para teclado, tentar Tab/Shift+Tab e, em cada controle focável, sua ativação
natural por Enter/Espaço/setas, registrando qual funciona. Tentar rolagem de
texto/lista por setas/PageUp/PageDown/Home/End quando o foco estiver nesse
conteúdo; se não funcionar ou não houver foco, registrar lacuna. Não criar
atalhos adicionais nem bindings para fazer o caso passar.

Leitor de tela: se disponível na sessão, registrar nome/versão e testar anúncio
de busca, categoria/ordem, checkbox/contador, erro e ação de modal. Separar
nome/papel/estado/valor anunciado e mudanças de estado; sem ferramenta ou sem
execução, manter **não executado**. Inspeção visual não comprova suporte a
leitor de tela, alto contraste ou navegação completa sem mouse.

## 5. Roteiro dos casos

Cada caso começa com motor parado e janela no mínimo; registrar a escala.
Capturas, se a sessão permitir, devem representar o estado observado. Não
alterar timer, congelar callback, chamar `flush_rule_search()` ou fabricar
texto para capturar o estado pendente. O roteiro não executa essa sessão.

### V01 — primeira configuração e sugestões

Abrir o destino ausente; conferir aviso de arquivo não criado, listas/horários
vazios e Iniciar indisponível. Percorrer Visão geral e Configuração, rolando
até a última sugestão e **Adicionar selecionadas**; sugestões desmarcadas.
Selecionar uma sugestão, adicionar ao rascunho e conferir dirty; motor parado.
Abrir Adicionar horário e cancelar por Escape. Sair/descartar e conferir que
o destino continua ausente. Reabrir esse destino, Salvar explicitamente e
conferir criação/motor ainda parado. Não ativar o bloqueio. Critérios C1–C5.

### V02 — quatro abas e tamanho mínimo

Abrir `lista60.json`; reduzir até o mínimo. Percorrer as quatro abas,
incluindo topo/fim da Visão geral e Configuração. Conferir cabeçalho do motor,
agenda carregada distinta do rascunho, rodapé Salvar/Recarregar/Enviar à bandeja
e Desfazer/Refazer. Verificar se textos, sugestões e revisão são alcançáveis
sem maximizar. Abrir menus de categoria/ordem e verificar seus limites na tela.
Repetir para caminho longo e texto acentuado da fixture. Critérios C1–C5.

### V03 — busca pendente sem seleção

Em Executáveis, Cadastro, busca vazia, pressionar Ctrl+F. Digitar em rajada
`qa-game-0`, continuar substituindo por `sem-correspondencia` e voltar para
`qa-game-`; observar durante a digitação contínua. Durante pendência, procurar
**Atualizando busca…**, linhas antigas desabilitadas e pager inerte; entry,
categoria e ordem continuam utilizáveis. Selecionar regras deve estar inerte.
Sem seleção ativa, observar a indicação na descrição/pager, não um contador
que só existe no outro modo. Depois de parar de digitar, conferir 60 resultados
e ações restauradas. C1–C5; registrar se o transitório foi realmente visto.

### V04 — busca pendente com seleção

Com consulta `qa-game-` concluída, ativar Selecionar regras e Selecionar exibidas:
contador 60 selecionadas/60 resultados, embora só 25 linhas pertençam à página.
Digitar nova consulta: seleção deve zerar imediatamente; contador indica busca
pendente/Atualizando busca, checkboxes, lote e pager inertes. Observar que não
se remove/edita linha antiga. Concluir `qa-game-05`: dez resultados (050–059),
zero selecionadas; controles habilitados conforme contexto. C1–C5.

### V05 — busca concluída, vazia e ações explícitas

Sem seleção, consultar `sem-correspondencia` e conferir mensagem sem resultado;
Limpar restaura a lista. Na entry, Escape limpa sem fechar a raiz; Escape em
busca já vazia não deve desorganizar lista/foco. Repetir com seleção ativa.
Durante uma nova rajada, usar Limpar, ordem A–Z/Z–A ou categoria: conferir
destino final, seleção zerada e nenhuma volta tardia à vista anterior.
Ctrl+F em outra aba deve abrir Jogos / Apps, preservar categoria/ordem e
selecionar texto existente. Critérios C1–C5.

### V06 — FULL, páginas e rolagem

Na fixture `lista60.json`, Cadastro e filtro `qa-game-`, marcar uma linha da página 1;
Próxima duas vezes, rolar ao fim e marcar uma linha da página 3. Voltar:
as duas seleções permanecem. Selecionar exibidas deve levar a 60, abrangendo
todas as páginas; Limpar seleção leva a zero; Fechar seleção tira a barra.
Reabrir o modo e inspecionar contador/barra/pager no mínimo. Usar Limpar e
aguardar a consulta vazia concluída antes de trocar categoria; o filtro
persiste entre categorias. Sem editar dados, repetir paginação e rolagem nas
quatro listas completas. Abrir sequencialmente as
fixtures vazio/25/26 para conferir mensagens, ausência/presença do pager e
botões Anterior/Próxima desabilitados nos limites. Critérios C1–C5.

Como subcaso suplementar, abrir `integridade1000.json` com motor parado:
Executáveis deve ter 40 páginas e Selecionar exibidas deve abranger as 1000
posições, incluindo duplicatas e outras páginas. Limpar seleção não edita
dados. Conferir a apresentação do horário noturno/desativado e registrar
hash ativo intacto; navegar não reordena `(6,0)` nem modifica extras tipados.
Essas últimas invariantes exigem o diagnóstico/JSON da seção2.3 e não são
inferidas apenas do texto da tela. Não é benchmark ou limite de cadastro.

### V07 — revisão até o índice original

Na fixture `lista60.json`, escolher o apontamento de Executáveis **item 26** (duplicata
do item25) na Visão geral e usar Ir para item. Em Cadastro deve revelar a
página 2, destacar a segunda duplicata com texto **Selecionado pela revisão**
e trazê-la ao alcance por rolagem. Abrir Editar, conferir nome em maiúsculas
da segunda duplicata e cancelar. Navegação não deve marcar dirty.
Repetir em Nome Z–A com consulta incluinte `qa-game-`: preservar filtro;
com filtro excluinte `sem-correspondencia`: limpar para revelar alvo.
Repetir iniciando navegação enquanto a busca estiver pendente, se observável.
Registrar foco real depois da navegação; destaque não prova foco de teclado.
Critérios C1–C5; se ocorrer fallback de rolagem manual, registrar a mensagem
e o alcance, sem afirmar que a rolagem automática passou.

### V08 — confirmação de lote e recuperação do rascunho

Em cópia de trabalho de `lista60.json`, selecionar todas as 60 regras de Executáveis,
inclusive fora da página; Remover selecionadas deve informar quantidade e
categoria. Cancelar preserva lista/seleção e permite continuar. Repetir e
confirmar: lista vazia no rascunho, sem gravação automática; Desfazer uma vez
restaura as 60; Refazer reaplica a remoção. Conferir hash ativo inalterado
até Save explícito nessa cópia. Salvar e conferir dirty=false, lista salva
vazia e Desfazer ainda disponível; Desfazer restaura as 60 no rascunho,
com dirty=true e sem alterar novamente o arquivo. Recarregar/confirmar volta
à base salva vazia e limpa history; outros casos usam cópia nova da fixture.
Identificar e alcançar os botões de confirmação pelo teclado. Critérios C1–C5.

### V09 — teclado, foco e tecnologia assistiva

Usar Tab/Shift+Tab para registrar o percurso em abas, busca, categoria/ordem,
checkboxes, barra FULL, paginação e rodapé, com e sem seleção. Tentar ativação
sem mouse e documentar controles inacessíveis. Na entry verificar Ctrl+F,
seleção/caret, edição, Escape e continuação da digitação após reconstrução.
Ctrl+Z/Ctrl+Y dentro de campo não devem substituir o histórico global;
fora de campos, em cópia editada, conferir Desfazer/Refazer do rascunho.
Em cópia de trabalho, Ctrl+S salva somente a fixture e Ctrl+R recarrega com
confirmação se necessário. Testar leitor de tela conforme seção 4 ou registrar
não executado. Critérios C2–C5; anotar ordem real, sem pressupor Tab em CTk.

### V10 — modais, erro, campos longos e retorno

Em cópia de trabalho: Adicionar horário (560×470 lógico), Todos/Seg–Sex/Fim
de semana/Nenhum; todos os dias/ações alcançáveis. Tentar início=fim para ver
erro legível e corrigir; Cancelar/Escape fecha só o formulário. Em cada
categoria abrir Adicionar/Editar e cancelar; cmdline tem dois campos e
preserva espaços do trecho. Editar as linhas longas da página 3 e conferir
acesso ao fim do texto. Configuração → Ver alterações abre modal rolável e
redimensionável (760×560 inicial; mínimo 620×420); produzir uma edição de
trabalho antes para incluir Antes/Depois. Conferir foco inicial, ordem Tab,
ausência de interação indevida com a raiz, fechamentos por Cancelar/Escape/X
e retorno que permite retomar busca/edição. Não esperar reconstrução de busca
enquanto modal estiver aberto. Se pendência tiver sido observada antes de
abrir, conferir destino consistente ao retornar. Critérios C1–C5.

### V11 — seletores nativos e confirmação de importação

Em cópia de trabalho, Selecionar .exe nas duas categorias permitidas; escolher
os dois arquivos vazios da pasta `seletores`, conferir inclusão apenas no
rascunho e motor parado. Repetir cancelando. Em Pastas, abrir seletor no
formulário e cancelar/selecionar a pasta isolada. Em Configuração, Importar
JSON de fixture isolada: cancelar seletor, cancelar confirmação e, em outra
tentativa, confirmar; conferir retorno utilizável. Exportar para destino novo
na pasta QA, sem publicar no arquivo ativo. Observar layout/foco do diálogo
Windows separadamente dos modais CTk e mensagem de bloqueio das ações da raiz.
Se houver pendência observada antes de abrir, ela deve terminar sem deixar
vista inerte após cancelar/concluir. C1–C5. Não forçar query via código durante
picker; os testes automatizados dessa condição não são evidência visual.

### V12 — bandeja real e retorno

Em cópia de trabalho com edição não salva, registrar aba/categoria/consulta,
ordem, página, seleção e foco antes de Enviar à bandeja. Observar preparação:
ocultar somente com ícone disponível; localizar também no overflow. Abrir o
menu real, registrar legibilidade/alcance por teclado e escolher Mostrar Focus.
Conferir janela acessível no mesmo monitor, rascunho e contexto de vista
preservados, motor parado; registrar posição/foco/rolagem efetivos, sem inferir
restauração exata que o contrato não promete. Com consulta pendente observada,
conferir o resultado atual ao retornar, sem exigir mesma página após a busca.
Enviar novamente, Sair pelo menu e Cancelar o prompt: janela visível e edição
preservada. Não confundir X com ocultar. Falha real do ícone: registrar erro,
janela visível/restaurada e caso de menu bloqueado; não fabricar ready/erro,
reiniciar Explorer ou considerar simulação prova da bandeja. Critérios C1–C5.

### V13 — saída cancelada e encerramento

Em cópia com dirty, iniciar uma nova consulta e usar X; se pendência for vista,
registrar esse pré-estado. Cancelar a saída: janela aberta, consulta atual
concluída/utilizável, sem motor iniciado. Repetir e descartar; terminal retorna
e ícone termina. Em destino novo separado, testar a alternativa Salvar e sair
somente se ainda não coberta por V01. Nenhuma ação antiga deve reaparecer após
fechar. Registrar erro de terminal/caixa de diálogo se ocorrer. Critérios C2–C5.

## 6. Registro — ainda não executado

Situações permitidas: **Não executado**, **Passou**, **Falhou**, **Bloqueado por
ambiente** e **Parcial**. Se um transitório não for observado, registrar essa
parte como não executada/parcial, mesmo que o resultado final tenha passado.
Uma imagem final não prova o intervalo pendente. Anotar tentativas humanas;
não prolongar debounce nem congelar estado para convertê-lo em aprovação.

### Ambiente da sessão (preencher antes de executar)

| Campo | Registro atual |
| --- | --- |
| Executor/data/hora/fuso | Não executado |
| Commit efetivo/diff local | Não registrado; base prevista `79607c9` |
| Windows edição/build, sessão local/remota, privilégios | Não registrado |
| Python executável/versão; Tk/CTk/pystray/Pillow | Não registrado |
| Monitor(es), resolução, escala Windows, área útil | Não registrado |
| Aumento de texto / modo alto contraste / tema real | Não registrado; app configura aparência clara |
| Fatores CTk widget/janela, real ou simulado | Não registrado |
| Dimensão lógica/cliente físico/moldura | Não medido |
| Fixture/cópia/hash inicial | Não registrado |
| Teclado/layout, mouse, leitor de tela/versão | Não registrado |
| Motor parado antes/depois | Não verificado nesta unidade |
| Ferramenta de observação/captura e limitação | Não executado |

### Matriz de casos (abrir uma cópia por ambiente da seção 3)

| Caso | Critérios | Resultado | Observado / evidência real |
| --- | --- | --- | --- |
| V01 Primeiro uso | C1–C5 | Não executado | — |
| V02 Abas/mínimo | C1–C5 | Não executado | — |
| V03 Pendente sem seleção | C1–C5 | Não executado | — |
| V04 Pendente com seleção | C1–C5 | Não executado | — |
| V05 Busca concluída/clear | C1–C5 | Não executado | — |
| V06 FULL/páginas | C1–C5 | Não executado | — |
| V07 Review/índice original | C1–C5 | Não executado | — |
| V08 Lote/confirmar/cancelar | C1–C5 | Não executado | — |
| V09 Teclado/assistiva | C2–C5 | Não executado | — |
| V10 Modais/retorno | C1–C5 | Não executado | — |
| V11 Seletores nativos | C1–C5 | Não executado | — |
| V12 Bandeja real | C1–C5 | Não executado | — |
| V13 Saída/cancelamento | C2–C5 | Não executado | — |

Registro por observação: `ID ambiente + caso + subpasso; fixture; ação exata;
esperado; observado; critério; resultado; evidência; limitação`. Para falha,
anotar controle/texto cortado ou inacessível, escala, tamanho e sequência
mínima de reprodução. Distinguir problema de produto, falha de captura e
ambiente sem Shell/ícone. Registrar separadamente mouse, teclado e leitor.

Evidência futura: arquivos em `evidencias/` dentro da pasta UUID, com nomes
como `R125-V04-pendente-01.png` ou notas datadas da observação direta. Não
registrar caminho de imagem inexistente; captura com timeout não prova layout.
Excluir informações pessoais; usar somente conteúdo das fixtures. Se houver
simulação, identificá-la no nome/registro. Capturas servem para cortes/cores;
foco, teclado, rolagem e sequências exigem também registro da interação.

O encerramento do aceite deve listar ambientes realmente ensaiados, casos
aprovados/falhos/parciais e pendências. Não declarar “DPI/acessibilidade
aprovados” sem qualificar cobertura; contraste visual sem medição não é
certificação. Suporte a alto contraste/leitor de tela não ensaiado permanece
pendente. Não extrapolar Windows 10 para 11, um runtime para outro ou simulação
CTk para uma escala Windows real.

## 7. Limpeza e continuidade

Depois de fechar todos os processos de QA, conferir hashes das fixtures-base
e ausência de motor/ícone da sessão. Preservar a pasta UUID se contiver
evidências; registrar seu caminho para continuidade. Se for descartá-la,
resolver o caminho absoluto e confirmar que é exatamente a pasta
`.qa/gui-acceptance-<UUID>` criada nesta sessão, dentro do workspace, antes
de qualquer remoção. Nunca apagar `.qa/`, perfis ou processos de forma ampla.

Retomar a sessão visual conforme os casos acima e consolidar resultados por
ambiente. Defeitos demonstrados de layout/acessibilidade devem ser corrigidos
em unidade coerente, com implementação, regressões e registro no log juntos.
Não substituir evidência real por simulações ou captura indisponível.

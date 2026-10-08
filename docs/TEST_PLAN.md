# Plano de validação

Fonte: [escopo](Focus%20Blocker_%20escopo%20do%20projeto.md), [requisitos](REQUIREMENTS.md) e [decisões](DECISIONS.md). Fases 1/2: 206 testes OK em Python 3.14.6/psutil 7.2.2 por `.venv/Scripts/python.exe -B -m unittest discover -s tests` (10,542 s). Sintaxe 3.12 dos 18 arquivos Python conferida; runtime 3.12 ainda não executado. Encerramentos reais e fases posteriores continuam pendentes.

## Evidência do editor independente — 2026-10-08

- Suíte completa com as fases 1/2 e editor: **273 testes OK**, 18,358 s, Python 3.14.6, na conferência final do Maestro após os três relatórios. Frontend confirmou independentemente 273 testes em 18,507 s e os sete testes de flags/importações com `ui.config_cli` previamente importado. Sintaxe Python 3.12 verificada por `ast.parse(feature_version=(3, 12))` em 27 arquivos; runtime 3.12 ainda não executado. UTF-8/links locais conferidos.
- `tests/test_config_editor.py`: CRUD de janelas/quatro listas, dias/índices estritos, iteração de dias com falha, erro sem mutação, ordem/duplicatas, extras/cópias defensivas e ausência de IO.
- `tests/test_config_repository.py`: mesma leitura capturada/validada, UTF-8/JSON inválido, chaves duplicadas/constantes inválidas, roundtrip, conflitos inclusive remoção/formatação, segunda conferência após fsync, falhas de escrita/flush/replace/cleanup e baseline próprio após escritor posterior.
- `tests/test_config_cli.py` e `tests/test_config_editor_main.py`: menus/índices humanos, CRUD, validação, salvar/retry, conflito/reload, baseline após salvar, EOF/Ctrl+C e flags/lazy import sem bloqueadores. Doubles exercitam as fronteiras do frontend; testes de integração abaixo usam módulos reais.
- `tests/test_config_editor_integration.py`: cinco sessões com JSON/agenda reais, três via subprocess. Incluem janela noturna, regra conjunta, dias vazios, extras, EOF sem salvar, conflito externo seguido de recarga e falha real de publicação injetada seguida de retry com rascunho preservado.
- Arquivos de teste isolados no workspace; nenhum hosts, perfil do usuário ou processo real alterado. GUI/bandeja não são validadas nesta entrega. Comparação de bytes não elimina a pequena corrida entre conferência e replace, conforme [contrato](CONFIG_EDITOR_CONTRACT.md).

## Evidência da fase 2

- `tests/test_process_config.py`: listas promovidas/defaults vazios, nomes/pastas/variáveis, regras conjuntas/legado rejeitado, extras/bytes preservados e falhas antes de gravação.
- `tests/test_proc_blocker.py` e `tests/test_process_adapter.py`: fronteira de SO falsa; proteção antes de regras, helpers/ancestrais vivos/órfãos, acesso negado, destinos, PID reutilizado e metadados alterados antes de efeitos. Descoberta leve não autoriza ação; candidatos são reinspecionados completamente.
- Espera coletiva limitada, pending confirmado fora da janela sem nova enumeração/efeito, uma tentativa por identidade confirmada, falhas/desaparecimento prévio sem evento, relatório parcial entregue uma vez, Ctrl+C e ciclos concorrentes recusados.
- `tests/test_process_main.py`: flag explícito, lazy import, relógio fresco, recarga/erro sem snapshot antigo, prazos/atrasos, pending separado de sucesso e relatórios parciais. `tests/test_phase2_integration.py` integra JSON/agenda/CLI/bloqueador real com adaptador falso.
- `tests/test_process_wait_integration.py`: wait_procs instalado com handles falsos, sem processos do sistema; confirmação/negado/alive/interrupt/reuso de identidade.
- Integração **somente por leitura** no Windows build 10.0.19045: contexto próprio passou após corrigir ancestral do Explorer já ausente. Aproximadamente 293 processos; descoberta vazia 0,910 s, por nome sintético 0,923 s, por pasta workspace 1,243 s, com terminate/kill impedidos: zero chamadas/eventos. Antes da otimização, uma varredura completa de 291 registros levou 21,899 s.
- Essas amostras não comprovam RNF01, cadência sob muitos alvos, elevação, jogos reais, classificação universal do catálogo, Windows 11 ou instalador. Nenhum teste alterou hosts ou encerrou aplicativo do usuário.

## Evidência da fase 1

Testes em `tests/test_config.py`, `tests/test_scheduler.py`, `tests/test_scheduler_reference.py`, `tests/test_main.py` e `tests/test_phase1_integration.py`. Há comparação independente do calendário, validação/roundtrip, falhas de fsync/replace com original preservado, consultas via subprocess e watch com recarga/Ctrl+C controlados. Nenhum teste altera hosts, encerra processos ou usa o perfil real. Sintaxe 3.12 verificada; runtime validado foi 3.14.6.

## Resultados esperados já esclarecidos pelo usuário

- Avisos aos 5 e 1 minuto; Sair libera; crash recupera ao reabrir, podendo manter bloqueio antes disso (D01–D03).
- Segunda 22:00–02:00 inclui terça até 02:00, segunda=0 até domingo=6; início incluído/fim excluído; igualdade inválida; unir adjacentes. Foco fora das janelas e durante pausa não conta; lista de estudo editável; única conta Windows (D04–D08).
- Pausa só durante bloqueio; espera mantém bloqueio; cancelamento não conta; nenhuma retomada fora de janela (D09).
- Semana local segunda–domingo; uma tentativa por processo encerrado com sucesso, sem visitas web; dados mínimos para totais, sem expiração, histórico apagado na desinstalação (D11/D12/D16).
- Configuração inicial escolhida pelo usuário antes de ativar; sem horários ativos e com listas sugeridas (D13).

## Estratégia proposta

- Validar agendamento e contabilização com relógio/entrada controlados, sem tocar em processos reais ou hosts.
- Para regras de processo e hosts, primeiro usar entradas e arquivos isolados; só depois integração Windows com alvos de teste autorizados.
- Usar ambiente Windows dedicado para encerramento de processos, hosts, privilégio elevado, tarefa agendada e desinstalação. Registrar versão Windows/Brave, privilégios e estado do DNS seguro.
- Medir desempenho do executável distribuído. Não prometer RNF de CPU/RAM com base em teste unitário.
- Fase 1 usa unittest da biblioteca padrão; ferramentas/ambientes de integração das fases posteriores ainda a definir.

## Cenários por área

| Grupo | Cenários essenciais | Rastreabilidade | Decisões necessárias |
| --- | --- | --- | --- |
| Agendamento | Antes/início/dentro/fim de janela; múltiplas janelas; dias não selecionados; virada de semana e meia-noite; sobreposição; intervalos adjacentes; início=fim | RF01–04 | D04, D08 |
| Relógio e retomada | Iniciar no meio da janela aplica imediatamente; suspender/acordar dentro/fora; mudar relógio; evitar tempo fictício de foco | C04–05, RF20 | D09–D12 |
| JSON | Criar/editar/excluir e reabrir; validação de horas/dias/listas; arquivo ausente/inválido; falha de gravação e mudanças simultâneas | RF01/24, C02 | D13, D17 |
| Processos | Nome/pasta/cmdline; regras combinadas; `javaw.exe` com e sem `.minecraft`; safelist prioritária; prefixo parecido fora da pasta; processo que desaparece; acesso negado; reabertura; terminate sem sucesso | RF07–11, C03 | D14–D16 |
| Hosts | Backup antes da primeira escrita; IPv4/IPv6; entrar/sair; ciclos repetidos sem duplicar; preservar entradas externas; alteração externa durante bloqueio; marcador ausente/corrompido; somente leitura; falha de DNS flush | RF12–15, C06 | D03, D17 |
| Recuperação | Sair normal; encerrar abruptamente processo; reiniciar app; reiniciar Windows; desinstalar durante bloqueio; falha de cleanup | RNF04, C04, C08 | D02–D03, D07, D17 |
| Avisos | 5/1 min se confirmados; jogo/launcher aberto ou ausente; modo sempre avisar; sobreposição sem duplicar; loop atravessa instante do aviso; suspensão/edição/relógio | RF05–06 | D01, D10, D13 |
| Pausa | Espera 60 s; cancelar; pedido repetido; liberação de sites/processos por 15 min; aviso 1 min antes; janela termina durante espera/pausa; retomada; reabrir/suspender durante pausa | RF16–19 | D09–D10 |
| Foco | App elegível em primeiro plano; outro app; ociosidade abaixo/exatamente/acima de 5 min; retomada de input; atraso/suspensão; troca de dia/semana; pausa e horário livre | RF20–21 | D05–D06, D12 |
| Brave e foco | Domínio cadastrado como estudo versus não cadastrado; adicionar/remover lista; não contar fora da janela nem na pausa; troca de aba ativa | RF20; D19 | Identificação da aba/domínio, subdomínios e conflitos ainda a definir |
| Métricas | Total diário/semanal/geral; pausa cancelada/iniciada; processo bloqueado/reaberto; falha ao encerrar; não contar múltiplas regras para um evento segundo definição aprovada | RF19/21, C03 | D09, D11–D12, D16 |
| UI | Abrir/fechar janela repetidamente; manter bandeja; estados coerentes; cinco abas; listas/horários editáveis; cancelamento; falha visível sem travar UI | RF22–24, C01/C06 | D02, D06, D09, D13–D15 |
| Instalação | Instalador completo; dados em APPDATA; login elevado sem UAC por login; segunda instância; desinstalação remove tarefa e bloco do hosts | RNF02–03, C02/C08 | D03, D07, D17–D18 |
| Recursos | CPU/RAM em repouso; núcleo de 5 s com muitos processos; UI aberta/fechada; sessões longas sem crescimento indevido | RNF01, RF04/11 | D18; carga de referência pendente |

## Validação dos sites no Brave

Confirmado: nove serviços-alvo, DNS seguro desligado, hosts sem curinga e possível persistência de conexões já abertas. Fonte: §§1, 6, 8–9.

Para cada serviço, registrar domínios exatos testados, janela ativa/inativa, aba nova ou conexão preexistente e resultado de acesso/reprodução. Conferir liberação após janela/pausa e acesso a ferramentas livres previstas no escopo. Não considerar `www.` um hostname completo nem inferir bloqueio de subdomínio apenas por bloquear domínio raiz.

As listas são ponto de partida. Cobertura parcial deve ser relatada como limitação; não classificar um bloqueio como completo com base apenas no hosts correto. O critério final para conteúdo parcialmente disponível precisa de definição do usuário e evidência prática.

## Registro de resultado por entrega

Proposta: registrar cenário, requisito, ambiente, configuração relevante, resultado esperado, resultado observado e limitação. Evitar copiar dados pessoais ou cmdlines completas para relatórios sem política aprovada (D11).

Testes acompanham o mesmo commit da implementação correspondente. Não criar commits exclusivos por adicionar, modificar ou executar testes. Documentos de planejamento não substituem a execução.

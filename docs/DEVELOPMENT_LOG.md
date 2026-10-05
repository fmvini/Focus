## 2026-10-05 — Base documental e decisões de desenvolvimento

### Implementado
- Análise do escopo e criação da documentação de requisitos, arquitetura, interface, dados, decisões, plano de entrega e validação, com índice de leitura.
- Coordenação dos agentes Backend, Frontend e Banco de dados pelo Maestro; cada especialista produziu seu documento, posteriormente consolidado com as respostas do usuário.
- Registro de decisões: avisos 5/1 min, Sair com liberação, recuperação após crash ao reabrir, janelas noturnas pelo dia inicial, segunda=0 até domingo=6, início incluído/fim excluído, igualdade inválida e união de adjacentes.
- Foco apenas nas janelas e fora da pausa de descanso; apps de estudo editáveis; uma conta Windows; configuração escolhida antes de ativar; semana local segunda–domingo; tentativas por processo efetivamente encerrado; dados mínimos e exclusão do histórico na desinstalação.
- Regra adicional para Brave: contar por domínios de estudo adicionados pelo usuário, com lista de bloqueio também personalizável; não contar uso indiscriminado do navegador.

### Arquivos principais alterados
- `docs/README.md`
- `docs/REQUIREMENTS.md`
- `docs/DECISIONS.md`
- `docs/ARCHITECTURE_BACKEND.md`
- `docs/UI_FLOWS.md`
- `docs/DATA_MODEL.md`
- `docs/DELIVERY_PLAN.md`
- `docs/TEST_PLAN.md`
- `docs/DEVELOPMENT_LOG.md`

### Decisões técnicas
- Preservar o escopo original; respostas explícitas prevalecem nos documentos complementares e ficam rastreadas em `DECISIONS.md`.
- Separar requisitos, propostas técnicas e pendências. Contratos de código, schema SQLite, migrações e integrações ainda não foram aprovados nem implementados.
- Recuperação diferida escolhida pelo usuário mantém a arquitetura de processo único; não há watchdog exigido. Após crash, hosts pode continuar bloqueado até reabrir.
- Não inferir executáveis a partir dos nomes Brave, IDEs, Codex, Claude e ChatGPT; identificação real depende de configuração e ambiente.

### Estado atual
- Repositório contém documentação; não há aplicação, testes executáveis, banco criado ou instalador.
- A documentação fornece RF01–RF24 rastreados, sete fases e critérios de validação planejados; não constitui evidência de funcionamento do app.
- Validação documental: os 10 arquivos Markdown (escopo original + 9 novos) foram lidos como UTF-8; links locais conferidos e RF01–RF24 presentes na matriz. Não há testes de aplicação para executar nesta etapa.
- Regra de produto D19 respondida: lista editável de domínios de estudo; mecanismo de identificação da aba/domínio ainda pendente. Medir somente processo em primeiro plano não atende essa distinção. Não há extensão, coleta de histórico ou nova API aprovada.
- Outras pendências estão registradas: proteção obrigatória, correspondência cmdline/pastas, interrupções de pausa, avisos, configuração inválida, durabilidade, identidade elevada e critérios de desempenho.

### Próximos passos
- Antes da fase 6, propor fonte do domínio ativo no Brave e representação da lista de estudo (D19), submetendo mecanismo e políticas de subdomínios/conflitos à revisão; preservar dados mínimos.
- Para a fase 1, fechar contrato de validação/persistência JSON (D17), preservando calendário e fluxo inicial já respondidos; propor interfaces concretas Backend/Banco/Frontend para revisão.
- Antes da fase 2, resolver proteção de processos (D14) e regra conjunta `javaw.exe` + `.minecraft`/normalização de pastas (D15).
- Consultar `DELIVERY_PLAN.md` ao iniciar software; manter testes acompanhantes e este log no mesmo commit da unidade correspondente, sem push automático.

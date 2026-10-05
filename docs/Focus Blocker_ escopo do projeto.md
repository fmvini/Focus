# Focus Blocker: escopo do projeto

App para Windows 10/11 que bloqueia jogos, launchers e sites de consumo de conteúdo em janelas de horário definidas, mantendo livres as ferramentas de estudo e desenvolvimento.

## 1. Decisões fechadas

| Tema | Decisão |
| --- | --- |
| Sistema | Windows 10/11 |
| Linguagem | Python 3.12+ |
| Rigidez | Leve: dá para pausar, com fricção |
| Horários | Várias janelas por dia, salvas em JSON |
| Jogos | Por `.exe` e por pasta (launchers + avulsos) |
| Sites | YouTube, Netflix, Instagram, TikTok, X, Twitch, Prime Video, Disney+, Max |
| Liberado | Reddit, Google, docs, IDE, terminal e tudo fora das listas |
| Navegador | Brave (desativar DNS seguro) |
| Aviso | 2 a 5 min antes do início do bloqueio |
| Pausa | Espera de 60s, depois libera tudo por 15 min |
| Estatísticas | Horas de foco = tempo com apps de dev em uso |
| Interface | Ícone na bandeja + janela de configuração |
| Distribuição | Instalador completo (.exe + auto-start) |

## 2. Requisitos funcionais

**Horários**

- RF01: cadastrar, editar e remover janelas (início, fim, dias da semana; padrão: todos os dias).
- RF02: suportar janelas que cruzam a meia-noite (ex.: 22:00-02:00).
- RF03: janelas sobrepostas são unidas numa só.
- RF04: o app calcula "agora estou em bloqueio?" a cada 5s.

**Aviso**

- RF05: notificação do Windows 5 min e 1 min antes do início da janela.
- RF06: o aviso só aparece se houver jogo ou launcher aberto (configurável para sempre avisar).

**Bloqueio de processos**

- RF07: encerrar processos por nome do executável.
- RF08: encerrar processos cujo caminho esteja dentro de pastas bloqueadas.
- RF09: encerrar processos cuja linha de comando contenha um padrão (necessário para Minecraft, que roda como `javaw.exe`).
- RF10: lista de proteção (safelist): nunca encerrar IDEs, terminais, navegadores e processos do sistema.
- RF11: se o processo reabrir, encerrar de novo (varredura a cada 5s durante o bloqueio).

**Bloqueio de sites**

- RF12: ao entrar em janela, adicionar os domínios ao `hosts` apontando para `127.0.0.1` e `::1`.
- RF13: ao sair da janela, remover só as linhas do app (marcadores `# FOCUS-BLOCKER-START/END`).
- RF14: limpar o cache de DNS (`ipconfig /flushdns`) depois de cada mudança.
- RF15: fazer backup do `hosts` antes da primeira alteração.

**Pausa**

- RF16: botão "Pausar" na bandeja inicia contagem de 60s, cancelável.
- RF17: após os 60s, libera sites e apps por 15 min, com contagem regressiva no ícone.
- RF18: ao fim, retoma o bloqueio (com aviso de 1 min antes).
- RF19: registrar cada pausa nas estatísticas.

**Estatísticas**

- RF20: medir tempo em que um app de dev está em primeiro plano e o usuário não está ocioso (>5 min sem input pausa a contagem).
- RF21: tela com horas de foco por dia, semana e total, número de pausas e tentativas bloqueadas.

**Interface**

- RF22: ícone na bandeja com estado (bloqueando, livre, pausado) e menu (Abrir, Pausar, Sair).
- RF23: janela com abas: Horários, Sites, Jogos/Apps, Estatísticas, Configurações.
- RF24: editar as listas pela interface (adicionar/remover domínios, `.exe`, pastas).

## 3. Requisitos não funcionais

- Uso de CPU abaixo de 1% e RAM abaixo de 80 MB em repouso.
- Uma única instância (mutex).
- Iniciar com o Windows, elevado (administrador), sem pedir UAC todo login.
- Se o app fechar ou travar, o `hosts` não pode ficar bloqueado para sempre (ver seção 8).
- Todos os dados locais, sem internet nem conta.

## 4. Arquitetura

Um processo único, elevado, com três partes:

1. **Núcleo (thread de fundo):** loop de 5s que consulta o agendador e chama os bloqueadores.
2. **Bandeja:** `pystray` em thread própria.
3. **Janela de configuração:** CustomTkinter, aberta sob demanda.

A comunicação entre as partes usa um objeto de estado compartilhado, protegido por lock. Numa versão futura dá para separar em serviço (SYSTEM) + UI, mas para bloqueio leve um processo único basta.

```
focus-blocker/
├── main.py              # inicia tudo, mutex, cleanup
├── core/
│   ├── config.py        # carrega/salva config.json, validação
│   ├── scheduler.py     # janelas, meia-noite, pausa, estado
│   ├── proc_blocker.py  # psutil: nome, pasta, cmdline
│   ├── site_blocker.py  # hosts + flush DNS + backup
│   ├── notifier.py      # toasts do Windows
│   └── stats.py         # SQLite, janela em foco, ociosidade
├── ui/
│   ├── tray.py
│   └── window.py
├── data/
│   ├── config.json
│   └── stats.db
├── installer/
│   ├── build.bat        # PyInstaller (--uac-admin)
│   └── setup.iss        # Inno Setup
└── tests/
```

**Bibliotecas:** `psutil`, `pystray`, `Pillow`, `customtkinter`, `pywin32` (janela em primeiro plano, `GetLastInputInfo`), `win11toast`, `sqlite3` (padrão).

## 5. Modelo de dados (`config.json`)

```json
{
  "windows": [
    {"start": "08:00", "end": "12:00", "days": [0,1,2,3,4,5,6]},
    {"start": "14:00", "end": "18:00", "days": [0,1,2,3,4,5,6]}
  ],
  "warn_minutes": [5, 1],
  "pause": {"wait_seconds": 60, "duration_minutes": 15},
  "sites": {
    "YouTube": ["youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "googlevideo.com", "ytimg.com"],
    "Netflix": ["netflix.com", "www.netflix.com", "nflxvideo.net", "nflximg.net", "nflxext.com"]
  },
  "block_exes": ["steam.exe", "EpicGamesLauncher.exe", "Battle.net.exe"],
  "block_folders": ["C:\\Program Files (x86)\\Steam\\steamapps\\common"],
  "block_cmdline": [".minecraft"],
  "safelist_exes": ["code.exe", "pycharm64.exe", "WindowsTerminal.exe", "brave.exe"],
  "dev_apps": ["code.exe", "pycharm64.exe", "WindowsTerminal.exe", "idea64.exe"]
}
```

## 6. Listas iniciais

**Launchers:** `steam.exe`, `steamwebhelper.exe`, `EpicGamesLauncher.exe`, `EpicWebHelper.exe`, `Battle.net.exe`, `RiotClientServices.exe`

**Jogos avulsos:**

- Minecraft: `Minecraft.exe`, `MinecraftLauncher.exe`, e `javaw.exe` somente quando a linha de comando contém `.minecraft`. Bloquear `javaw.exe` por nome derrubaria IDEs Java.
- Roblox: `RobloxPlayerBeta.exe`, `RobloxPlayerLauncher.exe`
- Riot: `LeagueClient.exe`, `VALORANT-Win64-Shipping.exe`

**Pastas:** `...\Steam\steamapps\common`, `C:\Program Files\Epic Games`, `C:\Program Files (x86)\Battle.net`, `C:\Riot Games`, `%LOCALAPPDATA%\Roblox\Versions`

**Domínios por site (ponto de partida, validar na prática):**

- **YouTube:** `youtube.com`, `www.`, `m.`, `youtu.be`, `googlevideo.com`, `ytimg.com`, `youtubei.googleapis.com`
- **Netflix:** `netflix.com`, `www.`, `nflxvideo.net`, `nflximg.net`, `nflxext.com`, `nflxso.net`
- **Instagram:** `instagram.com`, `www.`, `cdninstagram.com`
- **TikTok:** `tiktok.com`, `www.`, `tiktokcdn.com`, `tiktokv.com`, `byteoversea.com`
- **X:** `x.com`, `twitter.com`, `www.`, `twimg.com`, `t.co`
- **Twitch:** `twitch.tv`, `www.`, `ttvnw.net`, `jtvnw.net`
- **Prime Video:** `primevideo.com`, `www.`, `aiv-cdn.net`, `pv-cdn.net`
- **Disney+:** `disneyplus.com`, `www.`, `disney-plus.net`, `bamgrid.com`, `dssott.com`
- **Max:** `max.com`, `www.`, `hbomax.com`

**Limitação:** o `hosts` não aceita curinga (`*.youtube.com`), então cada subdomínio precisa estar listado. Se faltar algum, o site pode carregar parcialmente. Solução futura: proxy DNS local que bloqueia por sufixo.

## 7. Fluxos principais

**Ciclo do núcleo (a cada 5s)**

1. Lê relógio e config.
2. Se está pausado e a pausa venceu, retoma.
3. Calcula se está em janela de bloqueio.
4. Se há janela começando em 5 min ou 1 min, dispara o aviso.
5. Se bloqueando: garante sites no `hosts` e varre processos.
6. Se livre: garante `hosts` limpo.
7. Atualiza ícone e estatísticas.

**Varredura de processos**

1. `psutil.process_iter(['pid','name','exe','cmdline'])`.
2. Ignora quem estiver na safelist.
3. Marca para encerrar se bater por nome, pasta ou cmdline.
4. `terminate()`, espera 2s, depois `kill()` se necessário.
5. Conta uma "tentativa bloqueada" nas estatísticas.

**Pausa**

1. Clique em Pausar abre contagem de 60s, cancelável.
2. Aos 60s: remove bloqueio, estado = pausado por 15 min.
3. No fim: avisa 1 min antes e retoma.

**Estatísticas**

1. A cada 5s, pega o processo da janela em primeiro plano.
2. Se estiver em `dev_apps` e o usuário não estiver ocioso, soma 5s ao dia.
3. Grava em SQLite (`focus_log`, `pauses`, `blocked_attempts`).

## 8. Casos extremos

- **App fechou com `hosts` bloqueado:** na inicialização, o app limpa qualquer bloco antigo e reavalia. Também limpa no encerramento normal (`atexit`).
- **PC ligado no meio da janela:** o bloqueio vale imediatamente, sem aviso.
- **Suspensão/hibernação:** ao acordar, o próximo ciclo reavalia.
- **Relógio alterado:** aceito, já que o bloqueio é leve.
- **`hosts` somente leitura ou antivírus bloqueando:** registrar erro e mostrar alerta na bandeja.
- **Abas já abertas no Brave:** conexões existentes podem continuar até recarregar. Mitigação: DNS flush e, opcionalmente, avisar para fechar abas.
- **Jogo fecha e o launcher reabre sozinho:** a varredura de 5s encerra de novo.
- **Falso positivo:** pasta ou nome batendo em app legítimo. A safelist tem prioridade.

## 9. Configuração do Brave (passo de instalação)

1. `brave://settings/security` e desativar **Usar DNS seguro**.
2. Opcional: desativar o Brave News e a página de nova guia com conteúdo.
3. Testar: abrir `youtube.com` durante uma janela e confirmar o bloqueio.

## 10. Instalação e auto-start

1. Empacotar com PyInstaller (`--noconsole --uac-admin`).
2. Gerar instalador com Inno Setup, que cria uma tarefa no Agendador (`schtasks /create /sc onlogon /rl highest`) para iniciar elevado sem prompt de UAC.
3. O desinstalador remove a tarefa e limpa o `hosts`.
4. Dados do usuário ficam em `%APPDATA%\FocusBlocker`.

## 11. Fases de entrega

| Fase | Entrega | Critério de pronto |
| --- | --- | --- |
| 1 | Agendador + config JSON + testes | Janelas, meia-noite e sobreposição testadas |
| 2 | Bloqueio de processos | Launchers e jogos fecham; IDEs ficam intactas |
| 3 | Bloqueio de sites | Brave bloqueado na janela e livre fora dela |
| 4 | Avisos + pausa | Toast 5/1 min; pausa 60s + 15 min funcionando |
| 5 | Bandeja + janela de configuração | Tudo editável sem tocar no JSON |
| 6 | Estatísticas | Horas de foco por dia/semana |
| 7 | Instalador + auto-start | Instala, inicia no login e desinstala limpo |

## 12. Fora do escopo (por enquanto)

- Bloqueio de celular ou outros dispositivos.
- Bloqueio por proxy DNS/curinga.
- Exceções por canal do YouTube.
- Sincronização na nuvem.
- Modo rígido (anti-burla).

## 13. Riscos

- Domínios incompletos nas listas, o que pede ajuste iterativo com testes reais.
- Falso positivo em `javaw.exe` se a regra por linha de comando for mal configurada.
- Antivírus pode estranhar um app que edita o `hosts` e encerra processos; talvez seja preciso assinar o executável ou criar exceção.
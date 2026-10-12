"""Catálogo técnico compartilhado de proteção, sem descoberta ou efeitos.

Nomes conhecidos não classificam universalmente aplicações renomeadas/helpers;
o motor também verifica identidade, usuário, caminhos e ancestrais reais.
"""

IDE_NAMES = frozenset({"code.exe", "idea64.exe", "pycharm64.exe"})
BROWSER_NAMES = frozenset({"brave.exe", "chrome.exe", "msedge.exe", "firefox.exe", "opera.exe"})
TERMINAL_NAMES = frozenset({"windowsterminal.exe", "cmd.exe", "powershell.exe", "pwsh.exe", "conhost.exe", "openconsole.exe"})
# Observados neste ambiente; nenhuma instalação/caminho é presumido.
TOOL_NAMES = frozenset({"codex.exe", "codex-code-mode-host.exe", "codex-computer-use-swift.exe", "codex-windows-sandbox-service.exe"})
SYSTEM_NAMES = frozenset({"system", "registry", "smss.exe", "csrss.exe", "wininit.exe", "services.exe", "lsass.exe", "svchost.exe", "winlogon.exe", "explorer.exe"})
MANDATORY_NAMES = IDE_NAMES | BROWSER_NAMES | TERMINAL_NAMES | TOOL_NAMES | SYSTEM_NAMES
INHERITED_NAMES = IDE_NAMES | BROWSER_NAMES | TOOL_NAMES

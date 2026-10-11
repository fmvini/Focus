"""Sugestões opt-in do escopo §6, sem descobrir instalações ou ativar motor."""

from collections.abc import Iterable
from dataclasses import dataclass

from core.config import ConfigError, config_to_dict, parse_config
from core.models import AppConfig


@dataclass(frozen=True)
class ProcessSuggestion:
    key: str
    label: str
    executable: str
    contains: str | None = None


PROCESS_SUGGESTIONS: tuple[ProcessSuggestion, ...] = (
    ProcessSuggestion("steam", "Steam", "steam.exe"),
    ProcessSuggestion("steam_webhelper", "Steam Web Helper", "steamwebhelper.exe"),
    ProcessSuggestion("epic_games_launcher", "Epic Games Launcher", "EpicGamesLauncher.exe"),
    ProcessSuggestion("epic_webhelper", "Epic Web Helper", "EpicWebHelper.exe"),
    ProcessSuggestion("battle_net", "Battle.net", "Battle.net.exe"),
    ProcessSuggestion("riot_client_services", "Riot Client Services", "RiotClientServices.exe"),
    ProcessSuggestion("minecraft", "Minecraft", "Minecraft.exe"),
    ProcessSuggestion("minecraft_launcher", "Minecraft Launcher", "MinecraftLauncher.exe"),
    ProcessSuggestion("minecraft_java", "Minecraft Java (.minecraft)", "javaw.exe", ".minecraft"),
    ProcessSuggestion("roblox_player", "Roblox Player", "RobloxPlayerBeta.exe"),
    ProcessSuggestion("roblox_launcher", "Roblox Player Launcher", "RobloxPlayerLauncher.exe"),
    ProcessSuggestion("league_client", "League Client", "LeagueClient.exe"),
    ProcessSuggestion("valorant", "VALORANT", "VALORANT-Win64-Shipping.exe"),
)


def with_process_suggestions(config: AppConfig, keys: Iterable[str]) -> AppConfig:
    """Retorna cópia validada com somente IDs selecionados, na ordem catálogo.

    O iterable é consumido uma única vez e inteiramente antes das adições.
    IDs são exatos e estáveis; string isolada, ID inválido ou falha de iteração
    levanta ConfigError sem modificar a configuração de origem. IDs repetidos
    não repetem adições. Deduplicação por casefold só impede regras novas
    equivalentes, preservando ordem, caixa e duplicatas já existentes.
    """
    candidate = config_to_dict(config)
    if isinstance(keys, (str, bytes, bytearray)):
        raise ConfigError("sugestões: esperado iterable de IDs, não texto isolado")
    valid_keys = {suggestion.key for suggestion in PROCESS_SUGGESTIONS}
    selected = set()
    try:
        for key in keys:
            if not isinstance(key, str) or key not in valid_keys:
                raise ConfigError("sugestões: ID desconhecido ou inválido")
            selected.add(key)
    except ConfigError:
        raise
    except Exception as exc:
        raise ConfigError("sugestões: não foi possível consumir os IDs selecionados") from exc

    names = {name.casefold() for name in candidate["block_exes"]}
    pairs = {
        (rule["executable"].casefold(), rule["contains"].casefold())
        for rule in candidate["block_cmdline"]
    }
    for suggestion in PROCESS_SUGGESTIONS:
        if suggestion.key not in selected:
            continue
        if suggestion.contains is None:
            name = suggestion.executable.casefold()
            if name not in names:
                candidate["block_exes"].append(suggestion.executable)
                names.add(name)
        else:
            pair = (suggestion.executable.casefold(), suggestion.contains.casefold())
            if pair not in pairs:
                candidate["block_cmdline"].append({
                    "executable": suggestion.executable, "contains": suggestion.contains,
                })
                pairs.add(pair)
    return parse_config(candidate)

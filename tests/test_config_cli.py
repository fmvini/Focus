"""Testa os fluxos interativos sem depender de Windows ou de I/O real."""

from copy import deepcopy
from dataclasses import dataclass
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import unittest
from unittest.mock import patch
from uuid import uuid4

from core.config import ConfigError, config_to_dict, parse_config
from core.models import AppConfig


class _Draft:
    """Double da API pública do ConfigDraft para testar apenas o frontend."""

    def __init__(self, config):
        self._config = deepcopy(config)

    @property
    def config(self):
        return deepcopy(self._config)

    def _replace(self, data):
        self._config = parse_config(data)

    def add_window(self, start, end, days=None):
        data = config_to_dict(self._config)
        data["windows"].append({"start": start, "end": end, "days": list(range(7)) if days is None else list(days)})
        self._replace(data)

    def update_window(self, index, start, end, days=None):
        data = config_to_dict(self._config)
        data["windows"][index] = {"start": start, "end": end, "days": list(range(7)) if days is None else list(days)}
        self._replace(data)

    def remove_window(self, index):
        data = config_to_dict(self._config)
        del data["windows"][index]
        self._replace(data)

    def add_rule(self, field, value):
        data = config_to_dict(self._config)
        data[field].append(value)
        self._replace(data)

    def update_rule(self, field, index, value):
        data = config_to_dict(self._config)
        data[field][index] = value
        self._replace(data)

    def remove_rule(self, field, index):
        data = config_to_dict(self._config)
        del data[field][index]
        self._replace(data)


@dataclass(frozen=True)
class _Snapshot:
    config: AppConfig
    contents: bytes


class _Conflict(ConfigError):
    pass


def _read_snapshot(path):
    contents = Path(path).read_bytes()
    return _Snapshot(parse_config(json.loads(contents.decode("utf-8"))), contents)


def _save_snapshot(path, config, snapshot):
    try:
        current = Path(path).read_bytes()
    except FileNotFoundError:
        raise _Conflict("Configuração removida desde a leitura") from None
    if current != snapshot.contents:
        raise _Conflict("Configuração alterada desde a leitura; recarregue antes de salvar")
    contents = (json.dumps(config_to_dict(config), ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    Path(path).write_bytes(contents)
    return _Snapshot(parse_config(json.loads(contents.decode("utf-8"))), contents)


def _load_cli_module():
    name = f"_test_config_cli_{uuid4().hex}"
    spec = importlib.util.spec_from_file_location(name, Path(__file__).resolve().parents[1] / "ui" / "config_cli.py")
    module = importlib.util.module_from_spec(spec)
    editor_api = type(sys)("core.config_editor")
    editor_api.ConfigDraft = _Draft
    repository_api = type(sys)("core.config_repository")
    repository_api.ConfigConflictError = _Conflict
    repository_api.read_snapshot = _read_snapshot
    repository_api.save_snapshot = _save_snapshot
    with patch.dict(sys.modules, {
        "core.config_editor": editor_api,
        "core.config_repository": repository_api,
    }):
        spec.loader.exec_module(module)
    return module


class ConfigCliTests(unittest.TestCase):
    def setUp(self):
        self.module = _load_cli_module()
        self.root = Path(__file__).resolve().parents[1] / f".config-cli-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = self.root / "config.json"
        self.original = b'{"windows":[],"custom":{"keep":true}}'
        self.path.write_bytes(self.original)

    def run_editor(self, answers):
        output = []
        iterator = iter(answers)
        code = self.module.run_config_editor(
            self.path, input_fn=lambda _prompt: next(iterator), output_fn=output.append,
        )
        return code, "\n".join(output)

    def test_add_schedule_and_process_rules_then_save(self):
        answers = [
            "1", "2", "22:00", "02:00", "0,2",  # janela noturna
            "2", "1", "2", "Minecraft.exe",  # executável bloqueado
            "2", "2", "2", r"C:\Games",  # pasta bloqueada
            "2", "3", "2", "Code.exe",  # proteção adicional
            "2", "4", "2", "javaw.exe", ".minecraft",  # regra literal conjunta
            "3", "5",
        ]
        code, output = self.run_editor(answers)
        self.assertEqual(code, 0)
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["windows"], [{"start": "22:00", "end": "02:00", "days": [0, 2]}])
        self.assertEqual(saved["block_exes"], ["Minecraft.exe"])
        self.assertEqual(saved["block_folders"], [r"C:\Games"])
        self.assertEqual(saved["safelist_exes"], ["Code.exe"])
        self.assertEqual(saved["block_cmdline"], [{"executable": "javaw.exe", "contains": ".minecraft"}])
        self.assertEqual(saved["custom"], {"keep": True})
        self.assertIn("Configuração salva", output)

    def test_empty_days_can_disable_a_window(self):
        code, _ = self.run_editor(["1", "2", "09:00", "10:00", "nenhum", "3", "5"])
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["windows"][0]["days"], [])

    def test_invalid_window_keeps_file_unchanged_and_session_open(self):
        code, output = self.run_editor(["1", "2", "09:00", "09:00", "", "5"])
        self.assertEqual(code, 0)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertIn("Erro:", output)

    def test_exit_and_eof_discard_unsaved_changes(self):
        code, output = self.run_editor(["1", "2", "09:00", "10:00", "", "5"])
        self.assertEqual(code, 0)
        self.assertIn("descartadas", output)
        self.assertEqual(self.path.read_bytes(), self.original)

        output = []
        self.assertEqual(self.module.run_config_editor(self.path, input_fn=lambda _: (_ for _ in ()).throw(EOFError()), output_fn=output.append), 0)
        self.assertIn("descartadas", "\n".join(output))

    def test_external_edit_is_detected_and_preserved(self):
        prompts = iter(["1", "2", "09:00", "10:00", "", "3", "1", "1", "5"])
        menu_count = 0

        def input_fn(prompt):
            nonlocal menu_count
            value = next(prompts)
            if prompt == "Editor > ":
                menu_count += 1
                if menu_count == 2:
                    self.path.write_bytes(b'{"windows":[],"external":true}')
            return value

        output = []
        self.assertEqual(self.module.run_config_editor(self.path, input_fn=input_fn, output_fn=output.append), 0)
        self.assertEqual(self.path.read_bytes(), b'{"windows":[],"external":true}')
        self.assertIn("recarregue antes de salvar", "\n".join(output))
        self.assertIn("1. 09:00", "\n".join(output))
        self.assertNotIn("Configuração salva.", "\n".join(output))

    def test_reload_discards_draft_then_save_keeps_external_revision(self):
        prompts = iter(["1", "2", "09:00", "10:00", "", "4", "3", "5"])
        menu_count = 0

        def input_fn(prompt):
            nonlocal menu_count
            value = next(prompts)
            if prompt == "Editor > ":
                menu_count += 1
                if menu_count == 2:
                    self.path.write_bytes(b'{"windows":[],"external":true}')
            return value

        output = []
        self.assertEqual(self.module.run_config_editor(self.path, input_fn=input_fn, output_fn=output.append), 0)
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved, {
            "windows": [], "external": True, "block_exes": [],
            "block_folders": [], "safelist_exes": [], "block_cmdline": [],
        })
        self.assertIn("recarregada", "\n".join(output))

    def test_initial_invalid_json_returns_one_without_replacing_file(self):
        self.path.write_bytes(b"{invalid")
        output = []
        code = self.module.run_config_editor(self.path, input_fn=lambda _: "5", output_fn=output.append)
        self.assertEqual(code, 1)
        self.assertEqual(self.path.read_bytes(), b"{invalid")
        self.assertIn("Erro ao abrir", "\n".join(output))

    def test_list_update_and_remove_windows_with_human_indices(self):
        code, output = self.run_editor([
            "1", "2", "08:00", "09:00", "",
            "1", "2", "10:00", "11:00", "0",
            "1", "3", "2", "22:00", "02:00", "nenhum",
            "1", "1", "1", "4", "1", "3", "5",
        ])
        self.assertEqual(code, 0)
        self.assertIn("1. 08:00", output)
        self.assertIn("2. 22:00", output)
        self.assertIn("nenhum (desativada)", output)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["windows"], [
            {"start": "22:00", "end": "02:00", "days": []},
        ])

    def test_list_update_and_remove_each_rule_list(self):
        cases = (
            ("1", "block_exes", ["first.exe"], ["second.exe"], "second.exe"),
            ("2", "block_folders", [r"C:\Games"], [r"D:\Games"], r"D:\Games"),
            ("3", "safelist_exes", ["Code.exe"], ["study.exe"], "study.exe"),
            ("4", "block_cmdline", ["javaw.exe", ".minecraft"],
             ["other.exe", " literal with spaces "],
             {"executable": "other.exe", "contains": " literal with spaces "}),
        )
        for selection, field, original, replacement, expected in cases:
            with self.subTest(field=field):
                self.path.write_bytes(self.original)
                code, output = self.run_editor([
                    "2", selection, "2", *original,
                    "2", selection, "3", "1", *replacement,
                    "2", selection, "1", "3",
                    "2", selection, "4", "1", "3", "5",
                ])
                self.assertEqual(code, 0)
                self.assertIn("1. ", output)
                self.assertEqual(output.count("Configuração salva."), 2)
                self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))[field], [])

                # Conferir também a revisão intermediária salva, antes da remoção.
                self.path.write_bytes(self.original)
                code, _ = self.run_editor([
                    "2", selection, "2", *original,
                    "2", selection, "3", "1", *replacement, "3", "5",
                ])
                self.assertEqual(code, 0)
                self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))[field], [expected])

    def test_invalid_indices_keep_draft_and_do_not_prompt_for_new_fields(self):
        for index in ("0", "-1", "2", "texto"):
            with self.subTest(index=index):
                self.path.write_bytes(self.original)
                code, output = self.run_editor([
                    "1", "2", "08:00", "09:00", "",
                    "1", "3", index, "1", "4", index,
                    "2", "1", "2", "game.exe",
                    "2", "1", "3", index, "2", "1", "4", index,
                    "3", "5",
                ])
                self.assertEqual(code, 0)
                self.assertEqual(output.count("Erro:"), 4)
                saved = json.loads(self.path.read_text(encoding="utf-8"))
                self.assertEqual(saved["windows"][0]["start"], "08:00")
                self.assertEqual(saved["block_exes"], ["game.exe"])

    def test_invalid_days_and_rules_leave_valid_draft_intact(self):
        answers = ["1", "2", "08:00", "09:00", ""]
        for days in ("0,0", "7", "-1", "0,", "seg"):
            answers.extend(["1", "2", "10:00", "11:00", days])
        answers.extend([
            "2", "1", "2", "game", "2", "2", "2", "relative",
            "2", "3", "2", "*", "2", "4", "2", "javaw.exe", "",
            "3", "5",
        ])
        code, output = self.run_editor(answers)
        self.assertEqual(code, 0)
        self.assertEqual(output.count("Erro:"), 9)
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["windows"], [{
            "start": "08:00", "end": "09:00", "days": list(range(7)),
        }])
        for field in ("block_exes", "block_folders", "safelist_exes", "block_cmdline"):
            self.assertEqual(saved[field], [])

    def test_invalid_menus_and_back_choices_never_write(self):
        with patch.object(self.module, "save_snapshot") as save:
            code, output = self.run_editor([
                "wrong", "1", "wrong", "1", "0", "2", "wrong", "2", "0",
                "2", "1", "wrong", "2", "1", "0", "5",
            ])
        self.assertEqual(code, 0)
        self.assertEqual(output.count("Erro:"), 4)
        save.assert_not_called()
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_failed_save_keeps_draft_for_retry_and_confirms_only_publication(self):
        for failure in (ConfigError("replace falhou"), OSError("disco cheio")):
            with self.subTest(failure=type(failure).__name__):
                self.path.write_bytes(self.original)
                attempts = 0

                def save(path, config, snapshot):
                    nonlocal attempts
                    attempts += 1
                    if attempts == 1:
                        self.assertEqual(Path(path).read_bytes(), self.original)
                        raise failure
                    return _save_snapshot(path, config, snapshot)

                with patch.object(self.module, "save_snapshot", side_effect=save):
                    code, output = self.run_editor([
                        "1", "2", "08:00", "09:00", "", "3", "1", "1", "3", "5",
                    ])
                self.assertEqual(code, 0)
                self.assertEqual(output.count("Configuração salva."), 1)
                self.assertIn("1. 08:00", output)
                self.assertLess(output.index("Erro:"), output.index("Configuração salva."))
                self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["windows"][0]["start"], "08:00")

    def test_failed_reload_keeps_draft_and_baseline(self):
        for failure in (ConfigError("JSON inválido"), OSError("acesso negado")):
            with self.subTest(failure=type(failure).__name__):
                self.path.write_bytes(self.original)
                with patch.object(self.module, "read_snapshot", side_effect=[
                    _read_snapshot(self.path), failure,
                ]):
                    code, output = self.run_editor([
                        "1", "2", "08:00", "09:00", "", "4", "1", "1", "3", "5",
                    ])
                self.assertEqual(code, 0)
                self.assertIn("Erro:", output)
                self.assertIn("1. 08:00", output)
                self.assertNotIn("configuração recarregada", output)
                self.assertEqual(json.loads(self.path.read_text(encoding="utf-8"))["windows"][0]["start"], "08:00")

    def test_removed_destination_conflicts_and_is_not_recreated(self):
        def save(path, config, snapshot):
            Path(path).unlink()
            return _save_snapshot(path, config, snapshot)

        with patch.object(self.module, "save_snapshot", side_effect=save):
            code, output = self.run_editor(["3", "5"])
        self.assertEqual(code, 0)
        self.assertFalse(self.path.exists())
        self.assertIn("Conflito:", output)
        self.assertIn("Use Recarregar", output)
        self.assertNotIn("Configuração salva.", output)

    def test_save_updates_baseline_and_exit_keeps_only_saved_revision(self):
        with patch.object(self.module, "read_snapshot", wraps=_read_snapshot) as read:
            code, output = self.run_editor([
                "1", "2", "08:00", "09:00", "", "3",
                "2", "1", "2", "game.exe", "3",
                "1", "4", "1", "5",
            ])
        self.assertEqual(code, 0)
        read.assert_called_once_with(self.path)
        self.assertEqual(output.count("Configuração salva."), 2)
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(len(saved["windows"]), 1)
        self.assertEqual(saved["block_exes"], ["game.exe"])

    def test_eof_and_ctrl_c_during_editing_discard_unsaved_changes(self):
        prefixes = (
            ["1", "2", "08:00", "09:00", ""],  # rascunho válido
            ["1", "2", "08:00"],  # janela incompleta
            ["2", "4", "2", "javaw.exe"],  # regra conjunta incompleta
        )
        for interruption in (EOFError, KeyboardInterrupt):
            for prefix in prefixes:
                with self.subTest(interruption=interruption.__name__, prefix=prefix):
                    with patch("builtins.input", side_effect=[*prefix, interruption()]):
                        with patch("builtins.print") as output:
                            code = self.module.run_config_editor(self.path)
                    self.assertEqual(code, 0)
                    self.assertIn("descartadas", output.call_args.args[0])
                    self.assertEqual(self.path.read_bytes(), self.original)

    def test_ctrl_c_during_initial_load_exits_normally(self):
        output = []
        with patch.object(self.module, "read_snapshot", side_effect=KeyboardInterrupt):
            code = self.module.run_config_editor(self.path, output_fn=output.append)
        self.assertEqual(code, 0)
        self.assertIn("descartadas", "\n".join(output))
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_missing_initial_file_returns_one_without_creation_or_prompts(self):
        self.path.unlink()
        with patch("builtins.input", side_effect=AssertionError("prompt inesperado")):
            with patch("builtins.print") as output:
                code = self.module.run_config_editor(self.path)
        self.assertEqual(code, 1)
        self.assertFalse(self.path.exists())
        self.assertIn("Erro ao abrir", output.call_args.args[0])


if __name__ == "__main__":
    unittest.main()

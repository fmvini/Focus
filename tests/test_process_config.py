"""Contrato JSON de processos, sem inspecionar instalações ou encerrar alvos."""

import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from uuid import uuid4

from core.config import ConfigError, config_to_dict, default_config, load_config, parse_config, save_config
from core.models import AppConfig, CmdlineRule


PROCESS_FIELDS = ("block_exes", "block_folders", "safelist_exes", "block_cmdline")


def payload(**changes):
    return {"windows": [], **changes}


class ProcessConfigTests(unittest.TestCase):
    def test_old_schedule_and_each_omitted_field_have_empty_tuples(self):
        for present in (None, *PROCESS_FIELDS):
            data = payload(**({present: []} if present else {}))
            with self.subTest(present=present):
                config = parse_config(data)
                self.assertEqual(config, default_config())
                for field in PROCESS_FIELDS:
                    self.assertEqual(getattr(config, field), ())
                self.assertEqual(config_to_dict(config), payload(**dict.fromkeys(PROCESS_FIELDS, [])))

    def test_promotes_fields_preserving_original_text_order_and_duplicates(self):
        data = payload(
            block_exes=["Game.exe", "Game.exe", "Another Game.EXE"],
            block_folders=[r"C:\Synthetic Games", r"\\server\share\games"],
            safelist_exes=["Editor.EXE"],
            block_cmdline=[{"executable": "javaw.exe", "contains": ".minecraft"},
                           {"executable": "Game.exe", "contains": " A.*[B] "}],
        )
        config = parse_config(data)
        self.assertEqual(config.block_exes, ("Game.exe", "Game.exe", "Another Game.EXE"))
        self.assertEqual(config.block_folders, tuple(data["block_folders"]))
        self.assertEqual(config.safelist_exes, ("Editor.EXE",))
        self.assertEqual(config.block_cmdline, (CmdlineRule("javaw.exe", ".minecraft"),
                                              CmdlineRule("Game.exe", " A.*[B] ")))
        self.assertEqual(config.extra, {})
        self.assertEqual(config_to_dict(config), data)

    def test_unpromoted_extras_remain_opaque_and_isolated(self):
        data = payload(block_exes=["Game.exe"], sites=False, pause="opaque",
                       dev_apps=None, safelist={"future": [1, None]},
                       future={"block_cmdline": ["legacy text"]})
        config = parse_config(data)
        expected_extra = {key: value for key, value in data.items()
                          if key not in ("windows", *PROCESS_FIELDS)}
        self.assertEqual(config.extra, expected_extra)
        result = config_to_dict(config)
        self.assertEqual(result, {**dict.fromkeys(PROCESS_FIELDS, []), **data})
        data["safelist"]["future"].append("input")
        result["safelist"]["future"].append("output")
        self.assertEqual(config.extra["safelist"], {"future": [1, None]})

    def test_process_fields_require_lists_not_null_or_other_types(self):
        for field in PROCESS_FIELDS:
            for value in (None, True, 1, "", "Game.exe", {}, (), ("Game.exe",)):
                with self.subTest(field=field, value=value), self.assertRaisesRegex(ConfigError, field):
                    parse_config(payload(**{field: value}))

    def test_executable_names_are_strict_in_all_three_locations(self):
        invalid = (None, True, 1, [], {}, "", "exe", ".exe", "Game", "Game.com",
                   " Game.exe", "Game.exe ", "Game.exe\n", r"C:\Game.exe",
                   "folder/Game.exe", "*.exe", "Game?.exe", 'Game".exe',
                   "Game|.exe", "Game<.exe", "Game>.exe", "Game\x00.exe")
        for value in invalid:
            for field in ("block_exes", "safelist_exes", "block_cmdline"):
                entries = ([{"executable": value, "contains": "literal"}]
                           if field == "block_cmdline" else [value])
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ConfigError, rf"{field}\[0\]"):
                        parse_config(payload(**{field: entries}))

    def test_valid_folder_syntax_does_not_consult_filesystem(self):
        paths = ["C:\\", r"D:\Synthetic\missing\..\Games", "C:/Synthetic/Games",
                 r"\\server\share", r"\\server\share\Games", "//server/share/Games"]
        with patch("pathlib.Path.resolve", side_effect=AssertionError("filesystem resolution")), \
             patch("os.path.exists", side_effect=AssertionError("installation probe")):
            config = parse_config(payload(block_folders=paths))
            self.assertEqual(config.block_folders, tuple(paths))
            self.assertEqual(config_to_dict(config)["block_folders"], paths)

    def test_percent_variables_expand_for_validation_but_original_is_saved(self):
        paths = [r"%FOCUS_TEST_ROOT%\Games", r"%focus_test_root%\%FOCUS_TEST_SUB%"]
        with patch.dict(os.environ, {"FOCUS_TEST_ROOT": r"C:\Synthetic", "FOCUS_TEST_SUB": "Games"}, clear=True):
            config = parse_config(payload(block_folders=paths))
            self.assertEqual(config.block_folders, tuple(paths))
            self.assertEqual(config_to_dict(config)["block_folders"], paths)

    def test_unresolved_empty_or_malformed_variable_is_error(self):
        paths = [r"%MISSING%\Games", r"%EMPTY%\Games", r"C:\%MISSING%",
                 r"C:\%UNCLOSED", r"C:\%%", r"C:\%NESTED%"]
        with patch.dict(os.environ, {"EMPTY": "", "NESTED": "%MISSING%"}, clear=True):
            for value in paths:
                with self.subTest(value=value), self.assertRaisesRegex(ConfigError, r"block_folders\[0\].*variável"):
                    parse_config(payload(block_folders=[value]))

    def test_expanded_variable_must_produce_valid_absolute_path(self):
        for expanded in ("relative", r"C:relative", "C:\\*", r"\\?\C:\Games", "C:\\bad\x00"):
            with patch("core.config.os.environ", {"FOCUS_TEST_ROOT": expanded}):
                with self.subTest(expanded=expanded), self.assertRaisesRegex(ConfigError, r"block_folders\[0\]"):
                    parse_config(payload(block_folders=["%FOCUS_TEST_ROOT%\\Games"]))

    def test_folders_reject_relative_wildcard_device_and_invalid_syntax(self):
        paths = (None, True, 1, [], {}, "", " ", "C:Games", "Games", r"\Games",
                 r"...\Games", r"~\Games", r"\\server", "\\\\server\\",
                 r"\\?\C:\Games", r"\\.\C:\Games", r"\??\C:\Games",
                 "//?/C:/Games", r"C:\Games\*", r"C:\Games\?", r"C:\bad:stream",
                 'C:\\bad"path', "C:\\bad\x00", r"\\server\share\bad|path")
        for value in paths:
            with self.subTest(value=value), self.assertRaisesRegex(ConfigError, r"block_folders\[0\]"):
                parse_config(payload(block_folders=[value]))

    def test_cmdline_requires_exactly_both_fields(self):
        invalid = ({}, {"contains": "literal"}, {"executable": "Game.exe"},
                   {"executable": "Game.exe", "contains": "literal", "regex": False},
                   None, True, [], 1)
        for rule in invalid:
            with self.subTest(rule=rule), self.assertRaisesRegex(ConfigError, r"block_cmdline\[0\]"):
                parse_config(payload(block_cmdline=[rule]))

    def test_contains_requires_nonempty_string_and_is_preserved_literally(self):
        for value in (None, False, 1, [], {}, "", " ", "   ", "\u00a0", "\t", "\n",
                      "valid\x00text", "valid\ttext", "valid\ntext", "valid\x7ftext", "valid\x85text"):
            with self.subTest(value=value), self.assertRaisesRegex(ConfigError, r"block_cmdline\[0\].contains"):
                parse_config(payload(block_cmdline=[{"executable": "Game.exe", "contains": value}]))
        for literal in (" meaningful ", "Case", "case", r".*\[literal]", "--first --second"):
            data = payload(block_cmdline=[{"executable": "Game.exe", "contains": literal}])
            self.assertEqual(config_to_dict(parse_config(data))["block_cmdline"], data["block_cmdline"])

    def test_legacy_cmdline_string_has_explicit_error_without_inference(self):
        with self.assertRaisesRegex(ConfigError, r"block_cmdline\[0\].*string legada.*sem migração"):
            parse_config(payload(block_cmdline=[".minecraft"]))

    def test_errors_locate_second_entry(self):
        data = payload(block_cmdline=[{"executable": "Game.exe", "contains": "ok"},
                                      {"executable": "Game.exe", "contains": None}])
        with self.assertRaisesRegex(ConfigError, r"block_cmdline\[1\].contains"):
            parse_config(data)
        with self.assertRaisesRegex(ConfigError, r"block_exes\[1\]"):
            parse_config(payload(block_exes=["Game.exe", "bad"]))

    def test_direct_models_require_tuples_typed_rules_and_valid_values(self):
        invalid = [AppConfig(block_cmdline=(".minecraft",)),
                   AppConfig(block_cmdline=({"executable": "Game.exe", "contains": "x"},)),
                   AppConfig(block_cmdline=(CmdlineRule("Game.exe", ""),)),
                   AppConfig(block_cmdline=(CmdlineRule("bad", "x"),)),
                   AppConfig(block_folders=("relative",)),
                   AppConfig(block_exes=(True,)), AppConfig(safelist_exes=("bad",))]
        invalid.extend(AppConfig(**{field: []}) for field in PROCESS_FIELDS)
        for config in invalid:
            with self.subTest(config=config), self.assertRaises(ConfigError):
                config_to_dict(config)

    def test_reserved_extra_collisions_never_override_typed_fields(self):
        for field in ("windows", *PROCESS_FIELDS):
            with self.subTest(field=field), self.assertRaisesRegex(ConfigError, f"extra.{field}"):
                config_to_dict(AppConfig(extra={field: []}))


class ProcessConfigPersistenceTests(unittest.TestCase):
    def setUp(self):
        self.root = Path(__file__).resolve().parents[1] / f"process-config-test-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = self.root / "config.json"

    def test_load_missing_fields_does_not_rewrite_bytes(self):
        original = b'{ "windows" : [], "future": {"keep": true} }\r\n'
        self.path.write_bytes(original)
        config = load_config(self.path)
        for field in PROCESS_FIELDS:
            self.assertEqual(getattr(config, field), ())
        self.assertEqual(self.path.read_bytes(), original)

    def test_explicit_save_roundtrip_preserves_raw_variable_and_extras(self):
        data = payload(block_exes=["Game.exe"], block_folders=[r"%FOCUS_TEST_ROOT%\Games"],
                       safelist_exes=["Editor.exe"],
                       block_cmdline=[{"executable": "Game.exe", "contains": " literal.* "}],
                       future={"ação": [None, True, "opaque"]})
        with patch.dict(os.environ, {"FOCUS_TEST_ROOT": r"C:\Synthetic"}, clear=True):
            config = parse_config(data)
            save_config(self.path, config)
            self.assertEqual(load_config(self.path), config)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), data)
        self.assertEqual(set(self.root.iterdir()), {self.path})

    def test_invalid_process_fields_and_legacy_data_preserve_original_bytes(self):
        invalid = [payload(block_cmdline=[".minecraft"]), payload(block_exes=["bad"]),
                   payload(block_folders=["relative"]), payload(safelist_exes=None),
                   payload(block_cmdline=[{"executable": "Game.exe", "contains": "x", "future": 1}])]
        for data in invalid:
            original = (json.dumps(data, indent=3) + "\r\n").encode()
            self.path.write_bytes(original)
            with self.subTest(data=data), self.assertRaises(ConfigError):
                load_config(self.path)
            self.assertEqual(self.path.read_bytes(), original)
            self.assertEqual(set(self.root.iterdir()), {self.path})

    def test_duplicate_promoted_and_nested_keys_preserve_bytes(self):
        for original in (
            b'{"windows":[],"block_exes":[],"block_exes":["Game.exe"]}',
            b'{"windows":[],"block_cmdline":[{"executable":"Game.exe","executable":"Other.exe","contains":"x"}]}',
            b'{"windows":[],"block_cmdline":[{"executable":"Game.exe","contains":"x","contains":"y"}]}',
        ):
            self.path.write_bytes(original)
            with self.subTest(original=original), self.assertRaisesRegex(ConfigError, "duplicada"):
                load_config(self.path)
            self.assertEqual(self.path.read_bytes(), original)

    def test_invalid_direct_model_does_not_start_write_or_replace(self):
        original = b'{"windows":[],"keep":"original"}\r\n'
        self.path.write_bytes(original)
        for config in (AppConfig(block_cmdline=(".minecraft",)),
                       AppConfig(block_exes=("bad",)),
                       AppConfig(extra={"block_folders": []}),
                       AppConfig(block_folders=(r"%MISSING%\Games",))):
            with patch.dict(os.environ, {}, clear=True), \
                 patch("core.config.tempfile.NamedTemporaryFile") as temporary, \
                 patch("core.config.os.replace") as replace:
                with self.subTest(config=config), self.assertRaises(ConfigError):
                    save_config(self.path, config)
                temporary.assert_not_called()
                replace.assert_not_called()
            self.assertEqual(self.path.read_bytes(), original)
            self.assertEqual(set(self.root.iterdir()), {self.path})


if __name__ == "__main__":
    unittest.main()

"""Testes de configuração isolados em diretórios temporários."""

from datetime import time, timezone
import json
import os
from pathlib import Path
import shutil
import unittest
from unittest.mock import patch
from uuid import uuid4

from core.config import (
    ConfigError, config_to_dict, default_config, default_config_path,
    load_config, parse_config, save_config,
)
from core.models import AppConfig, ScheduleWindow


def window(**changes):
    result = {"start": "09:00", "end": "17:00", "days": [0, 4, 6]}
    result.update(changes)
    return result


def canonical(data):
    return {"block_exes": [], "block_folders": [], "safelist_exes": [],
            "block_cmdline": [], **data}


class ParseConfigTests(unittest.TestCase):
    def test_default_has_no_windows_or_activated_suggestions(self):
        self.assertEqual(default_config(), AppConfig(windows=(), extra={}))
        self.assertEqual(config_to_dict(default_config()), canonical({"windows": []}))
        self.assertEqual(parse_config({"windows": []}), default_config())

    def test_missing_days_means_every_day(self):
        config = parse_config({"windows": [{"start": "00:00", "end": "23:59"}]})
        self.assertEqual(config.windows, (ScheduleWindow(time(0), time(23, 59)),))

    def test_empty_days_is_preserved_as_disabled_window(self):
        data = {"windows": [window(days=[])]}
        config = parse_config(data)
        self.assertEqual(config.windows[0].days, ())
        self.assertEqual(config_to_dict(config), canonical(data))

    def test_overnight_and_numeric_days_preserve_order(self):
        config = parse_config({"windows": [window(start="22:00", end="02:00", days=[6, 0])]})
        self.assertEqual(config.windows, (ScheduleWindow(time(22), time(2), (6, 0)),))

    def test_root_must_be_object(self):
        for data in (None, True, False, 0, 1.5, "", [], [window()]):
            with self.subTest(data=data), self.assertRaisesRegex(ConfigError, "raiz"):
                parse_config(data)

    def test_windows_is_required_list(self):
        for data in ({}, {"windows": None}, {"windows": {}}, {"windows": ()},
                     {"windows": True}, {"windows": "09:00"}):
            with self.subTest(data=data), self.assertRaisesRegex(ConfigError, "windows"):
                parse_config(data)

    def test_window_must_be_object(self):
        for value in (None, [], True, "09:00", 1):
            with self.subTest(value=value), self.assertRaisesRegex(ConfigError, r"windows\[0\]"):
                parse_config({"windows": [value]})

    def test_unknown_window_fields_are_rejected_instead_of_discarded(self):
        for key in ("label", "enabled", "strat"):
            with self.subTest(key=key), self.assertRaisesRegex(ConfigError, key):
                parse_config({"windows": [window(**{key: "value"})]})

    def test_time_format_is_strict_for_both_fields(self):
        values = (None, True, 900, [], "9:00", "09:0", "09:00:00", "24:00",
                  "23:60", "-1:00", " 09:00", "09:00 ", "09:00\n", "０９:００",
                  "٠٩:٠٠", "09:00Z", "09.00", "")
        for field in ("start", "end"):
            for value in values:
                with self.subTest(field=field, value=value):
                    with self.assertRaisesRegex(ConfigError, rf"windows\[0\].{field}"):
                        parse_config({"windows": [window(**{field: value})]})

    def test_start_and_end_are_required(self):
        for field in ("start", "end"):
            value = window()
            del value[field]
            with self.subTest(field=field), self.assertRaisesRegex(ConfigError, field):
                parse_config({"windows": [value]})

    def test_equal_times_rejected_even_when_disabled(self):
        for days in ([0], []):
            with self.subTest(days=days), self.assertRaisesRegex(ConfigError, "diferentes"):
                parse_config({"windows": [window(end="09:00", days=days)]})

    def test_days_require_unique_integers_without_bool(self):
        values = (None, True, False, "0", 0, (0,), {}, [True], [False], [0, True],
                  [0, False], [0.0], ["0"], [-1], [7], [0, 0], [6, 6], [[0]])
        for value in values:
            with self.subTest(value=value), self.assertRaisesRegex(ConfigError, "days"):
                parse_config({"windows": [window(days=value)]})

    def test_errors_locate_second_window(self):
        with self.assertRaisesRegex(ConfigError, r"windows\[1\].days\[1\]"):
            parse_config({"windows": [window(), window(days=[0, True])]})

    def test_extra_fields_are_opaque_and_copied(self):
        data = {"windows": [window()], "blocked_processes": "not-yet-validated",
                "future": {"values": [None, True, 7, "ação"]}, "pause": False}
        config = parse_config(data)
        self.assertEqual(config.extra["blocked_processes"], "not-yet-validated")
        self.assertNotIn("windows", config.extra)
        result = config_to_dict(config)
        self.assertEqual(result, canonical(data))
        data["future"]["values"].append("input mutation")
        result["future"]["values"].append("output mutation")
        self.assertEqual(config.extra["future"]["values"], [None, True, 7, "ação"])

    def test_direct_model_invalid_values_cannot_be_silently_serialized(self):
        invalid = (
            None,
            AppConfig(windows=[]),
            AppConfig(windows=(None,)),
            AppConfig(extra=[]),
            AppConfig(extra={"windows": []}),
            AppConfig(windows=(ScheduleWindow(time(9), time(9)),)),
            AppConfig(windows=(ScheduleWindow(time(9), time(10), (True,)),)),
            AppConfig(windows=(ScheduleWindow(time(9), time(10), [0]),)),
            AppConfig(windows=(ScheduleWindow("09:00", time(10)),)),
            AppConfig(windows=(ScheduleWindow(time(9, 0, 1), time(10)),)),
            AppConfig(windows=(ScheduleWindow(time(9, microsecond=1), time(10)),)),
            AppConfig(windows=(ScheduleWindow(time(9, tzinfo=timezone.utc), time(10)),)),
        )
        for config in invalid:
            with self.subTest(config=config), self.assertRaises(ConfigError):
                config_to_dict(config)


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        # Python 3.14 aplica ACL privada ao mkdir(0o700) de TemporaryDirectory
        # no Windows; o token restrito do runner não consegue reabrir a pasta.
        self.root = Path(__file__).resolve().parents[1] / f"config-test-{uuid4().hex}"
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.path = self.root / "config.json"

    def test_save_load_roundtrip_with_extra_fields(self):
        data = {"windows": [window(start="22:00", end="02:00"), window(days=[])],
                "blocked_sites": ["exemplo.com"], "future": {"ação": [None, True, 42]},
                "study_apps": "opaque"}
        config = parse_config(data)
        save_config(self.path, config)
        self.assertEqual(load_config(self.path), config)
        self.assertEqual(json.loads(self.path.read_text(encoding="utf-8")), canonical(data))
        self.assertEqual(set(self.root.iterdir()), {self.path})
        self.assertIn("ação", self.path.read_text(encoding="utf-8"))

    def test_save_creates_explicit_parent_directory(self):
        target = self.root / "nested" / "FocusBlocker" / "config.json"
        save_config(target, default_config())
        self.assertEqual(load_config(target), default_config())

    def test_successfully_replaces_existing_config(self):
        save_config(self.path, default_config())
        config = parse_config({"windows": [window()]})
        save_config(str(self.path), config)
        self.assertEqual(load_config(str(self.path)), config)
        self.assertEqual(set(self.root.iterdir()), {self.path})

    def test_invalid_json_always_raises_config_error_and_preserves_bytes(self):
        contents = (b"", b"{", b'{"windows":[],}', b'{"windows":[]} garbage',
                    b'{"windows":[],"extra":NaN}', b'{"windows":[],"extra":Infinity}',
                    b'{"windows":[],"extra":-Infinity}', b'\xff',
                    b'\xef\xbb\xbf{"windows":[]}',
                    ('{"windows":[],"extra":' + '9' * 5000 + '}').encode())
        for content in contents:
            with self.subTest(content=content[:40]):
                self.path.write_bytes(content)
                with self.assertRaises(ConfigError):
                    load_config(self.path)
                self.assertEqual(self.path.read_bytes(), content)
                self.assertEqual(set(self.root.iterdir()), {self.path})

    def test_invalid_root_and_fields_preserve_file(self):
        for data in (None, True, [], {}, {"windows": False},
                     {"windows": [window(days=[True])]},
                     {"windows": [window(label="must not be lost")]}):
            content = json.dumps(data).encode()
            self.path.write_bytes(content)
            with self.subTest(data=data), self.assertRaises(ConfigError):
                load_config(self.path)
            self.assertEqual(self.path.read_bytes(), content)

    def test_duplicate_json_keys_are_rejected_and_original_preserved(self):
        contents = (
            '{"windows":[],"windows":[{"start":"09:00","end":"10:00"}]}',
            '{"windows":[{"start":"09:00","start":"22:00","end":"23:00"}]}',
            '{"windows":[{"start":"09:00","end":"10:00","end":"11:00"}]}',
            '{"windows":[{"start":"09:00","end":"10:00","days":[0],"days":[]}]}',
            '{"windows":[],"extra":{"key":1,"key":2}}',
            '{"windows":[{"start":"09:00","st\\u0061rt":"10:00","end":"11:00"}]}',
        )
        for content in contents:
            original = content.encode("utf-8")
            self.path.write_bytes(original)
            with self.subTest(content=content), self.assertRaisesRegex(ConfigError, "duplicada"):
                load_config(self.path)
            self.assertEqual(self.path.read_bytes(), original)
            self.assertEqual(set(self.root.iterdir()), {self.path})

    def test_missing_file_and_directory_are_config_errors_without_creation(self):
        with self.assertRaises(ConfigError):
            load_config(self.path)
        self.assertFalse(self.path.exists())
        with self.assertRaises(ConfigError):
            load_config(self.root)

    def test_replace_failure_cleans_temp_and_preserves_original(self):
        original = b'{"windows":[],"keep":"original bytes"}\n'
        self.path.write_bytes(original)

        def fail_replace(source, destination):
            self.assertEqual(Path(source).parent, self.root)
            self.assertEqual(Path(destination), self.path)
            self.assertEqual(load_config(source), default_config())
            # Abrir para escrita é possível porque o temporário já está fechado.
            with Path(source).open("a", encoding="utf-8"):
                pass
            raise PermissionError("replace denied")

        with patch("core.config.os.replace", side_effect=fail_replace) as replace:
            with self.assertRaisesRegex(ConfigError, "replace denied"):
                save_config(self.path, default_config())
            replace.assert_called_once()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(set(self.root.iterdir()), {self.path})

    def test_fsync_failure_cleans_temp_and_preserves_original(self):
        original = b"original"
        self.path.write_bytes(original)
        with patch("core.config.os.fsync", side_effect=OSError("sync failed")):
            with patch("core.config.os.replace") as replace:
                with self.assertRaisesRegex(ConfigError, "sync failed"):
                    save_config(self.path, default_config())
                replace.assert_not_called()
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(set(self.root.iterdir()), {self.path})

    def test_validation_or_serialization_error_does_not_touch_original(self):
        original = b"original"
        self.path.write_bytes(original)
        configs = (
            AppConfig(windows=(ScheduleWindow(time(9), time(9)),)),
            AppConfig(extra={"not_json": object()}),
            AppConfig(extra={"not_json": float("nan")}),
            AppConfig(extra={"not_json": float("inf")}),
            AppConfig(extra={"invalid_utf8": "\ud800"}),
        )
        for config in configs:
            with self.subTest(config=config), patch("core.config.os.replace") as replace:
                with self.assertRaises(ConfigError):
                    save_config(self.path, config)
                replace.assert_not_called()
            self.assertEqual(self.path.read_bytes(), original)
            self.assertEqual(set(self.root.iterdir()), {self.path})

    def test_parent_creation_failure_is_config_error(self):
        self.path.write_bytes(b"original")
        with self.assertRaises(ConfigError):
            save_config(self.path / "child.json", default_config())
        self.assertEqual(self.path.read_bytes(), b"original")

    def test_default_path_uses_appdata_without_creating_anything(self):
        with patch.dict(os.environ, {"APPDATA": str(self.root)}):
            self.assertEqual(default_config_path(), self.root / "FocusBlocker" / "config.json")
        self.assertEqual(list(self.root.iterdir()), [])

    def test_missing_or_empty_appdata_has_no_silent_fallback(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ConfigError, "APPDATA"):
                default_config_path()
        with patch.dict(os.environ, {"APPDATA": ""}):
            with self.assertRaisesRegex(ConfigError, "APPDATA"):
                default_config_path()


if __name__ == "__main__":
    unittest.main()

"""Bounded visual projections preserve the complete ordered rule universe."""

import ast
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

from ui.rule_pagination import RulePage, rule_page, rule_page_for_index


class RulePaginationTests(unittest.TestCase):
    def test_empty_always_has_one_empty_page(self):
        expected = RulePage(0, 1, 0, 0, 0, ())
        for page in (0, 1, 1000, 10**100):
            for size in (1, 25, 100):
                with self.subTest(page=page, size=size):
                    self.assertEqual(rule_page((), page, size=size), expected)
        self.assertIsNone(rule_page_for_index((), 0))

    def test_default_size_boundaries_and_last_page_offsets(self):
        for total, count, start, stop in (
            (0, 1, 0, 0), (25, 1, 0, 25), (26, 2, 25, 26),
            (50, 2, 25, 50), (51, 3, 50, 51), (1000, 40, 975, 1000),
        ):
            source = tuple(range(total))
            with self.subTest(total=total):
                first = rule_page(source)
                self.assertEqual(first, RulePage(0, count, total, 0, min(25, total), source[:25]))
                last = rule_page(source, count - 1)
                self.assertEqual(last, RulePage(count - 1, count, total, start, stop, source[start:stop]))
                self.assertEqual(rule_page(source, count), last)
                self.assertEqual(rule_page(source, 10**100), last)

    def test_all_pages_reconstruct_order_and_duplicates(self):
        source = (91, 4, 4, 300, 0, 91, 7, 1, 4, 99)
        for size in (1, 2, 3, 4, 25):
            with self.subTest(size=size):
                count = rule_page(source, size=size).page_count
                pages = [rule_page(source, page, size=size) for page in range(count)]
                self.assertEqual(tuple(index for page in pages for index in page.indices), source)
                self.assertEqual(pages[0].start, 0)
                self.assertEqual(pages[-1].stop, len(source))
                self.assertTrue(all(left.stop == right.start for left, right in zip(pages, pages[1:])))
                self.assertTrue(all(len(page.indices) <= size for page in pages))

    def test_offsets_are_positions_not_original_indices(self):
        source = (800, 41, 0, 999, 5, 5, 2)
        self.assertEqual(rule_page(source, 1, size=3), RulePage(1, 3, 7, 3, 6, (999, 5, 5)))
        self.assertEqual(rule_page(source, 2, size=3), RulePage(2, 3, 7, 6, 7, (2,)))

    def test_lookup_first_duplicate_absent_and_page_boundaries(self):
        source = tuple(range(51)) + (0, 25, 50)
        for index, page in ((0, 0), (24, 0), (25, 1), (49, 1), (50, 2)):
            with self.subTest(index=index):
                self.assertEqual(rule_page_for_index(source, index), page)
        self.assertIsNone(rule_page_for_index(source, 100))
        reordered = (9, 80, 2, 9, 17, 80)
        self.assertEqual(rule_page_for_index(reordered, 80, size=2), 0)
        self.assertEqual(rule_page_for_index(reordered, 17, size=2), 2)

    def test_large_integers_use_exact_arithmetic(self):
        source = (10**100, 0, 10**100)
        self.assertEqual(rule_page(source, 10**100, size=1), RulePage(2, 3, 3, 2, 3, (10**100,)))
        self.assertEqual(rule_page(source, 10**100, size=10**100), RulePage(0, 1, 3, 0, 3, source))
        self.assertEqual(rule_page_for_index(source, 10**100, size=1), 0)

    def test_result_is_frozen_and_source_unchanged(self):
        source = (9, 2, 9)
        before = source[:]
        result = rule_page(source, 1, size=2)
        self.assertIsInstance(result, RulePage)
        self.assertIs(type(result.indices), tuple)
        for field in fields(RulePage):
            with self.subTest(field=field.name), self.assertRaises(FrozenInstanceError):
                setattr(result, field.name, None)
        with self.assertRaises(TypeError):
            result.indices[0] = 7
        self.assertEqual(source, before)
        self.assertEqual(rule_page(source, 1, size=2), result)

    def test_non_tuple_inputs_rejected_without_consuming_iterable(self):
        def unconsumable():
            raise AssertionError("iterable must not be consumed")
            yield 0

        iterator = unconsumable()
        try:
            for source in (None, [0], {0}, {0: 1}, "0", b"0", bytearray(b"0"), iterator):
                for operation in (lambda: rule_page(source), lambda: rule_page_for_index(source, 0)):
                    with self.subTest(source=type(source).__name__), self.assertRaises(TypeError):
                        operation()
        finally:
            iterator.close()

    def test_tuple_subclass_accepted_but_integer_subclasses_rejected(self):
        class IndexTuple(tuple):
            pass

        class Integer(int):
            pass

        self.assertEqual(rule_page(IndexTuple((7, 2))), RulePage(0, 1, 2, 0, 2, (7, 2)))
        self.assertEqual(rule_page_for_index(IndexTuple((7, 2)), 2), 0)
        operations = (
            lambda value: rule_page((value,)),
            lambda value: rule_page_for_index((value,), 0),
            lambda value: rule_page((0,), value),
            lambda value: rule_page((0,), size=value),
            lambda value: rule_page_for_index((0,), value),
            lambda value: rule_page_for_index((0,), 0, size=value),
        )
        for value in (False, True, Integer(0), Integer(1), 0.0, "0", None):
            for number, operation in enumerate(operations):
                with self.subTest(value=repr(value), operation=number), self.assertRaises(TypeError):
                    operation(value)

    def test_negative_values_and_zero_size_are_value_errors(self):
        operations = (
            lambda: rule_page((-1,)), lambda: rule_page_for_index((-1,), 0),
            lambda: rule_page((0,), -1), lambda: rule_page_for_index((0,), -1),
            lambda: rule_page((0,), size=0), lambda: rule_page_for_index((0,), 0, size=0),
            lambda: rule_page((), size=-1), lambda: rule_page_for_index((), 0, size=-1),
        )
        for number, operation in enumerate(operations):
            with self.subTest(operation=number), self.assertRaises(ValueError):
                operation()

    def test_invalid_tail_is_validated_even_outside_slice_or_after_lookup_match(self):
        for tail, error in ((True, TypeError), ("1", TypeError), (-1, ValueError)):
            source = (0,) * 25 + (tail,)
            for operation in (lambda: rule_page(source), lambda: rule_page_for_index(source, 0)):
                with self.subTest(tail=repr(tail)), self.assertRaises(error):
                    operation()

    def test_size_is_keyword_only(self):
        with self.assertRaises(TypeError):
            rule_page((0,), 0, 1)
        with self.assertRaises(TypeError):
            rule_page_for_index((0,), 0, 1)

    def test_operations_do_not_access_io_environment_or_clock(self):
        with patch("builtins.open", side_effect=AssertionError("IO")), \
             patch("pathlib.Path.resolve", side_effect=AssertionError("path discovery")), \
             patch("os.getenv", side_effect=AssertionError("environment")), \
             patch("time.time", side_effect=AssertionError("clock")), \
             patch("time.monotonic", side_effect=AssertionError("clock")):
            self.assertEqual(rule_page((3, 1, 3), 1, size=2), RulePage(1, 2, 3, 2, 3, (3,)))
            self.assertEqual(rule_page_for_index((3, 1, 3), 1, size=2), 0)

    def test_module_has_only_stdlib_imports_and_fresh_import_is_lazy(self):
        root = Path(__file__).resolve().parents[1]
        source = (root / "ui" / "rule_pagination.py").read_text(encoding="utf-8")
        tree = ast.parse(source)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                self.assertTrue(all(name.name.partition(".")[0] in sys.stdlib_module_names for name in node.names))
            elif isinstance(node, ast.ImportFrom):
                self.assertEqual(node.level, 0)
                self.assertIn(node.module.partition(".")[0], sys.stdlib_module_names)
        script = """
import builtins
original_import = builtins.__import__
def guarded_import(name, *args, **kwargs):
    if name.split('.')[0] in {'core', 'tkinter', 'customtkinter', 'psutil', 'pystray', 'PIL'}:
        raise AssertionError('unexpected dependency: ' + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import
from ui.rule_pagination import rule_page, rule_page_for_index
assert rule_page((99, 1), size=1).indices == (99,)
assert rule_page_for_index((99, 1), 1, size=1) == 1
"""
        result = subprocess.run(
            [sys.executable, "-B", "-c", script], cwd=root, capture_output=True, text=True, timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()

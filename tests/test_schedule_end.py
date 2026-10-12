"""Fins de intervalos recorrentes, com referência independente por minuto."""

from datetime import datetime, time, timedelta, timezone
import random
import unittest

from core.models import ScheduleWindow
from core.scheduler import current_block_end, is_blocking


def window(start, end, days):
    return ScheduleWindow(time(*start), time(*end), tuple(days))


class CurrentBlockEndTests(unittest.TestCase):
    def test_half_open_boundaries_and_subminute_clock(self):
        windows = [window((9, 0), (12, 0), [0])]
        for now, expected in (
            (datetime(2026, 10, 12, 8, 59, 59), None),
            (datetime(2026, 10, 12, 9), datetime(2026, 10, 12, 12)),
            (datetime(2026, 10, 12, 11, 59, 59, 999999), datetime(2026, 10, 12, 12)),
            (datetime(2026, 10, 12, 12), None),
            (datetime(2026, 10, 13, 10), None),
        ):
            with self.subTest(now=now):
                self.assertEqual(current_block_end(windows, now), expected)

    def test_overnight_uses_start_day_and_returns_next_date(self):
        windows = [window((22, 0), (2, 0), [0])]
        self.assertEqual(current_block_end(windows, datetime(2026, 10, 12, 23)), datetime(2026, 10, 13, 2))
        self.assertEqual(current_block_end(windows, datetime(2026, 10, 13, 1)), datetime(2026, 10, 13, 2))
        self.assertIsNone(current_block_end(windows, datetime(2026, 10, 13, 22)))

    def test_overlap_adjacency_and_one_minute_gap(self):
        windows = [window((9, 0), (11, 0), [0]), window((10, 0), (12, 0), [0]),
                   window((12, 0), (13, 0), [0]), window((13, 1), (14, 0), [0])]
        self.assertEqual(current_block_end(windows, datetime(2026, 10, 12, 10)), datetime(2026, 10, 12, 13))
        self.assertIsNone(current_block_end(windows, datetime(2026, 10, 12, 13)))
        self.assertEqual(current_block_end(windows, datetime(2026, 10, 12, 13, 1)), datetime(2026, 10, 12, 14))

    def test_weekly_seam_unites_sunday_monday_and_tuesday(self):
        windows = [window((22, 0), (2, 0), [6]), window((2, 0), (1, 0), [0]),
                   window((1, 0), (2, 0), [1])]
        expected = datetime(2026, 10, 13, 2)
        for now in (datetime(2026, 10, 11, 23), datetime(2026, 10, 12, 0), datetime(2026, 10, 13, 1)):
            self.assertEqual(current_block_end(windows, now), expected)
        self.assertIsNone(current_block_end(windows, expected))

    def test_calendar_year_and_leap_boundaries(self):
        for now in (datetime(2026, 12, 31, 23), datetime(2024, 2, 28, 23)):
            windows = [window((22, 0), (2, 0), [now.weekday()])]
            expected = (now + timedelta(days=1)).replace(hour=2)
            self.assertEqual(current_block_end(windows, now), expected)

    def test_empty_disabled_and_continuous_week_distinguished_by_active(self):
        now = datetime(2026, 10, 11, 23)
        for windows in ([], [window((9, 0), (10, 0), [])]):
            self.assertIsNone(current_block_end(windows, now))
            self.assertFalse(is_blocking(windows, now))
        all_week = [window((0, 0), (12, 0), range(7)), window((12, 0), (0, 0), range(7))]
        self.assertIsNone(current_block_end(all_week, now))
        self.assertTrue(is_blocking(all_week, now))

    def test_generator_consumed_once_source_preserved_and_aware_clock_rejected(self):
        windows = [window((9, 0), (12, 0), [0])]
        class Once:
            used = False
            def __iter__(self):
                if self.used:
                    raise AssertionError("second consumption")
                self.used = True
                return iter(windows)
        self.assertEqual(current_block_end(Once(), datetime(2026, 10, 12, 10)), datetime(2026, 10, 12, 12))
        self.assertEqual(windows, [window((9, 0), (12, 0), [0])])
        with self.assertRaises(ValueError):
            current_block_end(windows, datetime(2026, 10, 12, tzinfo=timezone.utc))

    def test_independent_weekly_minute_reference_fixed_and_seeded_scenarios(self):
        rng = random.Random(625871)
        scenarios = [[], [window((22, 0), (2, 0), [6])]]
        for _ in range(10):
            windows = []
            for _ in range(rng.randint(1, 7)):
                start = rng.randrange(1440)
                end = (start + rng.randrange(1, 1440)) % 1440
                windows.append(window(divmod(start, 60), divmod(end, 60), rng.sample(range(7), rng.randrange(8))))
            scenarios.append(windows)
        base = datetime(2026, 10, 12)
        for windows in scenarios:
            active = set()
            for item in windows:
                start = item.start.hour * 60 + item.start.minute
                length = (item.end.hour * 60 + item.end.minute - start) % 1440
                for day in item.days:
                    active.update((day * 1440 + start + offset) % 10080 for offset in range(length))
            points = {0, 10079, *rng.sample(range(10080), 30)}
            for minute in points:
                now = base + timedelta(minutes=minute, seconds=31)
                expected = None
                if minute in active and len(active) < 10080:
                    distance = next(d for d in range(1, 10081) if (minute + d) % 10080 not in active)
                    expected = base + timedelta(minutes=minute + distance)
                with self.subTest(windows=windows, now=now):
                    self.assertEqual(current_block_end(iter(windows), now), expected)


if __name__ == "__main__":
    unittest.main()

"""Fixed-calendar checks for RF01-04 and the D04/D08 boundary rules."""

from datetime import date, datetime, time, timedelta, timezone
import unittest

from core.models import ScheduleWindow
from core.scheduler import (
    ScheduleInterval,
    effective_intervals,
    is_blocking,
    next_block_start,
)


def window(start: str, end: str, days: tuple[int, ...] = tuple(range(7))):
    return ScheduleWindow(time.fromisoformat(start), time.fromisoformat(end), days)


class SchedulerTests(unittest.TestCase):
    MONDAY = date(2026, 10, 5)

    def test_empty_and_disabled_schedules(self):
        now = datetime(2026, 10, 5, 10)
        for windows in ((), (window("09:00", "17:00", ()),)):
            with self.subTest(windows=windows):
                self.assertEqual(effective_intervals(windows, self.MONDAY, self.MONDAY), ())
                self.assertFalse(is_blocking(windows, now))
                self.assertIsNone(next_block_start(windows, now))

    def test_default_days_recur_every_day(self):
        windows = (window("09:00", "10:00"),)
        intervals = effective_intervals(windows, self.MONDAY, date(2026, 10, 11))
        self.assertEqual(len(intervals), 7)
        for day_index in range(7):
            day = self.MONDAY + timedelta(days=day_index)
            with self.subTest(day=day):
                self.assertEqual(intervals[day_index], ScheduleInterval(
                    datetime.combine(day, time(9)), datetime.combine(day, time(10))
                ))
                self.assertTrue(is_blocking(windows, datetime.combine(day, time(9, 30))))

    def test_start_included_end_excluded_at_subminute_precision(self):
        windows = (window("09:00", "10:00", (0,)),)
        start = datetime(2026, 10, 5, 9)
        end = datetime(2026, 10, 5, 10)
        for instant, expected in (
            (start - timedelta(microseconds=1), False), (start, True),
            (end - timedelta(microseconds=1), True), (end, False),
        ):
            with self.subTest(instant=instant):
                self.assertEqual(is_blocking(windows, instant), expected)

    def test_night_window_uses_start_day_and_preserves_endpoints(self):
        windows = (window("22:00", "02:00", (0,)),)
        expected = (ScheduleInterval(datetime(2026, 10, 5, 22), datetime(2026, 10, 6, 2)),)
        for day in (self.MONDAY, date(2026, 10, 6)):
            with self.subTest(day=day):
                self.assertEqual(effective_intervals(windows, day, day), expected)
        self.assertFalse(is_blocking(windows, datetime(2026, 10, 5, 1)))
        self.assertTrue(is_blocking(windows, datetime(2026, 10, 6, 1)))
        self.assertFalse(is_blocking(windows, datetime(2026, 10, 6, 2)))
        self.assertFalse(is_blocking(windows, datetime(2026, 10, 6, 22)))

    def test_occurrences_ending_at_range_start_are_excluded(self):
        windows = (window("22:00", "00:00", (6,)),)
        self.assertEqual(effective_intervals(windows, self.MONDAY, self.MONDAY), ())
        self.assertFalse(is_blocking(windows, datetime(2026, 10, 5)))

    def test_overlap_adjacency_duplicates_and_unsorted_input_union(self):
        windows = (
            window("12:00", "13:00", (0,)), window("10:00", "12:00", (0,)),
            window("09:00", "11:00", (0,)), window("09:30", "10:30", (0,)),
            window("09:00", "11:00", (0,)), window("15:00", "16:00", (0,)),
        )
        self.assertEqual(effective_intervals(windows, self.MONDAY, self.MONDAY), (
            ScheduleInterval(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 13)),
            ScheduleInterval(datetime(2026, 10, 5, 15), datetime(2026, 10, 5, 16)),
        ))
        self.assertTrue(is_blocking(windows, datetime(2026, 10, 5, 12)))
        self.assertFalse(is_blocking(windows, datetime(2026, 10, 5, 14)))

    def test_week_rollover_union_and_next_start(self):
        windows = (window("22:00", "02:00", (6,)), window("01:00", "03:00", (0,)))
        self.assertEqual(effective_intervals(windows, self.MONDAY, self.MONDAY), (
            ScheduleInterval(datetime(2026, 10, 4, 22), datetime(2026, 10, 5, 3)),
        ))
        self.assertTrue(is_blocking(windows, datetime(2026, 10, 5, 2)))
        self.assertEqual(next_block_start(windows, datetime(2026, 10, 5, 0, 30)),
                         datetime(2026, 10, 11, 22))
        self.assertEqual(next_block_start(windows, datetime(2026, 10, 4, 21)),
                         datetime(2026, 10, 4, 22))

    def test_adjacency_at_midnight_is_continuous(self):
        windows = (window("22:00", "00:00", (6,)), window("00:00", "02:00", (0,)))
        self.assertTrue(is_blocking(windows, datetime(2026, 10, 5)))
        self.assertEqual(next_block_start(windows, datetime(2026, 10, 4, 23)),
                         datetime(2026, 10, 11, 22))
        self.assertEqual(effective_intervals(windows, date(2026, 10, 4), self.MONDAY), (
            ScheduleInterval(datetime(2026, 10, 4, 22), datetime(2026, 10, 5, 2)),
        ))

    def test_next_start_is_strict_and_skips_internal_window_starts(self):
        windows = (
            window("09:00", "11:00", (0,)), window("10:00", "12:00", (0,)),
            window("12:00", "13:00", (0,)), window("15:00", "16:00", (0,)),
        )
        for hour, minute, expected in (
            (8, 59, datetime(2026, 10, 5, 9)),
            (9, 0, datetime(2026, 10, 5, 15)),
            (9, 30, datetime(2026, 10, 5, 15)),
            (12, 0, datetime(2026, 10, 5, 15)),
            (13, 0, datetime(2026, 10, 5, 15)),
            (15, 0, datetime(2026, 10, 12, 9)),
        ):
            with self.subTest(hour=hour, minute=minute):
                self.assertEqual(next_block_start(windows, datetime(2026, 10, 5, hour, minute)), expected)

    def test_next_start_waits_full_week_when_only_current_block_remains(self):
        windows = (window("09:00", "17:00", (0,)),)
        for now in (datetime(2026, 10, 5, 10), datetime(2026, 10, 5, 17)):
            with self.subTest(now=now):
                self.assertEqual(next_block_start(windows, now), datetime(2026, 10, 12, 9))

    def test_continuity_across_generation_limit_does_not_invent_a_start(self):
        # A near-week-long chain crosses Monday and ends on Saturday morning.
        windows = (
            window("08:00", "07:00", (6, 0, 1, 2, 3, 4)),
            window("07:00", "09:00", (0, 1, 2, 3, 4, 5)),
        )
        now = datetime(2026, 10, 5, 6)
        self.assertTrue(is_blocking(windows, now))
        self.assertEqual(next_block_start(windows, now), datetime(2026, 10, 11, 8))
        self.assertEqual(effective_intervals(windows, self.MONDAY, date(2026, 10, 10)), (
            ScheduleInterval(datetime(2026, 10, 4, 8), datetime(2026, 10, 10, 9)),
        ))

    def test_full_24h_coverage_from_distinct_windows_has_no_next_start(self):
        for windows in (
            (window("00:00", "12:00"), window("12:00", "00:00")),
            (window("22:00", "10:00"), window("09:00", "23:00")),
        ):
            for day_index in range(8):
                for hour in (0, 9, 12, 22, 23):
                    now = datetime(2026, 10, 4, hour) + timedelta(days=day_index)
                    with self.subTest(windows=windows, now=now):
                        self.assertTrue(is_blocking(windows, now))
                        self.assertIsNone(next_block_start(windows, now))
        windows = (window("00:00", "12:00"), window("12:00", "00:00"))
        self.assertEqual(effective_intervals(windows, self.MONDAY, date(2026, 10, 11)), (
            ScheduleInterval(datetime(2026, 10, 5), datetime(2026, 10, 12)),
        ))

    def test_small_weekly_gap_produces_a_real_transition(self):
        windows = (
            window("00:00", "12:00"), window("12:00", "00:00", (0, 1, 2, 3, 4, 5)),
            window("12:01", "00:00", (6,)),
        )
        self.assertFalse(is_blocking(windows, datetime(2026, 10, 11, 12)))
        self.assertEqual(next_block_start(windows, datetime(2026, 10, 5, 10)),
                         datetime(2026, 10, 11, 12, 1))
        self.assertEqual(next_block_start(windows, datetime(2026, 10, 11, 12, 1)),
                         datetime(2026, 10, 18, 12, 1))

    def test_end_of_year_and_leap_day_use_calendar_dates(self):
        for day, days, following in (
            (date(2026, 12, 31), (3,), date(2027, 1, 1)),
            (date(2028, 2, 28), (0,), date(2028, 2, 29)),
        ):
            with self.subTest(day=day):
                windows = (window("23:00", "01:00", days),)
                self.assertEqual(effective_intervals(windows, following, following), (
                    ScheduleInterval(datetime.combine(day, time(23)),
                                     datetime.combine(following, time(1))),
                ))

    def test_one_shot_window_iterables(self):
        windows = (window("09:00", "11:00", (0,)), window("10:00", "12:00", (0,)))
        self.assertEqual(effective_intervals(iter(windows), self.MONDAY, self.MONDAY), (
            ScheduleInterval(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 12)),
        ))
        self.assertTrue(is_blocking(iter(windows), datetime(2026, 10, 5, 11)))
        self.assertEqual(next_block_start(iter(windows), datetime(2026, 10, 5, 10)),
                         datetime(2026, 10, 12, 9))

    def test_reversed_date_range_is_rejected(self):
        with self.assertRaises(ValueError):
            effective_intervals((), date(2026, 10, 6), self.MONDAY)

    def test_aware_datetime_is_rejected_in_local_civil_api(self):
        now = datetime(2026, 10, 5, tzinfo=timezone.utc)
        for query in (is_blocking, next_block_start):
            with self.subTest(query=query.__name__), self.assertRaises(ValueError):
                query((), now)


if __name__ == "__main__":
    unittest.main()

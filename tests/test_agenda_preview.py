"""Calendários fixos e referência independente por minuto para a prévia."""

from dataclasses import FrozenInstanceError
from datetime import date, datetime, time, timedelta
from pathlib import Path
import random
import unittest
from unittest.mock import patch

from core.agenda_preview import DayPreview, WeekPreview, week_preview
from core.models import ScheduleWindow
from core.scheduler import ScheduleInterval


def window(start, end, days=tuple(range(7))):
    return ScheduleWindow(time.fromisoformat(start), time.fromisoformat(end), days)


def reference_day(windows, day):
    """Membership direto: dia inicial ou cauda do dia anterior, sem scheduler."""
    occupied = []
    for minute in range(1440):
        active = False
        for item in windows:
            start = item.start.hour * 60 + item.start.minute
            end = item.end.hour * 60 + item.end.minute
            if start < end:
                active |= day.weekday() in item.days and start <= minute < end
            else:
                active |= (
                    (day.weekday() in item.days and minute >= start)
                    or ((day.weekday() - 1) % 7 in item.days and minute < end)
                )
        occupied.append(active)

    midnight = datetime.combine(day, time.min)
    intervals = []
    run_start = None
    for minute, active in enumerate([*occupied, False]):
        if active and run_start is None:
            run_start = minute
        elif not active and run_start is not None:
            intervals.append(ScheduleInterval(
                midnight + timedelta(minutes=run_start),
                midnight + timedelta(minutes=minute),
            ))
            run_start = None
    return DayPreview(day, tuple(intervals), sum(occupied))


class AgendaPreviewTests(unittest.TestCase):
    MONDAY = date(2026, 10, 5)

    def test_empty_and_disabled_have_seven_zero_days(self):
        expected_days = tuple(
            DayPreview(self.MONDAY + timedelta(days=offset), (), 0)
            for offset in range(7)
        )
        for windows in ((), (window("22:00", "02:00", ()),)):
            with self.subTest(windows=windows):
                self.assertEqual(week_preview(windows, self.MONDAY),
                                 WeekPreview(self.MONDAY, expected_days, 0))

    def test_each_anchor_weekday_selects_same_monday_to_sunday(self):
        windows = (window("09:00", "10:30"),)
        for offset in range(7):
            with self.subTest(offset=offset):
                result = week_preview(windows, self.MONDAY + timedelta(days=offset))
                self.assertEqual(result.start, self.MONDAY)
                self.assertEqual(result.total_minutes, 630)
                for day_index, day in enumerate(result.days):
                    expected_date = self.MONDAY + timedelta(days=day_index)
                    self.assertEqual(day, DayPreview(expected_date, (ScheduleInterval(
                        datetime.combine(expected_date, time(9)),
                        datetime.combine(expected_date, time(10, 30)),
                    ),), 90))

    def test_overlap_adjacency_containment_duplicates_and_gaps(self):
        windows = (
            window("15:00", "16:00", (0,)), window("12:00", "13:00", (0,)),
            window("10:00", "12:00", (0,)), window("09:30", "10:30", (0,)),
            window("09:00", "11:00", (0,)), window("09:00", "11:00", (0,)),
        )
        result = week_preview(windows, self.MONDAY)
        self.assertEqual(result.days[0], DayPreview(self.MONDAY, (
            ScheduleInterval(datetime(2026, 10, 5, 9), datetime(2026, 10, 5, 13)),
            ScheduleInterval(datetime(2026, 10, 5, 15), datetime(2026, 10, 5, 16)),
        ), 300))
        self.assertEqual(result.total_minutes, 300)
        self.assertTrue(all(day.minutes == 0 for day in result.days[1:]))

    def test_overnight_splits_between_start_day_and_following_day(self):
        result = week_preview((window("22:30", "02:15", (1,)),), self.MONDAY)
        self.assertEqual(result.days[1], DayPreview(date(2026, 10, 6), (
            ScheduleInterval(datetime(2026, 10, 6, 22, 30), datetime(2026, 10, 7)),
        ), 90))
        self.assertEqual(result.days[2], DayPreview(date(2026, 10, 7), (
            ScheduleInterval(datetime(2026, 10, 7), datetime(2026, 10, 7, 2, 15)),
        ), 135))
        self.assertEqual([day.minutes for day in result.days], [0, 90, 135, 0, 0, 0, 0])
        self.assertEqual(result.total_minutes, 225)

    def test_previous_sunday_tail_and_current_sunday_are_clipped_to_week(self):
        result = week_preview((window("22:00", "02:00", (6,)),), self.MONDAY)
        self.assertEqual(result.days[0], DayPreview(self.MONDAY, (
            ScheduleInterval(datetime(2026, 10, 5), datetime(2026, 10, 5, 2)),
        ), 120))
        self.assertEqual(result.days[6], DayPreview(date(2026, 10, 11), (
            ScheduleInterval(datetime(2026, 10, 11, 22), datetime(2026, 10, 12)),
        ), 120))
        self.assertEqual(result.total_minutes, 240)

    def test_previous_sunday_tail_unions_with_monday_without_double_counting(self):
        result = week_preview((
            window("22:00", "02:00", (6,)), window("01:00", "03:00", (0,)),
        ), self.MONDAY)
        self.assertEqual(result.days[0], DayPreview(self.MONDAY, (
            ScheduleInterval(datetime(2026, 10, 5), datetime(2026, 10, 5, 3)),
        ), 180))
        self.assertEqual(result.total_minutes, 300)

    def test_ending_at_midnight_has_no_zero_length_tail(self):
        result = week_preview((window("22:00", "00:00", (6,)),), self.MONDAY)
        self.assertEqual(result.days[0], DayPreview(self.MONDAY, (), 0))
        self.assertEqual(result.days[6].intervals, (
            ScheduleInterval(datetime(2026, 10, 11, 22), datetime(2026, 10, 12)),
        ))
        self.assertEqual(result.total_minutes, 120)

    def test_midnight_adjacency_and_multiday_union_are_clipped_per_day(self):
        result = week_preview((
            window("22:00", "10:00"), window("09:00", "23:00"),
        ), self.MONDAY)
        self.assertEqual(result.total_minutes, 10080)
        for day in result.days:
            midnight = datetime.combine(day.date, time.min)
            self.assertEqual(day.intervals, (
                ScheduleInterval(midnight, midnight + timedelta(days=1)),
            ))
            self.assertEqual(day.minutes, 1440)

    def test_minute_precision_preserves_one_minute_gap_and_half_open_edges(self):
        result = week_preview((
            window("00:00", "00:01", (0,)),
            window("00:02", "00:03", (0,)),
            window("23:59", "00:00", (0,)),
        ), self.MONDAY)
        self.assertEqual(result.days[0].intervals, (
            ScheduleInterval(datetime(2026, 10, 5), datetime(2026, 10, 5, 0, 1)),
            ScheduleInterval(datetime(2026, 10, 5, 0, 2), datetime(2026, 10, 5, 0, 3)),
            ScheduleInterval(datetime(2026, 10, 5, 23, 59), datetime(2026, 10, 6)),
        ))
        self.assertEqual(result.days[1].intervals, ())
        self.assertEqual(result.total_minutes, 3)

    def test_year_rollover_and_leap_day_are_calendar_dates(self):
        for anchor, monday, minutes in (
            (date(2027, 1, 1), date(2026, 12, 28), [0, 0, 0, 60, 60, 0, 0]),
            (date(2028, 2, 29), date(2028, 2, 28), [60, 60, 0, 0, 0, 0, 0]),
        ):
            start_day = 3 if anchor.year == 2027 else 0
            with self.subTest(anchor=anchor):
                result = week_preview((window("23:00", "01:00", (start_day,)),), anchor)
                self.assertEqual(result.start, monday)
                self.assertEqual([day.date for day in result.days],
                                 [monday + timedelta(days=i) for i in range(7)])
                self.assertEqual([day.minutes for day in result.days], minutes)
                self.assertEqual(result.total_minutes, 120)

    def test_input_iterable_is_consumed_once_for_entire_week(self):
        windows = [window("22:00", "02:00", (6,)), window("01:00", "03:00", (0,))]

        class Once:
            used = False

            def __iter__(self):
                if self.used:
                    raise AssertionError("iterable consumido novamente")
                self.used = True
                return iter(windows)

        expected = week_preview(windows, self.MONDAY)
        for iterable in (Once(), iter(windows), (item for item in windows)):
            with self.subTest(iterable=type(iterable).__name__):
                self.assertEqual(week_preview(iterable, self.MONDAY), expected)
        self.assertEqual(windows, [window("22:00", "02:00", (6,)), window("01:00", "03:00", (0,))])

    def test_result_is_immutable_and_queries_do_not_use_files_or_clock(self):
        with patch.object(Path, "open", side_effect=AssertionError("IO proibido")), \
             patch("os.replace", side_effect=AssertionError("IO proibido")), \
             patch("time.time", side_effect=AssertionError("relógio proibido")):
            result = week_preview((window("09:00", "10:00", (0,)),), self.MONDAY)
        with self.assertRaises(FrozenInstanceError):
            result.total_minutes = 0
        with self.assertRaises(FrozenInstanceError):
            result.days[0].minutes = 0
        with self.assertRaises(FrozenInstanceError):
            result.days[0].intervals[0].end = datetime(2026, 10, 5, 11)

    def test_independent_minute_reference_for_fixed_and_generated_scenarios(self):
        scenarios = [
            (), (window("09:00", "10:00", ()),),
            (window("22:00", "02:00", (6,)), window("01:00", "03:00", (0,))),
            (window("00:00", "12:00"), window("12:00", "00:00")),
            (window("08:00", "07:00", (6, 0, 1, 2, 3, 4)),
             window("07:00", "09:00", (0, 1, 2, 3, 4, 5))),
        ]
        rng = random.Random(20261011)
        for _ in range(12):
            windows = []
            for _ in range(6):
                start, end = rng.sample(range(1440), 2)
                days = tuple(day for day in range(7) if rng.choice((True, False)))
                windows.append(ScheduleWindow(time(start // 60, start % 60),
                                              time(end // 60, end % 60), days))
            scenarios.append(tuple(windows))

        for index, windows in enumerate(scenarios):
            expected = tuple(reference_day(windows, self.MONDAY + timedelta(days=i))
                             for i in range(7))
            with self.subTest(scenario=index):
                result = week_preview(iter(windows), self.MONDAY + timedelta(days=3))
                self.assertEqual(result.days, expected)
                self.assertEqual(result.total_minutes, sum(day.minutes for day in expected))


if __name__ == "__main__":
    unittest.main()

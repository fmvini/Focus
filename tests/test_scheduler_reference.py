"""Compara a agenda com uma referência por dia/minuto, sem união de intervalos."""

from datetime import datetime, time, timedelta
import random
import unittest

from core.models import ScheduleWindow
from core.scheduler import is_blocking, next_block_start


def reference_blocking(windows, now):
    minute = now.hour * 60 + now.minute
    for window in windows:
        start = window.start.hour * 60 + window.start.minute
        end = window.end.hour * 60 + window.end.minute
        if start < end:
            if now.weekday() in window.days and start <= minute < end:
                return True
        elif (
            now.weekday() in window.days and minute >= start
        ) or (
            (now.weekday() - 1) % 7 in window.days and minute < end
        ):
            return True
    return False


class SchedulerReferenceTests(unittest.TestCase):
    def scenarios(self):
        rng = random.Random(20261005)
        scenarios = [(), (ScheduleWindow(time(22), time(2), (6,)),)]
        for _ in range(8):
            windows = []
            for _ in range(4):
                start, end = rng.sample(range(0, 1440, 30), 2)
                days = tuple(day for day in range(7) if rng.choice((True, False)))
                windows.append(ScheduleWindow(
                    time(start // 60, start % 60),
                    time(end // 60, end % 60),
                    days,
                ))
            scenarios.append(tuple(windows))
        return scenarios

    def test_weekly_state_matches_reference(self):
        anchor = datetime(2026, 10, 4)
        for scenario_index, windows in enumerate(self.scenarios()):
            for offset in range(0, 14 * 1440, 17):
                now = anchor + timedelta(minutes=offset, seconds=35)
                with self.subTest(scenario=scenario_index, now=now):
                    self.assertEqual(is_blocking(windows, now), reference_blocking(windows, now))

    def test_next_start_is_a_real_free_to_blocking_transition(self):
        now = datetime(2026, 10, 4, 23, 43, 35)
        for scenario_index, windows in enumerate(self.scenarios()):
            candidate = now.replace(second=0, microsecond=0) + timedelta(minutes=1)
            expected = None
            for _ in range(8 * 1440):
                if reference_blocking(windows, candidate) and not reference_blocking(
                    windows, candidate - timedelta(seconds=1)
                ):
                    expected = candidate
                    break
                candidate += timedelta(minutes=1)
            with self.subTest(scenario=scenario_index):
                self.assertEqual(next_block_start(windows, now), expected)


if __name__ == "__main__":
    unittest.main()

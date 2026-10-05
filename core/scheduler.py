"""Pure scheduling over validated windows in the local civil calendar.

All intervals include their start and exclude their end. No clock, filesystem,
pause state or operating-system integration is consulted here.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from .models import ScheduleWindow


_DAY_MINUTES = 24 * 60
_WEEK_MINUTES = 7 * _DAY_MINUTES


@dataclass(frozen=True)
class ScheduleInterval:
    """A merged, half-open interval in local naive datetimes."""

    start: datetime
    end: datetime


def _minute_of_day(value: time) -> int:
    return value.hour * 60 + value.minute


def _weekly_intervals(
    windows: Iterable[ScheduleWindow],
) -> tuple[tuple[int, int], ...]:
    """Union a recurring week, splitting Sunday continuations at Monday."""
    occurrences = []
    for window in windows:
        start_minute = _minute_of_day(window.start)
        duration = (_minute_of_day(window.end) - start_minute) % _DAY_MINUTES
        for weekday in window.days:
            start = weekday * _DAY_MINUTES + start_minute
            end = start + duration
            if end > _WEEK_MINUTES:
                occurrences.append((start, _WEEK_MINUTES))
                occurrences.append((0, end - _WEEK_MINUTES))
            else:
                occurrences.append((start, end))

    merged: list[tuple[int, int]] = []
    for start, end in sorted(occurrences):
        if merged and start <= merged[-1][1]:
            previous_start, previous_end = merged[-1]
            merged[-1] = (previous_start, max(previous_end, end))
        else:
            merged.append((start, end))
    return tuple(merged)


def _require_local(now: datetime) -> None:
    if now.tzinfo is not None:
        raise ValueError("now must be a naive datetime in the local calendar")


def effective_intervals(
    windows: Iterable[ScheduleWindow], start_date: date, end_date: date
) -> tuple[ScheduleInterval, ...]:
    """Union occurrences intersecting the inclusive range of calendar days.

    Endpoints are preserved rather than clipped to midnight. The preceding
    start day is included for overnight continuations. This finite occurrence
    view is not used to infer transitions of the recurring weekly schedule.
    """
    if end_date < start_date:
        raise ValueError("end_date must not precede start_date")

    windows = tuple(windows)
    range_start = datetime.combine(start_date, time.min)
    range_end = datetime.combine(end_date + timedelta(days=1), time.min)
    occurrences = []
    # A valid individual window lasts less than 24 hours.
    day = start_date - timedelta(days=1)
    while day <= end_date:
        for window in windows:
            if day.weekday() not in window.days:
                continue
            start = datetime.combine(day, window.start)
            end_day = day + timedelta(days=window.end < window.start)
            end = datetime.combine(end_day, window.end)
            if start < range_end and end > range_start:
                occurrences.append(ScheduleInterval(start, end))
        day += timedelta(days=1)

    merged: list[ScheduleInterval] = []
    for interval in sorted(occurrences, key=lambda item: (item.start, item.end)):
        if merged and interval.start <= merged[-1].end:
            previous = merged[-1]
            merged[-1] = ScheduleInterval(
                previous.start, max(previous.end, interval.end)
            )
        else:
            merged.append(interval)
    return tuple(merged)


def is_blocking(windows: Iterable[ScheduleWindow], now: datetime) -> bool:
    """Whether the recurring schedule includes now, without pause handling."""
    _require_local(now)
    week_start = datetime.combine(
        now.date() - timedelta(days=now.weekday()), time.min
    )
    elapsed = now - week_start
    return any(
        timedelta(minutes=start) <= elapsed < timedelta(minutes=end)
        for start, end in _weekly_intervals(windows)
    )


def next_block_start(
    windows: Iterable[ScheduleWindow], now: datetime
) -> datetime | None:
    """Return the next effective start strictly after now.

    Only unblocked-to-blocked transitions count. A start inside an existing
    union (including one crossing the weekly seam) never becomes a candidate.
    An empty or continuously covered week has no future effective start.
    """
    _require_local(now)
    intervals = _weekly_intervals(windows)
    if not intervals or intervals == ((0, _WEEK_MINUTES),):
        return None

    week_start = datetime.combine(
        now.date() - timedelta(days=now.weekday()), time.min
    )
    candidates = []
    for start, _ in intervals:
        # Monday midnight continues Sunday's final interval if both touch it.
        if start == 0 and intervals[-1][1] == _WEEK_MINUTES:
            continue
        candidate = week_start + timedelta(minutes=start)
        if candidate <= now:
            candidate += timedelta(days=7)
        candidates.append(candidate)
    return min(candidates)

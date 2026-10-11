"""Prévia pura dos minutos planejados, sem medir foco ou aplicar bloqueios."""

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from core.models import ScheduleWindow
from core.scheduler import ScheduleInterval, effective_intervals


@dataclass(frozen=True)
class DayPreview:
    date: date
    intervals: tuple[ScheduleInterval, ...]
    minutes: int


@dataclass(frozen=True)
class WeekPreview:
    start: date
    days: tuple[DayPreview, ...]
    total_minutes: int


def week_preview(
    windows: Iterable[ScheduleWindow], anchor_date: date,
) -> WeekPreview:
    """Resume a semana local de segunda a domingo de ``anchor_date``.

    Como no scheduler, as janelas devem estar previamente validadas, em
    precisão de minuto. Intervalos incluem início e excluem fim, com união
    de sobrepostas/adjacentes antes do recorte diário. A continuação do
    domingo anterior conta na segunda; a do domingo atual termina no limite
    desta semana. Um iterable de uso único é consumido apenas uma vez.
    """
    start = anchor_date - timedelta(days=anchor_date.weekday())
    intervals = effective_intervals(windows, start, start + timedelta(days=6))
    days = []
    for offset in range(7):
        day = start + timedelta(days=offset)
        day_start = datetime.combine(day, time.min)
        day_end = day_start + timedelta(days=1)
        clipped = tuple(
            ScheduleInterval(max(interval.start, day_start), min(interval.end, day_end))
            for interval in intervals
            if interval.start < day_end and interval.end > day_start
        )
        minutes = sum(
            (interval.end - interval.start) // timedelta(minutes=1)
            for interval in clipped
        )
        days.append(DayPreview(day, clipped, minutes))
    return WeekPreview(start, tuple(days), sum(day.minutes for day in days))

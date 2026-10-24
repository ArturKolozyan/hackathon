"""Относительные даты в Europe/Moscow. Сегодня берётся из часов приложения."""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

MONTH_STEMS: tuple[tuple[str, int], ...] = (
    ("январ", 1),
    ("феврал", 2),
    ("март", 3),
    ("апрел", 4),
    ("мая", 5),
    ("мае", 5),
    ("май", 5),
    ("июн", 6),
    ("июл", 7),
    ("август", 8),
    ("сентябр", 9),
    ("октябр", 10),
    ("ноябр", 11),
    ("декабр", 12),
)


def week_bounds(today: date) -> tuple[date, date]:
    """Календарная неделя понедельник–воскресенье, в которой лежит today."""
    start = today - timedelta(days=today.weekday())
    return start, start + timedelta(days=6)


def previous_month(today: date) -> tuple[int, int]:
    first = today.replace(day=1)
    prev = first - timedelta(days=1)
    return prev.year, prev.month


def extract_month(text: str, today: date) -> tuple[int, int]:
    """Именованный месяц, «прошлый» или текущий. Год — текущий, кроме прошлого месяца."""
    low = text.lower().replace("ё", "е")
    if re.search(r"прошл\w*\s+месяц", low):
        return previous_month(today)
    for stem, number in MONTH_STEMS:
        if re.search(rf"(?<![а-я]){stem}", low):
            return today.year, number
    return today.year, today.month


def month_mentioned(text: str) -> bool:
    low = text.lower().replace("ё", "е")
    if re.search(r"прошл\w*\s+месяц|этот месяц|за месяц", low):
        return True
    return any(re.search(rf"(?<![а-я]){stem}", low) for stem, _number in MONTH_STEMS)


def first_due(starts_on: date, day_of_month: int) -> date:
    year, month = starts_on.year, starts_on.month
    for _ in range(18):
        last = calendar.monthrange(year, month)[1]
        due = date(year, month, min(day_of_month, last))
        if due >= starts_on:
            return due
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1
    return starts_on


def parse_explicit_start(text: str, today: date) -> date | None:
    low = text.lower().replace("ё", "е")
    if "со следующего месяца" in low or "с следующего месяца" in low:
        year, month = today.year, today.month
        if month == 12:
            return date(year + 1, 1, 1)
        return date(year, month + 1, 1)
    match = re.search(
        r"\bс\s+(\d{1,2})\s+(январ\w*|феврал\w*|март\w*|апрел\w*|ма[йяе]\w*|июн\w*|июл\w*|август\w*|сентябр\w*|октябр\w*|ноябр\w*|декабр\w*)",
        low,
    )
    if match is None:
        return None
    day = int(match.group(1))
    if not 1 <= day <= 31:
        return None
    year, month = extract_month(match.group(2), today)
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day, last))

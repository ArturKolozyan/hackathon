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


_PERIODS = (
    "today", "tomorrow", "yesterday", "this_week", "next_week", "last_week",
    "this_month", "last_month", "next_month", "this_quarter", "last_quarter", "this_year", "last_year", "all",
)


def _month_span(year: int, month: int) -> tuple[date, date]:
    return date(year, month, 1), date(year, month, calendar.monthrange(year, month)[1])


def _shift_month(year: int, month: int, delta: int) -> tuple[int, int]:
    index = year * 12 + (month - 1) + delta
    return index // 12, index % 12 + 1


def resolve_period(period: str | None, today: date) -> tuple[date | None, date | None]:
    """Ключ периода → границы включительно. Неизвестное — (None, None), значит без фильтра по дате."""
    key = (period or "").strip().lower()
    if not key or key == "all":
        return None, None
    if key == "today":
        return today, today
    if key == "tomorrow":
        day = today + timedelta(days=1)
        return day, day
    if key == "yesterday":
        day = today - timedelta(days=1)
        return day, day
    if key in {"this_week", "next_week", "last_week"}:
        start, end = week_bounds(today)
        shift = {"this_week": 0, "next_week": 7, "last_week": -7}[key]
        return start + timedelta(days=shift), end + timedelta(days=shift)
    if key in {"this_month", "last_month", "next_month"}:
        delta = {"this_month": 0, "last_month": -1, "next_month": 1}[key]
        return _month_span(*_shift_month(today.year, today.month, delta))
    if key in {"this_quarter", "last_quarter"}:
        first = ((today.month - 1) // 3) * 3 + 1
        year, month = _shift_month(today.year, first, -3 if key == "last_quarter" else 0)
        start, _ = _month_span(year, month)
        _, end = _month_span(*_shift_month(year, month, 2))
        return start, end
    if key == "this_year":
        return date(today.year, 1, 1), date(today.year, 12, 31)
    if key == "last_year":
        return date(today.year - 1, 1, 1), date(today.year - 1, 12, 31)
    if re.fullmatch(r"\d{4}-\d{2}", key):
        year, month = int(key[:4]), int(key[5:])
        if 1 <= month <= 12:
            return _month_span(year, month)
    if re.fullmatch(r"\d{4}", key):
        return date(int(key), 1, 1), date(int(key), 12, 31)
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", key):
        try:
            day = date.fromisoformat(key)
        except ValueError:
            return None, None
        return day, day
    return None, None


def parse_day(value: object) -> date | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


WEEKDAYS = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")

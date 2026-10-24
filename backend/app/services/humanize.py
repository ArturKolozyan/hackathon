"""Человеческие суммы, даты и сроки по-русски. Общие для Telegram и ассистента."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

MONTHS_GENITIVE = (
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)
CURRENCY_SIGN = {"RUB": "₽", "USD": "$", "EUR": "€"}
THIN = "\u202f"
NBSP = "\u00a0"


def plural(count: int, one: str, few: str, many: str) -> str:
    tail = abs(count) % 100
    if 11 <= tail <= 14:
        return many
    last = tail % 10
    if last == 1:
        return one
    if 2 <= last <= 4:
        return few
    return many


def days(count: int) -> str:
    return f"{count} {plural(count, 'день', 'дня', 'дней')}"


def money(amount: object, currency: str) -> str:
    """12 500 ₽, 40,50 $. Копейки только когда они есть."""
    value = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    whole = f"{int(abs(value)):,}".replace(",", THIN)
    cents = int((abs(value) * 100) % 100)
    text = f"{whole},{cents:02d}" if cents else whole
    if value < 0:
        text = "−" + text
    return f"{text}{NBSP}{CURRENCY_SIGN.get(currency, currency)}"


def ru_date(value: date, *, year: bool = True) -> str:
    text = f"{value.day} {MONTHS_GENITIVE[value.month - 1]}"
    return f"{text} {value.year}" if year else text


def due_phrase(due: date, today: date) -> str:
    """Срок относительно сегодня: «сегодня», «через 3 дня», «просрочено на 2 дня»."""
    delta = (due - today).days
    if delta == 0:
        return "сегодня"
    if delta == 1:
        return "завтра"
    if delta > 1:
        return f"через {days(delta)}"
    return f"просрочено на {days(-delta)}"

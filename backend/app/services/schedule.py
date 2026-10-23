import calendar
from datetime import date, datetime
from zoneinfo import ZoneInfo

MONTHS_RU = (
    "январь",
    "февраль",
    "март",
    "апрель",
    "май",
    "июнь",
    "июль",
    "август",
    "сентябрь",
    "октябрь",
    "ноябрь",
    "декабрь",
)


def due_date(year: int, month: int, day_of_month: int) -> date:
    """Нет такого числа в месяце — последний день (product.md)."""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, min(day_of_month, last))


def add_months(value: date, months: int) -> date:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    return due_date(year, month, value.day)


def iter_months(start: date, end: date):
    year, month = start.year, start.month
    stop = (end.year, end.month)
    while (year, month) <= stop:
        yield year, month
        if month == 12:
            year += 1
            month = 1
        else:
            month += 1


def classify(due: date, paid_at: datetime | None, today: date, soon_days: int) -> str:
    if paid_at is not None:
        return "paid"
    # В день срока ещё не просрочка: оплата в этот день — вовремя.
    if today > due:
        return "overdue"
    if (due - today).days <= soon_days:
        return "due_soon"
    return "upcoming"


def bucket_for(status: str) -> str:
    return {"overdue": "overdue", "due_soon": "soon", "upcoming": "rest", "paid": "history"}[status]


def paid_on_time(paid_at: datetime, due: date, zone: ZoneInfo) -> bool:
    """Сравниваем календарные даты в едином часовом поясе команды."""
    return paid_at.astimezone(zone).date() <= due


def period_key(year: int, month: int) -> str:
    return f"{year:04d}-{month:02d}"


def period_label(year: int, month: int) -> str:
    return f"{MONTHS_RU[month - 1]} {year}"


def parse_paid_at(raw: str | None, *, now: datetime, zone: ZoneInfo) -> datetime:
    if raw is None or not str(raw).strip():
        return now
    text = str(raw).strip()
    if len(text) == 10:
        day = date.fromisoformat(text)
        return datetime(day.year, day.month, day.day, 12, 0, tzinfo=zone)
    parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=zone)
    return parsed.astimezone(zone)

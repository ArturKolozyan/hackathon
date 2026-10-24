"""Когда по периоду есть событие для каналов.

should_remind — союз с инбоксом: до срока ≤ SOON_DAYS, просрочка тоже.
notification_events режет это окно на два разных события:
напоминание с T-3 по день срока и «просрочено» со следующего дня.
Оба шлются один раз: дедуп живёт в notify.
Оплаченный и архивный молчат.
"""

from datetime import date, datetime

REMINDER = "occurrence.reminder"
OVERDUE = "occurrence.overdue"


def should_remind(
    *,
    due: date,
    paid_at: datetime | None,
    archived: bool,
    today: date,
    soon_days: int,
) -> bool:
    return bool(
        notification_events(due=due, paid_at=paid_at, archived=archived, today=today, soon_days=soon_days)
    )


def notification_events(
    *,
    due: date,
    paid_at: datetime | None,
    archived: bool,
    today: date,
    soon_days: int,
) -> list[str]:
    if archived or paid_at is not None:
        return []
    days = (due - today).days
    if days < 0:
        return [OVERDUE]
    if days <= soon_days:
        return [REMINDER]
    return []

"""Каденция напоминаний одного периода.

Организация включает тумблерами: за 7, за 3 и за 1 день до срока и «о просрочке».
Просрочка — каждый день, начиная со следующего после срока, пока не оплачено.
Ключ события (d7, d3, d1, overdue, overdue.rN) дедуплицирует доставку: один раз
на период, вид и получателя.
За один проход уходит только ближайшая уже наступившая точка: платёж,
созданный за два дня, получает одно «за 3 дня», а не T-7 вместе с T-3.
Оплаченный молчит. Архив не шлёт будущие точки; повтор уже существующей
просрочки остаётся, пока его не выключили при архивации.
"""

from datetime import date, datetime

REMINDER = "occurrence.reminder"
OVERDUE = "occurrence.overdue"
DIGEST = "occurrence.overdue.digest"
# Дни, которые можно включить. Порядок — как в настройках.
REMINDER_CHOICES = (7, 3, 1)
DEFAULT_OFFSETS = REMINDER_CHOICES


def is_reminder(event: str) -> bool:
    return event.startswith(f"{REMINDER}.") or event == REMINDER


def is_overdue(event: str) -> bool:
    return event.startswith(OVERDUE)


def reminder_event(days_until: int, offsets: tuple[int, ...]) -> str | None:
    reached = [offset for offset in offsets if days_until <= offset]
    if not reached:
        return None
    return f"{REMINDER}.d{min(reached)}"


def overdue_event(days_late: int) -> str | None:
    """Первый день просрочки — overdue, дальше каждый день новый ключ overdue.rN."""
    if days_late < 1:
        return None
    if days_late == 1:
        return OVERDUE
    return f"{OVERDUE}.r{days_late - 1}"


def notification_events(
    *,
    due: date,
    paid_at: datetime | None,
    archived: bool,
    today: date,
    soon_days: int | None = None,
    offsets: tuple[int, ...] | None = None,
    overdue: bool = True,
    remind_archived_overdue: bool = True,
) -> list[str]:
    if paid_at is not None:
        return []
    chosen = offsets
    if chosen is None:
        chosen = (soon_days,) if soon_days is not None else DEFAULT_OFFSETS
    days_until = (due - today).days
    if days_until < 0:
        if not overdue or (archived and not remind_archived_overdue):
            return []
        event = overdue_event(-days_until)
        return [event] if event else []
    if archived:
        return []
    event = reminder_event(days_until, chosen)
    return [event] if event else []


def should_remind(
    *,
    due: date,
    paid_at: datetime | None,
    archived: bool,
    today: date,
    soon_days: int | None = None,
    offsets: tuple[int, ...] | None = None,
    overdue: bool = True,
    remind_archived_overdue: bool = True,
) -> bool:
    return bool(
        notification_events(
            due=due,
            paid_at=paid_at,
            archived=archived,
            today=today,
            soon_days=soon_days,
            offsets=offsets,
            overdue=overdue,
            remind_archived_overdue=remind_archived_overdue,
        )
    )

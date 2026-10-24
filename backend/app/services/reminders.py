"""Каденция напоминаний одного периода.

Точки до срока задаёт организация (по умолчанию за 7 и за 3 дня, в день срока молчим).
Просрочка — на следующий день, затем повтор каждые N дней (по умолчанию каждый день), пока не оплачено.
За один проход уходит только ближайшая уже наступившая точка: платёж,
созданный за два дня, получает одно «скоро», а не T-7 вместе с T-3.
Оплаченный молчит. Архив не шлёт будущие точки; повтор уже существующей
просрочки остаётся, пока его не выключили при архивации.
"""

from datetime import date, datetime

REMINDER = "occurrence.reminder"
OVERDUE = "occurrence.overdue"
DIGEST = "occurrence.overdue.digest"
DEFAULT_OFFSETS = (7, 3)
DEFAULT_OVERDUE_REPEAT = 1


def is_reminder(event: str) -> bool:
    return event.startswith(f"{REMINDER}.") or event == REMINDER


def is_overdue(event: str) -> bool:
    return event.startswith(OVERDUE)


def reminder_event(days_until: int, offsets: tuple[int, ...]) -> str | None:
    reached = [offset for offset in offsets if days_until <= offset]
    if not reached:
        return None
    return f"{REMINDER}.d{min(reached)}"


def overdue_event(days_late: int, every: int) -> str | None:
    if days_late < 1:
        return None
    step = every if every >= 1 else 1
    repeat = (days_late - 1) // step
    if repeat == 0:
        return OVERDUE
    return f"{OVERDUE}.r{repeat}"


def notification_events(
    *,
    due: date,
    paid_at: datetime | None,
    archived: bool,
    today: date,
    soon_days: int | None = None,
    offsets: tuple[int, ...] | None = None,
    overdue_repeat_days: int = DEFAULT_OVERDUE_REPEAT,
    remind_archived_overdue: bool = True,
) -> list[str]:
    if paid_at is not None:
        return []
    chosen = offsets
    if chosen is None:
        chosen = (soon_days,) if soon_days is not None else DEFAULT_OFFSETS
    days_until = (due - today).days
    if days_until < 0:
        if archived and not remind_archived_overdue:
            return []
        event = overdue_event(-days_until, overdue_repeat_days)
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
    overdue_repeat_days: int = DEFAULT_OVERDUE_REPEAT,
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
            overdue_repeat_days=overdue_repeat_days,
            remind_archived_overdue=remind_archived_overdue,
        )
    )

"""Настройки организации. Нет строки — часовой пояс и копия владельцу из .env, напоминания по умолчанию."""

from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.organization import OrganizationSettings
from app.services import time as clock
from app.services.reminders import DEFAULT_OFFSETS, REMINDER_CHOICES

SINGLETON = 1


@dataclass(frozen=True)
class OrgConfig:
    timezone: str
    # Включённые дни до срока из REMINDER_CHOICES, по убыванию.
    reminder_days: tuple[int, ...]
    overdue_reminders: bool
    owner_overdue_copy: bool
    stored: bool


def parse_reminder_days(raw: str) -> tuple[int, ...]:
    """Строка из базы: подмножество 7, 3, 1. Лишнее молча отбрасывается."""
    days = set()
    for part in (raw or "").split(","):
        part = part.strip()
        if part.isdigit() and int(part) in REMINDER_CHOICES:
            days.add(int(part))
    return tuple(sorted(days, reverse=True))


def format_reminder_days(days: tuple[int, ...]) -> str:
    return ",".join(str(day) for day in days)


def _from_env(settings: Settings) -> OrgConfig:
    return OrgConfig(
        timezone=settings.timezone,
        reminder_days=DEFAULT_OFFSETS,
        overdue_reminders=True,
        owner_overdue_copy=settings.owner_overdue_copy,
        stored=False,
    )


def _from_row(row: OrganizationSettings) -> OrgConfig:
    return OrgConfig(
        timezone=row.timezone,
        reminder_days=parse_reminder_days(row.reminder_days),
        overdue_reminders=row.overdue_reminders,
        owner_overdue_copy=row.owner_overdue_copy,
        stored=True,
    )


def load_org(db: Session, settings: Settings | None = None) -> OrgConfig:
    current = settings or get_settings()
    row = db.get(OrganizationSettings, SINGLETON)
    if row is None:
        return _from_env(current)
    return _from_row(row)


def ensure_organization(settings: Settings | None = None) -> None:
    """Строка появляется при старте из .env и дальше живёт в базе."""
    from app.core.database import SessionLocal

    current = settings or get_settings()
    db = SessionLocal()
    try:
        if db.get(OrganizationSettings, SINGLETON) is not None:
            return
        defaults = _from_env(current)
        db.add(
            OrganizationSettings(
                id=SINGLETON,
                timezone=defaults.timezone,
                reminder_days=format_reminder_days(defaults.reminder_days),
                overdue_reminders=defaults.overdue_reminders,
                owner_overdue_copy=defaults.owner_overdue_copy,
                updated_at=clock.now(),
            )
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def save_org(
    db: Session,
    *,
    timezone: str | None = None,
    reminder_days: tuple[int, ...] | None = None,
    overdue_reminders: bool | None = None,
    owner_overdue_copy: bool | None = None,
) -> OrgConfig:
    current = load_org(db)
    zone_name = (timezone or current.timezone).strip()
    try:
        ZoneInfo(zone_name)
    except ZoneInfoNotFoundError:
        raise HTTPException(status_code=422, detail="Неизвестный часовой пояс") from None
    days = current.reminder_days if reminder_days is None else tuple(sorted(set(reminder_days), reverse=True))
    if any(day not in REMINDER_CHOICES for day in days):
        raise HTTPException(status_code=422, detail="Напоминать можно за 7, 3 или 1 день")
    overdue = current.overdue_reminders if overdue_reminders is None else overdue_reminders
    copy = current.owner_overdue_copy if owner_overdue_copy is None else owner_overdue_copy
    row = db.get(OrganizationSettings, SINGLETON)
    if row is None:
        row = OrganizationSettings(id=SINGLETON)
        db.add(row)
    row.timezone = zone_name
    row.reminder_days = format_reminder_days(days)
    row.overdue_reminders = overdue
    row.owner_overdue_copy = copy
    row.updated_at = clock.now()
    db.flush()
    return _from_row(row)


def bind_org_zone(db: Session):
    """Часовой пояс организации на текущий контекст: «сегодня», просрочка и даты оплаты считаются в нём.

    Возвращает токен для clock.reset_zone. API делает это в OrgZoneMiddleware, воркер и бот — сами.
    """
    return clock.bind_zone(load_org(db).timezone)

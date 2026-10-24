"""Настройки организации. Нет строки — берутся значения из .env."""

from dataclasses import dataclass
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.models.organization import OrganizationSettings
from app.services import time as clock
from app.services.reminders import DEFAULT_OFFSETS, DEFAULT_OVERDUE_REPEAT

SINGLETON = 1


@dataclass(frozen=True)
class OrgConfig:
    timezone: str
    reminder_days: tuple[int, ...]
    overdue_repeat_days: int
    owner_overdue_copy: bool
    stored: bool


def parse_reminder_days(raw: str) -> tuple[int, ...]:
    parts = [item.strip() for item in raw.replace(";", ",").split(",") if item.strip()]
    if not parts:
        raise HTTPException(status_code=422, detail="Укажите дни напоминаний, например 7,3")
    days: list[int] = []
    for part in parts:
        try:
            value = int(part)
        except ValueError:
            raise HTTPException(status_code=422, detail="Дни напоминаний — целые числа") from None
        if value < 0 or value > 90:
            raise HTTPException(status_code=422, detail="День напоминания от 0 до 90")
        days.append(value)
    unique = tuple(sorted(set(days), reverse=True))
    if not any(day >= 3 for day in unique):
        raise HTTPException(status_code=422, detail="В каденции нужен срок не меньше чем за 3 дня")
    return unique


def format_reminder_days(days: tuple[int, ...]) -> str:
    return ",".join(str(day) for day in days)


def _from_env(settings: Settings) -> OrgConfig:
    raw = (settings.reminder_days or "").strip()
    try:
        days = parse_reminder_days(raw) if raw else DEFAULT_OFFSETS
    except HTTPException:
        days = DEFAULT_OFFSETS
    repeat = settings.overdue_repeat_days if settings.overdue_repeat_days >= 1 else DEFAULT_OVERDUE_REPEAT
    return OrgConfig(
        timezone=settings.timezone,
        reminder_days=days,
        overdue_repeat_days=repeat,
        owner_overdue_copy=settings.owner_overdue_copy,
        stored=False,
    )


def _from_row(row: OrganizationSettings) -> OrgConfig:
    try:
        days = parse_reminder_days(row.reminder_days)
    except HTTPException:
        days = DEFAULT_OFFSETS
    return OrgConfig(
        timezone=row.timezone,
        reminder_days=days,
        overdue_repeat_days=row.overdue_repeat_days,
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
                overdue_repeat_days=defaults.overdue_repeat_days,
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
    reminder_days: str | None = None,
    overdue_repeat_days: int | None = None,
    owner_overdue_copy: bool | None = None,
) -> OrgConfig:
    current = load_org(db)
    zone_name = (timezone or current.timezone).strip()
    try:
        ZoneInfo(zone_name)
    except ZoneInfoNotFoundError:
        raise HTTPException(status_code=422, detail="Неизвестный часовой пояс") from None
    days = parse_reminder_days(reminder_days) if reminder_days is not None else current.reminder_days
    repeat = current.overdue_repeat_days if overdue_repeat_days is None else overdue_repeat_days
    if repeat < 1 or repeat > 90:
        raise HTTPException(status_code=422, detail="Повтор просрочки — от 1 до 90 дней")
    copy = current.owner_overdue_copy if owner_overdue_copy is None else owner_overdue_copy
    row = db.get(OrganizationSettings, SINGLETON)
    if row is None:
        row = OrganizationSettings(id=SINGLETON)
        db.add(row)
    row.timezone = zone_name
    row.reminder_days = format_reminder_days(days)
    row.overdue_repeat_days = repeat
    row.owner_overdue_copy = copy
    row.updated_at = clock.now()
    db.flush()
    return _from_row(row)

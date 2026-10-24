"""Личные каналы.

notify_scope=mine — только платежи, где человек ответственный.
notify_scope=department — все платежи его отделов.
Выключенный тумблер Telegram молчит и для ответственного.
Просрочку в личку можно выключить (notify_overdue). Чат отдела её всё равно получает.
email_team_ids / telegram_team_ids по-прежнему принимаются и проверяются.
"""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import ChannelSubscription, User
from app.services import time as clock
from app.services.access import memberships_of

EMAIL = "email"
TELEGRAM = "telegram"


def _ids(db: Session, user: User) -> list[UUID]:
    return [row.team_id for row in memberships_of(db, user)]


def _chosen(db: Session, user_id: UUID, channel: str) -> set[UUID]:
    rows = db.scalars(
        select(ChannelSubscription.team_id).where(
            ChannelSubscription.user_id == user_id,
            ChannelSubscription.channel == channel,
        )
    ).all()
    return set(rows)


def effective_team_ids(db: Session, user: User, channel: str) -> list[UUID]:
    ids = _ids(db, user)
    scoped = user.email_scope_set if channel == EMAIL else user.telegram_scope_set
    if not scoped:
        return ids
    chosen = _chosen(db, user.id, channel)
    return [team_id for team_id in ids if team_id in chosen]


def _in_personal_scope(user: User, responsible: bool) -> bool:
    if user.notify_scope == "department":
        return True
    return responsible


def wants_email(
    db: Session,
    user: User,
    team_id: UUID,
    *,
    responsible: bool = False,
    event: str = "",
) -> bool:
    del db, team_id
    if not user.is_active or not user.email_reminders:
        return False
    if event == "occurrence.overdue" and not user.notify_overdue:
        return False
    return _in_personal_scope(user, responsible)


def wants_telegram(
    db: Session,
    user: User,
    team_id: UUID,
    *,
    responsible: bool,
    event: str = "",
) -> bool:
    del db, team_id
    if not user.is_active or user.telegram_user_id is None or not user.telegram_reminders:
        return False
    if event == "occurrence.overdue" and not user.notify_overdue:
        return False
    return _in_personal_scope(user, responsible)


def _replace(db: Session, user_id: UUID, channel: str, team_ids: list[UUID]) -> None:
    db.execute(
        delete(ChannelSubscription).where(
            ChannelSubscription.user_id == user_id,
            ChannelSubscription.channel == channel,
        )
    )
    seen: set[UUID] = set()
    for team_id in team_ids:
        if team_id in seen:
            continue
        seen.add(team_id)
        db.add(ChannelSubscription(user_id=user_id, channel=channel, team_id=team_id))


def save_personal(
    db: Session,
    user: User,
    *,
    email_enabled: bool,
    email_team_ids: list[UUID],
    telegram_enabled: bool,
    telegram_team_ids: list[UUID],
    notify_scope: str | None = None,
    notify_overdue: bool | None = None,
) -> None:
    allowed = set(_ids(db, user))
    if user.is_owner:
        from app.models import Team

        allowed = set(db.scalars(select(Team.id)).all())
    foreign = [team_id for team_id in [*email_team_ids, *telegram_team_ids] if team_id not in allowed]
    if foreign:
        raise HTTPException(status_code=422, detail="Можно выбрать только свои команды")
    if notify_scope is not None and notify_scope not in {"mine", "department"}:
        raise HTTPException(status_code=422, detail="Скоуп: mine или department")
    user.email_reminders = email_enabled
    user.telegram_reminders = telegram_enabled
    user.email_scope_set = True
    user.telegram_scope_set = True
    if notify_scope is not None:
        user.notify_scope = notify_scope
    if notify_overdue is not None:
        user.notify_overdue = notify_overdue
    user.updated_at = clock.now()
    _replace(db, user.id, EMAIL, email_team_ids)
    _replace(db, user.id, TELEGRAM, telegram_team_ids)
    db.commit()
    db.refresh(user)

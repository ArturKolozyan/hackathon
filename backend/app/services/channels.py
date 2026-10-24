"""Личные каналы: почта и Telegram, каждый со своим набором команд.

Пока человек не сохранял выбор, канал слушает все его команды.
Ответственный за платёж получает Telegram в личку даже без этой команды в скоупе
и даже при выключенном тумблере личных напоминаний. Почта так не обходится.
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


def wants_email(db: Session, user: User, team_id: UUID) -> bool:
    if not user.is_active or not user.email_reminders:
        return False
    if not user.email_scope_set:
        return True
    return team_id in _chosen(db, user.id, EMAIL)


def wants_telegram(db: Session, user: User, team_id: UUID, *, responsible: bool) -> bool:
    if not user.is_active or user.telegram_user_id is None:
        return False
    if responsible:
        return True
    if not user.telegram_reminders:
        return False
    if not user.telegram_scope_set:
        return True
    return team_id in _chosen(db, user.id, TELEGRAM)


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
) -> None:
    allowed = set(_ids(db, user))
    foreign = [team_id for team_id in [*email_team_ids, *telegram_team_ids] if team_id not in allowed]
    if foreign:
        raise HTTPException(status_code=422, detail="Можно выбрать только свои команды")
    user.email_reminders = email_enabled
    user.telegram_reminders = telegram_enabled
    user.email_scope_set = True
    user.telegram_scope_set = True
    user.updated_at = clock.now()
    _replace(db, user.id, EMAIL, email_team_ids)
    _replace(db, user.id, TELEGRAM, telegram_team_ids)
    db.commit()
    db.refresh(user)

"""Личные каналы.

notify_scope=mine — только платежи, где человек ответственный.
notify_scope=department — все платежи его отделов.
Выключенный тумблер Telegram молчит и для ответственного.
Просрочку в личку можно выключить (notify_overdue). Чат отдела её всё равно получает.

Почта настраивается по отделам: у каждого отдела свой тумблер и свой охват
(строка channel_subscriptions с channel=email и scope). Пока человек ничего
не выбирал (email_scope_set ложь), письма идут по всем его отделам с охватом notify_scope.
Владелец может не состоять в отделах: по таким отделам писем нет, пока он сам их не включит.
"""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import ChannelSubscription, User
from app.services import time as clock
from app.services.access import department_access, memberships_of

EMAIL = "email"
TELEGRAM = "telegram"


def _ids(db: Session, user: User) -> list[UUID]:
    return [row.team_id for row in department_access(db, user)]


def _default_ids(db: Session, user: User) -> list[UUID]:
    """Отделы канала, пока человек ничего не выбирал: те, где он состоит. Владелец без места — ни одного."""
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
    scoped = user.email_scope_set if channel == EMAIL else user.telegram_scope_set
    if not scoped:
        return _default_ids(db, user)
    chosen = _chosen(db, user.id, channel)
    return [team_id for team_id in _ids(db, user) if team_id in chosen]


def email_teams(db: Session, user: User) -> list[tuple[UUID, str, bool, str]]:
    """(отдел, название, письма включены, охват) по всем отделам, которые человек видит."""
    if user.email_scope_set:
        rows = db.scalars(
            select(ChannelSubscription).where(
                ChannelSubscription.user_id == user.id,
                ChannelSubscription.channel == EMAIL,
            )
        ).all()
        chosen = {row.team_id: row.scope for row in rows}
    else:
        chosen = {team_id: user.notify_scope for team_id in _default_ids(db, user)}
    result = []
    for row in department_access(db, user):
        scope = chosen.get(row.team_id)
        result.append((row.team_id, row.team.name, scope is not None, scope or user.notify_scope or "mine"))
    return result


def email_scope_for(db: Session, user: User, team_id: UUID) -> str | None:
    """Охват писем по отделу или None, если письма по нему выключены."""
    if not user.email_scope_set:
        if team_id not in set(_default_ids(db, user)):
            return None
        return user.notify_scope or "mine"
    row = db.get(ChannelSubscription, (user.id, EMAIL, team_id))
    return row.scope if row is not None else None


def set_email_team(db: Session, user: User, team_id: UUID, *, enabled: bool, scope: str) -> None:
    if team_id not in set(_ids(db, user)):
        raise HTTPException(status_code=403, detail="Вы не в этом отделе")
    if scope not in {"mine", "department"}:
        raise HTTPException(status_code=422, detail="Охват: mine или department")
    if not user.email_scope_set:
        # Первая ручная настройка: фиксируем текущие отделы строками, дальше правим одну.
        for current in _default_ids(db, user):
            if db.get(ChannelSubscription, (user.id, EMAIL, current)) is None:
                db.add(ChannelSubscription(user_id=user.id, channel=EMAIL, team_id=current, scope=user.notify_scope or "mine"))
        db.flush()
        user.email_scope_set = True
    row = db.get(ChannelSubscription, (user.id, EMAIL, team_id))
    if enabled:
        if row is None:
            db.add(ChannelSubscription(user_id=user.id, channel=EMAIL, team_id=team_id, scope=scope))
        else:
            row.scope = scope
    elif row is not None:
        db.delete(row)
    user.updated_at = clock.now()
    db.commit()
    db.refresh(user)


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
    if not user.is_active or not user.email_reminders:
        return False
    if event.startswith("occurrence.overdue") and not user.notify_overdue:
        return False
    if responsible and not user.email_scope_set:
        return True
    scope = email_scope_for(db, user, team_id)
    if scope is None:
        return False
    return scope == "department" or responsible


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
    if event.startswith("occurrence.overdue") and not user.notify_overdue:
        return False
    return _in_personal_scope(user, responsible)


def _replace(db: Session, user: User, channel: str, team_ids: list[UUID]) -> None:
    kept = {
        row.team_id: row.scope
        for row in db.scalars(
            select(ChannelSubscription).where(
                ChannelSubscription.user_id == user.id,
                ChannelSubscription.channel == channel,
            )
        ).all()
    }
    db.execute(
        delete(ChannelSubscription).where(
            ChannelSubscription.user_id == user.id,
            ChannelSubscription.channel == channel,
        )
    )
    seen: set[UUID] = set()
    for team_id in team_ids:
        if team_id in seen:
            continue
        seen.add(team_id)
        scope = kept.get(team_id, user.notify_scope or "mine")
        db.add(ChannelSubscription(user_id=user.id, channel=channel, team_id=team_id, scope=scope))


def save_personal(
    db: Session,
    user: User,
    *,
    email_enabled: bool,
    email_team_ids: list[UUID] | None,
    telegram_enabled: bool,
    telegram_team_ids: list[UUID] | None,
    notify_scope: str | None = None,
    notify_overdue: bool | None = None,
) -> None:
    allowed = set(_ids(db, user))
    foreign = [team_id for team_id in [*(email_team_ids or []), *(telegram_team_ids or [])] if team_id not in allowed]
    if foreign:
        raise HTTPException(status_code=422, detail="Можно выбрать только свои отделы")
    if notify_scope is not None and notify_scope not in {"mine", "department"}:
        raise HTTPException(status_code=422, detail="Скоуп: mine или department")
    user.email_reminders = email_enabled
    user.telegram_reminders = telegram_enabled
    if notify_scope is not None:
        user.notify_scope = notify_scope
    if notify_overdue is not None:
        user.notify_overdue = notify_overdue
    user.updated_at = clock.now()
    if email_team_ids is not None:
        _replace(db, user, EMAIL, email_team_ids)
        user.email_scope_set = True
    if telegram_team_ids is not None:
        _replace(db, user, TELEGRAM, telegram_team_ids)
        user.telegram_scope_set = True
    db.commit()
    db.refresh(user)

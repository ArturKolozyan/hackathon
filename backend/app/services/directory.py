"""Люди организации. Эндпоинты кейса GET/POST/PATCH/DELETE /users."""

import secrets
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.security import hash_password, revoke_user_sessions
from app.integrations.email import public_url
from app.models import Membership, RecurringPayment, Team, User
from app.schemas.telegram import TelegramLinkOut
from app.schemas.user import DepartmentRole, InviteOut, UserCreate, UserOut, UserUpdate
from app.services import time as clock
from app.services.accounts import create_verified_user
from app.services.audit import record
from app.services.teams import add_member, membership

OWNER_LOCKED = "Учётку владельца нельзя изменить"


def _api_role(user: User, seats: list[Membership]) -> str:
    if user.is_owner:
        return "owner"
    if any(row.role == "admin" for row in seats):
        return "admin"
    return "user"


def _seat_role(api_role: str) -> str:
    return "admin" if api_role == "admin" else "member"


def user_out(db: Session, user: User) -> UserOut:
    seats = list(
        db.scalars(
            select(Membership)
            .where(Membership.user_id == user.id)
            .options(joinedload(Membership.team))
            .order_by(Membership.created_at)
        )
        .unique()
        .all()
    )
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=_api_role(user, seats),
        is_active=user.is_active,
        is_owner=user.is_owner,
        telegram_linked=user.telegram_user_id is not None,
        must_change_password=user.must_change_password,
        invite_pending=user.invite_token is not None,
        departments=[
            DepartmentRole(id=row.team_id, name=row.team.name, role="admin" if row.role == "admin" else "user")
            for row in seats
        ],
    )


def _admin_team_ids(db: Session, actor: User) -> set[UUID]:
    if actor.is_owner:
        return set(db.scalars(select(Team.id)).all())
    return set(
        db.scalars(
            select(Membership.team_id).where(Membership.user_id == actor.id, Membership.role == "admin")
        ).all()
    )


def assert_can_list(actor: User) -> None:
    if actor.is_owner:
        return
    raise HTTPException(status_code=403, detail="Недостаточно прав")


def list_users(db: Session, actor: User) -> list[UserOut]:
    if actor.is_owner:
        rows = list(db.scalars(select(User).order_by(User.full_name, User.email)).all())
        return [user_out(db, row) for row in rows]
    team_ids = _admin_team_ids(db, actor)
    if not team_ids:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    user_ids = set(
        db.scalars(select(Membership.user_id).where(Membership.team_id.in_(team_ids))).all()
    )
    if not user_ids:
        return []
    rows = list(db.scalars(select(User).where(User.id.in_(user_ids)).order_by(User.full_name, User.email)).all())
    return [user_out(db, row) for row in rows]


def _resolve_department(db: Session, actor: User, payload: UserCreate) -> Team:
    team: Team | None = None
    if payload.department_id is not None:
        team = db.get(Team, payload.department_id)
        if team is None:
            raise HTTPException(status_code=404, detail="Отдел не найден")
    elif payload.department:
        matches = list(db.scalars(select(Team).where(Team.name == payload.department)).all())
        if len(matches) != 1:
            raise HTTPException(status_code=404, detail="Отдел не найден")
        team = matches[0]
    else:
        allowed = _admin_team_ids(db, actor)
        if actor.active_team_id in allowed:
            team = db.get(Team, actor.active_team_id)
        elif len(allowed) == 1:
            team = db.get(Team, next(iter(allowed)))
    if team is None:
        raise HTTPException(status_code=422, detail="Укажите отдел")
    if team.id not in _admin_team_ids(db, actor):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    return team


def _guard_role(actor: User, role: str) -> None:
    if role == "admin" and not actor.is_owner:
        raise HTTPException(status_code=403, detail="Админа назначает владелец")


def _new_invite() -> str:
    return secrets.token_urlsafe(24)


def invite_url(token: str) -> str:
    """Без APP_PUBLIC_URL путь относительный: панель дописывает свой адрес."""
    return f"{public_url()}/invite/{token}"


def _start_invite(user: User) -> None:
    """Пароль человек задаёт сам по ссылке. До этого войти нельзя."""
    user.password_hash = hash_password(secrets.token_urlsafe(32))
    user.must_change_password = False
    user.telegram_onboarding_done = False
    user.invite_token = _new_invite()


def _with_invite(db: Session, user: User) -> UserOut:
    out = user_out(db, user)
    if not user.invite_token:
        return out
    return out.model_copy(update={"invite_url": invite_url(user.invite_token)})


def create_user(db: Session, actor: User, payload: UserCreate) -> UserOut:
    """Без пароля — ссылка-приглашение, письмо не уходит. С паролем — временный пароль, как раньше."""
    if not actor.is_owner and not _admin_team_ids(db, actor):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    _guard_role(actor, payload.role)
    team = _resolve_department(db, actor, payload)
    existing = db.scalar(select(User).where(User.email == payload.email))
    if existing is not None and existing.is_owner:
        raise HTTPException(status_code=403, detail=OWNER_LOCKED)
    if existing is None:
        user = create_verified_user(
            db,
            email=payload.email,
            full_name=payload.full_name,
            password=payload.password or secrets.token_urlsafe(32),
            must_change_password=payload.password is not None,
        )
        if payload.password is None:
            _start_invite(user)
        add_member(db, team, user, _seat_role(payload.role), actor=actor)
        record(
            db,
            action="user.create",
            actor=actor,
            entity_type="user",
            entity_id=user.id,
            meta={"email": user.email, "role": payload.role, "team": team.name},
            team_id=team.id,
        )
        db.commit()
        return _with_invite(db, user)
    seat = membership(db, team.id, existing.id)
    if seat is not None and existing.is_active:
        raise HTTPException(status_code=409, detail="Человек уже в этом отделе")
    if not actor.is_owner:
        foreign = db.scalar(
            select(Membership.id).where(Membership.user_id == existing.id, Membership.team_id != team.id)
        )
        if foreign is not None:
            raise HTTPException(status_code=403, detail="В другой отдел добавляет только владелец")
    existing.full_name = payload.full_name
    if payload.password is not None:
        existing.password_hash = hash_password(payload.password)
        existing.must_change_password = True
        existing.invite_token = None
    elif not existing.is_active:
        # Вернувшийся человек заново задаёт пароль по новой ссылке.
        _start_invite(existing)
        revoke_user_sessions(db, existing.id)
    existing.is_active = True
    existing.updated_at = clock.now()
    if existing.email_verified_at is None:
        existing.email_verified_at = clock.now()
    if seat is None:
        add_member(db, team, existing, _seat_role(payload.role), actor=actor)
    elif payload.role == "admin" and actor.is_owner:
        seat.role = "admin"
    record(
        db,
        action="user.update",
        actor=actor,
        entity_type="user",
        entity_id=existing.id,
        meta={"email": existing.email, "team": team.name, "role": payload.role},
        team_id=team.id,
    )
    db.commit()
    return _with_invite(db, existing)


def _editable(db: Session, actor: User, target: User) -> None:
    if target.is_owner:
        raise HTTPException(status_code=403, detail=OWNER_LOCKED)
    if actor.is_owner:
        return
    admin_teams = _admin_team_ids(db, actor)
    seats = list(db.scalars(select(Membership).where(Membership.user_id == target.id)).all())
    if not seats or any(row.team_id not in admin_teams for row in seats):
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    if any(row.role == "admin" for row in seats):
        raise HTTPException(status_code=403, detail="Админа меняет только владелец")


def update_user(db: Session, actor: User, user_id: UUID, payload: UserUpdate) -> UserOut:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    _editable(db, actor, target)
    data = payload.model_dump(exclude_unset=True)
    if payload.role is not None:
        _guard_role(actor, payload.role)
        team_id = payload.department_id or target.active_team_id
        seat = membership(db, team_id, target.id) if team_id is not None else None
        if seat is None:
            seats = list(db.scalars(select(Membership).where(Membership.user_id == target.id)).all())
            if len(seats) == 1:
                seat = seats[0]
        if seat is None:
            raise HTTPException(status_code=422, detail="Укажите отдел для смены роли")
        if not actor.is_owner and seat.team_id not in _admin_team_ids(db, actor):
            raise HTTPException(status_code=403, detail="Недостаточно прав")
        seat.role = _seat_role(payload.role)
    if payload.full_name is not None:
        target.full_name = payload.full_name
    if payload.password is not None:
        target.password_hash = hash_password(payload.password)
        target.must_change_password = True
        revoke_user_sessions(db, target.id)
    if payload.is_active is not None:
        target.is_active = payload.is_active
    elif payload.blocked is not None:
        target.is_active = not payload.blocked
    if target.is_active is False:
        revoke_user_sessions(db, target.id)
    target.updated_at = clock.now()
    record(
        db,
        action="user.update",
        actor=actor,
        entity_type="user",
        entity_id=target.id,
        meta={"email": target.email, "fields": sorted(key for key in data if key != "password")},
        team_id=target.active_team_id,
    )
    db.commit()
    return user_out(db, target)


def delete_user(db: Session, actor: User, user_id: UUID) -> None:
    target = db.get(User, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if target.is_owner:
        raise HTTPException(status_code=403, detail=OWNER_LOCKED)
    seats = list(db.scalars(select(Membership).where(Membership.user_id == target.id)).all())
    if not actor.is_owner:
        admin_teams = _admin_team_ids(db, actor)
        if not seats or any(row.team_id not in admin_teams or row.role == "admin" for row in seats):
            raise HTTPException(status_code=403, detail="Недостаточно прав")
    team_ids = [row.team_id for row in seats]
    if team_ids:
        db.query(RecurringPayment).filter(
            RecurringPayment.team_id.in_(team_ids),
            RecurringPayment.responsible_user_id == target.id,
        ).update({RecurringPayment.responsible_user_id: None, RecurringPayment.updated_at: clock.now()}, synchronize_session=False)
    for row in seats:
        db.delete(row)
    target.is_active = False
    target.active_team_id = None
    target.must_change_password = False
    target.updated_at = clock.now()
    revoke_user_sessions(db, target.id)
    record(
        db,
        action="user.delete",
        actor=actor,
        entity_type="user",
        entity_id=target.id,
        meta={"email": target.email},
    )
    db.commit()


def _manageable(db: Session, actor: User, user_id: UUID) -> User:
    target = db.get(User, user_id)
    if target is None or not target.is_active:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    _editable(db, actor, target)
    return target


def invite_link(db: Session, actor: User, user_id: UUID, *, renew: bool = False) -> InviteOut:
    """Текущая ссылка-приглашение. renew — новая, старая перестаёт работать."""
    target = _manageable(db, actor, user_id)
    if target.invite_token is None:
        raise HTTPException(status_code=409, detail="Человек уже задал пароль. Для Telegram — ссылка привязки.")
    if renew:
        target.invite_token = _new_invite()
        target.updated_at = clock.now()
        record(
            db,
            action="user.invite",
            actor=actor,
            entity_type="user",
            entity_id=target.id,
            meta={"email": target.email},
            team_id=target.active_team_id,
        )
        db.commit()
    return InviteOut(url=invite_url(target.invite_token))


def person_telegram_link(db: Session, actor: User, user_id: UUID, *, renew: bool = False) -> TelegramLinkOut:
    """Ссылка привязки Telegram человека. Админ копирует её и передаёт сам, письма нет."""
    from app.services.telegram_links import bot_username, current_user_token, deep_link, issue_token

    target = _manageable(db, actor, user_id)
    username = bot_username(db)
    if not username:
        raise HTTPException(
            status_code=503,
            detail="Имя бота ещё неизвестно. Подождите getMe или задайте TELEGRAM_BOT_USERNAME.",
        )
    token = issue_token(db, purpose="user", user=target) if renew else current_user_token(db, target)
    return TelegramLinkOut(url=deep_link(username, token.token, group=False), expires_at=token.expires_at)


def unlink_person_telegram(db: Session, actor: User, user_id: UUID) -> UserOut:
    from app.services.telegram_links import unlink_user

    target = _manageable(db, actor, user_id)
    unlink_user(db, target, actor=actor)
    db.refresh(target)
    return user_out(db, target)

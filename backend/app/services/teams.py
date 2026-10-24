"""Команды, роли, приглашения. Права проверяет вызывающий код и эти функции."""

import secrets
from datetime import timedelta
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.security import hash_token
from app.integrations.email import public_url
from app.models import Membership, RecurringPayment, Team, TeamInvite, User
from app.services import time as clock
from app.services.audit import record
from app.services.mail import send_invite

INVITE_TTL = timedelta(days=7)


def create_team(db: Session, owner: User, name: str) -> Team:
    if not owner.is_owner:
        raise HTTPException(status_code=403, detail="Отдел создаёт владелец")
    cleaned = name.strip()
    if not cleaned:
        raise HTTPException(status_code=422, detail="Укажите название отдела")
    team = Team(name=cleaned)
    db.add(team)
    db.flush()
    if owner.active_team_id is None:
        owner.active_team_id = team.id
    owner.updated_at = clock.now()
    db.flush()
    record(
        db,
        action="team.create",
        actor=owner,
        entity_type="team",
        entity_id=team.id,
        meta={"name": team.name},
        team_id=team.id,
    )
    return team


def add_member(db: Session, team: Team, user: User, role: str, *, actor: User | None = None) -> Membership:
    if role not in {"admin", "member"}:
        raise ValueError("Неизвестная роль")
    existing = db.scalar(
        select(Membership).where(Membership.team_id == team.id, Membership.user_id == user.id)
    )
    if existing is not None:
        if existing.role == "member" and role == "admin":
            existing.role = "admin"
        return existing
    row = Membership(team_id=team.id, user_id=user.id, role=role)
    db.add(row)
    if user.active_team_id is None:
        user.active_team_id = team.id
    db.flush()
    record(
        db,
        action="member.join",
        actor=actor or user,
        entity_type="user",
        entity_id=user.id,
        meta={"email": user.email, "role": role, "team": team.name},
        team_id=team.id,
    )
    return row


def membership(db: Session, team_id: UUID, user_id: UUID) -> Membership | None:
    return db.scalar(select(Membership).where(Membership.team_id == team_id, Membership.user_id == user_id))


def require_membership(db: Session, team: Team, user: User) -> Membership:
    row = membership(db, team.id, user.id)
    if row is None:
        raise HTTPException(status_code=403, detail="Вы не в этой команде")
    return row


def _owner_row(db: Session, team_id: UUID) -> Membership:
    row = db.scalar(select(Membership).where(Membership.team_id == team_id, Membership.role == "owner"))
    if row is None:
        raise HTTPException(status_code=409, detail="У команды нет владельца")
    return row


def assert_owner(row: Membership) -> None:
    if row.role != "owner":
        raise HTTPException(status_code=403, detail="Недостаточно прав")


def assert_manager(row: Membership) -> None:
    if row.role not in {"owner", "admin"}:
        raise HTTPException(status_code=403, detail="Недостаточно прав")


def rename_team(db: Session, team: Team, actor: User, name: str) -> Team:
    if not actor.is_owner:
        raise HTTPException(status_code=403, detail="Отдел переименовывает владелец")
    team.name = name
    team.updated_at = clock.now()
    record(db, action="team.rename", actor=actor, entity_type="team", entity_id=team.id, meta={"name": name}, team_id=team.id)
    db.flush()
    return team


def delete_team(db: Session, team: Team, actor: User, confirm_name: str) -> None:
    if not actor.is_owner:
        raise HTTPException(status_code=403, detail="Отдел удаляет владелец")
    if confirm_name != team.name:
        raise HTTPException(status_code=409, detail="Введите название команды без изменений")
    member_ids = list(db.scalars(select(Membership.user_id).where(Membership.team_id == team.id)).all())
    record(db, action="team.delete", actor=actor, entity_type="team", entity_id=team.id, meta={"name": team.name}, team_id=team.id)
    db.delete(team)
    db.flush()
    for user_id in member_ids:
        user = db.get(User, user_id)
        if user is None or user.active_team_id is not None:
            continue
        other = db.scalar(select(Membership.team_id).where(Membership.user_id == user_id))
        user.active_team_id = other


def transfer(db: Session, team: Team, actor: User, new_owner_id: UUID) -> None:
    actor_row = require_membership(db, team, actor)
    assert_owner(actor_row)
    target = membership(db, team.id, new_owner_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Участник не найден")
    if target.user_id == actor.id:
        return
    actor_row.role = "admin"
    db.flush()
    target.role = "owner"
    record(
        db,
        action="team.transfer",
        actor=actor,
        entity_type="team",
        entity_id=team.id,
        meta={"user_id": str(new_owner_id)},
        team_id=team.id,
    )


def leave(db: Session, team: Team, user: User) -> None:
    require_membership(db, team, user)
    _drop_member(db, team, user, actor=user)


def remove_member(db: Session, team: Team, actor: User, user_id: UUID) -> None:
    if user_id == actor.id:
        raise HTTPException(status_code=409, detail="Себя удаляют кнопкой «Выйти»")
    target = membership(db, team.id, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Участник не найден")
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Участник не найден")
    if user.is_owner:
        raise HTTPException(status_code=403, detail="Учётку владельца нельзя изменить")
    if not actor.is_owner:
        actor_row = require_membership(db, team, actor)
        assert_manager(actor_row)
        if target.role == "admin":
            raise HTTPException(status_code=403, detail="Админа снимает только владелец")
    _drop_member(db, team, user, actor=actor)


def set_role(db: Session, team: Team, actor: User, user_id: UUID, role: str) -> Membership:
    if not actor.is_owner:
        raise HTTPException(status_code=403, detail="Роли назначает владелец")
    if role not in {"admin", "member"}:
        raise HTTPException(status_code=422, detail="Роль: admin или member")
    target = membership(db, team.id, user_id)
    if target is None:
        raise HTTPException(status_code=404, detail="Участник не найден")
    person = db.get(User, user_id)
    if person is not None and person.is_owner:
        raise HTTPException(status_code=403, detail="Учётку владельца нельзя изменить")
    target.role = role
    record(
        db,
        action="member.role",
        actor=actor,
        entity_type="user",
        entity_id=user_id,
        meta={"role": role},
        team_id=team.id,
    )
    db.flush()
    return target


def _drop_member(db: Session, team: Team, user: User, *, actor: User) -> None:
    row = membership(db, team.id, user.id)
    if row is None:
        return
    db.execute(
        update(RecurringPayment)
        .where(RecurringPayment.team_id == team.id, RecurringPayment.responsible_user_id == user.id)
        .values(responsible_user_id=None, updated_at=clock.now())
    )
    db.delete(row)
    if user.active_team_id == team.id:
        other = db.scalar(
            select(Membership.team_id).where(Membership.user_id == user.id, Membership.team_id != team.id)
        )
        user.active_team_id = other
    record(
        db,
        action="member.remove",
        actor=actor,
        entity_type="user",
        entity_id=user.id,
        meta={"email": user.email},
        team_id=team.id,
    )
    db.flush()


def list_member_rows(db: Session, team_id: UUID) -> list[Membership]:
    stmt = (
        select(Membership)
        .where(Membership.team_id == team_id)
        .order_by(Membership.role, Membership.created_at)
    )
    rows = list(db.scalars(stmt).all())
    order = {"owner": 0, "admin": 1, "member": 2}
    rows.sort(key=lambda row: (order.get(row.role, 9), row.created_at))
    return rows


def rotate_link(db: Session, team: Team, actor: User) -> str:
    assert_manager(require_membership(db, team, actor))
    team.invite_token = secrets.token_urlsafe(24)
    team.updated_at = clock.now()
    record(db, action="team.invite_link", actor=actor, entity_type="team", entity_id=team.id, meta={}, team_id=team.id)
    db.flush()
    return team.invite_token


def join_url(token: str) -> str:
    base = public_url()
    path = f"/join/{token}"
    return f"{base}{path}" if base else path


def invite_email(db: Session, team: Team, actor: User, email: str, role: str) -> tuple[TeamInvite, str, str]:
    actor_row = require_membership(db, team, actor)
    assert_manager(actor_row)
    if role == "admin" and actor_row.role != "owner":
        raise HTTPException(status_code=403, detail="Админа приглашает только владелец")
    if role not in {"admin", "member"}:
        raise HTTPException(status_code=422, detail="Пригласить можно админом или участником")
    existing_user = db.scalar(select(User).where(User.email == email))
    if existing_user is not None and membership(db, team.id, existing_user.id) is not None:
        raise HTTPException(status_code=409, detail="Человек уже в команде")
    raw = secrets.token_urlsafe(32)
    now = clock.now()
    pending = db.scalars(
        select(TeamInvite).where(
            TeamInvite.team_id == team.id,
            TeamInvite.email == email,
            TeamInvite.accepted_at.is_(None),
        )
    ).all()
    for old in pending:
        old.accepted_at = now
    invite = TeamInvite(
        team_id=team.id,
        email=email,
        role=role,
        token_hash=hash_token(raw),
        expires_at=now + INVITE_TTL,
        created_by_id=actor.id,
    )
    db.add(invite)
    db.flush()
    url = join_url(raw)
    record(
        db,
        action="team.invite",
        actor=actor,
        entity_type="team",
        entity_id=team.id,
        meta={"email": email, "role": role},
        team_id=team.id,
    )
    db.commit()
    delivery = send_invite(email=email, team_name=team.name, role=role, url=url)
    return invite, url, delivery


def list_invites(db: Session, team_id: UUID) -> list[TeamInvite]:
    now = clock.now()
    rows = db.scalars(
        select(TeamInvite)
        .where(TeamInvite.team_id == team_id, TeamInvite.accepted_at.is_(None))
        .order_by(TeamInvite.created_at.desc())
    ).all()
    return [row for row in rows if row.expires_at > now]


def cancel_invite(db: Session, team: Team, actor: User, invite_id: UUID) -> None:
    assert_manager(require_membership(db, team, actor))
    row = db.get(TeamInvite, invite_id)
    if row is None or row.team_id != team.id:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")
    row.accepted_at = clock.now()
    db.flush()


def preview_token(db: Session, raw: str) -> tuple[str, str, str | None, bool]:
    team = db.scalar(select(Team).where(Team.invite_token == raw))
    if team is not None:
        return team.name, "member", None, True
    invite = db.scalar(select(TeamInvite).where(TeamInvite.token_hash == hash_token(raw)))
    if invite is None:
        raise HTTPException(status_code=404, detail="Приглашение не найдено")
    parent = db.get(Team, invite.team_id)
    name = parent.name if parent is not None else "Команда"
    valid = invite.accepted_at is None and invite.expires_at > clock.now()
    return name, invite.role, invite.email, valid


def accept_token(db: Session, user: User, raw: str) -> Membership:
    if user.email_verified_at is None:
        raise HTTPException(status_code=403, detail="Сначала подтвердите почту")
    team = db.scalar(select(Team).where(Team.invite_token == raw))
    if team is not None:
        return add_member(db, team, user, "member", actor=user)
    invite = db.scalar(select(TeamInvite).where(TeamInvite.token_hash == hash_token(raw)))
    if invite is None or invite.accepted_at is not None or invite.expires_at <= clock.now():
        raise HTTPException(status_code=404, detail="Приглашение недействительно или истекло")
    if invite.email != user.email:
        raise HTTPException(status_code=403, detail="Приглашение отправлено на другую почту")
    parent = db.get(Team, invite.team_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Команда не найдена")
    invite.accepted_at = clock.now()
    return add_member(db, parent, user, invite.role, actor=user)


def require_participant(db: Session, team_id: UUID, user_id: UUID) -> User:
    user = db.get(User, user_id)
    row = membership(db, team_id, user_id)
    if user is None or not user.is_active or (row is None and not user.is_owner):
        raise HTTPException(status_code=400, detail="Ответственный не в этом отделе")
    return user

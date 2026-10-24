"""Отделы и роли. Права проверяет вызывающий код и эти функции."""

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.models import Membership, RecurringPayment, Team, User
from app.services import time as clock
from app.services.audit import record


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
        raise HTTPException(status_code=403, detail="Вы не в этом отделе")
    return row


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
        raise HTTPException(status_code=409, detail="Введите название отдела без изменений")
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


def require_participant(db: Session, team_id: UUID, user_id: UUID) -> User:
    user = db.get(User, user_id)
    row = membership(db, team_id, user_id)
    if user is None or not user.is_active or (row is None and not user.is_owner):
        raise HTTPException(status_code=400, detail="Ответственный не в этом отделе")
    return user

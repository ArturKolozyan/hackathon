from dataclasses import dataclass
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import Membership, Team, User
from app.services import time as clock

RANK = {"member": 1, "admin": 2, "owner": 3}


@dataclass
class TeamContext:
    user: User
    team: Team
    membership: Membership | None

    @property
    def role(self) -> str:
        if self.user.is_owner:
            return "owner"
        if self.membership is None:
            return "member"
        return self.membership.role


@dataclass
class DeptAccess:
    team_id: UUID
    team: Team
    role: str


def require_role(ctx: TeamContext, minimum: str) -> TeamContext:
    if RANK[ctx.role] < RANK[minimum]:
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    return ctx


def memberships_of(db: Session, user: User) -> list[Membership]:
    stmt = (
        select(Membership)
        .where(Membership.user_id == user.id)
        .options(joinedload(Membership.team))
        .order_by(Membership.created_at, Membership.id)
    )
    return list(db.scalars(stmt).unique().all())


def department_access(db: Session, user: User) -> list[DeptAccess]:
    if user.is_owner:
        teams = list(db.scalars(select(Team).order_by(Team.created_at, Team.id)).all())
        return [DeptAccess(team_id=team.id, team=team, role="owner") for team in teams]
    return [
        DeptAccess(team_id=row.team_id, team=row.team, role=row.role) for row in memberships_of(db, user)
    ]


def resolve_team(db: Session, user: User, team_id: UUID | None) -> TeamContext | None:
    if user.is_owner:
        return _resolve_owner(db, user, team_id)
    rows = memberships_of(db, user)
    if not rows:
        if team_id is not None:
            raise HTTPException(status_code=403, detail="Вы не в этом отделе")
        return None
    chosen: Membership | None = None
    if team_id is not None:
        chosen = next((row for row in rows if row.team_id == team_id), None)
        if chosen is None:
            raise HTTPException(status_code=403, detail="Вы не в этом отделе")
    elif user.active_team_id is not None:
        chosen = next((row for row in rows if row.team_id == user.active_team_id), None)
    if chosen is None:
        chosen = rows[0]
    if user.active_team_id != chosen.team_id:
        user.active_team_id = chosen.team_id
        user.updated_at = clock.now()
        db.commit()
    return TeamContext(user=user, team=chosen.team, membership=chosen)


def _resolve_owner(db: Session, user: User, team_id: UUID | None) -> TeamContext | None:
    team: Team | None = None
    if team_id is not None:
        team = db.get(Team, team_id)
        if team is None:
            raise HTTPException(status_code=404, detail="Отдел не найден")
    elif user.active_team_id is not None:
        team = db.get(Team, user.active_team_id)
    if team is None:
        team = db.scalar(select(Team).order_by(Team.created_at, Team.id))
    if team is None:
        return None
    seat = db.scalar(select(Membership).where(Membership.team_id == team.id, Membership.user_id == user.id))
    if user.active_team_id != team.id:
        user.active_team_id = team.id
        user.updated_at = clock.now()
        db.commit()
    return TeamContext(user=user, team=team, membership=seat)

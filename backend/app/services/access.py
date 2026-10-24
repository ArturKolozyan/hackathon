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
    membership: Membership


def require_role(ctx: TeamContext, minimum: str) -> TeamContext:
    if RANK[ctx.membership.role] < RANK[minimum]:
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


def resolve_team(db: Session, user: User, team_id: UUID | None) -> TeamContext | None:
    rows = memberships_of(db, user)
    if not rows:
        if team_id is not None:
            raise HTTPException(status_code=403, detail="Вы не в этой команде")
        return None
    chosen: Membership | None = None
    if team_id is not None:
        chosen = next((row for row in rows if row.team_id == team_id), None)
        if chosen is None:
            raise HTTPException(status_code=403, detail="Вы не в этой команде")
    elif user.active_team_id is not None:
        chosen = next((row for row in rows if row.team_id == user.active_team_id), None)
    if chosen is None:
        chosen = rows[0]
    if user.active_team_id != chosen.team_id:
        user.active_team_id = chosen.team_id
        user.updated_at = clock.now()
        db.commit()
    return TeamContext(user=user, team=chosen.team, membership=chosen)

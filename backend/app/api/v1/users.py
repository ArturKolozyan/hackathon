from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_team_context
from app.schemas.team import MemberOut
from app.services.access import TeamContext
from app.services.teams import list_member_rows

router = APIRouter(prefix="/users", tags=["users"])


def _out(row) -> MemberOut:
    user = row.user
    return MemberOut(id=user.id, email=user.email, full_name=user.full_name, role=row.role, is_active=user.is_active)


@router.get("", response_model=list[MemberOut], summary="Люди текущей команды")
def list_users(ctx: TeamContext = Depends(get_team_context), db: Session = Depends(get_db)) -> list[MemberOut]:
    return [_out(row) for row in list_member_rows(db, ctx.team.id)]


@router.get("/{user_id}", response_model=MemberOut, summary="Человек текущей команды")
def get_user(user_id: UUID, ctx: TeamContext = Depends(get_team_context), db: Session = Depends(get_db)) -> MemberOut:
    for row in list_member_rows(db, ctx.team.id):
        if row.user_id == user_id:
            return _out(row)
    raise HTTPException(status_code=404, detail="Участник не найден")

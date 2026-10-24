from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_active_user
from app.models import Team, User
from app.schemas.team import MemberOut, MemberRoleIn, TeamCreate, TeamDelete, TeamOut, TeamRename
from app.services.access import department_access
from app.services.teams import (
    create_team,
    delete_team,
    leave,
    list_member_rows,
    remove_member,
    rename_team,
    require_membership,
    set_role,
)

router = APIRouter(prefix="/teams", tags=["teams"])


def _team_or_404(db: Session, team_id: UUID) -> Team:
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Отдел не найден")
    return team


def _member_out(row) -> MemberOut:
    user = row.user
    return MemberOut(id=user.id, email=user.email, full_name=user.full_name, role=row.role, is_active=user.is_active)


@router.get("", response_model=list[TeamOut], summary="Мои отделы")
def my_teams(user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[TeamOut]:
    return [TeamOut(id=row.team_id, name=row.team.name, role=row.role) for row in department_access(db, user)]


@router.post("", response_model=TeamOut, status_code=201, summary="Создать отдел")
def open_team(payload: TeamCreate, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> TeamOut:
    team = create_team(db, user, payload.name)
    db.commit()
    return TeamOut(id=team.id, name=team.name, role="owner")


@router.patch("/{team_id}", response_model=TeamOut, summary="Переименовать")
def rename(
    team_id: UUID,
    payload: TeamRename,
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
) -> TeamOut:
    team = _team_or_404(db, team_id)
    rename_team(db, team, user, payload.name)
    db.commit()
    return TeamOut(id=team.id, name=team.name, role="owner")


@router.delete("/{team_id}", status_code=204, summary="Удалить отдел")
def remove_team(
    team_id: UUID,
    payload: TeamDelete,
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
) -> None:
    team = _team_or_404(db, team_id)
    delete_team(db, team, user, payload.name)
    db.commit()


@router.post("/{team_id}/leave", status_code=204, summary="Выйти из отдела")
def leave_team(team_id: UUID, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> None:
    team = _team_or_404(db, team_id)
    leave(db, team, user)
    db.commit()


@router.get("/{team_id}/members", response_model=list[MemberOut], summary="Участники")
def members(team_id: UUID, user: User = Depends(get_active_user), db: Session = Depends(get_db)) -> list[MemberOut]:
    team = _team_or_404(db, team_id)
    if not user.is_owner:
        require_membership(db, team, user)
    return [_member_out(row) for row in list_member_rows(db, team.id)]


@router.patch("/{team_id}/members/{user_id}", response_model=MemberOut, summary="Роль участника")
def member_role(
    team_id: UUID,
    user_id: UUID,
    payload: MemberRoleIn,
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
) -> MemberOut:
    team = _team_or_404(db, team_id)
    row = set_role(db, team, user, user_id, payload.role)
    db.commit()
    db.refresh(row)
    return _member_out(row)


@router.delete("/{team_id}/members/{user_id}", status_code=204, summary="Убрать участника")
def member_remove(
    team_id: UUID,
    user_id: UUID,
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
) -> None:
    team = _team_or_404(db, team_id)
    remove_member(db, team, user, user_id)
    db.commit()

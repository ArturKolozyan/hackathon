from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import Team, User
from app.schemas.team import (
    InviteCreated,
    InviteIn,
    InviteLinkOut,
    InviteOut,
    MemberOut,
    MemberRoleIn,
    TeamCreate,
    TeamDelete,
    TeamOut,
    TeamRename,
    TransferIn,
)
from app.services.access import memberships_of
from app.services.teams import (
    assert_manager,
    cancel_invite,
    create_team,
    delete_team,
    invite_email,
    join_url,
    leave,
    list_invites,
    list_member_rows,
    remove_member,
    rename_team,
    require_membership,
    rotate_link,
    set_role,
    transfer,
)

router = APIRouter(prefix="/teams", tags=["teams"])


def _team_or_404(db: Session, team_id: UUID) -> Team:
    team = db.get(Team, team_id)
    if team is None:
        raise HTTPException(status_code=404, detail="Команда не найдена")
    return team


def _member_out(row) -> MemberOut:
    user = row.user
    return MemberOut(id=user.id, email=user.email, full_name=user.full_name, role=row.role, is_active=user.is_active)


@router.get("", response_model=list[TeamOut], summary="Мои команды")
def my_teams(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[TeamOut]:
    return [
        TeamOut(id=row.team_id, name=row.team.name, role=row.role) for row in memberships_of(db, user)
    ]


@router.post("", response_model=TeamOut, status_code=201, summary="Создать команду")
def open_team(payload: TeamCreate, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TeamOut:
    team = create_team(db, user, payload.name)
    db.commit()
    return TeamOut(id=team.id, name=team.name, role="owner")


@router.patch("/{team_id}", response_model=TeamOut, summary="Переименовать")
def rename(
    team_id: UUID,
    payload: TeamRename,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> TeamOut:
    team = _team_or_404(db, team_id)
    rename_team(db, team, user, payload.name)
    db.commit()
    return TeamOut(id=team.id, name=team.name, role="owner")


@router.delete("/{team_id}", status_code=204, summary="Удалить команду")
def remove_team(
    team_id: UUID,
    payload: TeamDelete,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    team = _team_or_404(db, team_id)
    delete_team(db, team, user, payload.name)
    db.commit()


@router.post("/{team_id}/transfer", status_code=204, summary="Передать владение")
def transfer_owner(
    team_id: UUID,
    payload: TransferIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    team = _team_or_404(db, team_id)
    transfer(db, team, user, payload.user_id)
    db.commit()


@router.post("/{team_id}/leave", status_code=204, summary="Выйти из команды")
def leave_team(team_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    team = _team_or_404(db, team_id)
    leave(db, team, user)
    db.commit()


@router.get("/{team_id}/members", response_model=list[MemberOut], summary="Участники")
def members(team_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[MemberOut]:
    team = _team_or_404(db, team_id)
    require_membership(db, team, user)
    return [_member_out(row) for row in list_member_rows(db, team.id)]


@router.patch("/{team_id}/members/{user_id}", response_model=MemberOut, summary="Роль участника")
def member_role(
    team_id: UUID,
    user_id: UUID,
    payload: MemberRoleIn,
    user: User = Depends(get_current_user),
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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    team = _team_or_404(db, team_id)
    remove_member(db, team, user, user_id)
    db.commit()


@router.get("/{team_id}/invites", response_model=list[InviteOut], summary="Письма-приглашения")
def invites(team_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[InviteOut]:
    team = _team_or_404(db, team_id)
    assert_manager(require_membership(db, team, user))
    return [
        InviteOut(id=row.id, email=row.email, role=row.role, expires_at=row.expires_at, expired=False)
        for row in list_invites(db, team.id)
    ]


@router.post("/{team_id}/invites", response_model=InviteCreated, status_code=201, summary="Пригласить почтой")
def invite(
    team_id: UUID,
    payload: InviteIn,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InviteCreated:
    team = _team_or_404(db, team_id)
    row, url, delivery = invite_email(db, team, user, payload.email, payload.role)
    return InviteCreated(
        id=row.id,
        email=row.email,
        role=row.role,
        expires_at=row.expires_at,
        expired=False,
        url=url,
        delivery=delivery,
    )


@router.delete("/{team_id}/invites/{invite_id}", status_code=204, summary="Отменить приглашение")
def invite_cancel(
    team_id: UUID,
    invite_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> None:
    team = _team_or_404(db, team_id)
    cancel_invite(db, team, user, invite_id)
    db.commit()


@router.get("/{team_id}/invite-link", response_model=InviteLinkOut, summary="Общая ссылка")
def invite_link(team_id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> InviteLinkOut:
    team = _team_or_404(db, team_id)
    assert_manager(require_membership(db, team, user))
    if not team.invite_token:
        raise HTTPException(status_code=409, detail="Ссылки ещё нет")
    return InviteLinkOut(url=join_url(team.invite_token), token=team.invite_token)


@router.post("/{team_id}/invite-link/rotate", response_model=InviteLinkOut, summary="Сменить общую ссылку")
def invite_rotate(
    team_id: UUID,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InviteLinkOut:
    team = _team_or_404(db, team_id)
    token = rotate_link(db, team, user)
    db.commit()
    return InviteLinkOut(url=join_url(token), token=token)

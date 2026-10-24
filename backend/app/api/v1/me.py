from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.auth import SentOut, sent_message
from app.schemas.me import MeOut
from app.schemas.profile import CodeIn, EmailChangeIn, NameIn, PasswordIn
from app.schemas.team import ActiveTeamIn
from app.services.access import resolve_team
from app.services.accounts import change_password, confirm_email_change, request_email_change, to_me, touch_name

router = APIRouter(prefix="/me", tags=["profile"])


def _owner_locked(user: User) -> None:
    if user.is_owner:
        raise HTTPException(status_code=403, detail="Учётку владельца нельзя изменить")


@router.patch("", response_model=MeOut, summary="Имя")
def rename_me(payload: NameIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MeOut:
    _owner_locked(user)
    touch_name(db, user, payload.full_name)
    db.commit()
    return to_me(db, user)


@router.post("/password", status_code=204, summary="Сменить пароль")
def password(payload: PasswordIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    _owner_locked(user)
    change_password(db, user, payload.current_password, payload.new_password)
    db.commit()


@router.post("/email", response_model=SentOut, summary="Код на новую почту")
def email(payload: EmailChangeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> SentOut:
    _owner_locked(user)
    delivery = request_email_change(db, user, payload.email)
    return SentOut(delivery=delivery, message=sent_message(delivery))


@router.post("/email/confirm", response_model=MeOut, summary="Подтвердить новую почту")
def email_confirm(payload: CodeIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MeOut:
    _owner_locked(user)
    confirm_email_change(db, user, payload.code)
    db.commit()
    return to_me(db, user)


@router.post("/active-team", response_model=MeOut, summary="Текущий отдел")
def active_team(payload: ActiveTeamIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MeOut:
    ctx = resolve_team(db, user, payload.team_id)
    if ctx is None:
        raise HTTPException(status_code=409, detail="Сначала создайте отдел")
    return to_me(db, user)

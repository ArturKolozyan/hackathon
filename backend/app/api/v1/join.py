from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.me import MeOut
from app.schemas.team import InvitePreview
from app.services.accounts import to_me
from app.services.teams import accept_token, preview_token

router = APIRouter(prefix="/join", tags=["join"])


@router.get("/{token}", response_model=InvitePreview, summary="Что за приглашение")
def preview(token: str, db: Session = Depends(get_db)) -> InvitePreview:
    name, role, email, valid = preview_token(db, token)
    return InvitePreview(team_name=name, role=role, email=email, valid=valid)


@router.post("/{token}", response_model=MeOut, summary="Вступить")
def accept(token: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MeOut:
    accept_token(db, user, token)
    db.commit()
    return to_me(db, user)

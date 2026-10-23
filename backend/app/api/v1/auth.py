from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, read_token
from app.core.security import attach_cookie, authenticate, clear_cookie, issue_session, revoke_token
from app.models import User
from app.schemas.auth import LoginIn, TokenOut
from app.schemas.common import UserOut

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut, summary="Вход")
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    user = authenticate(db, payload.email, payload.password)
    token = issue_session(db, user)
    db.commit()
    attach_cookie(response, token)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Выход")
def logout(response: Response, token: str | None = Depends(read_token), db: Session = Depends(get_db)) -> None:
    revoke_token(db, token)
    db.commit()
    clear_cookie(response)


@router.get("/me", response_model=UserOut, summary="Текущий пользователь")
def me(user: User = Depends(get_current_user)) -> User:
    return user

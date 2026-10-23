from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, read_token
from app.core.security import attach_cookie, authenticate, clear_cookie, issue_session, revoke_token, user_from_token
from app.models import User
from app.schemas.auth import LoginIn, TokenOut
from app.schemas.common import UserOut
from app.services.audit import record

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenOut, summary="Вход")
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    try:
        user = authenticate(db, payload.email, payload.password)
    except HTTPException as exc:
        if exc.status_code in (401, 403):
            record(
                db,
                action="auth.login.failure",
                meta={"email": payload.email.strip().lower(), "status": exc.status_code},
            )
            db.commit()
        raise
    token = issue_session(db, user)
    record(
        db,
        action="auth.login.success",
        actor=user,
        entity_type="user",
        entity_id=user.id,
        meta={"email": user.email},
    )
    db.commit()
    attach_cookie(response, token)
    return TokenOut(access_token=token, user=UserOut.model_validate(user))


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Выход")
def logout(response: Response, token: str | None = Depends(read_token), db: Session = Depends(get_db)) -> None:
    user = user_from_token(db, token) if token else None
    revoke_token(db, token)
    if user is not None:
        record(db, action="auth.logout", actor=user, entity_type="user", entity_id=user.id, meta={"email": user.email})
    db.commit()
    clear_cookie(response)


@router.get("/me", response_model=UserOut, summary="Текущий пользователь")
def me(user: User = Depends(get_current_user)) -> User:
    return user

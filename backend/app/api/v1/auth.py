from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, read_token
from app.core.security import attach_cookie, clear_cookie, issue_session, revoke_token, user_from_token
from app.models import User
from app.schemas.auth import (
    ConfirmIn,
    ForgotIn,
    LoginIn,
    RegisterIn,
    ResendIn,
    ResetIn,
    SentOut,
    TokenOut,
    sent_message,
)
from app.schemas.me import MeOut
from app.services.accounts import (
    authenticate,
    confirm_registration,
    register_account,
    request_password_reset,
    resend_registration,
    reset_password,
    to_me,
)
from app.services.audit import record

router = APIRouter(prefix="/auth", tags=["auth"])


def _session(db: Session, response: Response, user: User) -> TokenOut:
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
    return TokenOut(access_token=token, user=to_me(db, user))


@router.post("/register", response_model=SentOut, status_code=201, summary="Регистрация")
def register(payload: RegisterIn, db: Session = Depends(get_db)) -> SentOut:
    delivery = register_account(
        db,
        email=payload.email,
        full_name=payload.full_name,
        password=payload.password,
        invite_token=payload.invite_token,
    )
    return SentOut(delivery=delivery, message=sent_message(delivery))


@router.post("/register/resend", response_model=SentOut, summary="Повтор кода регистрации")
def register_resend(payload: ResendIn, db: Session = Depends(get_db)) -> SentOut:
    delivery = resend_registration(db, payload.email)
    return SentOut(delivery=delivery, message=sent_message(delivery))


@router.post("/register/confirm", response_model=TokenOut, summary="Подтвердить почту")
def register_confirm(payload: ConfirmIn, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    user = confirm_registration(db, email=payload.email, code=payload.code)
    return _session(db, response, user)


@router.post("/login", response_model=TokenOut, summary="Вход")
def login(payload: LoginIn, response: Response, db: Session = Depends(get_db)) -> TokenOut:
    from fastapi import HTTPException

    try:
        user = authenticate(db, payload.email, payload.password)
    except HTTPException as exc:
        if exc.status_code in (401, 403):
            record(
                db,
                action="auth.login.failure",
                meta={"email": payload.email, "status": exc.status_code},
            )
            db.commit()
        raise
    return _session(db, response, user)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Выход")
def logout(response: Response, token: str | None = Depends(read_token), db: Session = Depends(get_db)) -> None:
    user = user_from_token(db, token) if token else None
    revoke_token(db, token)
    if user is not None:
        record(db, action="auth.logout", actor=user, entity_type="user", entity_id=user.id, meta={"email": user.email})
    db.commit()
    clear_cookie(response)


@router.post("/password/forgot", status_code=status.HTTP_204_NO_CONTENT, summary="Код для сброса пароля")
def forgot(payload: ForgotIn, db: Session = Depends(get_db)) -> None:
    request_password_reset(db, payload.email)


@router.post("/password/reset", status_code=status.HTTP_204_NO_CONTENT, summary="Новый пароль по коду")
def reset_password_route(payload: ResetIn, db: Session = Depends(get_db)) -> None:
    reset_password(db, email=payload.email, code=payload.code, password=payload.password)
    db.commit()


@router.get("/me", response_model=MeOut, summary="Текущий пользователь")
def me(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> MeOut:
    return to_me(db, user)

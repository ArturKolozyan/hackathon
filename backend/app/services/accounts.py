"""Регистрация, коды, вход, профиль. Сессия по-прежнему кука и bearer."""

import hmac
import secrets
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.security import hash_password, hash_token, revoke_user_sessions, verify_password, waste_password_check
from app.models import EmailCode, User
from app.schemas.me import MeOut, MembershipBrief
from app.services import time as clock
from app.services.access import memberships_of
from app.services.lockout import clear_failure, ensure_unlocked, register_failure
from app.services.mail import send_code

CODE_TTL = timedelta(minutes=15)
RESEND_AFTER = timedelta(seconds=60)
CODE_ATTEMPTS = 5
BAD_LOGIN = "Неверная почта или пароль"
BAD_CODE = "Неверный код."
EXPIRED = "Код недействителен или истёк. Запросите новый."
TOO_MANY = "Слишком много попыток. Запросите новый код."
TOO_SOON = "Повторная отправка возможна через минуту."


def to_me(db: Session, user: User) -> MeOut:
    rows = memberships_of(db, user)
    if user.active_team_id is not None and all(row.team_id != user.active_team_id for row in rows):
        user.active_team_id = rows[0].team_id if rows else None
    return MeOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        email_verified=user.email_verified_at is not None,
        created_at=user.created_at,
        active_team_id=user.active_team_id,
        memberships=[
            MembershipBrief(team_id=row.team_id, team_name=row.team.name, role=row.role) for row in rows
        ],
        telegram_chat_id=user.telegram_chat_id,
    )


def create_verified_user(db: Session, *, email: str, full_name: str, password: str) -> User:
    if len(password) < 8:
        raise ValueError("Пароль короче 8 символов")
    user = User(
        email=email.strip().lower(),
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        is_active=True,
        email_verified_at=clock.now(),
    )
    db.add(user)
    db.flush()
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    normalized = email.strip().lower()
    ensure_unlocked(db, normalized)
    user = db.scalar(select(User).where(User.email == normalized))
    if user is None:
        waste_password_check(password)
        raise HTTPException(status_code=401, detail=BAD_LOGIN)
    if not verify_password(password, user.password_hash):
        register_failure(db, normalized)
        raise HTTPException(status_code=401, detail=BAD_LOGIN)
    if user.email_verified_at is None:
        raise HTTPException(status_code=403, detail="Сначала подтвердите почту")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Учётная запись отключена")
    clear_failure(db, normalized)
    return user


def _too_soon(db: Session, email: str, purpose: str) -> bool:
    last = db.scalar(
        select(EmailCode)
        .where(EmailCode.email == email, EmailCode.purpose == purpose)
        .order_by(EmailCode.sent_at.desc())
    )
    return last is not None and last.sent_at + RESEND_AFTER > clock.now()


def issue_code(
    db: Session,
    *,
    email: str,
    purpose: str,
    user: User | None,
    payload: dict | None = None,
) -> str:
    if _too_soon(db, email, purpose):
        raise HTTPException(status_code=429, detail=TOO_SOON)
    previous = db.scalars(
        select(EmailCode).where(
            EmailCode.email == email,
            EmailCode.purpose == purpose,
            EmailCode.consumed_at.is_(None),
        )
    ).all()
    now = clock.now()
    for row in previous:
        row.consumed_at = now
    code = f"{secrets.randbelow(1_000_000):06d}"
    db.add(
        EmailCode(
            email=email,
            purpose=purpose,
            code_hash=hash_token(code),
            user_id=user.id if user is not None else None,
            payload=payload or {},
            expires_at=now + CODE_TTL,
            attempts=0,
            sent_at=now,
        )
    )
    db.flush()
    return code


def confirm_code(db: Session, *, email: str, purpose: str, code: str) -> EmailCode:
    row = db.scalar(
        select(EmailCode)
        .where(
            EmailCode.email == email,
            EmailCode.purpose == purpose,
            EmailCode.consumed_at.is_(None),
        )
        .order_by(EmailCode.sent_at.desc())
    )
    if row is None or row.expires_at <= clock.now():
        raise HTTPException(status_code=400, detail=EXPIRED)
    if not hmac.compare_digest(hash_token(code), row.code_hash):
        row.attempts += 1
        if row.attempts >= CODE_ATTEMPTS:
            row.consumed_at = clock.now()
            db.commit()
            raise HTTPException(status_code=400, detail=TOO_MANY)
        db.commit()
        raise HTTPException(status_code=400, detail=BAD_CODE)
    row.consumed_at = clock.now()
    db.flush()
    return row


def _find_user(db: Session, email: str) -> User | None:
    return db.scalar(select(User).where(User.email == email))


def register_account(db: Session, *, email: str, full_name: str, password: str, invite_token: str | None) -> str:
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="Пароль короче 8 символов")
    user = _find_user(db, email)
    if user is not None and user.email_verified_at is not None:
        raise HTTPException(status_code=409, detail="Почта уже зарегистрирована")
    if user is None:
        user = User(
            email=email,
            full_name=full_name,
            password_hash=hash_password(password),
            is_active=True,
            email_verified_at=None,
        )
        db.add(user)
        try:
            db.flush()
        except IntegrityError:
            db.rollback()
            raise HTTPException(status_code=409, detail="Почта уже зарегистрирована") from None
    else:
        user.full_name = full_name
        user.password_hash = hash_password(password)
        user.updated_at = clock.now()
        db.flush()
    payload = {}
    if invite_token:
        payload["invite_token"] = invite_token.strip()
    code = issue_code(db, email=email, purpose="register", user=user, payload=payload)
    db.commit()
    return send_code(email=email, purpose="register", code=code)


def resend_registration(db: Session, email: str) -> str:
    user = _find_user(db, email)
    if user is None:
        raise HTTPException(status_code=404, detail="Сначала зарегистрируйтесь")
    if user.email_verified_at is not None:
        raise HTTPException(status_code=409, detail="Почта уже подтверждена")
    last = db.scalar(
        select(EmailCode)
        .where(EmailCode.email == email, EmailCode.purpose == "register")
        .order_by(EmailCode.sent_at.desc())
    )
    payload = dict(last.payload) if last is not None and last.payload else {}
    code = issue_code(db, email=email, purpose="register", user=user, payload=payload)
    db.commit()
    return send_code(email=email, purpose="register", code=code)


def confirm_registration(db: Session, *, email: str, code: str) -> User:
    from app.services.teams import accept_token

    row = confirm_code(db, email=email, purpose="register", code=code)
    user = _find_user(db, email)
    if user is None:
        raise HTTPException(status_code=400, detail=EXPIRED)
    user.email_verified_at = clock.now()
    user.updated_at = clock.now()
    token = ""
    if isinstance(row.payload, dict):
        token = str(row.payload.get("invite_token") or "").strip()
    if token:
        try:
            with db.begin_nested():
                accept_token(db, user, token)
        except HTTPException:
            pass
    db.flush()
    return user


def request_password_reset(db: Session, email: str) -> None:
    user = _find_user(db, email)
    if user is None or user.email_verified_at is None:
        return
    code = issue_code(db, email=email, purpose="reset_password", user=user, payload={})
    db.commit()
    send_code(email=email, purpose="reset_password", code=code)


def reset_password(db: Session, *, email: str, code: str, password: str) -> User:
    if len(password) < 8:
        raise HTTPException(status_code=422, detail="Пароль короче 8 символов")
    confirm_code(db, email=email, purpose="reset_password", code=code)
    user = _find_user(db, email)
    if user is None or user.email_verified_at is None:
        raise HTTPException(status_code=400, detail=EXPIRED)
    user.password_hash = hash_password(password)
    user.updated_at = clock.now()
    revoke_user_sessions(db, user.id)
    clear_failure(db, email)
    db.flush()
    return user


def change_password(db: Session, user: User, current: str, new_password: str) -> None:
    if len(new_password) < 8:
        raise HTTPException(status_code=422, detail="Пароль короче 8 символов")
    ensure_unlocked(db, user.email)
    if not verify_password(current, user.password_hash):
        register_failure(db, user.email)
        raise HTTPException(status_code=401, detail="Неверный текущий пароль")
    user.password_hash = hash_password(new_password)
    user.updated_at = clock.now()
    revoke_user_sessions(db, user.id)
    clear_failure(db, user.email)
    db.flush()


def request_email_change(db: Session, user: User, new_email: str) -> str:
    if new_email == user.email:
        raise HTTPException(status_code=409, detail="Это уже ваша почта")
    taken = _find_user(db, new_email)
    if taken is not None:
        raise HTTPException(status_code=409, detail="Почта уже зарегистрирована")
    code = issue_code(
        db,
        email=new_email,
        purpose="change_email",
        user=user,
        payload={"new_email": new_email, "user_id": str(user.id)},
    )
    db.commit()
    return send_code(email=new_email, purpose="change_email", code=code)


def confirm_email_change(db: Session, user: User, code: str) -> User:
    row = db.scalar(
        select(EmailCode)
        .where(
            EmailCode.purpose == "change_email",
            EmailCode.user_id == user.id,
            EmailCode.consumed_at.is_(None),
        )
        .order_by(EmailCode.sent_at.desc())
    )
    if row is None:
        raise HTTPException(status_code=400, detail=EXPIRED)
    confirmed = confirm_code(db, email=row.email, purpose="change_email", code=code)
    new_email = str((confirmed.payload or {}).get("new_email") or row.email)
    other = _find_user(db, new_email)
    if other is not None and other.id != user.id:
        raise HTTPException(status_code=409, detail="Почта уже зарегистрирована")
    user.email = new_email
    user.updated_at = clock.now()
    db.flush()
    return user


def touch_name(db: Session, user: User, full_name: str) -> None:
    user.full_name = full_name
    user.updated_at = clock.now()
    db.flush()

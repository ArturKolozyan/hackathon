import hashlib
import os
import secrets
from datetime import timedelta

import bcrypt
from fastapi import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import AuthSession, User
from app.services import time as clock

COOKIE_NAME = "ik_session"
_DUMMY_HASH: str | None = None


def hash_password(password: str) -> str:
    rounds = int(os.environ.get("BCRYPT_ROUNDS", "12"))
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=rounds)).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def _dummy_hash() -> str:
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password("not-a-real-password")
    return _DUMMY_HASH


def hash_token(token: str) -> str:
    material = f"{get_settings().secret_key}:{token}".encode()
    return hashlib.sha256(material).hexdigest()


def authenticate(db: Session, email: str, password: str) -> User:
    from fastapi import HTTPException

    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None:
        verify_password(password, _dummy_hash())
        raise HTTPException(status_code=401, detail="Неверная почта или пароль")
    if not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Неверная почта или пароль")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Учётная запись отключена")
    return user


def issue_session(db: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    db.add(
        AuthSession(
            user_id=user.id,
            token_hash=hash_token(token),
            expires_at=clock.now() + timedelta(days=get_settings().session_days),
        )
    )
    db.flush()
    return token


def revoke_token(db: Session, token: str | None) -> None:
    if not token:
        return
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    if row is not None and row.revoked_at is None:
        row.revoked_at = clock.now()


def user_from_token(db: Session, token: str | None) -> User | None:
    if not token:
        return None
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == hash_token(token)))
    if row is None or row.revoked_at is not None or row.expires_at <= clock.now():
        return None
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        return None
    return user


def attach_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
        max_age=settings.session_days * 24 * 60 * 60,
        path="/",
    )


def clear_cookie(response: Response) -> None:
    response.delete_cookie(COOKIE_NAME, path="/")

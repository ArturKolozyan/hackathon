"""Владелец установки. Гарантируется при старте API, не только сидом."""

import logging

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import User
from app.services import time as clock

log = logging.getLogger("invoice_keeper.owner")


def ensure_owner(settings: Settings | None = None) -> None:
    current = settings or get_settings()
    email = current.resolved_owner_email
    password = current.resolved_owner_password
    if not email or "@" not in email:
        raise RuntimeError("Задайте OWNER_EMAIL в .env")
    if len(password) < 8:
        raise RuntimeError("OWNER_PASSWORD короче 8 символов")
    db = SessionLocal()
    try:
        _apply(
            db,
            email=email,
            password=password,
            name=current.resolved_owner_name,
            reset_password=current.owner_reset_password,
        )
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _apply(db: Session, *, email: str, password: str, name: str, reset_password: bool) -> User:
    owner = db.scalar(select(User).where(User.is_owner.is_(True)))
    if owner is not None:
        if owner.email != email:
            log.warning(
                "OWNER_EMAIL=%s не совпадает с владельцем %s: второй владелец не создаётся",
                email,
                owner.email,
            )
        if reset_password:
            owner.password_hash = hash_password(password)
            owner.updated_at = clock.now()
            log.warning(
                "пароль владельца %s записан из OWNER_PASSWORD; верните OWNER_RESET_PASSWORD=false",
                owner.email,
            )
        else:
            log.info("владелец на месте: %s", owner.email)
        db.flush()
        return owner
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            full_name=name,
            password_hash=hash_password(password),
            is_active=True,
            email_verified_at=clock.now(),
            is_owner=True,
            must_change_password=False,
            telegram_onboarding_done=True,
            notify_scope="mine",
            notify_overdue=True,
        )
        db.add(user)
        log.info("владелец создан: %s", email)
    else:
        user.is_owner = True
        user.is_active = True
        user.must_change_password = False
        if reset_password:
            user.password_hash = hash_password(password)
            log.warning(
                "пароль владельца %s записан из OWNER_PASSWORD; верните OWNER_RESET_PASSWORD=false",
                user.email,
            )
        if user.email_verified_at is None:
            user.email_verified_at = clock.now()
        user.updated_at = clock.now()
        log.info("владелец подтверждён: %s", user.email)
    db.flush()
    return user

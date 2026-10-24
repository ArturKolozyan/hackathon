"""Пять неверных паролей — 15 минут тишины на эту почту.

Чужой адрес не блокируем: иначе можно заморозить почту ещё до регистрации.
"""

from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.models import LoginAttempt
from app.services import time as clock

LOCK_AFTER = 5
LOCK_FOR = timedelta(minutes=15)
LOCKED = "Слишком много попыток. Повторите через 15 минут."


def ensure_unlocked(db: Session, email: str) -> None:
    row = db.get(LoginAttempt, email)
    if row is None or row.locked_until is None:
        return
    if row.locked_until > clock.now():
        raise HTTPException(status_code=429, detail=LOCKED)
    row.failed_count = 0
    row.locked_until = None
    row.updated_at = clock.now()


def register_failure(db: Session, email: str) -> None:
    row = db.get(LoginAttempt, email)
    if row is None:
        row = LoginAttempt(email=email, failed_count=0, updated_at=clock.now())
        db.add(row)
    row.failed_count += 1
    row.updated_at = clock.now()
    if row.failed_count >= LOCK_AFTER:
        row.failed_count = 0
        row.locked_until = clock.now() + LOCK_FOR
    db.commit()


def clear_failure(db: Session, email: str) -> None:
    row = db.get(LoginAttempt, email)
    if row is not None:
        db.delete(row)

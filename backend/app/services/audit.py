import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.models import AuditLog, User
from app.services import time as clock

# Одна установка — одна организация: журнал хранит последние 1000 записей.
AUDIT_KEEP = 1000

_SECRET_PARTS = ("password", "token", "secret", "authorization", "cookie", "smtp_")


def sanitize(value: Any) -> Any:
    """Пароли, токены и секреты в meta не пишем — даже если вызывающий передал."""
    if isinstance(value, dict):
        clean: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(part in lowered for part in _SECRET_PARTS):
                continue
            clean[str(key)] = sanitize(item)
        return clean
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, uuid.UUID):
        return str(value)
    return str(value)


def record(
    db: Session,
    *,
    action: str,
    actor: User | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    meta: dict | None = None,
    team_id: uuid.UUID | None = None,
    at: datetime | None = None,
) -> None:
    trim(db, keep=AUDIT_KEEP - 1)
    db.add(
        AuditLog(
            at=at or clock.now(),
            team_id=team_id,
            actor_user_id=actor.id if actor is not None else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            meta=sanitize(meta or {}),
        )
    )


def trim(db: Session, *, keep: int = AUDIT_KEEP) -> None:
    """Самые старые записи сверх лимита удаляются. Журнал ни для чего, кроме показа, не читается."""
    stale = select(AuditLog.id).order_by(AuditLog.at.desc(), AuditLog.id.desc()).offset(keep).scalar_subquery()
    db.execute(delete(AuditLog).where(AuditLog.id.in_(stale)).execution_options(synchronize_session=False))

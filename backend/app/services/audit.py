import uuid
from datetime import datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import AuditLog, User
from app.services import time as clock

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

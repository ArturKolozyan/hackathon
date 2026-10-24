from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import APIModel


class AuditOut(APIModel):
    id: UUID
    at: datetime
    actor_user_id: UUID | None
    actor_name: str | None
    actor_email: str | None
    action: str
    entity_type: str | None
    entity_id: UUID | None
    meta: dict


class AuditList(BaseModel):
    items: list[AuditOut]
    total: int
    timezone: str = Field(default="Europe/Moscow", description="Часовой пояс организации для показа времени")

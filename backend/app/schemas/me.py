from datetime import datetime
from uuid import UUID

from app.schemas.common import APIModel


class MembershipBrief(APIModel):
    team_id: UUID
    team_name: str
    role: str


class MeOut(APIModel):
    id: UUID
    email: str
    full_name: str
    is_active: bool
    email_verified: bool
    created_at: datetime
    active_team_id: UUID | None
    memberships: list[MembershipBrief]
    telegram_chat_id: str | None = None

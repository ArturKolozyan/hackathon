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
    is_owner: bool = False
    email_verified: bool
    created_at: datetime
    active_team_id: UUID | None
    memberships: list[MembershipBrief]
    telegram_chat_id: str | None = None
    telegram_linked: bool = False
    must_change_password: bool = False
    telegram_onboarding_done: bool = False

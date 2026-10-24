from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.telegram import TeamTelegram


class PersonalChannelOut(BaseModel):
    enabled: bool
    team_ids: list[UUID]
    address: str | None = None
    linked: bool = False
    username: str | None = None
    display_name: str | None = None
    bot_ready: bool = False
    bot_username: str | None = None
    test_pending: bool = False
    test_sent_at: datetime | None = None
    test_error: str | None = None


class TeamRef(BaseModel):
    id: UUID
    name: str


class TeamChannelsOut(BaseModel):
    team_id: UUID
    team_name: str
    can_manage: bool
    telegram: TeamTelegram
    webhook_url: str | None = None
    webhook_checked_at: datetime | None = None
    webhook_check_error: str | None = None


class NotificationsOut(BaseModel):
    email: PersonalChannelOut
    telegram: PersonalChannelOut
    teams: list[TeamRef]
    team: TeamChannelsOut


class PersonalNotificationsIn(BaseModel):
    email_enabled: bool
    email_team_ids: list[UUID] = Field(default_factory=list)
    telegram_enabled: bool
    telegram_team_ids: list[UUID] = Field(default_factory=list)


class WebhookIn(BaseModel):
    url: str = ""


class ProbeOut(BaseModel):
    ok: bool
    pending: bool = False
    detail: str

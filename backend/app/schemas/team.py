from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import APIModel
from app.schemas.fields import email_value, name_value

ROLES = {"admin", "member"}


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def clean(cls, value: str) -> str:
        return name_value(value)


class TeamRename(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def clean(cls, value: str) -> str:
        return name_value(value)


class TeamDelete(BaseModel):
    name: str = Field(min_length=1, max_length=120)

    @field_validator("name")
    @classmethod
    def clean(cls, value: str) -> str:
        return name_value(value)


class TeamOut(APIModel):
    id: UUID
    name: str
    role: str


class MemberOut(APIModel):
    id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool


class MemberRoleIn(BaseModel):
    role: str

    @field_validator("role")
    @classmethod
    def check(cls, value: str) -> str:
        if value not in ROLES:
            raise ValueError("Роль: admin или member")
        return value


class TransferIn(BaseModel):
    user_id: UUID


class ActiveTeamIn(BaseModel):
    team_id: UUID


class InviteIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    role: str = "member"

    @field_validator("email")
    @classmethod
    def clean_email(cls, value: str) -> str:
        return email_value(value)

    @field_validator("role")
    @classmethod
    def check(cls, value: str) -> str:
        if value not in ROLES:
            raise ValueError("Пригласить можно админом или участником")
        return value


class InviteOut(APIModel):
    id: UUID
    email: str
    role: str
    expires_at: datetime
    expired: bool


class InviteCreated(InviteOut):
    url: str
    delivery: str


class InviteLinkOut(BaseModel):
    url: str
    token: str


class InvitePreview(BaseModel):
    team_name: str
    role: str
    email: str | None = None
    valid: bool

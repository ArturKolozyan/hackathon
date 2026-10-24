import re
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import APIModel

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

__all__ = ["UserOut", "UserCreate", "UserUpdate", "DepartmentRole", "TelegramLinkSent"]


class DepartmentRole(APIModel):
    id: UUID
    name: str
    role: str


class UserOut(APIModel):
    id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    is_owner: bool = False
    telegram_linked: bool = False
    must_change_password: bool = False
    departments: list[DepartmentRole] = Field(default_factory=list)


class TelegramLinkSent(APIModel):
    url: str | None = None
    delivery: str
    message: str


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    role: str = "user"
    department_id: UUID | None = None
    team_id: UUID | None = None
    department: str | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if not _EMAIL.fullmatch(cleaned):
            raise ValueError("Укажите почту")
        return cleaned

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Укажите имя")
        return cleaned

    @field_validator("role")
    @classmethod
    def check_role(cls, value: str) -> str:
        cleaned = value.strip().lower()
        if cleaned == "member":
            return "user"
        if cleaned not in {"admin", "user"}:
            raise ValueError("Роль: admin или user")
        return cleaned

    @field_validator("department")
    @classmethod
    def strip_department(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @model_validator(mode="after")
    def one_department(self) -> "UserCreate":
        if self.department_id is None and self.team_id is not None:
            self.department_id = self.team_id
        return self


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    role: str | None = None
    is_active: bool | None = None
    blocked: bool | None = None
    department_id: UUID | None = None

    @field_validator("full_name")
    @classmethod
    def strip_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Укажите имя")
        return cleaned

    @field_validator("role")
    @classmethod
    def check_role(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if cleaned == "member":
            return "user"
        if cleaned not in {"admin", "user"}:
            raise ValueError("Роль: admin или user")
        return cleaned

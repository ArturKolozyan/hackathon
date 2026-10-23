import re

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import UserOut

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

__all__ = ["UserOut"]


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    full_name: str = Field(min_length=1, max_length=200)
    password: str = Field(min_length=8, max_length=200)
    role: str = "user"

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
        if value not in {"admin", "user"}:
            raise ValueError("Роль: admin или user")
        return value


class UserUpdate(BaseModel):
    email: str | None = Field(default=None, max_length=320)
    full_name: str | None = Field(default=None, max_length=200)
    password: str | None = Field(default=None, min_length=8, max_length=200)
    role: str | None = None
    is_active: bool | None = None

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip().lower()
        if not _EMAIL.fullmatch(cleaned):
            raise ValueError("Укажите почту")
        return cleaned

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
        if value not in {"admin", "user"}:
            raise ValueError("Роль: admin или user")
        return value

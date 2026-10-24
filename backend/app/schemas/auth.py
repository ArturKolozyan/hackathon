from pydantic import BaseModel, Field, field_validator

from app.schemas.fields import code_value, email_value
from app.schemas.me import MeOut


class LoginIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=1, max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return email_value(value)


class TokenOut(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: MeOut


class ForgotIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return email_value(value)


class ResetIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    code: str
    password: str = Field(min_length=8, max_length=200)

    @field_validator("email")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return email_value(value)

    @field_validator("code")
    @classmethod
    def digits(cls, value: str) -> str:
        return code_value(value)


class SentOut(BaseModel):
    delivery: str
    message: str


def sent_message(delivery: str) -> str:
    if delivery == "log":
        return "Почта не подключена: код записан в лог API."
    return "Письмо уходит. Если его нет через минуту — запросите код ещё раз."

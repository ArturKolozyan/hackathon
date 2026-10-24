from pydantic import BaseModel, Field, field_validator

from app.schemas.fields import code_value, email_value, name_value


class NameIn(BaseModel):
    full_name: str = Field(min_length=1, max_length=200)

    @field_validator("full_name")
    @classmethod
    def clean(cls, value: str) -> str:
        return name_value(value)


class PasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


class EmailChangeIn(BaseModel):
    email: str = Field(min_length=3, max_length=320)

    @field_validator("email")
    @classmethod
    def clean(cls, value: str) -> str:
        return email_value(value)


class CodeIn(BaseModel):
    code: str

    @field_validator("code")
    @classmethod
    def digits(cls, value: str) -> str:
        return code_value(value)

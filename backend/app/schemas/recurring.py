from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import Money, UserBrief

CURRENCIES = {"RUB", "USD", "EUR"}


def _amount(value: Decimal) -> Decimal:
    quantized = value.quantize(Decimal("0.01"))
    if value != quantized:
        raise ValueError("Не больше двух знаков после запятой")
    if quantized <= 0:
        raise ValueError("Сумма должна быть больше нуля")
    return quantized


class RecurringCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    description: str | None = None
    amount: Decimal
    currency: str
    day_of_month: int = Field(ge=1, le=31)
    starts_on: date
    responsible_user_id: UUID

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Укажите название")
        return cleaned

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("amount")
    @classmethod
    def check_amount(cls, value: Decimal) -> Decimal:
        return _amount(value)

    @field_validator("currency")
    @classmethod
    def check_currency(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in CURRENCIES:
            raise ValueError("Валюта: RUB, USD или EUR")
        return normalized


class RecurringUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    starts_on: date | None = None
    responsible_user_id: UUID | None = None
    is_archived: bool | None = None

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Укажите название")
        return cleaned

    @field_validator("description")
    @classmethod
    def strip_description(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

    @field_validator("amount")
    @classmethod
    def check_amount(cls, value: Decimal | None) -> Decimal | None:
        if value is None:
            return None
        return _amount(value)

    @field_validator("currency")
    @classmethod
    def check_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if normalized not in CURRENCIES:
            raise ValueError("Валюта: RUB, USD или EUR")
        return normalized


class RecurringOut(BaseModel):
    id: UUID
    title: str
    description: str | None
    amount: Money
    currency: str
    day_of_month: int
    starts_on: date
    is_archived: bool
    responsible: UserBrief
    open_count: int
    paid_count: int
    created_at: datetime

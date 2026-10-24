from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

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
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    starts_on: date | None = None
    next_payment_date: date | None = None
    periodicity: str = "monthly"
    responsible_user_id: UUID | None = None

    @model_validator(mode="after")
    def fill_schedule(self) -> "RecurringCreate":
        label = (self.periodicity or "").strip().lower()
        if label in {"ежемесячно", "monthly"}:
            self.periodicity = "monthly"
        else:
            raise ValueError("Периодичность: ежемесячно")
        if self.next_payment_date is not None:
            self.day_of_month = self.next_payment_date.day
            self.starts_on = self.next_payment_date
        if self.day_of_month is None or self.starts_on is None:
            raise ValueError("Укажите дату ближайшей оплаты")
        return self

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
    next_payment_date: date | None = None
    periodicity: str | None = None
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

    @field_validator("periodicity")
    @classmethod
    def check_periodicity(cls, value: str | None) -> str | None:
        if value is None:
            return None
        label = value.strip().lower()
        if label in {"ежемесячно", "monthly"}:
            return "monthly"
        raise ValueError("Периодичность: ежемесячно")


class RecurringOut(BaseModel):
    id: UUID
    title: str
    description: str | None
    amount: Money
    currency: str
    day_of_month: int
    starts_on: date
    next_payment_date: date | None = None
    periodicity: str = "monthly"
    is_archived: bool
    responsible: UserBrief | None = None
    open_count: int
    paid_count: int
    created_at: datetime

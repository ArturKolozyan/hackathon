from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

from app.schemas.common import Money, UserBrief

CURRENCIES = {"RUB", "USD", "EUR"}

_PERIODS = {
    "monthly": ("monthly", 1),
    "ежемесячно": ("monthly", 1),
    "quarterly": ("quarterly", 3),
    "квартал": ("quarterly", 3),
    "раз в квартал": ("quarterly", 3),
    "ежеквартально": ("quarterly", 3),
    "semiannual": ("semiannual", 6),
    "полгода": ("semiannual", 6),
    "раз в полгода": ("semiannual", 6),
    "yearly": ("yearly", 12),
    "ежегодно": ("yearly", 12),
    "раз в год": ("yearly", 12),
    "once": ("once", None),
    "разово": ("once", None),
    "один раз": ("once", None),
    "every_n": ("every_n", None),
    "каждые n месяцев": ("every_n", None),
}


def normalize_periodicity(label: str, interval: int | None) -> tuple[str, int | None]:
    key = (label or "").strip().lower()
    if key not in _PERIODS:
        raise ValueError("Периодичность: ежемесячно, раз в N месяцев, ежегодно или разово")
    kind, implied = _PERIODS[key]
    if kind == "every_n":
        if interval is None or interval < 1 or interval > 36:
            raise ValueError("Укажите интервал от 1 до 36 месяцев")
        if interval == 3:
            return "quarterly", 3
        if interval == 6:
            return "semiannual", 6
        if interval == 12:
            return "yearly", 12
        if interval == 1:
            return "monthly", 1
        return "every_n", interval
    return kind, implied


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
    interval_months: int | None = Field(default=None, ge=1, le=36)
    responsible_user_id: UUID | None = None

    @model_validator(mode="after")
    def fill_schedule(self) -> "RecurringCreate":
        kind, interval = normalize_periodicity(self.periodicity, self.interval_months)
        self.periodicity = kind
        self.interval_months = interval
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


_REQUIRED_ON_UPDATE = ("title", "amount", "currency", "day_of_month", "starts_on", "next_payment_date", "is_archived")


class RecurringUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    description: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    day_of_month: int | None = Field(default=None, ge=1, le=31)
    starts_on: date | None = None
    next_payment_date: date | None = None
    periodicity: str | None = None
    interval_months: int | None = Field(default=None, ge=1, le=36)
    responsible_user_id: UUID | None = None
    is_archived: bool | None = None

    @model_validator(mode="after")
    def fill_periodicity(self) -> "RecurringUpdate":
        # null в обязательном поле — ошибка ввода (422), а не попытка стереть значение.
        nulls = [name for name in _REQUIRED_ON_UPDATE if name in self.model_fields_set and getattr(self, name) is None]
        if "periodicity" in self.model_fields_set and self.periodicity is None and self.interval_months is None:
            nulls.append("periodicity")
        if nulls:
            raise ValueError(f"Поле нельзя очистить: {', '.join(nulls)}")
        if self.periodicity is None and self.interval_months is None:
            return self
        kind, interval = normalize_periodicity(self.periodicity or "every_n", self.interval_months)
        self.periodicity = kind
        self.interval_months = interval
        return self

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
    next_payment_date: date | None = None
    periodicity: str = "monthly"
    interval_months: int | None = None
    applies_from: date | None = None
    debt_count: int = 0
    is_archived: bool
    responsible: UserBrief | None = None
    open_count: int
    paid_count: int
    created_at: datetime

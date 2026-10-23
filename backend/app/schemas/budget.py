from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import APIModel, Money

CURRENCIES = ("RUB", "USD", "EUR")


def _period_key(period_type: str, period_key: str) -> str:
    text = period_key.strip()
    if period_type == "month":
        parts = text.split("-")
        if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2:
            raise ValueError("Месяц записывается как ГГГГ-ММ")
        year, month = int(parts[0]), int(parts[1])
        if year < 2000 or year > 2100 or month < 1 or month > 12:
            raise ValueError("Месяц записывается как ГГГГ-ММ")
        return f"{year:04d}-{month:02d}"
    if period_type == "year":
        if len(text) != 4 or not text.isdigit():
            raise ValueError("Год записывается как ГГГГ")
        year = int(text)
        if year < 2000 or year > 2100:
            raise ValueError("Год записывается как ГГГГ")
        return text
    raise ValueError("Период — month или year")


class BudgetCreate(BaseModel):
    period_type: str = Field(pattern="^(month|year)$")
    period_key: str = Field(min_length=4, max_length=7)
    currency: str = Field(pattern="^(RUB|USD|EUR)$")
    amount: Decimal = Field(gt=0, le=Decimal("9999999999.99"))

    @field_validator("period_key")
    @classmethod
    def key_matches_type(cls, value: str, info) -> str:
        period_type = info.data.get("period_type")
        if period_type not in ("month", "year"):
            return value.strip()
        return _period_key(period_type, value)

    @field_validator("amount")
    @classmethod
    def cents(cls, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))


class BudgetUpdate(BaseModel):
    amount: Decimal = Field(gt=0, le=Decimal("9999999999.99"))

    @field_validator("amount")
    @classmethod
    def cents(cls, value: Decimal) -> Decimal:
        return value.quantize(Decimal("0.01"))


class BudgetOut(APIModel):
    id: UUID
    period_type: str
    period_key: str
    currency: str
    amount: Money


class BudgetLine(BaseModel):
    id: UUID | None
    currency: str
    plan_amount: Money | None
    fact_amount: Money
    expected_amount: Money


class BudgetReport(BaseModel):
    period_type: str
    period_key: str
    timezone: str
    rows: list[BudgetLine]

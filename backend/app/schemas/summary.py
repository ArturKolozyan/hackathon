from datetime import date

from pydantic import BaseModel

from app.schemas.common import Money


class CurrencyTotals(BaseModel):
    currency: str
    overdue_amount: Money
    due_soon_amount: Money
    upcoming_amount: Money
    paid_amount: Money
    open_amount: Money


class SummaryOut(BaseModel):
    timezone: str
    today: date
    soon_days: int
    counts: dict[str, int]
    by_currency: list[CurrencyTotals]

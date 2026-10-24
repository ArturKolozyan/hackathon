from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field


class RatesOut(BaseModel):
    on: date | None = Field(default=None, description="Дата курса ЦБ РФ; null — курс сейчас недоступен")
    rates: dict[str, Decimal] = Field(default_factory=dict, description="Рублей за единицу валюты: USD, EUR")

from datetime import date
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.common import Money, UserBrief


class MoneyBucket(BaseModel):
    currency: str
    amount: Money
    count: int


class StatsTeam(BaseModel):
    team_id: UUID
    team_name: str
    role: str
    to_pay: list[MoneyBucket]
    overdue: list[MoneyBucket]
    paid: list[MoneyBucket]


class StatsItem(BaseModel):
    occurrence_id: UUID
    team_id: UUID
    team_name: str
    title: str
    due_date: date
    amount: Money
    currency: str
    status: str
    responsible: UserBrief | None = None


class StatsOut(BaseModel):
    timezone: str
    today: date
    paid_from: date = Field(description="Оплачено считаем по дате оплаты в этом окне.")
    paid_to: date
    due_from: date | None = Field(description="Если пусто, к оплате и просрочка — все открытые периоды.")
    due_to: date | None
    to_pay: list[MoneyBucket]
    overdue: list[MoneyBucket]
    paid: list[MoneyBucket]
    nearest: list[StatsItem]
    by_team: list[StatsTeam]
    people: list[UserBrief]

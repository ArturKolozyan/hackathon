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


class StatsOperation(BaseModel):
    occurrence_id: UUID
    team_id: UUID
    team_name: str
    title: str
    period_label: str
    due_date: date
    amount: Money
    paid_amount: Money | None = None
    currency: str
    status: str
    paid_on: date | None = None
    lateness_days: int | None = None
    has_receipt: bool = False
    planned: bool = Field(default=False, description="Будущий срок по расписанию, ещё не создан: открыть нельзя.")
    responsible: UserBrief | None = None


class StatsOperations(BaseModel):
    items: list[StatsOperation]
    total: int
    page: int
    page_size: int


class StatsMonth(BaseModel):
    month: str = Field(description="ГГГГ-ММ")
    currency: str
    paid: Money = Field(description="Оплачено по дате оплаты в этом месяце.")
    overdue: Money = Field(description="Не оплачено, срок в этом месяце уже прошёл.")
    planned: Money = Field(description="Не оплачено, срок в этом месяце ещё впереди.")


class StatsDepartment(BaseModel):
    id: UUID
    name: str


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
    departments: list[StatsDepartment] = Field(default_factory=list, description="Все отделы, доступные для фильтра.")
    paid_count: int = 0
    paid_on_time: int = Field(default=0, description="Сколько из оплаченных в окне закрыты не позже срока.")
    monthly: list[StatsMonth] = Field(
        default_factory=list,
        description="12 месяцев: 6 прошедших, текущий и 5 следующих. Фильтры отделов, валюты и ответственного учитываются.",
    )
    operations: StatsOperations | None = None

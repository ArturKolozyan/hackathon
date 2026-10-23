from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import Money, UserBrief


class OccurrenceOut(BaseModel):
    id: UUID
    recurring_payment_id: UUID
    title: str
    description: str | None
    period: str
    period_label: str
    due_date: date
    amount: Money
    currency: str
    status: str
    bucket: str
    paid_at: datetime | None
    paid_on: date | None
    paid_on_time: bool | None
    days_delta: int
    lateness_days: int | None
    note: str | None
    template_archived: bool
    responsible: UserBrief
    paid_by: UserBrief | None = Field(
        description=(
            "Кто подтвердил оплату. Веб (confirm и patch) — текущий пользователь. "
            "Кнопка «Оплачено» в общем Telegram-чате — активный администратор с почтой ADMIN_EMAIL; "
            "если такого администратора нет, null, а paid_at всё равно ставится. Заметку кнопка не меняет."
        )
    )
    telegram_reminded_at: datetime | None = Field(
        description="Когда напоминание по этому периоду успешно ушло в Telegram. Повторно не отправляется."
    )


class OccurrenceList(BaseModel):
    timezone: str
    today: date
    soon_days: int
    items: list[OccurrenceOut]


class InboxOut(BaseModel):
    timezone: str
    today: date
    soon_days: int
    overdue: list[OccurrenceOut]
    soon: list[OccurrenceOut]
    rest: list[OccurrenceOut]


class ConfirmIn(BaseModel):
    paid_at: str | None = None
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None


class OccurrencePatch(BaseModel):
    paid_at: str | None = None
    note: str | None = Field(default=None, max_length=2000)

    @field_validator("note")
    @classmethod
    def clean_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None

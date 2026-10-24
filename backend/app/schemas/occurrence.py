from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

from app.schemas.common import Money, UserBrief


def _money_or_none(value: Decimal | None) -> Decimal | None:
    if value is None:
        return None
    quantized = value.quantize(Decimal("0.01"))
    if value != quantized:
        raise ValueError("Не больше двух знаков после запятой")
    if quantized <= 0:
        raise ValueError("Сумма должна быть больше нуля")
    return quantized


def clean_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


class ReceiptOut(BaseModel):
    name: str
    content_type: str
    size: int
    uploaded_at: datetime | None = None
    url: str = Field(description="Скачать или открыть чек. Доступ — как к периоду.")


class OccurrenceOut(BaseModel):
    id: UUID
    team_id: UUID
    recurring_payment_id: UUID
    title: str
    description: str | None
    period: str
    period_label: str
    due_date: date
    amount: Money
    paid_amount: Money | None = None
    currency: str
    status: str
    bucket: str
    paid_at: datetime | None
    paid_on: date | None
    paid_on_time: bool | None
    days_delta: int
    lateness_days: int | None
    note: str | None
    receipt: ReceiptOut | None = None
    receipt_note: str | None = None
    template_archived: bool
    planned: bool = Field(
        default=False,
        description="Будущий срок по расписанию, которого ещё нет в базе. Только для просмотра: оплатить и править нельзя.",
    )
    responsible: UserBrief | None = None
    paid_by: UserBrief | None = Field(
        description=(
            "Кто подтвердил оплату. Веб (confirm и patch) — текущий пользователь. "
            "Кнопка «Оплачено» в Telegram — пользователь rekeeper, чей привязанный аккаунт нажал. "
            "Непривязанный клик оплату не ставит. Заметку кнопка не меняет."
        )
    )
    telegram_reminded_at: datetime | None = Field(
        description=(
            "Когда карточка периода ушла в Telegram. "
            "Повтор того же канала блокирует запись notification_deliveries, не это поле: письмо его не занимает."
        )
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
    paid_amount: Decimal | None = None
    note: str | None = Field(default=None, max_length=2000)
    receipt_note: str | None = Field(default=None, max_length=2000)

    @field_validator("note", "receipt_note")
    @classmethod
    def clean_note(cls, value: str | None) -> str | None:
        return clean_text(value)

    @field_validator("paid_amount")
    @classmethod
    def check_paid_amount(cls, value: Decimal | None) -> Decimal | None:
        return _money_or_none(value)


class OccurrencePatch(BaseModel):
    paid_at: str | None = None
    paid_amount: Decimal | None = None
    title: str | None = Field(default=None, max_length=200)
    amount: Decimal | None = None
    currency: str | None = None
    due_date: date | None = None
    note: str | None = Field(default=None, max_length=2000)
    receipt_note: str | None = Field(default=None, max_length=2000)

    @field_validator("note", "receipt_note")
    @classmethod
    def clean_note(cls, value: str | None) -> str | None:
        return clean_text(value)

    @field_validator("title")
    @classmethod
    def strip_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Укажите название")
        return cleaned

    @field_validator("currency")
    @classmethod
    def check_currency(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip().upper()
        if normalized not in {"RUB", "USD", "EUR"}:
            raise ValueError("Валюта: RUB, USD или EUR")
        return normalized

    @field_validator("amount", "paid_amount")
    @classmethod
    def check_amounts(cls, value: Decimal | None) -> Decimal | None:
        return _money_or_none(value)

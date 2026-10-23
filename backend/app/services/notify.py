"""Один пайплайн событий периода для email, webhook и Telegram.

Telegram-агент подключается через app.integrations.telegram.deliver.
Пока функция бросает NotImplementedError, канал пропускается
и не помечается доставленным — бот сможет отправить позже.
"""

import logging
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.integrations.email import send_reminder_email
from app.integrations.webhook import send_webhook
from app.models import NotificationDelivery, PaymentOccurrence
from app.services import time as clock
from app.services.reminders import should_remind
from app.services.schedule import classify, period_key

log = logging.getLogger("invoice_keeper.notify")

REMINDER = "occurrence.reminder"
PAID = "occurrence.paid"
UNPAID = "occurrence.unpaid"


def occurrence_payload(occurrence: PaymentOccurrence, event: str) -> dict:
    settings = get_settings()
    today = clock.today()
    status = classify(occurrence.due_date, occurrence.paid_at, today, settings.soon_days)
    amount = occurrence.amount.quantize(Decimal("0.01"))
    return {
        "event": event,
        "sent_at": clock.now().isoformat(),
        "occurrence": {
            "id": str(occurrence.id),
            "title": occurrence.title,
            "amount": f"{amount:.2f}",
            "currency": occurrence.currency,
            "due_date": occurrence.due_date.isoformat(),
            "status": status,
            "period": period_key(occurrence.period_year, occurrence.period_month),
        },
    }


def _already(db: Session, occurrence_id: uuid.UUID, event: str, channel: str) -> bool:
    stmt = select(NotificationDelivery.id).where(
        NotificationDelivery.occurrence_id == occurrence_id,
        NotificationDelivery.event == event,
        NotificationDelivery.channel == channel,
    )
    return db.scalar(stmt) is not None


def _mark(db: Session, occurrence_id: uuid.UUID, event: str, channel: str) -> None:
    try:
        with db.begin_nested():
            db.add(
                NotificationDelivery(
                    occurrence_id=occurrence_id,
                    event=event,
                    channel=channel,
                    created_at=clock.now(),
                )
            )
            db.flush()
    except IntegrityError:
        return


def _telegram(text: str, occurrence: PaymentOccurrence, event: str) -> str:
    settings = get_settings()
    token = settings.telegram_bot_token.strip()
    chat_id = settings.telegram_chat_id.strip()
    if not token or not chat_id:
        return "skipped"
    try:
        from app.integrations import telegram

        telegram.deliver(text, chat_id=chat_id, occurrence_id=str(occurrence.id), event=event)
    except NotImplementedError:
        return "skipped"
    except Exception:
        log.exception("telegram channel failed")
        return "failed"
    return "sent"


def _channels(event: str):
    if event == REMINDER:
        return ("email", "webhook", "telegram")
    return ("webhook",)


def _send(channel: str, occurrence: PaymentOccurrence, event: str, payload: dict) -> str:
    if channel == "email":
        return send_reminder_email(payload)
    if channel == "webhook":
        return send_webhook(payload)
    if channel == "telegram":
        occurrence_body = payload["occurrence"]
        text = (
            f"{occurrence_body['title']}\n"
            f"{occurrence_body['amount']} {occurrence_body['currency']}\n"
            f"Срок: {occurrence_body['due_date']}\n"
            f"Статус: {occurrence_body['status']}"
        )
        return _telegram(text, occurrence, event)
    return "skipped"


def fanout(db: Session, occurrence: PaymentOccurrence, event: str) -> int:
    payload = occurrence_payload(occurrence, event)
    sent = 0
    for channel in _channels(event):
        if _already(db, occurrence.id, event, channel):
            continue
        try:
            result = _send(channel, occurrence, event, payload)
        except Exception:
            log.exception("channel %s failed", channel)
            result = "failed"
        if result == "sent":
            _mark(db, occurrence.id, event, channel)
            sent += 1
    return sent


def notify_event(db: Session, occurrence: PaymentOccurrence, event: str) -> None:
    try:
        fanout(db, occurrence, event)
    except Exception:
        log.exception("notify %s failed", event)


def dispatch_due_reminders(db: Session) -> int:
    """Напоминания по всем периодам, которым пора. Возвращает число новых отправок."""
    settings = get_settings()
    today = clock.today()
    rows = db.scalars(
        select(PaymentOccurrence).options(joinedload(PaymentOccurrence.template))
    ).unique().all()
    sent = 0
    for row in rows:
        template = row.template
        archived = template is None or template.is_archived
        if not should_remind(
            due=row.due_date,
            paid_at=row.paid_at,
            archived=archived,
            today=today,
            soon_days=settings.soon_days,
        ):
            continue
        sent += fanout(db, row, REMINDER)
    return sent

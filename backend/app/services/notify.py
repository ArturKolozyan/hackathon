"""Один пайплайн событий периода для email, webhook и Telegram.

Telegram подключается через app.integrations.telegram.deliver.
NotImplementedError — транспорта нет: канал пропускается и не помечается,
следующий тик попробует снова. Другая ошибка — сбой сети, тоже без пометки.
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
from app.models import NotificationDelivery, PaymentOccurrence, RecurringPayment, User
from app.services import time as clock
from app.services.reminders import should_remind
from app.services.schedule import classify, period_key
from app.services.telegram_links import TEAM_RECIPIENT, resolve_team_chat_id

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


def _already(db: Session, occurrence_id: uuid.UUID, event: str, channel: str, recipient: str) -> bool:
    stmt = select(NotificationDelivery.id).where(
        NotificationDelivery.occurrence_id == occurrence_id,
        NotificationDelivery.event == event,
        NotificationDelivery.channel == channel,
        NotificationDelivery.recipient == recipient,
    )
    return db.scalar(stmt) is not None


def _mark(db: Session, occurrence_id: uuid.UUID, event: str, channel: str, recipient: str) -> None:
    try:
        with db.begin_nested():
            db.add(
                NotificationDelivery(
                    occurrence_id=occurrence_id,
                    event=event,
                    channel=channel,
                    recipient=recipient,
                    created_at=clock.now(),
                )
            )
            db.flush()
    except IntegrityError:
        return


def _personal_user(occurrence: PaymentOccurrence) -> User | None:
    template = occurrence.template
    if template is None:
        return None
    user = template.responsible
    if user is None or not user.is_active:
        return None
    if not user.telegram_reminders or user.telegram_user_id is None:
        return None
    return user


def _telegram(text: str, occurrence: PaymentOccurrence, event: str, *, chat_id: str, slot: str) -> str:
    token = get_settings().telegram_bot_token.strip()
    if not token or not chat_id:
        return "skipped"
    try:
        from app.integrations import telegram

        telegram.deliver(text, chat_id=chat_id, occurrence_id=str(occurrence.id), event=event, slot=slot)
    except NotImplementedError:
        return "skipped"
    except Exception:
        log.exception("telegram channel failed")
        return "failed"
    return "sent"


def _plan(occurrence: PaymentOccurrence, event: str) -> list[tuple[str, str]]:
    if event != REMINDER:
        return [("webhook", "")]
    plan = [("email", ""), ("webhook", ""), ("telegram", TEAM_RECIPIENT)]
    user = _personal_user(occurrence)
    if user is not None:
        plan.append(("telegram", f"user:{user.id}"))
    return plan


def _send(
    db: Session,
    channel: str,
    recipient: str,
    occurrence: PaymentOccurrence,
    event: str,
    payload: dict,
) -> str:
    if channel == "email":
        return send_reminder_email(payload)
    if channel == "webhook":
        return send_webhook(payload)
    if channel != "telegram":
        return "skipped"
    from app.services.telegram_cards import telegram_text

    text = telegram_text(occurrence)
    if recipient == TEAM_RECIPIENT:
        chat_id, _source = resolve_team_chat_id(db, occurrence.team_id)
        return _telegram(text, occurrence, event, chat_id=chat_id or "", slot="team")
    user = _personal_user(occurrence)
    if user is None or f"user:{user.id}" != recipient or user.telegram_user_id is None:
        return "skipped"
    return _telegram(text, occurrence, event, chat_id=str(user.telegram_user_id), slot="dm")


def fanout(db: Session, occurrence: PaymentOccurrence, event: str) -> int:
    payload = occurrence_payload(occurrence, event)
    sent = 0
    for channel, recipient in _plan(occurrence, event):
        if _already(db, occurrence.id, event, channel, recipient):
            continue
        try:
            result = _send(db, channel, recipient, occurrence, event, payload)
        except Exception:
            log.exception("channel %s failed", channel)
            result = "failed"
        if result == "sent":
            _mark(db, occurrence.id, event, channel, recipient)
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
        select(PaymentOccurrence).options(
            joinedload(PaymentOccurrence.template).joinedload(RecurringPayment.responsible)
        )
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

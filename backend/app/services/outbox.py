"""Очередь Telegram. Worker только кладёт pending. Шлёт контейнер bot."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models import NotificationDelivery, PaymentOccurrence, RecurringPayment
from app.services import time as clock
from app.services.reminders import DIGEST, is_reminder, is_overdue
from app.services.telegram_links import TEAM_RECIPIENT, resolve_team_chat_id

log = logging.getLogger("invoice_keeper.outbox")


def _already(db: Session, occurrence_id: uuid.UUID, event: str, recipient: str) -> bool:
    stmt = select(NotificationDelivery.id).where(
        NotificationDelivery.occurrence_id == occurrence_id,
        NotificationDelivery.event == event,
        NotificationDelivery.channel == "telegram",
        NotificationDelivery.recipient == recipient,
    )
    return db.scalar(stmt) is not None


def enqueue_telegram(
    db: Session,
    occurrence: PaymentOccurrence,
    event: str,
    *,
    recipient: str,
    chat_id: str,
) -> str:
    """pending-строка. Без токена или чата ничего не копим: слать всё равно некому."""
    if not get_settings().telegram_bot_token.strip() or not chat_id:
        return "skipped"
    if _already(db, occurrence.id, event, recipient):
        return "skipped"
    try:
        with db.begin_nested():
            db.add(
                NotificationDelivery(
                    occurrence_id=occurrence.id,
                    event=event,
                    channel="telegram",
                    recipient=recipient,
                    status="pending",
                    attempts=0,
                    created_at=clock.now(),
                )
            )
            db.flush()
    except IntegrityError:
        return "skipped"
    return "queued"


def _chat_for(db: Session, row: NotificationDelivery, occurrence: PaymentOccurrence) -> str:
    if row.recipient == TEAM_RECIPIENT:
        chat_id, _source = resolve_team_chat_id(db, occurrence.team_id)
        return chat_id or ""
    if row.recipient.startswith("user:"):
        from app.models import User

        try:
            user_id = uuid.UUID(row.recipient.removeprefix("user:"))
        except ValueError:
            return ""
        user = db.get(User, user_id)
        if user is None or user.telegram_user_id is None:
            return ""
        return str(user.telegram_user_id)
    return ""


def _outgoing_text(db: Session, occurrence: PaymentOccurrence, event: str, today) -> str:
    from app.services.telegram_cards import telegram_text

    if event != DIGEST:
        return telegram_text(occurrence)
    siblings = list(
        db.scalars(
            select(PaymentOccurrence)
            .where(
                PaymentOccurrence.recurring_payment_id == occurrence.recurring_payment_id,
                PaymentOccurrence.paid_at.is_(None),
                PaymentOccurrence.due_date < today,
            )
            .order_by(PaymentOccurrence.due_date, PaymentOccurrence.id)
        ).all()
    )
    lines = [f"Просрочено периодов: {len(siblings)}", occurrence.title]
    for row in siblings:
        lines.append(
            f"{row.period_year:04d}-{row.period_month:02d} · {row.amount:.2f} {row.currency} · до {row.due_date.strftime('%d.%m.%Y')}"
        )
    lines.append("Отметьте каждый период в панели.")
    return "\n".join(lines)


def drain_telegram(db: Session, bot) -> int:
    """Отправить pending. Просроченный T-3 не шлём: просрочка — отдельное событие.

    Оплаченный или архивный период пропускаем. Сбой сети оставляет pending.
    """
    from app.integrations.telegram import deliver

    rows = list(
        db.scalars(
            select(NotificationDelivery)
            .where(NotificationDelivery.channel == "telegram", NotificationDelivery.status == "pending")
            .order_by(NotificationDelivery.created_at)
        ).all()
    )
    today = clock.today()
    sent = 0
    for row in rows:
        occurrence = db.scalar(
            select(PaymentOccurrence)
            .where(PaymentOccurrence.id == row.occurrence_id)
            .options(joinedload(PaymentOccurrence.template).joinedload(RecurringPayment.responsible))
        )
        template = occurrence.template if occurrence is not None else None
        if occurrence is None or template is None or occurrence.paid_at is not None:
            row.status = "skipped"
            row.last_error = "closed"
            continue
        archived_overdue = template.is_archived and template.remind_archived_overdue and is_overdue(row.event)
        if template.is_archived and not archived_overdue:
            row.status = "skipped"
            row.last_error = "closed"
            continue
        if is_reminder(row.event) and today > occurrence.due_date:
            row.status = "skipped"
            row.last_error = "stale reminder"
            continue
        chat_id = _chat_for(db, row, occurrence)
        if not chat_id:
            row.attempts += 1
            row.last_error = "no chat"
            if row.attempts >= 5:
                row.status = "skipped"
            continue
        slot = "dm" if row.recipient.startswith("user:") else "team"
        try:
            deliver(
                _outgoing_text(db, occurrence, row.event, today),
                chat_id=chat_id,
                occurrence_id=str(occurrence.id),
                event=row.event,
                slot=slot,
            )
        except NotImplementedError:
            row.attempts += 1
            row.last_error = "no transport"
            continue
        except Exception as exc:
            row.attempts += 1
            row.last_error = str(exc)[:500]
            log.warning("telegram outbox failed occurrence=%s (%s)", row.occurrence_id, exc)
            continue
        row.status = "sent"
        row.last_error = None
        sent += 1
    db.commit()
    return sent

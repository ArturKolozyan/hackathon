"""Очередь Telegram. Worker только кладёт pending. Шлёт контейнер bot."""

from __future__ import annotations

import logging
import uuid
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.integrations.telegram import TelegramError
from app.models import NotificationDelivery, PaymentOccurrence, RecurringPayment
from app.services import time as clock
from app.services.reminders import DIGEST, is_reminder, is_overdue
from app.services.telegram_links import TEAM_RECIPIENT, move_chat, resolve_team_chat_id

log = logging.getLogger("invoice_keeper.outbox")

# Временный сбой (сеть, 429, 5xx) повторяем, но не вечно: сдаёмся после
# MAX_ATTEMPTS попыток, когда строка старше RETRY_WINDOW. Короткий обрыв
# сети на минуту не съедает напоминание.
MAX_ATTEMPTS = 30
RETRY_WINDOW = timedelta(hours=24)


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

    if not event.startswith(DIGEST):
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


def _previous_card(occurrence: PaymentOccurrence, slot: str) -> tuple[str | None, int | None]:
    if slot == "dm":
        return occurrence.dm_chat_id, occurrence.dm_message_id
    return occurrence.telegram_chat_id, occurrence.telegram_message_id


def _drop_button(bot, chat_id: str, message_id: int) -> None:
    """Новая карточка того же периода ушла в этот чат: у старой убираем «Оплачено»."""
    from app.services.telegram_cards import EMPTY_KEYBOARD

    try:
        bot.edit_markup(chat_id, message_id, EMPTY_KEYBOARD)
    except Exception as exc:
        log.info("old card button kept chat=%s message=%s (%s)", chat_id, message_id, exc)


def _send(db: Session, row: NotificationDelivery, occurrence: PaymentOccurrence, chat_id: str, slot: str, today) -> str:
    """Отправить карточку. Группа стала супергруппой — переносим id и шлём ещё раз. Возвращает чат."""
    from app.integrations.telegram import deliver

    text = _outgoing_text(db, occurrence, row.event, today)
    try:
        deliver(text, chat_id=chat_id, occurrence_id=str(occurrence.id), event=row.event, slot=slot)
        return chat_id
    except TelegramError as exc:
        moved = exc.migrate_to_chat_id
        if moved is None or slot != "team":
            raise
    new_chat = str(moved)
    # move_chat коммитит до повторной отправки: deliver пишет id сообщения своей сессией.
    move_chat(db, chat_id, new_chat)
    deliver(text, chat_id=new_chat, occurrence_id=str(occurrence.id), event=row.event, slot=slot)
    return new_chat


def drain_telegram(db: Session, bot) -> int:
    """Отправить pending. Просроченный T-3 не шлём: просрочка — отдельное событие.

    Оплаченный или архивный период пропускаем. Постоянная ошибка (бот
    заблокирован или выгнан, чата нет) сразу закрывает строку как skipped.
    Временная оставляет pending до лимита попыток.
    """

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
        old_chat, old_message = _previous_card(occurrence, slot)
        try:
            chat_id = _send(db, row, occurrence, chat_id, slot, today)
        except NotImplementedError:
            row.attempts += 1
            row.last_error = "no transport"
            continue
        except Exception as exc:
            row.attempts += 1
            row.last_error = str(exc)[:500]
            permanent = isinstance(exc, TelegramError) and exc.permanent
            expired = row.attempts >= MAX_ATTEMPTS and clock.now() - row.created_at >= RETRY_WINDOW
            if permanent or expired:
                row.status = "skipped"
            log.warning(
                "telegram outbox failed occurrence=%s permanent=%s (%s)", row.occurrence_id, permanent, exc
            )
            continue
        row.status = "sent"
        row.last_error = None
        sent += 1
        if old_message is not None and old_chat == chat_id and not row.event.startswith(DIGEST):
            _drop_button(bot, chat_id, int(old_message))
    db.commit()
    return sent

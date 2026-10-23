"""Карточка периода в Telegram: текст, правка того же сообщения, кнопка «Оплачено».

Новое напоминание отсюда не выбирается. Его шлёт notify через deliver().
Правка сообщения — не вторая отправка и не новая строка notification_deliveries.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any, Protocol

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.integrations.telegram import TelegramError
from app.models import PaymentOccurrence, User
from app.services import time as clock
from app.services.schedule import classify
from app.services.templates import touch

log = logging.getLogger("invoice_keeper.telegram")

PAID_PREFIX = "paid:"
EMPTY_KEYBOARD: dict[str, Any] = {"inline_keyboard": []}
_STATUS_RU = {
    "overdue": "просрочено",
    "due_soon": "скоро",
    "upcoming": "впереди",
    "paid": "оплачено",
}


class BotSender(Protocol):
    def edit_message(self, chat_id: str, message_id: int, text: str, reply_markup: dict[str, Any]) -> None: ...

    def answer_callback(self, callback_query_id: str, text: str) -> None: ...


def pay_keyboard(occurrence_id: uuid.UUID) -> dict[str, Any]:
    return {"inline_keyboard": [[{"text": "Оплачено", "callback_data": f"{PAID_PREFIX}{occurrence_id}"}]]}


def parse_paid_callback(data: str) -> uuid.UUID | None:
    if not data.startswith(PAID_PREFIX):
        return None
    try:
        return uuid.UUID(data[len(PAID_PREFIX) :])
    except ValueError:
        return None


def fingerprint(text: str, with_button: bool) -> str:
    marker = "btn" if with_button else "plain"
    return hashlib.sha256(f"{text}\n{marker}".encode()).hexdigest()[:32]


def telegram_text(occurrence: PaymentOccurrence) -> str:
    settings = get_settings()
    status = classify(occurrence.due_date, occurrence.paid_at, clock.today(), settings.soon_days)
    lines = [
        occurrence.title,
        f"{occurrence.amount:.2f} {occurrence.currency}",
        f"Срок: {occurrence.due_date.strftime('%d.%m.%Y')}",
        f"Статус: {_STATUS_RU[status]}",
    ]
    if occurrence.paid_at is not None:
        paid_on = occurrence.paid_at.astimezone(settings.zone).date()
        lines.append(f"Оплачено: {paid_on.strftime('%d.%m.%Y')}")
    return "\n".join(lines)


def _exec(db: Session, stmt):
    return db.execute(stmt, execution_options={"synchronize_session": False})


def _load_sent(db: Session) -> list[PaymentOccurrence]:
    stmt = (
        select(PaymentOccurrence)
        .where(PaymentOccurrence.telegram_message_id.is_not(None))
        .execution_options(populate_existing=True)
        .order_by(PaymentOccurrence.due_date, PaymentOccurrence.id)
    )
    return list(db.scalars(stmt).all())


def _load_one(db: Session, occurrence_id: uuid.UUID) -> PaymentOccurrence | None:
    stmt = select(PaymentOccurrence).where(PaymentOccurrence.id == occurrence_id)
    return db.scalars(stmt).one_or_none()


def telegram_payer(db: Session) -> User | None:
    """Кнопка общего чата. Не веб-пользователь, а активный админ из ADMIN_EMAIL."""
    email = get_settings().admin_email.strip().lower()
    if not email:
        return None
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not user.is_active or user.role != "admin":
        return None
    return user


def _edit_is_gone(description: str) -> bool:
    text = description.lower()
    return "message to edit not found" in text or "message_id_invalid" in text or "message can't be edited" in text


def _edit_not_modified(description: str) -> bool:
    return "message is not modified" in description.lower()


def _store_fingerprint(db: Session, occurrence_id: uuid.UUID, fingerprint_value: str) -> None:
    _exec(
        db,
        update(PaymentOccurrence)
        .where(PaymentOccurrence.id == occurrence_id)
        .values(telegram_fingerprint=fingerprint_value),
    )
    db.commit()


def _drop_message(db: Session, occurrence_id: uuid.UUID) -> None:
    # Сообщение в чате уже не отредактировать. Повторно не шлём: строка канала остаётся.
    _exec(
        db,
        update(PaymentOccurrence)
        .where(PaymentOccurrence.id == occurrence_id)
        .values(telegram_message_id=None, telegram_chat_id=None),
    )
    db.commit()


def sync_telegram_cards(db: Session, bot: BotSender) -> int:
    """Правит уже отправленные карточки. Новых сообщений не создаёт."""
    edited = 0
    for row in _load_sent(db):
        if row.telegram_message_id is None or not row.telegram_chat_id:
            continue
        text = telegram_text(row)
        with_button = row.paid_at is None
        current = fingerprint(text, with_button)
        if row.telegram_fingerprint == current:
            continue
        markup = pay_keyboard(row.id) if with_button else EMPTY_KEYBOARD
        try:
            bot.edit_message(row.telegram_chat_id, int(row.telegram_message_id), text, markup)
        except TelegramError as exc:
            if _edit_not_modified(exc.description):
                _store_fingerprint(db, row.id, current)
                continue
            if _edit_is_gone(exc.description):
                log.warning("telegram message gone occurrence=%s; delivery row stays", row.id)
                _drop_message(db, row.id)
                continue
            log.warning("edit failed occurrence=%s (%s)", row.id, exc.description)
            continue
        _store_fingerprint(db, row.id, current)
        edited += 1
    return edited


def handle_update(db: Session, bot: BotSender, update: dict[str, Any], *, expected_chat_id: str) -> None:
    callback = update.get("callback_query")
    if not isinstance(callback, dict):
        return
    handle_callback(db, bot, callback, expected_chat_id=expected_chat_id)


def handle_callback(db: Session, bot: BotSender, callback: dict[str, Any], *, expected_chat_id: str) -> None:
    callback_id = str(callback.get("id") or "")
    try:
        toast = _apply_callback(db, bot, callback, expected_chat_id=expected_chat_id.strip())
    except Exception:
        db.rollback()
        log.exception("telegram callback failed")
        toast = "Не получилось"
    if not callback_id:
        return
    try:
        bot.answer_callback(callback_id, toast)
    except TelegramError as exc:
        log.warning("answerCallbackQuery failed (%s)", exc.description)


def _apply_callback(db: Session, bot: BotSender, callback: dict[str, Any], *, expected_chat_id: str) -> str:
    message = callback.get("message") if isinstance(callback.get("message"), dict) else {}
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    if not expected_chat_id:
        return "Чат не настроен"
    if chat_id is None or str(chat_id) != expected_chat_id:
        return "Чат не подключён к инбоксу"

    occurrence_id = parse_paid_callback(str(callback.get("data") or ""))
    if occurrence_id is None:
        return "Некорректная кнопка"
    row = _load_one(db, occurrence_id)
    if row is None:
        return "Период не найден"

    if row.paid_at is None:
        _mark_paid(db, row)
        toast = "Оплачено"
    else:
        toast = "Уже оплачено"

    if message_id is None:
        return toast
    text = telegram_text(row)
    with_button = row.paid_at is None
    markup = pay_keyboard(row.id) if with_button else EMPTY_KEYBOARD
    current = fingerprint(text, with_button)
    try:
        bot.edit_message(str(chat_id), int(message_id), text, markup)
    except TelegramError as exc:
        if not _edit_not_modified(exc.description):
            log.warning("callback edit failed occurrence=%s (%s)", row.id, exc.description)
            return toast
    row.telegram_chat_id = str(chat_id)
    row.telegram_message_id = int(message_id)
    row.telegram_fingerprint = current
    if row.telegram_reminded_at is None:
        row.telegram_reminded_at = clock.now()
    db.commit()
    return toast


def _mark_paid(db: Session, row: PaymentOccurrence) -> None:
    from app.services.audit import record
    from app.services.notify import PAID, notify_event

    payer = telegram_payer(db)
    paid_at = clock.now()
    row.paid_at = paid_at
    row.paid_by_id = payer.id if payer is not None else None
    touch(row)
    record(
        db,
        action="occurrence.paid",
        actor=payer,
        entity_type="payment_occurrence",
        entity_id=row.id,
        meta={"paid_on": paid_at.astimezone(get_settings().zone).date().isoformat(), "title": row.title},
    )
    notify_event(db, row, PAID)
    db.commit()

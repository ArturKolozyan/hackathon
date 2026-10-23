"""Напоминания в общий чат. Один успешный send на период.

Окно — то же, что «скоро» и «просрочено» в инбоксе: до срока ≤ SOON_DAYS
или срок уже прошёл. Оплаченный и архивный шаблон новых сообщений не рождают.
Дальше правим то же сообщение (оплата с веба, возврат в инбокс, смена статуса).
Это не второй send.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import date
from typing import Any, Protocol

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.integrations.telegram import TelegramError
from app.models import PaymentOccurrence, RecurringPayment, User
from app.services import time as clock
from app.services.schedule import classify
from app.services.templates import touch

log = logging.getLogger("invoice_keeper.telegram")

PAID_PREFIX = "paid:"
EMPTY_KEYBOARD: dict[str, Any] = {"inline_keyboard": []}
_STATUS_RU = {
    "overdue": "просрочено",
    "due_soon": "скоро",
    "upcoming": "ожидается",
    "paid": "оплачено",
}


class BotSender(Protocol):
    def send_message(self, chat_id: str, text: str, reply_markup: dict[str, Any]) -> int: ...

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


def _fingerprint(text: str, with_button: bool) -> str:
    marker = "btn" if with_button else "plain"
    return hashlib.sha256(f"{text}\n{marker}".encode()).hexdigest()[:32]


def render_card(occurrence: PaymentOccurrence, today: date) -> tuple[str, bool]:
    settings = get_settings()
    status = classify(occurrence.due_date, occurrence.paid_at, today, settings.soon_days)
    paid_line = None
    if occurrence.paid_at is not None:
        paid_on = occurrence.paid_at.astimezone(settings.zone).date()
        paid_line = f"Оплачено: {paid_on.strftime('%d.%m.%Y')}"
    lines = [
        occurrence.title,
        f"{occurrence.amount:.2f} {occurrence.currency}",
        f"Срок: {occurrence.due_date.strftime('%d.%m.%Y')}",
        f"Статус: {_STATUS_RU[status]}",
    ]
    if paid_line is not None:
        lines.append(paid_line)
    return "\n".join(lines), occurrence.paid_at is None


def _in_window(occurrence: PaymentOccurrence, today: date) -> bool:
    if occurrence.paid_at is not None or occurrence.template.is_archived:
        return False
    status = classify(occurrence.due_date, None, today, get_settings().soon_days)
    return status in {"overdue", "due_soon"}


def _load_open(db: Session) -> list[PaymentOccurrence]:
    stmt = (
        select(PaymentOccurrence)
        .join(PaymentOccurrence.template)
        .where(
            PaymentOccurrence.paid_at.is_(None),
            PaymentOccurrence.reminded_at.is_(None),
            RecurringPayment.is_archived.is_(False),
        )
        .options(joinedload(PaymentOccurrence.template))
        .order_by(PaymentOccurrence.due_date, PaymentOccurrence.title, PaymentOccurrence.id)
    )
    return list(db.scalars(stmt).unique().all())


def _load_sent(db: Session) -> list[PaymentOccurrence]:
    stmt = (
        select(PaymentOccurrence)
        .where(PaymentOccurrence.telegram_message_id.is_not(None))
        .options(joinedload(PaymentOccurrence.template))
        .order_by(PaymentOccurrence.due_date, PaymentOccurrence.id)
    )
    return list(db.scalars(stmt).unique().all())


def _load_one(db: Session, occurrence_id: uuid.UUID) -> PaymentOccurrence | None:
    stmt = (
        select(PaymentOccurrence)
        .where(PaymentOccurrence.id == occurrence_id)
        .options(joinedload(PaymentOccurrence.template))
    )
    return db.scalars(stmt).unique().one_or_none()


def _exec(db: Session, stmt):
    # Core UPDATE не должен затирать поля в identity map и потом flush-ем вернуть NULL.
    return db.execute(stmt, execution_options={"synchronize_session": False})


def _claim(db: Session, occurrence_id: uuid.UUID) -> bool:
    # Коммит до send: второй процесс не отправит дубль. Неуспех send снимает claim.
    claimed = _exec(
        db,
        update(PaymentOccurrence)
        .where(
            PaymentOccurrence.id == occurrence_id,
            PaymentOccurrence.reminded_at.is_(None),
            PaymentOccurrence.paid_at.is_(None),
        )
        .values(reminded_at=clock.now())
        .returning(PaymentOccurrence.id),
    ).first()
    db.commit()
    return claimed is not None


def _release_claim(db: Session, occurrence_id: uuid.UUID) -> None:
    _exec(
        db,
        update(PaymentOccurrence)
        .where(
            PaymentOccurrence.id == occurrence_id,
            PaymentOccurrence.telegram_message_id.is_(None),
        )
        .values(reminded_at=None),
    )
    db.commit()


def _store_delivery(
    db: Session,
    occurrence_id: uuid.UUID,
    *,
    chat_id: str,
    message_id: int,
    fingerprint: str,
) -> None:
    _exec(
        db,
        update(PaymentOccurrence)
        .where(PaymentOccurrence.id == occurrence_id)
        .values(
            reminded_at=clock.now(),
            telegram_chat_id=str(chat_id),
            telegram_message_id=message_id,
            telegram_fingerprint=fingerprint,
        ),
    )
    db.commit()


def _store_fingerprint(db: Session, occurrence_id: uuid.UUID, fingerprint: str) -> None:
    _exec(
        db,
        update(PaymentOccurrence)
        .where(PaymentOccurrence.id == occurrence_id)
        .values(telegram_fingerprint=fingerprint),
    )
    db.commit()


def _drop_message(db: Session, occurrence_id: uuid.UUID) -> None:
    # Сообщение в чате уже не отредактировать. Новый send не делаем: reminded_at остаётся.
    _exec(
        db,
        update(PaymentOccurrence)
        .where(PaymentOccurrence.id == occurrence_id)
        .values(telegram_message_id=None, telegram_chat_id=None),
    )
    db.commit()


def telegram_payer(db: Session) -> User | None:
    """Кнопка общего чата. Не веб-пользователь, а активный админ из ADMIN_EMAIL."""
    email = get_settings().admin_email.strip().lower()
    if not email:
        return None
    user = db.scalar(select(User).where(func.lower(User.email) == email))
    if user is None or not user.is_active or user.role != "admin":
        return None
    return user


def send_due_reminders(db: Session, bot: BotSender, chat_id: str) -> int:
    db.expire_all()
    today = clock.today()
    sent = 0
    for row in _load_open(db):
        if not _in_window(row, today):
            continue
        if not _claim(db, row.id):
            continue
        text, with_button = render_card(row, today)
        markup = pay_keyboard(row.id) if with_button else EMPTY_KEYBOARD
        try:
            message_id = bot.send_message(chat_id, text, markup)
        except TelegramError as exc:
            log.warning(
                "remind failed occurrence=%s method=%s (%s); will retry. a lost response can duplicate",
                row.id,
                exc.method,
                exc.description,
            )
            _release_claim(db, row.id)
            continue
        _store_delivery(
            db,
            row.id,
            chat_id=chat_id,
            message_id=message_id,
            fingerprint=_fingerprint(text, with_button),
        )
        log.info("reminded occurrence=%s message_id=%s", row.id, message_id)
        sent += 1
    return sent


def _edit_is_gone(description: str) -> bool:
    text = description.lower()
    return "message to edit not found" in text or "message_id_invalid" in text or "message can't be edited" in text


def _edit_not_modified(description: str) -> bool:
    return "message is not modified" in description.lower()


def sync_rendered_messages(db: Session, bot: BotSender) -> int:
    db.expire_all()
    today = clock.today()
    edited = 0
    for row in _load_sent(db):
        if row.telegram_message_id is None or not row.telegram_chat_id:
            continue
        text, with_button = render_card(row, today)
        fingerprint = _fingerprint(text, with_button)
        if row.telegram_fingerprint == fingerprint:
            continue
        markup = pay_keyboard(row.id) if with_button else EMPTY_KEYBOARD
        try:
            bot.edit_message(row.telegram_chat_id, int(row.telegram_message_id), text, markup)
        except TelegramError as exc:
            if _edit_not_modified(exc.description):
                _store_fingerprint(db, row.id, fingerprint)
                continue
            if _edit_is_gone(exc.description):
                log.warning("telegram message gone occurrence=%s; keep reminded_at", row.id)
                _drop_message(db, row.id)
                continue
            log.warning("edit failed occurrence=%s (%s)", row.id, exc.description)
            continue
        _store_fingerprint(db, row.id, fingerprint)
        edited += 1
    return edited


def _remember_callback_message(
    db: Session,
    row: PaymentOccurrence,
    *,
    chat_id: str,
    message_id: int,
    fingerprint: str,
) -> None:
    row.telegram_chat_id = chat_id
    row.telegram_message_id = message_id
    row.telegram_fingerprint = fingerprint
    if row.reminded_at is None:
        row.reminded_at = clock.now()
    db.commit()


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
    db.expire_all()
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
        payer = telegram_payer(db)
        row.paid_at = clock.now()
        row.paid_by_id = payer.id if payer is not None else None
        touch(row)
        db.commit()
        toast = "Оплачено"
    else:
        toast = "Уже оплачено"

    if message_id is None:
        return toast
    today = clock.today()
    text, with_button = render_card(row, today)
    markup = pay_keyboard(row.id) if with_button else EMPTY_KEYBOARD
    fingerprint = _fingerprint(text, with_button)
    try:
        bot.edit_message(str(chat_id), int(message_id), text, markup)
    except TelegramError as exc:
        if not _edit_not_modified(exc.description):
            log.warning("callback edit failed occurrence=%s (%s)", row.id, exc.description)
            return toast
    _remember_callback_message(
        db,
        row,
        chat_id=str(chat_id),
        message_id=int(message_id),
        fingerprint=fingerprint,
    )
    return toast


def handle_update(db: Session, bot: BotSender, update: dict[str, Any], *, expected_chat_id: str) -> None:
    callback = update.get("callback_query")
    if not isinstance(callback, dict):
        return
    handle_callback(db, bot, callback, expected_chat_id=expected_chat_id)

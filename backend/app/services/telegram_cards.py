"""Карточка периода в Telegram: текст, правка того же сообщения, кнопка «Оплачено».

Новое напоминание отсюда не выбирается. Его шлёт notify через deliver().
Правка сообщения — не вторая отправка и не новая строка notification_deliveries.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any, Protocol

from sqlalchemy import or_, select, update
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

    def answer_callback(self, callback_query_id: str, text: str, *, show_alert: bool = False) -> None: ...


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


def _payer_name(occurrence: PaymentOccurrence) -> str | None:
    if occurrence.paid_by_id is None:
        return None
    payer = occurrence.payer
    if payer is None:
        return None
    name = payer.full_name.strip()
    return name or None


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
        stamp = paid_on.strftime("%d.%m.%Y")
        who = _payer_name(occurrence)
        if who:
            lines.append(f"✅ Оплачено — {who}, {stamp}")
        else:
            lines.append(f"Оплачено: {stamp}")
    return "\n".join(lines)


def _exec(db: Session, stmt):
    return db.execute(stmt, execution_options={"synchronize_session": False})


def _load_sent(db: Session) -> list[PaymentOccurrence]:
    stmt = (
        select(PaymentOccurrence)
        .where(
            or_(
                PaymentOccurrence.telegram_message_id.is_not(None),
                PaymentOccurrence.dm_message_id.is_not(None),
            )
        )
        .execution_options(populate_existing=True)
        .order_by(PaymentOccurrence.due_date, PaymentOccurrence.id)
    )
    return list(db.scalars(stmt).all())


def _load_one(db: Session, occurrence_id: uuid.UUID) -> PaymentOccurrence | None:
    stmt = select(PaymentOccurrence).where(PaymentOccurrence.id == occurrence_id)
    return db.scalars(stmt).one_or_none()


def _edit_is_gone(description: str) -> bool:
    text = description.lower()
    return "message to edit not found" in text or "message_id_invalid" in text or "message can't be edited" in text


def _edit_not_modified(description: str) -> bool:
    return "message is not modified" in description.lower()


def _drop_slot(db: Session, occurrence_id: uuid.UUID, slot: str) -> None:
    # Сообщение уже не отредактировать. Повторно не шлём: строка канала остаётся.
    if slot == "dm":
        values = {"dm_message_id": None, "dm_chat_id": None, "dm_fingerprint": None}
    else:
        values = {"telegram_message_id": None, "telegram_chat_id": None, "telegram_fingerprint": None}
    _exec(db, update(PaymentOccurrence).where(PaymentOccurrence.id == occurrence_id).values(**values))
    db.commit()


def _store_slot_fingerprint(db: Session, occurrence_id: uuid.UUID, slot: str, fingerprint_value: str) -> None:
    column = "dm_fingerprint" if slot == "dm" else "telegram_fingerprint"
    _exec(
        db,
        update(PaymentOccurrence).where(PaymentOccurrence.id == occurrence_id).values(**{column: fingerprint_value}),
    )
    db.commit()


def _slots(row: PaymentOccurrence) -> list[tuple[str, str, int, str | None]]:
    found: list[tuple[str, str, int, str | None]] = []
    if row.telegram_message_id is not None and row.telegram_chat_id:
        found.append(("team", row.telegram_chat_id, int(row.telegram_message_id), row.telegram_fingerprint))
    if row.dm_message_id is not None and row.dm_chat_id:
        found.append(("dm", row.dm_chat_id, int(row.dm_message_id), row.dm_fingerprint))
    return found


def sync_telegram_cards(db: Session, bot: BotSender) -> int:
    """Правит уже отправленные карточки команды и лички. Новых сообщений не создаёт."""
    edited = 0
    for row in _load_sent(db):
        text = telegram_text(row)
        with_button = row.paid_at is None
        current = fingerprint(text, with_button)
        markup = pay_keyboard(row.id) if with_button else EMPTY_KEYBOARD
        for slot, chat_id, message_id, stored in _slots(row):
            if stored == current:
                continue
            try:
                bot.edit_message(chat_id, message_id, text, markup)
            except TelegramError as exc:
                if _edit_not_modified(exc.description):
                    _store_slot_fingerprint(db, row.id, slot, current)
                    continue
                if _edit_is_gone(exc.description):
                    log.warning("telegram message gone occurrence=%s slot=%s; delivery row stays", row.id, slot)
                    _drop_slot(db, row.id, slot)
                    continue
                log.warning("edit failed occurrence=%s slot=%s (%s)", row.id, slot, exc.description)
                continue
            _store_slot_fingerprint(db, row.id, slot, current)
            edited += 1
    return edited


def handle_callback(db: Session, bot: BotSender, callback: dict[str, Any]) -> None:
    callback_id = str(callback.get("id") or "")
    try:
        toast, alert = _apply_callback(db, bot, callback)
    except Exception:
        db.rollback()
        log.exception("telegram callback failed")
        toast, alert = "Не получилось", True
    if not callback_id:
        return
    try:
        bot.answer_callback(callback_id, toast, show_alert=alert)
    except TelegramError as exc:
        log.warning("answerCallbackQuery failed (%s)", exc.description)


def _apply_callback(db: Session, bot: BotSender, callback: dict[str, Any]) -> tuple[str, bool]:
    from app.services.telegram_links import UNLINKED_ALERT, is_private_chat, resolve_team_chat_id

    message = callback.get("message") if isinstance(callback.get("message"), dict) else {}
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    chat_id = chat.get("id")
    message_id = message.get("message_id")
    private = is_private_chat(chat)
    if chat_id is None:
        return "Чат не подключён к инбоксу", True
    occurrence_id = parse_paid_callback(str(callback.get("data") or ""))
    if occurrence_id is None:
        return "Некорректная кнопка", True
    row = _load_one(db, occurrence_id)
    if row is None:
        return "Период не найден", True
    if not private:
        team_chat, _source = resolve_team_chat_id(db, row.team_id)
        if not team_chat:
            return "Чат не настроен", True
        if str(chat_id) != team_chat:
            return "Чат не подключён к инбоксу", True

    sender = callback.get("from") if isinstance(callback.get("from"), dict) else {}
    payer = _linked_sender(db, sender)
    if payer is None:
        return UNLINKED_ALERT, True

    if row.paid_at is None:
        _mark_paid(db, row, payer)
        toast, alert = "Оплачено", False
    else:
        who = _payer_name(row) or "ранее"
        toast, alert = f"Уже оплачено — {who}", True

    if message_id is None:
        return toast, alert
    _edit_known(db, bot, row, clicked_chat=str(chat_id), clicked_message=int(message_id), private=private)
    return toast, alert


def _linked_sender(db: Session, sender: dict[str, Any]) -> User | None:
    try:
        tg_id = int(sender.get("id"))
    except (TypeError, ValueError):
        return None
    user = db.scalar(select(User).where(User.telegram_user_id == tg_id))
    if user is None or not user.is_active:
        return None
    return user


def _assign_slot(row: PaymentOccurrence, slot: str, chat_id: str, message_id: int, fingerprint_value: str) -> None:
    if slot == "dm":
        row.dm_chat_id = chat_id
        row.dm_message_id = message_id
        row.dm_fingerprint = fingerprint_value
        return
    row.telegram_chat_id = chat_id
    row.telegram_message_id = message_id
    row.telegram_fingerprint = fingerprint_value
    if row.telegram_reminded_at is None:
        row.telegram_reminded_at = clock.now()


def _edit_known(
    db: Session,
    bot: BotSender,
    row: PaymentOccurrence,
    *,
    clicked_chat: str,
    clicked_message: int,
    private: bool,
) -> None:
    text = telegram_text(row)
    with_button = row.paid_at is None
    markup = pay_keyboard(row.id) if with_button else EMPTY_KEYBOARD
    current = fingerprint(text, with_button)
    clicked_slot = "dm" if private else "team"
    targets: list[tuple[str, str, int]] = [(clicked_slot, clicked_chat, clicked_message)]
    for slot, chat_id, message_id, _stored in _slots(row):
        if slot == clicked_slot:
            continue
        if chat_id == clicked_chat and message_id == clicked_message:
            continue
        targets.append((slot, chat_id, message_id))
    for slot, chat_id, message_id in targets:
        try:
            bot.edit_message(chat_id, message_id, text, markup)
        except TelegramError as exc:
            if not _edit_not_modified(exc.description):
                log.warning("callback edit failed occurrence=%s slot=%s (%s)", row.id, slot, exc.description)
                continue
        _assign_slot(row, slot, chat_id, message_id, current)
        if row.telegram_reminded_at is None:
            row.telegram_reminded_at = clock.now()
    db.commit()


def _mark_paid(db: Session, row: PaymentOccurrence, payer: User) -> None:
    from app.services.audit import record
    from app.services.notify import PAID, notify_event

    paid_at = clock.now()
    row.paid_at = paid_at
    row.paid_by_id = payer.id
    row.payer = payer
    touch(row)
    record(
        db,
        action="occurrence.paid",
        actor=payer,
        entity_type="payment_occurrence",
        entity_id=row.id,
        meta={
            "paid_on": paid_at.astimezone(get_settings().zone).date().isoformat(),
            "title": row.title,
            "source": "telegram",
        },
        team_id=row.team_id,
    )
    notify_event(db, row, PAID)
    db.commit()

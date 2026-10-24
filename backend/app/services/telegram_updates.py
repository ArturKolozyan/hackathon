"""Разбор апдейта long polling: /start, миграция чата, выход бота, кнопка, ответ на прочий текст."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.integrations.telegram import TelegramError

from app.services.telegram_cards import handle_callback
from app.services.telegram_links import (
    OLD_ASSISTANT_BUTTON,
    handle_membership,
    handle_start,
    is_private_chat,
    migrate_chat,
    reply_private,
    start_payload,
)


def handle_update(db: Session, bot: Any, update: dict[str, Any]) -> None:
    message = update.get("message")
    if isinstance(message, dict):
        if message.get("migrate_to_chat_id") is not None:
            migrate_chat(db, message)
            return
        if start_payload(message.get("text")) is not None:
            handle_start(db, bot, message)
            return
        chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        if is_private_chat(chat):
            reply_private(bot, message)
        return
    member = update.get("my_chat_member")
    if isinstance(member, dict):
        handle_membership(db, member)
        return
    callback = update.get("callback_query")
    if isinstance(callback, dict):
        data = callback.get("data")
        if isinstance(data, str) and data.startswith("asst:"):
            # Кнопки старых карточек ассистента: Кип теперь только в веб-версии.
            _answer(bot, callback, OLD_ASSISTANT_BUTTON)
            return
        handle_callback(db, bot, callback)


def _answer(bot: Any, callback: dict[str, Any], text: str) -> None:
    callback_id = str(callback.get("id") or "")
    if not callback_id:
        return
    try:
        bot.answer_callback(callback_id, text, show_alert=True)
    except TelegramError:
        pass

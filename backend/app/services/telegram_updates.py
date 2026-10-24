"""Разбор апдейта long polling: /start, миграция чата, выход бота, кнопка."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.assistant.telegram_bridge import handle_assistant_callback, handle_private_message
from app.services.telegram_cards import handle_callback
from app.services.telegram_links import handle_membership, handle_start, is_private_chat, migrate_chat, start_payload


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
            handle_private_message(db, bot, message)
        return
    member = update.get("my_chat_member")
    if isinstance(member, dict):
        handle_membership(db, member)
        return
    callback = update.get("callback_query")
    if isinstance(callback, dict):
        data = callback.get("data")
        if isinstance(data, str) and data.startswith("asst:"):
            handle_assistant_callback(db, bot, callback)
            return
        handle_callback(db, bot, callback)

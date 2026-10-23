"""Разбор апдейта long polling: /start, миграция чата, выход бота, кнопка."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.services.telegram_cards import handle_callback
from app.services.telegram_links import handle_membership, handle_start, migrate_chat


def handle_update(db: Session, bot: Any, update: dict[str, Any]) -> None:
    message = update.get("message")
    if isinstance(message, dict):
        if message.get("migrate_to_chat_id") is not None:
            migrate_chat(db, message)
            return
        handle_start(db, bot, message)
        return
    member = update.get("my_chat_member")
    if isinstance(member, dict):
        handle_membership(db, member)
        return
    callback = update.get("callback_query")
    if isinstance(callback, dict):
        handle_callback(db, bot, callback)

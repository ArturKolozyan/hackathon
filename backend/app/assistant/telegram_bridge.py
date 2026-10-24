"""Личный чат бота: тот же ассистент, что и веб. Голосовые Telegram уже OGG Opus."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from fastapi import HTTPException

from app.assistant.actions import load_for_user, perform
from app.assistant.chat import remember_telegram, run_turn
from app.assistant.speech import SpeechError, recognize
from app.core.config import get_settings
from app.core.security import issue_session
from app.integrations.telegram import TelegramError
from app.models import User
from app.schemas.assistant import MessageOut
from app.services.access import resolve_team
from app.services.telegram_links import UNLINKED_ALERT

log = logging.getLogger("invoice_keeper.assistant")

EMPTY: dict[str, Any] = {"inline_keyboard": []}
LINK_HINT = "Привязка в rekeeper: Настройки → Привязать Telegram."
VOICE_LONG = "Голосовое длиннее 30 секунд. Скажи короче или напиши текстом."
VOICE_BIG = "Голосовое больше 1 МБ. Скажи короче или напиши текстом."
EDIT_HINT = "Напиши, что поменять: сумму, день, название или ответственного. Карточка ждёт подтверждения."
COMMAND_HINT = "Напиши обычной фразой. Например: что горит на этой неделе?"
NO_TEAM = "Сначала создайте отдел в rekeeper."
UNAVAILABLE = "Ассистент временно недоступен"
OFF = "Это бот напоминаний. Ассистент на этом сервере не включён."


def assistant_keyboard(action_id: uuid.UUID) -> dict[str, Any]:
    token = str(action_id)
    return {
        "inline_keyboard": [[
            {"text": "Подтвердить", "callback_data": f"asst:ok:{token}"},
            {"text": "Изменить", "callback_data": f"asst:ed:{token}"},
        ]]
    }


def parse_callback(data: str) -> tuple[str, uuid.UUID] | None:
    if not data.startswith("asst:"):
        return None
    parts = data.split(":", 2)
    if len(parts) != 3 or parts[1] not in {"ok", "ed"}:
        return None
    try:
        return parts[1], uuid.UUID(parts[2])
    except ValueError:
        return None


def _linked_user(db: Session, sender: dict[str, Any]) -> User | None:
    try:
        tg_id = int(sender.get("id"))
    except (TypeError, ValueError):
        return None
    return db.scalar(select(User).where(User.telegram_user_id == tg_id, User.is_active.is_(True)))


def _send(bot: Any, chat_id: str, text: str, markup: dict[str, Any]) -> int | None:
    try:
        return int(bot.send_message(chat_id, text[:4000], markup))
    except TelegramError as exc:
        log.warning("assistant reply failed (%s)", exc.description)
        return None


def _context(db: Session, user: User, team_id: uuid.UUID | None = None):
    try:
        return resolve_team(db, user, team_id)
    except HTTPException:
        return None


def handle_private_message(db: Session, bot: Any, message: dict[str, Any]) -> None:
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    chat_id = chat.get("id")
    if chat_id is None:
        return
    sender = message.get("from") if isinstance(message.get("from"), dict) else {}
    user = _linked_user(db, sender)
    if user is None:
        _send(bot, str(chat_id), LINK_HINT, EMPTY)
        return
    ctx = _context(db, user)
    if ctx is None:
        _send(bot, str(chat_id), NO_TEAM, EMPTY)
        return
    voice = message.get("voice") if isinstance(message.get("voice"), dict) else None
    text = message.get("text") if isinstance(message.get("text"), str) else ""
    if voice is not None:
        heard, error = _transcribe(db, user, bot, voice)
        if error:
            _send(bot, str(chat_id), error, EMPTY)
            return
        text = heard or ""
    stripped = text.strip()
    if not stripped:
        return
    if stripped.startswith("/"):
        _send(bot, str(chat_id), COMMAND_HINT, EMPTY)
        return
    settings = get_settings()
    if not settings.assistant_configured:
        _send(bot, str(chat_id), OFF, EMPTY)
        return
    if settings.assistant_url.strip():
        reply = _remote_turn(db, user, stripped, settings.assistant_url.strip())
        if reply is None:
            _send(bot, str(chat_id), UNAVAILABLE, EMPTY)
            return
    else:
        try:
            reply = run_turn(db, ctx, stripped)
        except Exception:
            log.exception("assistant turn failed")
            _send(bot, str(chat_id), UNAVAILABLE, EMPTY)
            return
    markup = EMPTY
    if reply.action is not None and reply.action.status == "pending":
        markup = assistant_keyboard(reply.action.id)
    message_id = _send(bot, str(chat_id), reply.content, markup)
    if message_id is not None and reply.action is not None and reply.action.status == "pending":
        remember_telegram(db, reply.action.id, str(chat_id), message_id)


def _remote_turn(db: Session, user: User, text: str, url: str) -> MessageOut | None:
    import httpx

    token = issue_session(db, user)
    db.commit()
    try:
        response = httpx.post(
            f"{url.rstrip('/')}/api/v1/assistant/messages",
            params={"stream": "false"},
            json={"text": text},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10.0,
        )
        response.raise_for_status()
        return MessageOut.model_validate(response.json())
    except Exception:
        log.warning("assistant http failed")
        return None


def _transcribe(db: Session, user: User, bot: Any, voice: dict[str, Any]) -> tuple[str, str | None]:
    duration = voice.get("duration")
    if isinstance(duration, int) and duration > 30:
        return "", VOICE_LONG
    size = voice.get("file_size")
    if isinstance(size, int) and size > 1_000_000:
        return "", VOICE_BIG
    file_id = voice.get("file_id")
    if not isinstance(file_id, str) or not file_id:
        return "", "Не получилось скачать голосовое. Напиши текстом."
    try:
        audio = bot.download_voice(file_id)
    except TelegramError:
        return "", "Не получилось скачать голосовое. Напиши текстом."
    settings = get_settings()
    url = settings.assistant_url.strip()
    if url:
        heard = _remote_speech(db, user, audio, url)
        if heard is None:
            return "", UNAVAILABLE
        return heard, None
    try:
        return recognize(audio, "audio/ogg"), None
    except SpeechError as exc:
        return "", exc.detail
    except Exception:
        log.exception("telegram voice failed")
        return "", "Не получилось распознать голосовое. Напиши текстом."


def _remote_speech(db: Session, user: User, audio: bytes, url: str) -> str | None:
    """ffmpeg живёт в контейнере assistant. Бот только отдаёт уже ogg и сессию пользователя."""
    import httpx

    token = issue_session(db, user)
    db.commit()
    try:
        response = httpx.post(
            f"{url.rstrip('/')}/api/v1/assistant/speech",
            files={"file": ("voice.ogg", audio, "audio/ogg")},
            headers={"Authorization": f"Bearer {token}"},
            timeout=15.0,
        )
        if response.status_code >= 400:
            log.warning("assistant speech http %s", response.status_code)
            return None
        text = response.json().get("text")
        if not isinstance(text, str) or not text.strip():
            return None
        return text.strip()
    except Exception:
        log.warning("assistant speech unreachable")
        return None


def handle_assistant_callback(db: Session, bot: Any, callback: dict[str, Any]) -> None:
    callback_id = str(callback.get("id") or "")
    data = str(callback.get("data") or "")
    parsed = parse_callback(data)
    sender = callback.get("from") if isinstance(callback.get("from"), dict) else {}
    message = callback.get("message") if isinstance(callback.get("message"), dict) else {}
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    chat_id = chat.get("id")

    def answer(text: str, *, alert: bool = False) -> None:
        if not callback_id:
            return
        try:
            bot.answer_callback(callback_id, text, show_alert=alert)
        except TelegramError as exc:
            log.warning("assistant callback answer failed (%s)", exc.description)

    if parsed is None:
        answer("Не понял кнопку")
        return
    user = _linked_user(db, sender)
    if user is None:
        answer(UNLINKED_ALERT, alert=True)
        return
    kind, action_id = parsed
    try:
        action = load_for_user(db, user, action_id)
    except Exception:
        answer("Карточка не найдена", alert=True)
        return
    ctx = _context(db, user, action.team_id)
    if ctx is None:
        answer("Вы не в этом отделе", alert=True)
        return
    if kind == "ed":
        answer("Жду правку")
        if chat_id is not None:
            _send(bot, str(chat_id), EDIT_HINT, EMPTY)
        return
    try:
        reply = perform(db, ctx, action)
    except Exception as exc:
        detail = getattr(exc, "detail", None)
        answer(str(detail or "Не получилось"), alert=True)
        return
    answer("Готово" if action.status == "confirmed" else "Не записалось", alert=action.status != "confirmed")
    if chat_id is None:
        return
    message_id = message.get("message_id")
    try:
        if message_id is not None:
            bot.edit_message(str(chat_id), int(message_id), reply.content[:4000], EMPTY)
            return
    except TelegramError as exc:
        log.warning("assistant card edit failed (%s)", exc.description)
    _send(bot, str(chat_id), reply.content, EMPTY)

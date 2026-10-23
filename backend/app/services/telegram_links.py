"""Привязка чата команды и личного Telegram. Deep link собирает API, бот живёт в worker.

Токен одноразовый, 15 минут. Сырой токен в журнал не пишем.
TELEGRAM_CHAT_ID — запасной чат, только пока в базе нет явного состояния.
«Отключить» ставит disconnected и глушит env, иначе кнопка ничего не выключает.
"""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.integrations.telegram import TelegramError
from app.models import PaymentOccurrence, TelegramIntegration, TelegramLinkToken, User
from app.services import time as clock
from app.services.audit import record

log = logging.getLogger("invoice_keeper.telegram")

TOKEN_TTL = timedelta(minutes=15)
INTEGRATION_ID = 1
TEAM_RECIPIENT = "team"
UNLINKED_ALERT = "Сначала привяжи Telegram в профиле rekeeper"
_GONE = ("left", "kicked")


def integration_row(db: Session, *, create: bool = False) -> TelegramIntegration | None:
    row = db.get(TelegramIntegration, INTEGRATION_ID)
    if row is None and create:
        row = TelegramIntegration(id=INTEGRATION_ID, team_status="absent")
        db.add(row)
        db.flush()
    return row


def resolve_team_chat_id(db: Session) -> tuple[str | None, str]:
    """Куда слать карточку команды: (chat_id, source).

    source: database | env | none.
    disconnected не падает обратно в env.
    """
    row = integration_row(db)
    if row is not None and row.team_status == "connected" and row.team_chat_id:
        return row.team_chat_id, "database"
    if row is not None and row.team_status == "disconnected":
        return None, "none"
    env_chat = get_settings().telegram_chat_id.strip()
    if env_chat:
        return env_chat, "env"
    return None, "none"


def bot_username(db: Session) -> str | None:
    row = integration_row(db)
    if row is None or not row.bot_username:
        return None
    return row.bot_username.strip().lstrip("@") or None


def remember_bot(me: dict[str, Any]) -> None:
    username = str(me.get("username") or "").strip().lstrip("@")
    if not username:
        return
    db = SessionLocal()
    try:
        row = integration_row(db, create=True)
        assert row is not None
        row.bot_username = username[:64]
        raw_id = me.get("id")
        if raw_id is not None:
            row.bot_user_id = int(raw_id)
        row.updated_at = clock.now()
        db.commit()
    except Exception:
        db.rollback()
        log.exception("bot username was not cached")
    finally:
        db.close()


def issue_token(db: Session, *, purpose: str, user: User) -> TelegramLinkToken:
    row = TelegramLinkToken(
        token=secrets.token_urlsafe(24),
        purpose=purpose,
        user_id=user.id,
        expires_at=clock.now() + TOKEN_TTL,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def deep_link(username: str, token: str, *, group: bool) -> str:
    key = "startgroup" if group else "start"
    return f"https://t.me/{username}?{key}={token}"


def disconnect_team(db: Session, *, actor: User | None) -> TelegramIntegration:
    row = integration_row(db, create=True)
    assert row is not None
    title = row.team_chat_title
    row.team_status = "disconnected"
    row.team_chat_id = None
    row.team_chat_title = None
    row.team_chat_type = None
    row.team_disconnected_at = clock.now()
    row.updated_at = clock.now()
    record(
        db,
        action="telegram.team_disconnect",
        actor=actor,
        entity_type="telegram",
        meta={"title": title} if title else {},
    )
    db.commit()
    db.refresh(row)
    return row


def unlink_user(db: Session, user: User) -> None:
    user.telegram_user_id = None
    user.telegram_username = None
    user.telegram_display_name = None
    user.updated_at = clock.now()
    record(
        db,
        action="telegram.user_unlink",
        actor=user,
        entity_type="user",
        entity_id=user.id,
        meta={"email": user.email},
    )
    db.commit()


def request_test(db: Session) -> TelegramIntegration:
    chat_id, _source = resolve_team_chat_id(db)
    if not chat_id:
        raise ValueError("Сначала подключите чат команды")
    if not get_settings().telegram_bot_token.strip():
        raise ValueError("В .env нет TELEGRAM_BOT_TOKEN")
    row = integration_row(db, create=True)
    assert row is not None
    row.test_requested_at = clock.now()
    row.test_sent_at = None
    row.test_error = None
    row.updated_at = clock.now()
    db.commit()
    db.refresh(row)
    return row


def flush_test_message(bot: Any) -> None:
    """Своя сессия: тик воркера не должен откатить доставки, если тест упадёт."""
    db = SessionLocal()
    try:
        row = integration_row(db)
        if row is None or row.test_requested_at is None or row.test_sent_at is not None or row.test_error:
            return
        chat_id, _source = resolve_team_chat_id(db)
        if not chat_id:
            row.test_error = "Чат не подключён"
            row.updated_at = clock.now()
            db.commit()
            return
        try:
            bot.send_message(
                chat_id,
                "rekeeper на связи. Напоминания команды будут приходить сюда.",
                {"inline_keyboard": []},
            )
        except TelegramError as exc:
            row.test_error = exc.description[:200]
            row.updated_at = clock.now()
            db.commit()
            return
        row.test_sent_at = clock.now()
        row.test_error = None
        row.updated_at = clock.now()
        db.commit()
    except Exception:
        db.rollback()
        log.exception("telegram test flush failed")
    finally:
        db.close()


def start_payload(text: object) -> str | None:
    """None — это не /start. Пустая строка — /start без токена."""
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    if not stripped:
        return None
    head, _, rest = stripped.partition(" ")
    command = head.split("@", 1)[0]
    if command != "/start":
        return None
    return rest.strip()


def is_private_chat(chat: dict[str, Any]) -> bool:
    kind = chat.get("type")
    if isinstance(kind, str) and kind:
        return kind == "private"
    try:
        return int(chat.get("id")) > 0
    except (TypeError, ValueError):
        return False


def handle_start(db: Session, bot: Any, message: dict[str, Any]) -> None:
    payload = start_payload(message.get("text"))
    if payload is None:
        return
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    chat_id = chat.get("id")
    if chat_id is None:
        return
    sender = message.get("from") if isinstance(message.get("from"), dict) else {}
    reply = _consume_start(db, payload, chat, sender)
    try:
        bot.send_message(str(chat_id), reply, {"inline_keyboard": []})
    except TelegramError as exc:
        log.warning("start reply failed (%s)", exc.description)


def handle_membership(db: Session, member: dict[str, Any]) -> None:
    chat = member.get("chat") if isinstance(member.get("chat"), dict) else {}
    chat_id = chat.get("id")
    new_status = (member.get("new_chat_member") or {}).get("status") if isinstance(member.get("new_chat_member"), dict) else None
    if chat_id is None or new_status not in _GONE:
        return
    row = integration_row(db)
    if row is None or row.team_status != "connected" or row.team_chat_id != str(chat_id):
        return
    row.team_status = "disconnected"
    row.team_disconnected_at = clock.now()
    row.updated_at = clock.now()
    record(
        db,
        action="telegram.team_disconnect",
        entity_type="telegram",
        meta={"title": row.team_chat_title, "reason": "bot_removed"},
    )
    db.commit()
    log.info("telegram bot removed from team chat")


def migrate_chat(db: Session, message: dict[str, Any]) -> None:
    new_id = message.get("migrate_to_chat_id")
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    old_id = chat.get("id")
    if new_id is None or old_id is None:
        return
    old_key = str(old_id)
    new_key = str(new_id)
    row = integration_row(db)
    if row is not None and row.team_chat_id == old_key:
        row.team_chat_id = new_key
        row.team_chat_type = "supergroup"
        row.team_status = "connected"
        row.team_disconnected_at = None
        row.updated_at = clock.now()
    db.execute(
        update(PaymentOccurrence)
        .where(PaymentOccurrence.telegram_chat_id == old_key)
        .values(telegram_chat_id=new_key)
    )
    db.execute(
        update(PaymentOccurrence).where(PaymentOccurrence.dm_chat_id == old_key).values(dm_chat_id=new_key)
    )
    db.commit()
    log.info("telegram chat migrated %s -> %s", old_key, new_key)


def _consume_start(db: Session, payload: str, chat: dict[str, Any], sender: dict[str, Any]) -> str:
    private = is_private_chat(chat)
    if payload == "":
        if private:
            return "Привязка в rekeeper: Настройки → Привязать Telegram."
        return "Чат команды подключается из rekeeper: Настройки → Подключить чат команды."
    token = db.scalar(select(TelegramLinkToken).where(TelegramLinkToken.token == payload))
    if token is None or token.used_at is not None or token.expires_at <= clock.now():
        return "Ссылка недействительна или истекла. Создайте новую в rekeeper."
    if token.purpose == "team":
        if private:
            return "Эту ссылку откройте как добавление бота в группу, не в личном чате."
        return _connect_team(db, token, chat)
    if token.purpose == "user":
        if not private:
            return "Привязка человека — в личном чате с ботом. Откройте ссылку ещё раз."
        return _connect_user(db, token, sender)
    return "Ссылка недействительна или истекла. Создайте новую в rekeeper."


def _connect_team(db: Session, token: TelegramLinkToken, chat: dict[str, Any]) -> str:
    creator = token.user
    if creator is None or not creator.is_active or creator.role != "admin":
        return "Ссылку может выдать только администратор. Создайте новую в rekeeper."
    row = integration_row(db, create=True)
    assert row is not None
    title = str(chat.get("title") or "").strip() or "Группа"
    row.team_chat_id = str(chat.get("id"))
    row.team_chat_title = title[:255]
    row.team_chat_type = str(chat.get("type") or "")[:32] or None
    row.team_status = "connected"
    row.team_connected_at = clock.now()
    row.team_disconnected_at = None
    row.updated_at = clock.now()
    token.used_at = clock.now()
    record(
        db,
        action="telegram.team_connect",
        actor=creator,
        entity_type="telegram",
        meta={"title": row.team_chat_title},
    )
    db.commit()
    return "Подключено к rekeeper"


def _connect_user(db: Session, token: TelegramLinkToken, sender: dict[str, Any]) -> str:
    owner = token.user
    if owner is None or not owner.is_active:
        return "Пользователь rekeeper не найден или отключён."
    try:
        tg_id = int(sender.get("id"))
    except (TypeError, ValueError):
        return "Не вижу аккаунт Telegram. Откройте ссылку ещё раз."
    other = db.scalar(select(User).where(User.telegram_user_id == tg_id, User.id != owner.id))
    if other is not None:
        return "Этот Telegram уже привязан к другому человеку. Сначала отвяжите его в том профиле."
    username = sender.get("username")
    owner.telegram_user_id = tg_id
    owner.telegram_username = str(username).lstrip("@")[:32] if isinstance(username, str) and username else None
    owner.telegram_display_name = _display_name(sender)
    owner.updated_at = clock.now()
    token.used_at = clock.now()
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return "Этот Telegram уже привязан к другому человеку. Сначала отвяжите его в том профиле."
    record(
        db,
        action="telegram.user_link",
        actor=owner,
        entity_type="user",
        entity_id=owner.id,
        meta={"email": owner.email},
    )
    db.commit()
    return f"Привет, {owner.full_name}! Теперь кнопки «Оплачено» записываются на тебя"


def _display_name(sender: dict[str, Any]) -> str | None:
    parts = [sender.get("first_name"), sender.get("last_name")]
    name = " ".join(str(part).strip() for part in parts if isinstance(part, str) and part.strip())
    if not name:
        return None
    return name[:200]

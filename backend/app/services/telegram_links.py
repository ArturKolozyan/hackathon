"""Привязка чата отдела и личного Telegram. Deep link собирает API, бот — отдельный процесс.

Токен одноразовый и живёт до использования. Новая ссылка гасит прежние того же
человека или отдела. Сырой токен в журнал не пишем.
TELEGRAM_CHAT_ID — запасной чат, только когда в базе ровно одна команда
и у неё нет явного состояния (нет строки или status=absent). Несколько команд
env не делят: иначе один чат прилип бы ко всем.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from typing import Any

from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import SessionLocal
from app.integrations.telegram import TelegramError
from app.models import PaymentOccurrence, Team, TelegramBot, TelegramIntegration, TelegramLinkToken, User
from app.services import telegram_html as tg
from app.services import time as clock
from app.services.audit import record
from app.services.teams import membership

log = logging.getLogger("invoice_keeper.telegram")

TEAM_RECIPIENT = "team"
UNLINKED_ALERT = "Сначала привяжите Telegram в rekeeper: Настройки → Уведомления."
SETTINGS_PATH = "Настройки → Уведомления"
BUSY_TELEGRAM = (
    "Этот Telegram уже привязан к другому аккаунту rekeeper. "
    "Отвяжите его там (Настройки → Уведомления) или откройте ссылку из другого Telegram."
)
_GONE = ("left", "kicked")
_MANAGERS = {"owner", "admin"}


def bot_row(db: Session, *, create: bool = False) -> TelegramBot | None:
    row = db.get(TelegramBot, 1)
    if row is None and create:
        row = TelegramBot(id=1)
        db.add(row)
        db.flush()
    return row


def team_row(db: Session, team_id: uuid.UUID, *, create: bool = False) -> TelegramIntegration | None:
    row = db.scalar(select(TelegramIntegration).where(TelegramIntegration.team_id == team_id))
    if row is None and create:
        row = TelegramIntegration(team_id=team_id, team_status="absent")
        db.add(row)
        db.flush()
    return row


def _only_team(db: Session) -> uuid.UUID | None:
    rows = list(db.scalars(select(Team.id)).all())
    if len(rows) == 1:
        return rows[0]
    return None


def resolve_team_chat_id(db: Session, team_id: uuid.UUID | None = None) -> tuple[str | None, str]:
    """Куда слать карточку команды: (chat_id, source).

    source: database | env | none.
    disconnected не падает обратно в env.
    Без team_id берём единственную команду. Если команд несколько — none.
    """
    if team_id is None:
        team_id = _only_team(db)
        if team_id is None:
            return None, "none"
    row = team_row(db, team_id)
    if row is not None and row.team_status == "connected" and row.team_chat_id:
        return row.team_chat_id, "database"
    if row is not None and row.team_status == "disconnected":
        return None, "none"
    if _only_team(db) != team_id:
        return None, "none"
    if row is not None and row.team_status != "absent":
        return None, "none"
    env_chat = get_settings().telegram_chat_id.strip()
    if env_chat:
        return env_chat, "env"
    return None, "none"


def bot_username(db: Session) -> str | None:
    row = bot_row(db)
    if row is not None and row.bot_username:
        name = row.bot_username.strip().lstrip("@")
        if name:
            return name
    env_name = get_settings().telegram_bot_username.strip().lstrip("@")
    return env_name or None


def remember_bot(me: dict[str, Any]) -> None:
    username = str(me.get("username") or "").strip().lstrip("@")
    if not username:
        return
    db = SessionLocal()
    try:
        row = bot_row(db, create=True)
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


def issue_token(db: Session, *, purpose: str, user: User, team_id: uuid.UUID | None = None) -> TelegramLinkToken:
    """Новая ссылка. Прежние неиспользованные того же человека (или отдела) гаснут."""
    if purpose == "team" and team_id is None:
        team_id = user.active_team_id
    scope = TelegramLinkToken.team_id == team_id if purpose == "team" else TelegramLinkToken.user_id == user.id
    db.execute(
        update(TelegramLinkToken)
        .where(TelegramLinkToken.purpose == purpose, TelegramLinkToken.used_at.is_(None), scope)
        .values(used_at=clock.now())
    )
    row = TelegramLinkToken(
        token=secrets.token_urlsafe(24),
        purpose=purpose,
        team_id=team_id if purpose == "team" else None,
        user_id=user.id,
        expires_at=None,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def current_user_token(db: Session, user: User) -> TelegramLinkToken:
    """Действующая личная ссылка или новая. Повторный показ не гасит уже отправленную."""
    row = db.scalar(
        select(TelegramLinkToken)
        .where(
            TelegramLinkToken.purpose == "user",
            TelegramLinkToken.user_id == user.id,
            TelegramLinkToken.used_at.is_(None),
            or_(TelegramLinkToken.expires_at.is_(None), TelegramLinkToken.expires_at > clock.now()),
        )
        .order_by(TelegramLinkToken.created_at.desc())
    )
    return row or issue_token(db, purpose="user", user=user)


def deep_link(username: str, token: str, *, group: bool) -> str:
    key = "startgroup" if group else "start"
    return f"https://t.me/{username}?{key}={token}"


def disconnect_team(db: Session, *, actor: User | None, team_id: uuid.UUID) -> TelegramIntegration:
    row = team_row(db, team_id, create=True)
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
        team_id=team_id,
    )
    db.commit()
    db.refresh(row)
    return row


def _revoke_user_tokens(db: Session, user: User) -> None:
    db.execute(
        update(TelegramLinkToken)
        .where(
            TelegramLinkToken.purpose == "user",
            TelegramLinkToken.user_id == user.id,
            TelegramLinkToken.used_at.is_(None),
        )
        .values(used_at=clock.now())
    )


def unlink_user(db: Session, user: User, *, actor: User | None = None) -> None:
    """Сам или админ — одинаково. Выданные ссылки гаснут: следующая привязка — только по новой."""
    user.telegram_user_id = None
    user.telegram_chat_id = None
    user.telegram_username = None
    user.telegram_display_name = None
    user.telegram_test_requested_at = None
    user.telegram_test_sent_at = None
    user.telegram_test_error = None
    user.updated_at = clock.now()
    _revoke_user_tokens(db, user)
    record(
        db,
        action="telegram.user_unlink",
        actor=actor or user,
        entity_type="user",
        entity_id=user.id,
        meta={"email": user.email},
    )
    db.commit()


def request_test(db: Session, team_id: uuid.UUID) -> TelegramIntegration:
    chat_id, _source = resolve_team_chat_id(db, team_id)
    if not chat_id:
        raise ValueError("Сначала подключите чат отдела")
    if not get_settings().telegram_bot_token.strip():
        raise ValueError("В .env нет TELEGRAM_BOT_TOKEN")
    row = team_row(db, team_id, create=True)
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
        rows = db.scalars(
            select(TelegramIntegration).where(
                TelegramIntegration.test_requested_at.is_not(None),
                TelegramIntegration.test_sent_at.is_(None),
                TelegramIntegration.test_error.is_(None),
            )
        ).all()
        for row in rows:
            chat_id, _source = resolve_team_chat_id(db, row.team_id)
            if not chat_id:
                row.test_error = "Чат не подключён"
                row.updated_at = clock.now()
                db.commit()
                continue
            try:
                bot.send_message(chat_id, _team_test_text(db, row.team_id), {"inline_keyboard": []})
            except TelegramError as exc:
                row.test_error = exc.description[:200]
                row.updated_at = clock.now()
                db.commit()
                continue
            row.test_sent_at = clock.now()
            row.test_error = None
            row.updated_at = clock.now()
            db.commit()
        _flush_personal_tests(db, bot)
    except Exception:
        db.rollback()
        log.exception("telegram test flush failed")
    finally:
        db.close()


def _team_test_text(db: Session, team_id: uuid.UUID) -> str:
    team = db.get(Team, team_id)
    lines = [tg.field("Отдел", team.name)] if team is not None else []
    lines.append(tg.esc("Всё работает: напоминания и просрочки отдела будут приходить в этот чат."))
    return tg.compose("🔔", "Проверка связи", lines)


def request_personal_test(db: Session, user: User) -> None:
    if user.telegram_user_id is None:
        raise ValueError("Сначала привяжите Telegram")
    if not get_settings().telegram_bot_token.strip():
        raise ValueError("В .env нет TELEGRAM_BOT_TOKEN")
    user.telegram_test_requested_at = clock.now()
    user.telegram_test_sent_at = None
    user.telegram_test_error = None
    user.updated_at = clock.now()
    db.commit()


def _flush_personal_tests(db: Session, bot: Any) -> None:
    rows = db.scalars(
        select(User).where(
            User.telegram_test_requested_at.is_not(None),
            User.telegram_test_sent_at.is_(None),
            User.telegram_test_error.is_(None),
        )
    ).all()
    for user in rows:
        if user.telegram_user_id is None:
            user.telegram_test_error = "Telegram не привязан"
            user.updated_at = clock.now()
            db.commit()
            continue
        try:
            bot.send_message(
                str(user.telegram_user_id),
                tg.notice(
                    "🔔",
                    "Тестовое уведомление",
                    "Всё работает: личные напоминания rekeeper будут приходить в этот чат.",
                ),
                {"inline_keyboard": []},
            )
        except TelegramError as exc:
            user.telegram_test_error = exc.description[:200]
            user.updated_at = clock.now()
            db.commit()
            continue
        user.telegram_test_sent_at = clock.now()
        user.telegram_test_error = None
        user.updated_at = clock.now()
        db.commit()


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
    row = db.scalar(
        select(TelegramIntegration).where(
            TelegramIntegration.team_chat_id == str(chat_id),
            TelegramIntegration.team_status == "connected",
        )
    )
    if row is None:
        return
    row.team_status = "disconnected"
    row.team_disconnected_at = clock.now()
    row.updated_at = clock.now()
    record(
        db,
        action="telegram.team_disconnect",
        entity_type="telegram",
        meta={"title": row.team_chat_title, "reason": "bot_removed"},
        team_id=row.team_id,
    )
    db.commit()
    log.info("telegram bot removed from team chat")


def migrate_chat(db: Session, message: dict[str, Any]) -> None:
    new_id = message.get("migrate_to_chat_id")
    chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
    old_id = chat.get("id")
    if new_id is None or old_id is None:
        return
    move_chat(db, str(old_id), str(new_id))


def move_chat(db: Session, old_key: str, new_key: str) -> None:
    """Группа стала супергруппой: новый id чата у отдела и у отправленных карточек."""
    rows = db.scalars(select(TelegramIntegration).where(TelegramIntegration.team_chat_id == old_key)).all()
    for row in rows:
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


def _link_help(private: bool) -> str:
    if private:
        return tg.compose(
            "👋",
            "Это бот напоминаний rekeeper",
            [
                tg.esc("Здесь приходят личные напоминания о платежах, а кнопка «Оплачено» отмечает оплату."),
                tg.esc("Чтобы привязать Telegram:"),
                tg.bullet(tg.esc("откройте rekeeper")),
                tg.bullet(tg.esc(f"{SETTINGS_PATH} → Привязать Telegram")),
                tg.bullet(tg.esc("нажмите на ссылку и вернитесь сюда")),
            ],
        )
    return tg.notice(
        "👋",
        "Это бот напоминаний rekeeper",
        f"Чат отдела подключается из rekeeper: {SETTINGS_PATH} → Подключить чат отдела.",
    )


def _consume_start(db: Session, payload: str, chat: dict[str, Any], sender: dict[str, Any]) -> str:
    private = is_private_chat(chat)
    if payload == "":
        return _link_help(private)
    token = db.scalar(select(TelegramLinkToken).where(TelegramLinkToken.token == payload))
    expired = token is not None and token.expires_at is not None and token.expires_at <= clock.now()
    if token is not None and token.used_at is not None and token.purpose == "user" and private:
        # Telegram повторяет /start, когда ссылку открывают ещё раз. Уже привязан — так и скажем.
        holder = token.user
        if holder is not None and holder.telegram_user_id is not None and holder.telegram_user_id == _sender_id(sender):
            return tg.notice("✅", "Telegram уже привязан", f"Аккаунт: {holder.full_name}. Ничего делать не нужно.")
    if token is None or token.used_at is not None or expired:
        return tg.notice(
            "⚠️",
            "Ссылка не работает",
            f"Ссылка уже использована или заменена новой. Получите новую в rekeeper: {SETTINGS_PATH}.",
        )
    if token.purpose == "team":
        if private:
            return tg.notice(
                "⚠️",
                "Это ссылка для группы",
                "Откройте её как добавление бота в группу отдела, а не в личном чате.",
            )
        return _connect_team(db, token, chat)
    if token.purpose == "user":
        if not private:
            return tg.notice(
                "⚠️",
                "Привязка — в личном чате",
                "Личный Telegram привязывается в личном чате с ботом. Откройте ссылку ещё раз.",
            )
        return _connect_user(db, token, sender)
    return tg.notice("⚠️", "Ссылка недействительна", f"Получите новую в rekeeper: {SETTINGS_PATH}.")


def _sender_id(sender: dict[str, Any]) -> int | None:
    try:
        return int(sender.get("id"))
    except (TypeError, ValueError):
        return None


def _connect_team(db: Session, token: TelegramLinkToken, chat: dict[str, Any]) -> str:
    creator = token.user
    denied = tg.notice("⚠️", "Нет прав на подключение", "Ссылку выдаёт администратор отдела. Создайте новую в rekeeper.")
    if creator is None or not creator.is_active or token.team_id is None:
        return denied
    seat = membership(db, token.team_id, creator.id)
    if not creator.is_owner and (seat is None or seat.role not in _MANAGERS):
        return denied
    row = team_row(db, token.team_id, create=True)
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
        team_id=token.team_id,
    )
    from app.services.notify import acknowledge_team_backlog, connect_digest, list_open_occurrences

    open_rows = list_open_occurrences(db, token.team_id)
    acknowledge_team_backlog(db, token.team_id, open_rows)
    db.commit()
    team = db.get(Team, token.team_id)
    return connect_digest(open_rows, team.name if team is not None else None)


def _connect_user(db: Session, token: TelegramLinkToken, sender: dict[str, Any]) -> str:
    owner = token.user
    if owner is None or not owner.is_active:
        return tg.notice("⚠️", "Аккаунт не найден", "Пользователь rekeeper не найден или отключён.")
    tg_id = _sender_id(sender)
    if tg_id is None:
        return tg.notice("⚠️", "Не получилось привязать", "Не вижу аккаунт Telegram. Откройте ссылку ещё раз.")
    other = db.scalar(select(User).where(User.telegram_user_id == tg_id, User.id != owner.id))
    if other is not None:
        return tg.notice("⚠️", "Telegram уже занят", BUSY_TELEGRAM)
    username = sender.get("username")
    owner.telegram_user_id = tg_id
    owner.telegram_username = str(username).lstrip("@")[:32] if isinstance(username, str) and username else None
    owner.telegram_display_name = _display_name(sender)
    owner.telegram_onboarding_done = True
    # Одна привязка на всё: после неё личные напоминания включены.
    owner.telegram_reminders = True
    owner.updated_at = clock.now()
    token.used_at = clock.now()
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        return tg.notice("⚠️", "Telegram уже занят", BUSY_TELEGRAM)
    record(
        db,
        action="telegram.user_link",
        actor=owner,
        entity_type="user",
        entity_id=owner.id,
        meta={"email": owner.email},
    )
    db.commit()
    lines = [
        tg.esc("Telegram привязан к rekeeper."),
        tg.bullet(tg.esc("личные напоминания о платежах будут приходить сюда")),
        tg.bullet(tg.esc("кнопка «Оплачено» в чате отдела записывает оплату на вас")),
    ]
    if get_settings().assistant_configured:
        lines.append(tg.bullet(tg.esc("сюда же можно писать Кипу, помощнику: «что горит на этой неделе?»")))
    return tg.compose("👋", f"Здравствуйте, {owner.full_name}!", lines)


def _display_name(sender: dict[str, Any]) -> str | None:
    parts = [sender.get("first_name"), sender.get("last_name")]
    name = " ".join(str(part).strip() for part in parts if isinstance(part, str) and part.strip())
    if not name:
        return None
    return name[:200]


def team_count(db: Session) -> int:
    return int(db.scalar(select(func.count()).select_from(Team)) or 0)

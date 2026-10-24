"""Клиент Bot API. Только контейнер bot.

Сеть: TELEGRAM_NETWORK=auto|ipv4|ipv6. auto пробует IPv6, затем IPv4.
TELEGRAM_FORCE_IPV6=true — устаревший алиас ipv6, если сеть не задана.
TELEGRAM_PROXY — явный прокси. HTTP_PROXY из окружения не читаем.
"""

from __future__ import annotations

import logging
import socket
import uuid
from typing import Any

import httpx
from sqlalchemy import update

from app.core.config import Settings, get_settings
from app.core.logging import install_redaction, quiet_http_loggers

log = logging.getLogger("invoice_keeper.telegram")

API_HOST = "api.telegram.org"
ALLOWED_UPDATES = ["message", "callback_query", "my_chat_member"]


class TelegramError(Exception):
    def __init__(
        self,
        method: str,
        description: str,
        status: int | None = None,
        *,
        migrate_to_chat_id: int | None = None,
    ) -> None:
        self.method = method
        self.description = description
        self.status = status
        self.migrate_to_chat_id = migrate_to_chat_id
        super().__init__(f"{method}: {description}")

    @property
    def permanent(self) -> bool:
        """Повтор не поможет: бот заблокирован, выгнан, чата нет, запрос битый."""
        return self.status in (400, 403) and self.migrate_to_chat_id is None


_cached_family: str | None = None


def resolve_local_address(network: str) -> str | None:
    """Адрес bind. None — система выбирает сама. Сбой пробы не роняет процесс."""
    if network == "ipv6":
        return "::"
    if network == "ipv4":
        return "0.0.0.0"
    global _cached_family
    if _cached_family == "ipv6":
        return "::"
    if _cached_family == "ipv4":
        return "0.0.0.0"
    if _cached_family == "none":
        return None
    for family, local, af in (("ipv6", "::", socket.AF_INET6), ("ipv4", "0.0.0.0", socket.AF_INET)):
        sock = None
        try:
            infos = socket.getaddrinfo(API_HOST, 443, af, socket.SOCK_STREAM)
            if not infos:
                continue
            sock = socket.socket(af, socket.SOCK_STREAM)
            sock.settimeout(2.0)
            if family == "ipv6":
                sock.bind(("::", 0))
            sock.connect(infos[0][4])
        except OSError:
            continue
        finally:
            if sock is not None:
                sock.close()
        _cached_family = family
        return local
    _cached_family = "none"
    return None


def describe_transport() -> dict[str, object]:
    settings = get_settings()
    token = settings.telegram_bot_token.strip()
    chat = settings.telegram_chat_id.strip()
    network = settings.resolved_telegram_network
    return {
        "sender": "long_poll" if token else "skipped",
        "host": API_HOST,
        "network": network,
        "force_ipv6": network == "ipv6",
        "proxy": bool(settings.telegram_proxy.strip()),
        "token_configured": bool(token),
        "chat_configured": bool(chat),
        "vps_note": "Aeza RU: set TELEGRAM_NETWORK=ipv6 and ENABLE_IPV6=true",
    }


def make_bot(settings: Settings | None = None) -> TelegramClient | None:
    current = settings or get_settings()
    token = current.telegram_bot_token.strip()
    if not token:
        return None
    return TelegramClient(
        token,
        network=current.resolved_telegram_network,
        proxy=current.telegram_proxy.strip() or None,
    )


def _net_reason(exc: BaseException) -> str:
    parts = [type(exc).__name__]
    current: BaseException | None = exc
    seen = 0
    while current is not None and seen < 5:
        if isinstance(current, OSError) and current.strerror:
            parts.append(current.strerror)
            break
        current = current.__cause__ or current.__context__
        seen += 1
    return ": ".join(parts)


class TelegramClient:
    """Long polling и send/edit. Токен в лог и в repr не попадает."""

    def __init__(
        self,
        token: str,
        force_ipv6: bool = False,
        *,
        network: str | None = None,
        proxy: str | None = None,
    ) -> None:
        # Повторно: uvicorn dictConfig не трогает уже выставленный уровень,
        # но клиент мог появиться раньше configure_logging.
        quiet_http_loggers()
        install_redaction()
        self._token = token.strip()
        self.proxy = proxy or None
        if network is None:
            self.network = "ipv6" if force_ipv6 else "default"
            self.force_ipv6 = force_ipv6
            self._local: str | None = "::" if force_ipv6 else None
            self._resolved = True
        else:
            self.network = network
            self.force_ipv6 = network == "ipv6"
            self._local = None if network == "auto" else resolve_local_address(network)
            self._resolved = network != "auto"
            if network == "ipv6":
                self._local = "::"
        self._http = self._open()

    def _open(self) -> httpx.Client:
        transport = httpx.HTTPTransport(local_address=self._local, retries=0, trust_env=False)
        kwargs: dict[str, Any] = {"transport": transport, "trust_env": False}
        if self.proxy:
            kwargs["proxy"] = self.proxy
        return httpx.Client(**kwargs)

    def _ensure_network(self) -> None:
        if self._resolved:
            return
        self._local = resolve_local_address("auto")
        self.force_ipv6 = self._local == "::"
        self._resolved = True
        self._http.close()
        self._http = self._open()

    def __repr__(self) -> str:
        return f"TelegramClient(network={self.network})"

    def close(self) -> None:
        self._http.close()

    def _call(self, method: str, payload: dict[str, Any], *, read_timeout: float) -> Any:
        self._ensure_network()
        url = f"https://{API_HOST}/bot{self._token}/{method}"
        timeout = httpx.Timeout(connect=10.0, read=read_timeout, write=10.0, pool=10.0)
        try:
            response = self._http.post(url, json=payload, timeout=timeout)
        except httpx.HTTPError as exc:
            raise TelegramError(method, _net_reason(exc)) from None
        try:
            body = response.json()
        except ValueError:
            raise TelegramError(method, "bad json", response.status_code) from None
        if not isinstance(body, dict) or not body.get("ok") or response.status_code >= 400:
            description = body.get("description") if isinstance(body, dict) else "error"
            parameters = body.get("parameters") if isinstance(body, dict) else None
            migrate_to = parameters.get("migrate_to_chat_id") if isinstance(parameters, dict) else None
            raise TelegramError(
                method,
                str(description or "error"),
                response.status_code,
                migrate_to_chat_id=int(migrate_to) if migrate_to is not None else None,
            )
        return body.get("result")

    def get_me(self) -> dict[str, Any]:
        result = self._call("getMe", {}, read_timeout=20)
        if not isinstance(result, dict):
            raise TelegramError("getMe", "empty result")
        return result

    def delete_webhook(self) -> None:
        self._call("deleteWebhook", {"drop_pending_updates": False}, read_timeout=20)

    def get_updates(self, offset: int | None, timeout: int) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": timeout, "allowed_updates": ALLOWED_UPDATES}
        if offset is not None:
            payload["offset"] = offset
        result = self._call("getUpdates", payload, read_timeout=timeout + 15)
        if result is None:
            return []
        if not isinstance(result, list):
            raise TelegramError("getUpdates", "unexpected result")
        return [item for item in result if isinstance(item, dict)]

    def send_message(self, chat_id: str, text: str, reply_markup: dict[str, Any]) -> int:
        result = self._call(
            "sendMessage",
            {"chat_id": chat_id, "text": text, "reply_markup": reply_markup},
            read_timeout=20,
        )
        if not isinstance(result, dict) or "message_id" not in result:
            raise TelegramError("sendMessage", "no message_id")
        return int(result["message_id"])

    def edit_message(self, chat_id: str, message_id: int, text: str, reply_markup: dict[str, Any]) -> None:
        self._call(
            "editMessageText",
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "text": text,
                "reply_markup": reply_markup,
            },
            read_timeout=20,
        )

    def edit_markup(self, chat_id: str, message_id: int, reply_markup: dict[str, Any]) -> None:
        self._call(
            "editMessageReplyMarkup",
            {"chat_id": chat_id, "message_id": message_id, "reply_markup": reply_markup},
            read_timeout=20,
        )

    def answer_callback(self, callback_query_id: str, text: str, *, show_alert: bool = False) -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id, "text": text[:200]}
        if show_alert:
            payload["show_alert"] = True
        self._call("answerCallbackQuery", payload, read_timeout=20)

    def download_voice(self, file_id: str) -> bytes:
        """Файл голосового. URL с токеном в лог не пишем."""
        self._ensure_network()
        result = self._call("getFile", {"file_id": file_id}, read_timeout=20)
        path = result.get("file_path") if isinstance(result, dict) else None
        if not isinstance(path, str) or not path or path.startswith("/") or ".." in path:
            raise TelegramError("getFile", "no file_path")
        url = f"https://{API_HOST}/file/bot{self._token}/{path}"
        timeout = httpx.Timeout(connect=10.0, read=20.0, write=10.0, pool=10.0)
        try:
            response = self._http.get(url, timeout=timeout)
        except httpx.HTTPError as exc:
            raise TelegramError("getFile", _net_reason(exc)) from None
        if response.status_code >= 400 or not response.content:
            raise TelegramError("getFile", "download failed", response.status_code)
        return response.content


def deliver(text: str, *, chat_id: str, occurrence_id: str, event: str, slot: str = "team") -> None:
    """Отправка в chat_id. Порог «пора ли напоминать» здесь не считается.

    Контракт: успех — return, нет транспорта — NotImplementedError (канал
    пропускается и не считается доставленным), сбой сети — другое исключение
    (повтор на следующем тике воркера). Срок решает app.services.reminders.should_remind.
    """
    if not get_settings().telegram_bot_token.strip():
        raise NotImplementedError("TELEGRAM_BOT_TOKEN empty")
    client = make_bot()
    if client is None:
        raise NotImplementedError("TELEGRAM_BOT_TOKEN empty")
    from app.services.telegram_cards import EMPTY_KEYBOARD, fingerprint, pay_keyboard

    digest = event.startswith("occurrence.overdue.digest")
    with_button = not digest and (
        event.startswith("occurrence.reminder") or event.startswith("occurrence.overdue")
    )
    try:
        period_id = uuid.UUID(occurrence_id)
    except ValueError:
        client.close()
        raise
    markup = pay_keyboard(period_id) if with_button else EMPTY_KEYBOARD
    try:
        message_id = client.send_message(chat_id, text, markup)
    finally:
        client.close()
    if digest:
        # Сводка без кнопки не занимает слот карточки: иначе правка перепишет её в карточку периода.
        return
    _remember(period_id, chat_id, message_id, fingerprint(text, with_button), slot=slot)


def _remember(
    occurrence_id: uuid.UUID,
    chat_id: str,
    message_id: int,
    fingerprint_value: str,
    *,
    slot: str,
) -> None:
    """Своя сессия: вызывающий ещё не закоммитил строку доставки.

    0 строк — период ещё не виден. Сообщение уже ушло, канал всё равно успешный,
    иначе следующий тик пришлёт дубль.
    """
    from app.core.database import SessionLocal
    from app.models import PaymentOccurrence
    from app.services import time as clock

    db = SessionLocal()
    try:
        if slot == "dm":
            values = {
                "dm_chat_id": str(chat_id),
                "dm_message_id": message_id,
                "dm_fingerprint": fingerprint_value,
                "telegram_reminded_at": clock.now(),
            }
        else:
            values = {
                "telegram_chat_id": str(chat_id),
                "telegram_message_id": message_id,
                "telegram_fingerprint": fingerprint_value,
                "telegram_reminded_at": clock.now(),
            }
        result = db.execute(
            update(PaymentOccurrence)
            .where(PaymentOccurrence.id == occurrence_id)
            .values(**values),
            execution_options={"synchronize_session": False},
        )
        db.commit()
        if result.rowcount == 0:
            log.warning("telegram message stored nowhere, occurrence=%s is not visible yet", occurrence_id)
    except Exception:
        db.rollback()
        log.exception("telegram message id was not stored for occurrence=%s", occurrence_id)
    finally:
        db.close()

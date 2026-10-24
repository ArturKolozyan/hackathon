"""Логи api и worker.

httpx на INFO пишет строку запроса целиком. У Bot API токен стоит в пути
(`https://api.telegram.org/bot<token>/method`), поэтому логгеры httpx и httpcore
держатся на WARNING.

Этого мало, если сообщение исключения или чужой WARNING всё же содержит токен:
оплата из API зовёт тот же клиент. Поэтому Logger.handle вырезает токен из
текста, аргументов и traceback до того, как запись попадёт в handler.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

# BotFather: числовой id, двоеточие, длинный секрет. Короче 20 символов
# секрет из env всё равно вырезается отдельно.
_BOT_TOKEN = re.compile(r"\d{6,}:[A-Za-z0-9_-]{20,}")
_FORMAT = "%(levelname)s %(name)s %(message)s"


def _redact_value(value: object) -> object:
    if isinstance(value, str):
        return _redact_text(value)
    rendered = str(value)
    redacted = _redact_text(rendered)
    if redacted != rendered:
        return redacted
    return value


def _redact_text(text: str) -> str:
    text = _BOT_TOKEN.sub("<redacted>", text)
    token = _configured_token()
    if token and token in text:
        text = text.replace(token, "<redacted>")
    return text


def _configured_token() -> str:
    """Токен процесса. Не прогреваем кэш настроек из фильтра логирования."""
    from app.core.config import get_settings

    if get_settings.cache_info().currsize:
        return get_settings().telegram_bot_token.strip()
    return os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()


def _redact_record(record: logging.LogRecord) -> None:
    if isinstance(record.msg, str):
        record.msg = _redact_text(record.msg)
    if isinstance(record.args, dict):
        record.args = {key: _redact_value(value) for key, value in record.args.items()}
    elif isinstance(record.args, tuple):
        record.args = tuple(_redact_value(value) for value in record.args)
    if record.exc_info and not record.exc_text:
        record.exc_text = logging.Formatter().formatException(record.exc_info)
    if record.exc_text:
        record.exc_text = _redact_text(record.exc_text)
    # Иначе formatter соберёт traceback заново и вернёт токен в текст.
    if record.exc_text:
        record.exc_info = None


def quiet_http_loggers() -> None:
    # alembic fileConfig в serve() помечает уже созданные логгеры disabled.
    # Уровень WARNING сам по себе тогда не работает, пока флаг не снять.
    for name in ("httpx", "httpcore"):
        logger = logging.getLogger(name)
        logger.disabled = False
        logger.setLevel(logging.WARNING)


def install_redaction() -> None:
    current = logging.Logger.handle
    if getattr(current, "_rekeeper", False):
        return

    def handle(self: logging.Logger, record: logging.LogRecord) -> None:
        _redact_record(record)
        current(self, record)

    handle._rekeeper = True  # type: ignore[attr-defined]
    handle._rekeeper_original = current  # type: ignore[attr-defined]
    logging.Logger.handle = handle  # type: ignore[method-assign]


def uninstall_redaction() -> None:
    """Только тесты: вернуть штатный Logger.handle, чтобы увидеть утечку."""
    current = logging.Logger.handle
    original: Any = getattr(current, "_rekeeper_original", None)
    if original is not None:
        logging.Logger.handle = original


def configure_logging() -> None:
    logging.basicConfig(level=logging.INFO, format=_FORMAT)
    quiet_http_loggers()
    install_redaction()

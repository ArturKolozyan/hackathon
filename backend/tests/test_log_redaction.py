import logging

import httpx

from app.core.config import get_settings
from app.core.logging import configure_logging, quiet_http_loggers, uninstall_redaction
from app.integrations.telegram import TelegramClient

TOKEN = "123456789:AAH0123456789abcdefghijklmno"


class _ListHandler(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


def _request(token: str) -> None:
    def _ok(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"ok": True})

    with httpx.Client(transport=httpx.MockTransport(_ok)) as client:
        client.post(f"https://api.telegram.org/bot{token}/getMe")


def test_httpx_info_line_hides_bot_token():
    """Без приглушения httpx INFO содержит токен в URL. После configure_logging — нет."""
    uninstall_redaction()
    httpx_logger = logging.getLogger("httpx")
    httpcore_logger = logging.getLogger("httpcore")
    httpx_logger.setLevel(logging.INFO)
    caught = _ListHandler()
    httpx_logger.addHandler(caught)
    try:
        # alembic fileConfig в остальных тестах оставляет httpx disabled.
        # В worker этого нет: логгер включён, и INFO печатает URL с токеном.
        httpx_logger.disabled = False
        httpcore_logger.disabled = False
        _request(TOKEN)
        leaked = "\n".join(caught.lines)
        assert TOKEN in leaked
        assert "/getMe" in leaked

        caught.lines.clear()
        configure_logging()
        _request(TOKEN)
        quiet = "\n".join(caught.lines)
        assert TOKEN not in quiet
        assert "/getMe" not in quiet
        assert httpx_logger.level == logging.WARNING
        assert httpcore_logger.level == logging.WARNING

        httpx_logger.warning("HTTP Request: POST https://api.telegram.org/bot%s/sendMessage", TOKEN)
        warned = "\n".join(caught.lines)
        assert TOKEN not in warned
        assert "<redacted>" in warned
    finally:
        httpx_logger.removeHandler(caught)
        quiet_http_loggers()
        configure_logging()


def test_short_configured_token_is_redacted(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "999:short")
    get_settings.cache_clear()
    try:
        configure_logging()
        logger = logging.getLogger("invoice_keeper.test")
        caught = _ListHandler()
        logger.addHandler(caught)
        try:
            logger.warning("token was %s", "999:short")
        finally:
            logger.removeHandler(caught)
        text = "\n".join(caught.lines)
        assert "999:short" not in text
        assert "<redacted>" in text
    finally:
        get_settings.cache_clear()


def test_settings_and_client_repr_hide_token(monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", TOKEN)
    get_settings.cache_clear()
    client = TelegramClient(TOKEN, force_ipv6=False)
    try:
        assert TOKEN not in repr(get_settings())
        assert TOKEN not in repr(client)
        assert logging.getLogger("httpx").level == logging.WARNING
        assert logging.getLogger("httpcore").level == logging.WARNING
    finally:
        client.close()
        get_settings.cache_clear()


def test_traceback_redacts_token():
    configure_logging()
    logger = logging.getLogger("invoice_keeper.test")
    caught = _ListHandler()
    logger.addHandler(caught)
    try:
        try:
            raise RuntimeError(f"https://api.telegram.org/bot{TOKEN}/getUpdates")
        except RuntimeError:
            logger.exception("poll failed")
    finally:
        logger.removeHandler(caught)
    text = "\n".join(caught.lines)
    assert TOKEN not in text
    assert "<redacted>" in text

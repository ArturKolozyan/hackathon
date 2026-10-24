"""POST JSON на WEBHOOK_URL. Пустой URL или WEBHOOK_ENABLED=false — no-op.

Ретраи не роняют воркер: ошибка пишется в лог, платёж сохраняется.
Секрет в лог не попадает. Подпись: HMAC-SHA256 тела, заголовок X-Rekeeper-Signature.
"""

import hashlib
import hmac
import json
import logging
import time

import httpx

from app.core.config import get_settings

log = logging.getLogger("invoice_keeper.webhook")


def _post(url: str, body: bytes, headers: dict[str, str]) -> int:
    with httpx.Client(timeout=10.0) as client:
        response = client.post(url, content=body, headers=headers)
        return response.status_code


def _deliver(url: str, payload: dict, *, secret: str, attempts: int) -> str:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "rekeeper-webhook",
        "X-Rekeeper-Event": str(payload.get("event", "")),
    }
    if secret:
        digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
        headers["X-Rekeeper-Signature"] = f"sha256={digest}"
    tries = max(1, attempts)
    backoff = max(0.0, get_settings().webhook_backoff_seconds)
    last = "error"
    for attempt in range(tries):
        if attempt:
            time.sleep(backoff * (2 ** (attempt - 1)))
        try:
            status = _post(url, body, headers)
        except Exception as exc:
            last = type(exc).__name__
            log.warning("webhook attempt %s failed: %s", attempt + 1, last)
            continue
        if 200 <= status < 300:
            return "sent"
        last = f"http_{status}"
        log.warning("webhook attempt %s status %s", attempt + 1, status)
    log.error("webhook gave up: %s", last)
    return "failed"


def send_webhook(payload: dict) -> str:
    settings = get_settings()
    url = settings.webhook_url.strip()
    if not settings.webhook_enabled or not url:
        return "skipped"
    return _deliver(url, payload, secret=settings.webhook_secret.strip(), attempts=settings.webhook_attempts)


def send_team_webhook(url: str, payload: dict) -> str:
    """Один заход за тик. Секрет установки сюда не подставляется."""
    cleaned = url.strip()
    if not cleaned:
        return "skipped"
    return _deliver(cleaned, payload, secret="", attempts=1)


def probe_webhook(url: str, payload: dict) -> tuple[str, str]:
    cleaned = url.strip()
    if not cleaned:
        return "skipped", "URL пустой"
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "rekeeper-webhook",
        "X-Rekeeper-Event": str(payload.get("event", "")),
    }
    try:
        status = _post(cleaned, body, headers)
    except Exception as exc:
        return "failed", type(exc).__name__
    if 200 <= status < 300:
        return "sent", f"Ответ {status}"
    return "failed", f"Ответ {status}"

"""Клиент GigaChat: OAuth на 30 минут, ретраи, запасная модель, проверка TLS.

Корневой сертификат Минцифры добавлен к системному хранилищу. verify=False не используем.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import ssl
import threading
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import httpx

from app.core.config import get_settings

log = logging.getLogger("invoice_keeper.assistant")

ROOT_SHA256 = "D26D2D0231B7C39F92CC738512BA54103519E4405D68B5BD703E9788CA8ECF31"
_RETRY_STATUSES = {429, 500, 502, 503, 504}
_lock = threading.Lock()
_token = ""
_expires_at = 0.0


class GigaChatError(Exception):
    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]


@dataclass
class Completion:
    content: str
    tool_call: ToolCall | None
    model: str


def reset_token_cache() -> None:
    global _token, _expires_at
    with _lock:
        _token = ""
        _expires_at = 0.0


def ca_bundle_path() -> Path:
    configured = get_settings().gigachat_ca_file.strip()
    if configured:
        return Path(configured)
    return Path(__file__).resolve().parents[2] / "certs" / "russian_trusted_root_ca.pem"


def _pem_fingerprints(raw: bytes) -> set[str]:
    found: set[str] = set()
    chunks = raw.split(b"-----END CERTIFICATE-----")
    for chunk in chunks:
        body = chunk.split(b"-----BEGIN CERTIFICATE-----")
        if len(body) != 2:
            continue
        try:
            der = base64.b64decode(b"".join(body[1].split()))
        except ValueError:
            continue
        found.add(hashlib.sha256(der).hexdigest().upper())
    return found


def gigachat_verify() -> ssl.SSLContext:
    path = ca_bundle_path()
    if not path.is_file():
        raise GigaChatError("Нет корневого сертификата Минцифры для GigaChat.")
    fingerprints = _pem_fingerprints(path.read_bytes())
    if ROOT_SHA256 not in fingerprints:
        raise GigaChatError("Сертификат Минцифры не совпал с ожидаемым отпечатком.")
    context = ssl.create_default_context()
    context.load_verify_locations(cafile=str(path))
    context.verify_mode = ssl.CERT_REQUIRED
    context.check_hostname = True
    return context


def _parse_arguments(raw: Any) -> dict[str, Any]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            return {}
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError as exc:
            raise GigaChatError("Не разобрал ответ модели. Повтори фразу.") from exc
        if isinstance(loaded, dict):
            return loaded
    raise GigaChatError("Не разобрал ответ модели. Повтори фразу.")


def _message_of(payload: dict[str, Any]) -> tuple[str, ToolCall | None]:
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise GigaChatError("GigaChat вернул пустой ответ.")
    message = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(message, dict):
        raise GigaChatError("GigaChat вернул пустой ответ.")
    content = message.get("content")
    text = content if isinstance(content, str) else ""
    call = message.get("function_call")
    if not isinstance(call, dict) or not call.get("name"):
        return text, None
    return text, ToolCall(name=str(call["name"]), arguments=_parse_arguments(call.get("arguments")))


class GigaChatClient:
    def __init__(
        self,
        settings: Any | None = None,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.settings = settings or get_settings()
        self._transport = transport
        self._sleep = sleep
        self._now = now

    def _open(self) -> httpx.Client:
        timeout = httpx.Timeout(self.settings.assistant_http_timeout, connect=5.0)
        if self._transport is not None:
            return httpx.Client(transport=self._transport, timeout=timeout, trust_env=False)
        return httpx.Client(verify=gigachat_verify(), timeout=timeout, trust_env=False)

    def _send(self, client: httpx.Client, method: str, url: str, **kwargs: Any) -> httpx.Response:
        retries = max(0, int(self.settings.assistant_http_retries))
        delay = 0.4
        last: Exception | None = None
        for attempt in range(retries + 1):
            try:
                response = client.request(method, url, **kwargs)
            except httpx.TimeoutException as exc:
                last = exc
                if attempt >= retries:
                    raise GigaChatError("GigaChat не ответил вовремя. Повтори через минуту.") from exc
                self._sleep(delay)
                delay *= 2
                continue
            except httpx.HTTPError as exc:
                last = exc
                if attempt >= retries:
                    raise GigaChatError("GigaChat сейчас недоступен. Повтори через минуту.") from exc
                self._sleep(delay)
                delay *= 2
                continue
            if response.status_code in _RETRY_STATUSES and attempt < retries:
                self._sleep(delay)
                delay *= 2
                continue
            return response
        raise GigaChatError("GigaChat сейчас недоступен. Повтори через минуту.") from last

    def _fetch_token(self, client: httpx.Client) -> tuple[str, float]:
        key = str(self.settings.gigachat_auth_key or "").strip()
        if key.lower().startswith("basic "):
            key = key[6:].strip()
        if not key:
            raise GigaChatError("GigaChat не настроен.")
        response = self._send(
            client,
            "POST",
            self.settings.gigachat_oauth_url,
            headers={
                "Authorization": f"Basic {key}",
                "RqUID": str(uuid.uuid4()),
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            },
            data={"scope": self.settings.gigachat_scope},
        )
        if response.status_code >= 400:
            log.warning("gigachat oauth failed status=%s", response.status_code)
            raise GigaChatError("GigaChat не пустил по ключу. Проверь GIGACHAT_AUTH_KEY.")
        try:
            body = response.json()
        except ValueError as exc:
            raise GigaChatError("GigaChat сейчас недоступен. Повтори через минуту.") from exc
        token = body.get("access_token") if isinstance(body, dict) else None
        if not isinstance(token, str) or not token:
            raise GigaChatError("GigaChat сейчас недоступен. Повтори через минуту.")
        expires = body.get("expires_at") if isinstance(body, dict) else None
        if isinstance(expires, (int, float)) and expires > 10_000_000_000:
            expires_at = float(expires) / 1000.0
        elif isinstance(expires, (int, float)):
            expires_at = float(expires)
        else:
            expires_at = self._now() + 30 * 60
        return token, expires_at

    def access_token(self, client: httpx.Client) -> str:
        global _token, _expires_at
        with _lock:
            if _token and self._now() < _expires_at - 60:
                return _token
            token, expires_at = self._fetch_token(client)
            _token = token
            _expires_at = expires_at
            return token

    def _model_error(self, response: httpx.Response) -> bool:
        if response.status_code not in {400, 404, 422}:
            return False
        text = response.text.lower()
        return "model" in text

    def complete(self, messages: list[dict[str, Any]], *, functions: list[dict[str, Any]] | None = None) -> Completion:
        primary = str(self.settings.gigachat_model or "GigaChat-2-Max")
        fallback = str(self.settings.gigachat_fallback_model or "GigaChat-2-Pro")
        with self._open() as client:
            token = self.access_token(client)
            response = self._chat(client, token, primary, messages, functions)
            if response.status_code == 401:
                reset_token_cache()
                token = self.access_token(client)
                response = self._chat(client, token, primary, messages, functions)
            if self._model_error(response) and fallback and fallback != primary:
                log.warning("gigachat model %s failed, fallback %s", primary, fallback)
                response = self._chat(client, token, fallback, messages, functions)
                primary = fallback
            if response.status_code >= 400:
                log.warning("gigachat chat failed status=%s", response.status_code)
                raise GigaChatError("GigaChat сейчас недоступен. Повтори через минуту.")
            try:
                body = response.json()
            except ValueError as exc:
                raise GigaChatError("GigaChat сейчас недоступен. Повтори через минуту.") from exc
        if not isinstance(body, dict):
            raise GigaChatError("GigaChat вернул пустой ответ.")
        content, call = _message_of(body)
        return Completion(content=content, tool_call=call, model=primary)

    def _chat(
        self,
        client: httpx.Client,
        token: str,
        model: str,
        messages: list[dict[str, Any]],
        functions: list[dict[str, Any]] | None,
    ) -> httpx.Response:
        payload: dict[str, Any] = {"model": model, "messages": messages, "temperature": 0.2}
        if functions:
            payload["functions"] = functions
            payload["function_call"] = "auto"
        url = str(self.settings.gigachat_api_base).rstrip("/") + "/chat/completions"
        return self._send(
            client,
            "POST",
            url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
            json=payload,
        )

"""Голос → текст для чата в веб-версии. WebM конвертируется в OGG Opus.

Лимит синхронного SpeechKit — около 30 секунд и 1 МБ.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
from typing import Any, Callable

import httpx

from app.core.config import get_settings

log = logging.getLogger("invoice_keeper.assistant")

MAX_OGG_BYTES = 1_000_000
_RETRY_STATUSES = {429, 500, 502, 503, 504}


class SpeechError(Exception):
    def __init__(self, status: int, detail: str) -> None:
        self.status = status
        self.detail = detail
        super().__init__(detail)


def is_ogg(data: bytes) -> bool:
    return data.startswith(b"OggS")


def to_ogg_opus(raw: bytes, content_type: str | None = None, *, runner: Callable[..., Any] | None = None) -> bytes:
    if is_ogg(raw) or (content_type and "ogg" in content_type.lower() and is_ogg(raw)):
        if len(raw) > MAX_OGG_BYTES:
            raise SpeechError(413, "Запись длиннее лимита распознавания. Скажите короче.")
        return raw
    if content_type and "ogg" in content_type.lower() and not is_ogg(raw):
        pass
    run = runner or subprocess.run
    if runner is None and shutil.which("ffmpeg") is None:
        raise SpeechError(422, "Не удалось прочитать запись. Напишите текстом.")
    try:
        completed = run(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-i",
                "pipe:0",
                "-t",
                "30",
                "-ac",
                "1",
                "-ar",
                "48000",
                "-c:a",
                "libopus",
                "-b:a",
                "32k",
                "-f",
                "ogg",
                "pipe:1",
            ],
            input=raw,
            capture_output=True,
            timeout=20,
            check=False,
        )
    except FileNotFoundError as exc:
        raise SpeechError(422, "Не удалось прочитать запись. Напишите текстом.") from exc
    except subprocess.TimeoutExpired as exc:
        raise SpeechError(422, "Не удалось прочитать запись. Напишите текстом.") from exc
    stdout = getattr(completed, "stdout", b"") or b""
    code = getattr(completed, "returncode", 1)
    if code != 0 or not stdout.startswith(b"OggS"):
        raise SpeechError(422, "Не удалось прочитать запись. Напишите текстом.")
    if len(stdout) > MAX_OGG_BYTES:
        raise SpeechError(413, "Запись длиннее лимита распознавания. Скажите короче.")
    return stdout


def recognize(
    audio: bytes,
    content_type: str | None = None,
    *,
    transport: httpx.BaseTransport | None = None,
    runner: Callable[..., Any] | None = None,
    sleep: Callable[[float], None] | None = None,
) -> str:
    settings = get_settings()
    key = settings.yandex_speechkit_api_key.strip()
    folder = settings.yandex_folder_id.strip()
    if not key or not folder:
        raise SpeechError(503, "Распознавание не настроено. Напишите текстом.")
    ogg = to_ogg_opus(audio, content_type, runner=runner)
    params = {"lang": "ru-RU", "folderId": folder, "format": "oggopus"}
    headers = {"Authorization": f"Api-Key {key}"}
    timeout = httpx.Timeout(settings.assistant_http_timeout, connect=5.0)
    client_kwargs: dict[str, Any] = {"timeout": timeout, "trust_env": False}
    if transport is not None:
        client_kwargs["transport"] = transport
    pause = sleep or __import__("time").sleep
    retries = max(0, int(settings.assistant_http_retries))
    delay = 0.4
    with httpx.Client(**client_kwargs) as client:
        response: httpx.Response | None = None
        for attempt in range(retries + 1):
            try:
                response = client.post(settings.yandex_stt_url, params=params, headers=headers, content=ogg)
            except httpx.TimeoutException as exc:
                if attempt >= retries:
                    raise SpeechError(503, "Сеть не ответила. Напишите текстом.") from exc
                pause(delay)
                delay *= 2
                continue
            except httpx.HTTPError as exc:
                if attempt >= retries:
                    raise SpeechError(503, "Сеть не ответила. Напишите текстом.") from exc
                pause(delay)
                delay *= 2
                continue
            if response.status_code in _RETRY_STATUSES and attempt < retries:
                pause(delay)
                delay *= 2
                continue
            break
    if response is None:
        raise SpeechError(503, "Сеть не ответила. Напишите текстом.")
    if response.status_code in {401, 403}:
        log.warning("speechkit auth failed status=%s", response.status_code)
        raise SpeechError(503, "Сервис распознавания недоступен. Напишите текстом.")
    if response.status_code >= 400:
        log.warning("speechkit failed status=%s", response.status_code)
        raise SpeechError(503, "Сервис распознавания недоступен. Напишите текстом.")
    try:
        body = response.json()
    except ValueError as exc:
        raise SpeechError(503, "Сервис распознавания недоступен. Напишите текстом.") from exc
    text = body.get("result") if isinstance(body, dict) else None
    if not isinstance(text, str) or not text.strip():
        raise SpeechError(422, "Не распознано. Повторите или напишите текстом.")
    return text.strip()

import json
import time
from types import SimpleNamespace

import httpx

from app.assistant.gigachat import (
    ROOT_SHA256,
    Completion,
    GigaChatClient,
    gigachat_verify,
    reset_token_cache,
)
from app.assistant.speech import SpeechError, is_ogg, recognize, to_ogg_opus
from app.core.config import get_settings


def _settings(**overrides):
    payload = dict(
        gigachat_auth_key="aGVsbG8=",
        gigachat_scope="GIGACHAT_API_PERS",
        gigachat_model="GigaChat-2-Max",
        gigachat_fallback_model="GigaChat-2-Pro",
        gigachat_oauth_url="https://gigachat.test/oauth",
        gigachat_api_base="https://gigachat.test/api/v1",
        assistant_http_timeout=5,
        assistant_http_retries=1,
    )
    payload.update(overrides)
    return SimpleNamespace(**payload)


def _chat(content="ок", function_call=None, model="GigaChat-2-Max"):
    message = {"role": "assistant", "content": content}
    if function_call is not None:
        message["function_call"] = function_call
    return {"choices": [{"message": message, "finish_reason": "stop"}], "model": model}


def test_russian_root_is_in_verify_context():
    context = gigachat_verify()
    assert context.verify_mode.name == "CERT_REQUIRED"
    assert context.check_hostname is True
    assert ROOT_SHA256  # отпечаток сверяется внутри gigachat_verify


def test_token_is_cached_and_refreshed_before_expiry():
    reset_token_cache()
    clock = {"now": 1_700_000_000.0}
    oauth_calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth"):
            oauth_calls["n"] += 1
            assert request.headers["Authorization"] == "Basic aGVsbG8="
            assert request.headers["RqUID"]
            assert request.headers["Content-Type"].startswith("application/x-www-form-urlencoded")
            expires = int((clock["now"] + 1800) * 1000)
            return httpx.Response(200, json={"access_token": f"tok-{oauth_calls['n']}", "expires_at": expires})
        body = json.loads(request.content)
        assert body["model"] == "GigaChat-2-Max"
        assert request.headers["Authorization"].startswith("Bearer tok-")
        return httpx.Response(200, json=_chat())

    client = GigaChatClient(
        settings=_settings(),
        transport=httpx.MockTransport(handler),
        sleep=lambda _seconds: None,
        now=lambda: clock["now"],
    )
    assert client.complete([{"role": "user", "content": "привет"}]).content == "ок"
    assert client.complete([{"role": "user", "content": "ещё"}]).content == "ок"
    assert oauth_calls["n"] == 1
    clock["now"] += 1750
    client.complete([{"role": "user", "content": "снова"}])
    assert oauth_calls["n"] == 2
    reset_token_cache()


def test_retries_fallback_model_and_unauthorized(monkeypatch):
    reset_token_cache()
    sleeps: list[float] = []
    seen_models: list[str] = []
    state = {"chat": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth"):
            return httpx.Response(200, json={"access_token": "tok", "expires_at": int((time.time() + 1800) * 1000)})
        state["chat"] += 1
        body = json.loads(request.content)
        seen_models.append(body["model"])
        if state["chat"] == 1:
            return httpx.Response(503, json={"error": "busy"})
        if body["model"] == "GigaChat-2-Max":
            return httpx.Response(404, json={"error": "model not found"})
        return httpx.Response(200, json=_chat("готово", model=body["model"]))

    client = GigaChatClient(
        settings=_settings(assistant_http_retries=1),
        transport=httpx.MockTransport(handler),
        sleep=sleeps.append,
        now=time.time,
    )
    result = client.complete([{"role": "user", "content": "x"}], functions=[{"name": "week_outlook", "parameters": {}}])
    assert isinstance(result, Completion)
    assert result.content == "готово"
    assert result.model == "GigaChat-2-Pro"
    assert seen_models[0] == "GigaChat-2-Max"
    assert "GigaChat-2-Pro" in seen_models
    assert sleeps
    reset_token_cache()
    del monkeypatch


def test_ogg_goes_to_speechkit_without_ffmpeg(monkeypatch):
    monkeypatch.setenv("YANDEX_SPEECHKIT_API_KEY", "ya-key")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder-1")
    get_settings.cache_clear()

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params["lang"] == "ru-RU"
        assert request.url.params["folderId"] == "folder-1"
        assert request.url.params["format"] == "oggopus"
        assert request.headers["Authorization"] == "Api-Key ya-key"
        assert request.content.startswith(b"OggS")
        return httpx.Response(200, json={"result": "что горит на этой неделе"})

    def runner(*_args, **_kwargs):
        raise AssertionError("ogg не надо конвертировать")

    text = recognize(
        b"OggS" + b"a" * 40,
        "audio/ogg",
        transport=httpx.MockTransport(handler),
        runner=runner,
        sleep=lambda _seconds: None,
    )
    assert text == "что горит на этой неделе"
    get_settings.cache_clear()


def test_webm_is_converted_and_errors_are_plain(monkeypatch):
    monkeypatch.setenv("YANDEX_SPEECHKIT_API_KEY", "ya-key")
    monkeypatch.setenv("YANDEX_FOLDER_ID", "folder-1")
    get_settings.cache_clear()
    seen: list[list[str]] = []

    def runner(cmd, input, capture_output, timeout, check):
        seen.append(cmd)
        assert b"webm" in input
        assert "libopus" in cmd
        assert "-t" in cmd and "30" in cmd
        return SimpleNamespace(returncode=0, stdout=b"OggSconverted")

    def empty(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"result": "  "})

    try:
        recognize(b"webm-bytes", "audio/webm", transport=httpx.MockTransport(empty), runner=runner, sleep=lambda _s: None)
    except SpeechError as exc:
        assert exc.status == 422
        assert "Не распознано" in exc.detail
    else:
        raise AssertionError("пустой результат должен быть ошибкой")
    assert seen

    def denied(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "no"})

    try:
        recognize(b"OggSxxx", "audio/ogg", transport=httpx.MockTransport(denied), runner=runner, sleep=lambda _s: None)
    except SpeechError as exc:
        assert exc.status == 503
        assert "недоступен" in exc.detail
    else:
        raise AssertionError("403 должен стать понятной ошибкой")

    try:
        to_ogg_opus(b"OggS" + b"b" * 1_000_000)
    except SpeechError as exc:
        assert exc.status == 413
    else:
        raise AssertionError("слишком длинный ogg")
    assert is_ogg(b"OggSabc")
    get_settings.cache_clear()

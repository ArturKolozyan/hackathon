"""FakeGigaChat: проигрывает заранее записанные ответы модели и запоминает, что ей отправили."""

from __future__ import annotations

import json

from app.assistant.gigachat import Completion, GigaChatError, ToolCall


class FakeGigaChat:
    def __init__(self, *script) -> None:
        # Элемент сценария: ToolCall (вызов функции), str (текст ответа) или Exception.
        self.script = list(script)
        self.calls: list[dict] = []

    def complete(self, messages, functions=None):
        self.calls.append({"messages": [dict(item) for item in messages], "functions": functions})
        if not self.script:
            return Completion(content="Готово.", tool_call=None, model="fake")
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        if isinstance(step, ToolCall):
            return Completion(content="", tool_call=step, model="fake")
        return Completion(content=str(step), tool_call=None, model="fake")

    def function_results(self) -> list[dict]:
        """Все ответы инструментов, которые модель получила (role=function), как JSON."""
        last = self.calls[-1]["messages"] if self.calls else []
        return [json.loads(item["content"]) for item in last if item.get("role") == "function"]

    def system(self) -> str:
        return next(item["content"] for item in self.calls[0]["messages"] if item["role"] == "system")


def use(monkeypatch, fake: FakeGigaChat) -> FakeGigaChat:
    from app.core.config import get_settings

    monkeypatch.setenv("GIGACHAT_AUTH_KEY", "test-key")
    get_settings.cache_clear()
    monkeypatch.setattr("app.assistant.chat.GigaChatClient", lambda *args, **kwargs: fake)
    return fake


__all__ = ["FakeGigaChat", "GigaChatError", "ToolCall", "use"]

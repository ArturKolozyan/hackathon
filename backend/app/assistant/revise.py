"""Короткая правка уже показанной карточки, без нового вызова модели."""

from __future__ import annotations

import re

from app.assistant.intents import _amount, _day, _pair, _responsible


def try_revise(text: str) -> dict | None:
    raw, low = _pair(text)
    low = low.rstrip("?!., ")
    if re.match(r"(?:создай|добавь|отметь|закрой|архивируй|удали|что|сколько|кто|покажи)\b", low):
        return None
    updates: dict = {}
    if re.search(r"сумм|руб|доллар|евро|usd|eur|₽|\$|€", low):
        amount, currency, _rest = _amount(raw)
        if amount:
            updates["amount"] = amount
        if currency:
            updates["currency"] = currency
    if re.search(r"день|числ|кажд", low):
        day, _blanked = _day(raw)
        if day is None:
            found = re.search(r"\b(\d{1,2})\b", raw)
            if found and 1 <= int(found.group(1)) <= 31:
                day = int(found.group(1))
        if day is not None:
            updates["day_of_month"] = day
    if re.search(r"ответствен|отвечает", low):
        name = _responsible(raw, low)
        if name:
            updates["responsible_name"] = name
    quoted = re.search(r'"([^"]{1,200})"', raw)
    if quoted and "назван" in low:
        updates["title"] = quoted.group(1).strip()
    if not updates:
        return None
    return updates

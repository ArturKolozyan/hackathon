"""Разбор коротких фраз без модели. Неуверенное — None, дальше решает GigaChat.

Слоты не исполняются. Числа и имена здесь только из текста пользователя.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from app.assistant.dates import extract_month, month_mentioned, parse_explicit_start

_CURRENCY = (
    (r"руб(?:\.|лей|ля|ль)?|₽", "RUB"),
    (r"доллар(?:ов|а)?|usd|\$", "USD"),
    (r"евро|eur|€", "EUR"),
)
_CURRENCY_GROUP = "|".join(pattern for pattern, _code in _CURRENCY)
_AMOUNT_RE = re.compile(rf"(?<![\d.,])(\d+(?:[.,]\d{{1,2}})?)\s*({_CURRENCY_GROUP})?", re.IGNORECASE)
_DAY_RES = (
    re.compile(r"кажд(?:ое|ый|ую)\s+(\d{1,2})(?:\s*-?\s*(?:е|го|ое))?(?:\s+числ[оа])?", re.IGNORECASE),
    re.compile(r"(\d{1,2})\s*-\s*(?:го|е|ое)\b", re.IGNORECASE),
    re.compile(r"(\d{1,2})\s+числ[оа]", re.IGNORECASE),
)
_RESP_RE = re.compile(
    r"(?:ответственн\w*|отвечает|платит)\s+(?:за\s+)?([A-Za-zА-ЯЁа-яё][\w\-]+(?:\s+[A-Za-zА-ЯЁа-яё][\w\-]+)?)",
    re.IGNORECASE,
)
_UNSUPPORTED_RE = re.compile(
    r"еженедел|раз в (?:\d+\s+|две\s+)?недел|кажд(?:ую|ый)\s+недел|ежеднев|раз в день|кажд(?:ый|ого) дн",
    re.IGNORECASE,
)
_PERIODICITY = (
    (re.compile(r"ежеквартал|раз в квартал|кажд\w* квартал", re.IGNORECASE), "quarterly", None),
    (re.compile(r"раз в полгода|кажд\w* полгода|раз в пол года", re.IGNORECASE), "semiannual", None),
    (re.compile(r"ежегод|раз в год|кажд\w* год", re.IGNORECASE), "yearly", None),
    (re.compile(r"разово|один раз|однократно", re.IGNORECASE), "once", None),
)
_EVERY_N = re.compile(r"(?:раз в|кажд\w*)\s+(\d{1,2})\s+месяц", re.IGNORECASE)


@dataclass
class Intent:
    kind: str
    slots: dict = field(default_factory=dict)


def _pair(text: str) -> tuple[str, str]:
    raw = text.strip().replace("«", '"').replace("»", '"').replace("ё", "е").replace("Ё", "Е")
    raw = re.sub(r"\s+", " ", raw)
    return raw, raw.lower()


def _blank(text: str, match: re.Match[str]) -> str:
    return text[: match.start()] + (" " * (match.end() - match.start())) + text[match.end() :]


def _currency(token: str | None) -> str | None:
    if not token:
        return None
    for pattern, code in _CURRENCY:
        if re.fullmatch(pattern, token, flags=re.IGNORECASE):
            return code
    return None


def _day(text: str) -> tuple[int | None, str]:
    for pattern in _DAY_RES:
        match = pattern.search(text)
        if match is None:
            continue
        day = int(match.group(1))
        if 1 <= day <= 31:
            return day, _blank(text, match)
    return None, text


def _amount(text: str) -> tuple[str | None, str | None, str]:
    match = _AMOUNT_RE.search(text)
    if match is None:
        return None, None, text
    number = match.group(1).replace(",", ".")
    if number.startswith("0") and not number.startswith("0."):
        return None, None, text
    return number, _currency(match.group(2)), _blank(text, match)


def _responsible(raw: str, low: str) -> str | None:
    if re.search(r"\b(на меня|ответственный я|я ответствен)\b", low):
        return "__self__"
    match = _RESP_RE.search(raw)
    if match is None:
        return None
    name = match.group(1).strip(" .,")
    if name.lower() in {"за", "на", "я"}:
        return "__self__" if name.lower() == "я" else None
    return name


def _title_from(raw: str) -> str | None:
    quoted = re.search(r'"([^"]{1,200})"', raw)
    if quoted:
        title = quoted.group(1).strip()
        return title or None
    cut = re.split(
        r"\s+(?:на\s+)?\d|\s+кажд|\s+ответствен|\s+отвечает|\s+платит|,",
        raw,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0]
    title = cut.strip(" .,:;\"")
    title = re.sub(r"^(?:платеж|шаблон)\s+", "", title, flags=re.IGNORECASE).strip()
    title = re.sub(r"\s+на$", "", title, flags=re.IGNORECASE).strip()
    return title or None


def _query_tail(fragment: str) -> str:
    text = fragment.strip(" .,:;\"?!")
    text = re.sub(r"^(?:платеж|шаблон|период)\s+", "", text, flags=re.IGNORECASE).strip()
    return text


def _split_period(fragment: str, today: date) -> tuple[str, tuple[int, int] | None]:
    match = re.search(r"\s+за\s+(.+)$", fragment, flags=re.IGNORECASE)
    if match is None:
        return _query_tail(fragment), None
    period_text = match.group(1)
    if not month_mentioned(period_text) and not re.search(r"месяц|январ|феврал|март|апрел|ма[йяе]|июн|июл|август|сентябр|октябр|ноябр|декабр", period_text, re.I):
        return _query_tail(fragment), None
    return _query_tail(fragment[: match.start()]), extract_month(period_text, today)


def _parse_unpaid(raw: str, today: date) -> Intent | None:
    match = re.match(
        r"(?:верни|отмени оплату|сними оплату|сними отметку(?: оплаты)?)\s+(?:с\s+|у\s+)?(?:период\s+)?(?:платеж\w*\s+)?(.+?)(?:\s+в\s+(?:неоплачен\w*|инбокс))?$",
        raw,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    query, period = _split_period(match.group(1), today)
    if not query:
        return Intent("clarify", {"text": "Какой платёж вернуть в неоплаченные?"})
    slots: dict = {"query": query}
    if period is not None:
        slots["year"], slots["month"] = period
    return Intent("mark_unpaid", slots)


def parse_intent(text: str, today: date) -> Intent | None:
    """Только явные команды. Вопросы о данных и продукте разбирает модель с инструментами."""
    raw, low = _pair(text)
    low = low.rstrip("?!., ")
    if not low:
        return None
    if re.fullmatch(r"(?:что (?:ты |вы )?(?:умеешь|умеете|можешь|можете)|помощь|help|справка|что ты такое|кто ты)", low):
        return Intent("capabilities")
    if re.fullmatch(r"(?:очисти|очистить|сотри|удали)\s+(?:чат|историю|переписку)(?:\s+чата)?", low):
        return Intent("clear")
    if _UNSUPPORTED_RE.search(low) and re.search(r"платеж|создай|добавь|заведи|новый", low):
        return Intent("unsupported_frequency")
    unpaid = _parse_unpaid(raw, today)
    if unpaid is not None:
        return unpaid
    updated = _parse_update(raw)
    if updated is not None:
        return updated
    archived = re.match(
        r"(?:архивируй(?:\s+(?:платеж|шаблон))?|(?:удали|убери)\s+(?:платеж|шаблон))\s+(.+)$",
        raw,
        flags=re.IGNORECASE,
    )
    if archived:
        return Intent("archive", {"query": _query_tail(archived.group(1))})
    paid = _parse_paid(raw, today)
    if paid is not None:
        return paid
    if re.match(r"(?:создай|добавь|заведи|новый)\b", low) and "платеж" in low:
        return _parse_create(raw, low, today)
    return None


def _parse_update(raw: str) -> Intent | None:
    amount = re.search(
        rf"(?:измени|поменяй|смени|поставь)\s+сумм\w*\s+(?:платежа\s+|у\s+)?(.+?)\s+на\s+(\d+(?:[.,]\d{{1,2}})?)\s*({_CURRENCY_GROUP})?",
        raw,
        flags=re.IGNORECASE,
    )
    if amount:
        return Intent(
            "update",
            {
                "query": _query_tail(amount.group(1)),
                "amount": amount.group(2).replace(",", "."),
                "currency": _currency(amount.group(3)),
            },
        )
    day = re.search(
        r"(?:измени|поменяй|смени)\s+день\s+(?:платежа\s+)?(.+?)\s+на\s+(\d{1,2})\b",
        raw,
        flags=re.IGNORECASE,
    )
    if day:
        return Intent("update", {"query": _query_tail(day.group(1)), "day_of_month": int(day.group(2))})
    person = re.search(
        r"(?:измени|поменяй|смени)\s+ответственн\w*\s+(?:за\s+|у\s+)?(.+?)\s+на\s+([A-Za-zА-ЯЁа-яё][\w\-]+(?:\s+[A-Za-zА-ЯЁа-яё][\w\-]+)?)",
        raw,
        flags=re.IGNORECASE,
    )
    if person:
        return Intent(
            "update",
            {"query": _query_tail(person.group(1)), "responsible_name": person.group(2).strip(" .,")},
        )
    return None


def _parse_paid(raw: str, today: date) -> Intent | None:
    low = raw.lower()
    if re.match(r"^(?:что|какие|сколько|кто|покажи)\b", low):
        return None
    if re.fullmatch(r"(?:отметь|закрой|погаси)\s+оплачен\w*", low):
        return Intent("clarify", {"text": "Какой платёж отметить оплаченным?"})
    close = re.match(r"(?:закрой|погаси)\s+(?:период\s+)?(?:платеж\s+)?(.+)$", raw, flags=re.IGNORECASE)
    if close and "оплачен" not in low:
        query, period = _split_period(close.group(1), today)
        if not query:
            return Intent("clarify", {"text": "Какой платёж отметить оплаченным?"})
        slots: dict = {"query": query}
        if period is not None:
            slots["year"], slots["month"] = period
        return Intent("mark_paid", slots)
    match = re.match(
        r"(?:отметь|закрой|погаси)\s+(?:период\s+)?(?:платеж\s+)?(.+?)\s+оплачен\w*\s*$",
        raw,
        flags=re.IGNORECASE,
    )
    if match is None:
        match = re.match(r"(.+?)\s+оплачен[аоы]?\s*$", raw, flags=re.IGNORECASE)
        if match and re.match(r"^(?:что|какие|сколько|кто|покажи)\b", match.group(1), flags=re.IGNORECASE):
            return None
    if match is None:
        return None
    query, period = _split_period(match.group(1), today)
    if not query:
        return Intent("clarify", {"text": "Какой платёж отметить оплаченным?"})
    slots: dict = {"query": query}
    if period is not None:
        slots["year"], slots["month"] = period
    return Intent("mark_paid", slots)


def _parse_create(raw: str, low: str, today: date) -> Intent:
    tail = re.split(r"платеж\s+", raw, maxsplit=1, flags=re.IGNORECASE)[-1]
    day, without_day = _day(tail)
    amount, currency, _rest = _amount(without_day)
    title = _title_from(tail if '"' in tail else without_day)
    responsible = _responsible(raw, low)
    missing: list[str] = []
    if not title:
        missing.append("название")
    if not amount:
        missing.append("сумму")
    elif not currency:
        missing.append("валюту (RUB, USD или EUR)")
    if day is None:
        missing.append("день месяца")
    elif not 1 <= day <= 31:
        missing.append("день месяца от 1 до 31")
    if not responsible:
        missing.append("ответственного")
    if missing:
        return Intent("clarify", {"text": "Чтобы создать платёж, не хватает: " + ", ".join(missing) + "."})
    starts = parse_explicit_start(low, today) or today
    periodicity, interval = _periodicity(low)
    return Intent(
        "create",
        {
            "title": title,
            "amount": amount,
            "currency": currency,
            "day_of_month": day,
            "responsible_name": responsible,
            "starts_on": starts.isoformat(),
            "periodicity": periodicity,
            "interval_months": interval,
        },
    )


def _periodicity(low: str) -> tuple[str, int | None]:
    every = _EVERY_N.search(low)
    if every:
        return "every_n", int(every.group(1))
    for pattern, kind, interval in _PERIODICITY:
        if pattern.search(low):
            return kind, interval
    return "monthly", None

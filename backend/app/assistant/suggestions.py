"""Три подсказки-вопроса под ответом Кипа.

Модель дописывает в конце ответа строку `>>> вопрос | вопрос | вопрос`; бэкенд её
вырезает, чистит и доводит до ровно трёх коротких вопросов. Нет строки или модель
не ответила — подставляем вопросы по роли и по инструментам, которые звучали в ходе.
"""

from __future__ import annotations

import re

from app.services.access import RANK

MAX_LEN = 40
MARK = ">>>"
_LINE = re.compile(r"^\s*(?:>{3}|подсказки\s*:)\s*(.+?)\s*$", re.IGNORECASE | re.MULTILINE)

START = {
    "member": ["Что оплатить на этой неделе?", "Средний чек за прошлый месяц", "Сколько долга в рублях?"],
    "admin": ["Что оплатить завтра?", "Средний чек за прошлый месяц", "Кто что менял сегодня?"],
    "owner": ["Сравни отделы за этот месяц", "Средний чек за прошлый месяц", "Сколько долга в рублях?"],
}
AFTER = {
    "query_operations": ["А в рублях?", "Сравни с прошлым месяцем", "Покажи по отделам"],
    "get_payment": ["Когда следующий срок?", "Есть ли просрочки?", "Сколько заплатили за год?"],
    "get_budget": ["Что ещё к оплате?", "Сравни с прошлым месяцем", "Покажи по платежам"],
    "product_help": ["Что ещё ты умеешь?", "Как работают напоминания?", "Как приложить чек?"],
    "list_people": ["У кого больше всего долгов?", "Кто не привязал Telegram?", "Что висит на мне?"],
    "get_audit": ["А за вчера?", "Кто отмечал оплаты?", "Что менял я?"],
}
ADMIN_ONLY_HINTS = ("менял", "логи", "людей", "кто в отделе", "telegram")


def _fits(text: str, role: str) -> bool:
    if RANK.get(role, 1) >= RANK["admin"]:
        return True
    low = text.lower()
    return not any(word in low for word in ADMIN_ONLY_HINTS)


def clean(items: list[str], role: str) -> list[str]:
    out: list[str] = []
    for raw in items:
        text = re.sub(r"\s+", " ", str(raw)).strip(" -•*\"«»'`")
        if not text or len(text) > MAX_LEN or not re.search(r"[а-яё]", text, re.IGNORECASE):
            continue
        if not _fits(text, role):
            continue
        if text.lower() not in {item.lower() for item in out}:
            out.append(text)
    return out


def split(content: str) -> tuple[str, list[str]]:
    """Ответ модели → (текст без строки подсказок, сырые подсказки)."""
    found = list(_LINE.finditer(content or ""))
    if not found:
        return content, []
    last = found[-1]
    body = (content[: last.start()] + content[last.end() :]).rstrip()
    return body, [part for part in re.split(r"\s*\|\s*", last.group(1)) if part]


def defaults(role: str, tools_used: list[str] | None = None) -> list[str]:
    key = role if role in START else "member"
    pool: list[str] = []
    for name in reversed(tools_used or []):
        pool += AFTER.get(name, [])
    pool += START[key] + START["member"]
    return clean(pool, role)[:3]


def finish(role: str, proposed: list[str], tools_used: list[str] | None = None) -> list[str]:
    picked = clean(proposed, role)[:3]
    for item in defaults(role, tools_used):
        if len(picked) >= 3:
            break
        if item.lower() not in {row.lower() for row in picked}:
            picked.append(item)
    return picked[:3]

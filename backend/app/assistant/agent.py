"""Цикл Кипа: модель вызывает инструменты по шагам, затем пишет ответ по их данным.

GigaChat за один ответ возвращает не больше одного function_call. Поэтому:
до MAX_STEPS шагов, результат каждого — сообщением role=function (компактный JSON),
а несколько подвопросов модель собирает в один пакет query_operations(queries=[...]).
"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.assistant import answers, tools
from app.assistant.gigachat import GigaChatError
from app.assistant.guide import help_text
from app.models import AssistantAction
from app.services import humanize

log = logging.getLogger("invoice_keeper.assistant")

MAX_STEPS = 5
TURN_BUDGET = 25.0
RESULT_LIMIT = 2000
FALLBACK = "Не понял запрос. Спросите, например: «что оплатить на этой неделе?» или «что вы умеете?»"
DOWN = "Кип сейчас не может связаться с моделью. Попробуйте через минуту."

Result = tuple[str, AssistantAction | None]
LABELS = {"sum": "сумма", "avg": "средний чек", "min": "минимум", "max": "максимум"}


def compact(data: Any, limit: int = RESULT_LIMIT) -> str:
    """JSON для модели не длиннее limit: сначала режем строки и группы, потом остальное."""
    text = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    if len(text) <= limit:
        return text
    trimmed = json.loads(text)
    targets = trimmed.get("results", [trimmed]) if isinstance(trimmed, dict) else []
    for keep in (10, 6, 3, 1, 0):
        for item in targets:
            if not isinstance(item, dict):
                continue
            for key in ("rows", "groups", "periods", "available"):
                if isinstance(item.get(key), list) and len(item[key]) > keep:
                    item[f"{key}_cut"] = item.get(f"{key}_cut", 0) + len(item[key]) - keep
                    item[key] = item[key][:keep]
            for dept in item.get("departments", []) if isinstance(item.get("departments"), list) else []:
                if isinstance(dept, dict) and isinstance(dept.get("people"), list) and len(dept["people"]) > keep:
                    dept["people"] = dept["people"][:keep]
        text = json.dumps(trimmed, ensure_ascii=False, separators=(",", ":"), default=str)
        if len(text) <= limit:
            return text
    return text[:limit]


def run(
    turn: tools.Turn,
    client,
    messages: list[dict],
    *,
    budget: float = TURN_BUDGET,
    max_steps: int = MAX_STEPS,
    used: list[str] | None = None,
) -> Result:
    """Ответ хода. В used складываются имена вызванных инструментов (для подсказок)."""
    used = used if used is not None else []
    functions = tools.functions_for(turn.ctx)
    started = time.monotonic()
    last: dict | None = None
    try:
        for _step in range(max_steps):
            if time.monotonic() - started > budget:
                break
            completion = client.complete(messages, functions=functions)
            call = completion.tool_call
            if call is None:
                content = (completion.content or "").strip()
                return content or (render(last) if last else FALLBACK), None
            used.append(call.name)
            data, card = tools.call(turn, call.name, call.arguments)
            if card is not None:
                return card
            last = data if isinstance(data, dict) else {"result": data}
            assistant: dict[str, Any] = {
                "role": "assistant",
                "content": completion.content or "",
                "function_call": {"name": call.name, "arguments": call.arguments},
            }
            if call.state_id:
                assistant["functions_state_id"] = call.state_id
            messages.append(assistant)
            messages.append({"role": "function", "name": call.name, "content": compact(last)})
        # Шаги кончились: просим ответ без инструментов по уже собранным данным.
        if last is not None and time.monotonic() - started <= budget:
            final = client.complete(messages, functions=None)
            content = (final.content or "").strip()
            if content and final.tool_call is None:
                return content, None
    except GigaChatError as exc:
        log.warning("assistant model failed")
        return (render(last) if last else fallback(turn, messages, exc.detail)), None
    except Exception:
        log.exception("assistant model crashed")
        return (render(last) if last else fallback(turn, messages, DOWN)), None
    return (render(last) if last else FALLBACK), None


def _last_user(messages: list[dict]) -> str:
    for item in reversed(messages):
        if item.get("role") == "user":
            return str(item.get("content") or "")
    return ""


def fallback(turn: tools.Turn, messages: list[dict], detail: str) -> str:
    """Модель недоступна: очевидные вопросы закрываем без неё, остальное — вежливая ошибка."""
    text = _last_user(messages).lower().replace("ё", "е")
    db, ctx = turn.db, turn.ctx
    if "просроч" in text:
        return answers.overdue_text(db, ctx)
    if any(word in text for word in ("горит", "недел", "ближайш", "скоро")):
        return answers.week_text(db, ctx)
    if text.startswith(("как ", "где ", "что такое")):
        return help_text(text, ctx.role)
    return detail


def _money(value: str, currency: str) -> str:
    return humanize.money(value, currency)


def render(data: dict | None) -> str:
    """Запасной ответ по данным инструмента, если модель не дописала текст."""
    if not data:
        return FALLBACK
    if "markdown" in data:
        return str(data["markdown"])
    items = data.get("results") if isinstance(data.get("results"), list) else [data]
    blocks: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        if item.get("denied"):
            blocks.append("Нет доступа к отделам: " + ", ".join(item["denied"]) + ".")
        if "count" in item:
            title = item.get("label") or "Итог"
            lines = [f"### {str(title)[:1].upper()}{str(title)[1:]}", "", f"- Операций: **{item['count']}**"]
            for row in item.get("totals", []):
                parts = [f"{LABELS[key]} {_money(row[key], row['currency'])}" for key in LABELS if key in row]
                if parts:
                    lines.append(f"- {row['currency']}: " + ", ".join(parts))
            if item.get("rub", {}).get("total_rub"):
                lines.append(f"- Всего в рублях по курсу ЦБ: **{_money(item['rub']['total_rub'], 'RUB')}**")
            blocks.append("\n".join(lines))
        elif item.get("title"):
            blocks.append(f"### {item['title']}\n\n- Сумма: {_money(item['amount'], item['currency'])}\n- Срок: {item.get('schedule')}\n- Ответственный: {item.get('responsible') or 'не назначен'}")
        elif item.get("error"):
            blocks.append(str(item["error"]).capitalize() + ".")
    return "\n\n".join(blocks) or FALLBACK

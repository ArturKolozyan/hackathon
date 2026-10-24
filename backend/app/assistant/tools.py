"""Инструменты ассистента: одно место, где решается, что можно этому человеку.

Каждый инструмент — роль-минимум и функция над TeamContext активного отдела.
Модель видит только инструменты своей роли, а run() ещё раз проверяет роль:
вызов чужого инструмента по имени ничего не даст. Данные берутся теми же
сервисами, что и REST (list_views, budgets.report, department_access),
изменения — только карточкой с подтверждением (actions.plan → REST-функции).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from typing import Callable

from sqlalchemy.orm import Session

from app.assistant import answers
from app.assistant import match as names
from app.assistant.actions import plan
from app.assistant.guide import capabilities, help_text
from app.models import AssistantAction
from app.services import time as clock
from app.services.access import RANK, TeamContext

Result = tuple[str, AssistantAction | None]

ADMIN_ONLY = "Это может админ отдела или владелец. Отметить период оплаченным или вернуть в неоплаченные можете вы сами."
_MONTH = {"type": "string", "description": "Месяц YYYY-MM. Пусто — текущий месяц."}
_QUERY = {"type": "string", "description": "Название платежа или его часть, как сказал человек."}
_EMPTY = {"type": "object", "properties": {}}


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    parameters: dict
    role: str
    run: Callable[[Session, TeamContext, dict], Result]


def _month(arguments: dict, today: date) -> tuple[int, int]:
    raw = arguments.get("month")
    if isinstance(raw, str) and re.fullmatch(r"\d{4}-\d{2}", raw.strip()):
        year, month = (int(part) for part in raw.strip().split("-"))
        if 1 <= month <= 12:
            return year, month
    year, month = arguments.get("year"), arguments.get("month")
    if isinstance(year, int) and isinstance(month, int) and 1 <= month <= 12:
        return year, month
    return today.year, today.month


def _int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _text(arguments: dict, key: str) -> str:
    value = arguments.get(key)
    return str(value).strip() if value is not None else ""


def _read(render: Callable[[Session, TeamContext, dict], str]) -> Callable[[Session, TeamContext, dict], Result]:
    return lambda db, ctx, arguments: (render(db, ctx, arguments), None)


def _open(db: Session, ctx: TeamContext, arguments: dict) -> str:
    person = None
    name = _text(arguments, "responsible_name")
    if name:
        if name == "__self__":
            person = ctx.user
        else:
            found = names.match_users(db, name, ctx.team.id)
            if len(found) != 1:
                return answers.person_text(db, ctx, name)
            person = found[0]
    currency = _text(arguments, "currency").upper() or None
    if currency not in {None, "RUB", "USD", "EUR"}:
        currency = None
    return answers.open_text(db, ctx, person=person, currency=currency)


def _budget(db: Session, ctx: TeamContext, arguments: dict) -> str:
    today = clock.today()
    raw_year = arguments.get("year")
    if raw_year and not arguments.get("month"):
        return answers.budget_text(db, ctx, _int(raw_year, today.year), None)
    year, month = _month(arguments, today)
    return answers.budget_text(db, ctx, year, month)


def _paid_slots(arguments: dict) -> dict:
    slots: dict = {"query": arguments.get("query")}
    month = arguments.get("month")
    if isinstance(month, str) and re.fullmatch(r"\d{4}-\d{2}", month.strip()):
        year, mon = month.strip().split("-")
        slots["year"], slots["month"] = int(year), int(mon)
    elif isinstance(arguments.get("year"), int) and isinstance(month, int):
        slots["year"], slots["month"] = arguments["year"], month
    return slots


def _create(db: Session, ctx: TeamContext, arguments: dict) -> Result:
    slots = {
        "title": arguments.get("title"),
        "amount": arguments.get("amount"),
        "currency": arguments.get("currency"),
        "day_of_month": arguments.get("day_of_month"),
        "responsible_name": arguments.get("responsible_name"),
        "starts_on": arguments.get("starts_on") or clock.today().isoformat(),
        "periodicity": arguments.get("periodicity") or "monthly",
        "interval_months": arguments.get("interval_months"),
    }
    return plan(db, ctx, "create", slots)


TOOLS: tuple[Tool, ...] = (
    Tool(
        "week_outlook",
        "Что горит на этой неделе: просроченные и сроки до воскресенья.",
        _EMPTY,
        "member",
        _read(lambda db, ctx, a: answers.week_text(db, ctx)),
    ),
    Tool(
        "list_overdue",
        "Просроченные неоплаченные периоды и сумма просрочки по валютам.",
        _EMPTY,
        "member",
        _read(lambda db, ctx, a: answers.overdue_text(db, ctx)),
    ),
    Tool(
        "list_open",
        "Все неоплаченные периоды с итогами по валютам. Можно сузить до ответственного или валюты.",
        {
            "type": "object",
            "properties": {
                "responsible_name": {"type": "string", "description": "Имя ответственного. «__self__» — сам пользователь."},
                "currency": {"type": "string", "description": "RUB, USD или EUR"},
            },
        },
        "member",
        _read(_open),
    ),
    Tool(
        "upcoming_payments",
        "Платежи со сроком в ближайшие N дней (по умолчанию 14).",
        {"type": "object", "properties": {"days": {"type": "integer", "description": "Сколько дней вперёд, 1–92"}}},
        "member",
        _read(lambda db, ctx, a: answers.upcoming_text(db, ctx, _int(a.get("days"), 14))),
    ),
    Tool(
        "department_summary",
        "Сводка отдела по валютам: просрочено, к оплате, оплачено за текущий месяц, ближайший срок.",
        _EMPTY,
        "member",
        _read(lambda db, ctx, a: answers.totals_text(db, ctx)),
    ),
    Tool(
        "month_spending",
        "Сколько оплачено и сколько ещё не оплачено за месяц, по валютам.",
        {"type": "object", "properties": {"month": _MONTH}},
        "member",
        _read(lambda db, ctx, a: answers.spending_text(db, ctx, *_month(a, clock.today()))),
    ),
    Tool(
        "paid_history",
        "Что оплачено за месяц: платёж, сумма, дата оплаты и кто отметил.",
        {"type": "object", "properties": {"month": _MONTH}},
        "member",
        _read(lambda db, ctx, a: answers.paid_month_text(db, ctx, *_month(a, clock.today()))),
    ),
    Tool(
        "monthly_stats",
        "Статистика отдела по месяцам: оплачено, не оплачено, сколько с опозданием.",
        {"type": "object", "properties": {"months": {"type": "integer", "description": "Сколько последних месяцев, 1–12"}}},
        "member",
        _read(lambda db, ctx, a: answers.months_text(db, ctx, _int(a.get("months"), 6))),
    ),
    Tool(
        "departments_stats",
        "Сравнение отделов, доступных пользователю: просрочено, к оплате, оплачено за месяц.",
        _EMPTY,
        "member",
        _read(lambda db, ctx, a: answers.departments_text(db, ctx)),
    ),
    Tool(
        "budget_status",
        "Бюджет отдела: план, оплачено, ещё к оплате и остаток по валютам за месяц или год.",
        {
            "type": "object",
            "properties": {"month": _MONTH, "year": {"type": "integer", "description": "Год, если нужен годовой бюджет"}},
        },
        "member",
        _read(_budget),
    ),
    Tool(
        "payment_details",
        "Карточка регулярного платежа: сумма, расписание, ответственный и история последних периодов.",
        {"type": "object", "properties": {"query": _QUERY}, "required": ["query"]},
        "member",
        _read(lambda db, ctx, a: answers.payment_text(db, ctx, _text(a, "query"))),
    ),
    Tool(
        "find_responsible",
        "Кто ответственный за платёж.",
        {"type": "object", "properties": {"query": _QUERY}, "required": ["query"]},
        "member",
        _read(lambda db, ctx, a: answers.responsible_text(db, ctx, _text(a, "query"))),
    ),
    Tool(
        "person_payments",
        "Открытые платежи конкретного человека отдела.",
        {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"]},
        "member",
        _read(lambda db, ctx, a: answers.person_text(db, ctx, _text(a, "name"))),
    ),
    Tool(
        "list_templates",
        "Список регулярных платежей отдела (шаблонов): сумма, расписание, ответственный.",
        {"type": "object", "properties": {"archived": {"type": "boolean", "description": "true — показать архив"}}},
        "member",
        _read(lambda db, ctx, a: answers.templates_text(db, ctx, archived=bool(a.get("archived")))),
    ),
    Tool(
        "list_people",
        "Люди отдела: роль, привязан ли Telegram, сколько открытых платежей.",
        _EMPTY,
        "admin",
        _read(lambda db, ctx, a: answers.people_text(db, ctx)),
    ),
    Tool(
        "product_help",
        (
            "Как пользоваться rekeeper. topic: inbox, templates, export, telegram, reminders, budget, "
            "stats, history, calendar, receipts, people, assistant."
        ),
        {"type": "object", "properties": {"topic": {"type": "string"}}, "required": ["topic"]},
        "member",
        _read(lambda db, ctx, a: help_text(_text(a, "topic"), ctx.role)),
    ),
    Tool(
        "propose_mark_paid",
        "Карточка «отметить период оплаченным». Ничего не записывает до подтверждения. month — YYYY-MM, если назван.",
        {"type": "object", "properties": {"query": _QUERY, "month": _MONTH}, "required": ["query"]},
        "member",
        lambda db, ctx, a: plan(db, ctx, "mark_paid", _paid_slots(a)),
    ),
    Tool(
        "propose_mark_unpaid",
        "Карточка «вернуть оплаченный период в неоплаченные». Ничего не меняет до подтверждения.",
        {"type": "object", "properties": {"query": _QUERY, "month": _MONTH}, "required": ["query"]},
        "member",
        lambda db, ctx, a: plan(db, ctx, "mark_unpaid", _paid_slots(a)),
    ),
    Tool(
        "propose_create_payment",
        (
            "Карточка создания регулярного платежа. Ничего не записывает до подтверждения. "
            "Валюта RUB, USD или EUR. periodicity: monthly, quarterly, semiannual, yearly, once или every_n "
            "(тогда interval_months). starts_on — дата первой оплаты YYYY-MM-DD."
        ),
        {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "amount": {"type": "string"},
                "currency": {"type": "string"},
                "day_of_month": {"type": "integer"},
                "starts_on": {"type": "string", "description": "YYYY-MM-DD"},
                "periodicity": {"type": "string"},
                "interval_months": {"type": "integer"},
                "responsible_name": {"type": "string"},
            },
            "required": ["title", "amount", "currency", "responsible_name"],
        },
        "admin",
        _create,
    ),
    Tool(
        "propose_update_payment",
        "Карточка изменения шаблона: сумма, валюта, день, название или ответственный. Не записывает до подтверждения.",
        {
            "type": "object",
            "properties": {
                "query": _QUERY,
                "amount": {"type": "string"},
                "currency": {"type": "string"},
                "day_of_month": {"type": "integer"},
                "responsible_name": {"type": "string"},
                "title": {"type": "string"},
            },
            "required": ["query"],
        },
        "admin",
        lambda db, ctx, a: plan(db, ctx, "update", dict(a)),
    ),
    Tool(
        "propose_archive_payment",
        "Карточка архивации шаблона. Новые периоды перестанут создаваться после подтверждения.",
        {"type": "object", "properties": {"query": _QUERY}, "required": ["query"]},
        "admin",
        lambda db, ctx, a: plan(db, ctx, "archive", {"query": a.get("query")}),
    ),
)

BY_NAME = {tool.name: tool for tool in TOOLS}

# Быстрый разбор фраз (intents) идёт через те же инструменты и ту же проверку роли.
INTENT_TOOL = {
    "week": "week_outlook",
    "overdue": "list_overdue",
    "open": "list_open",
    "upcoming": "upcoming_payments",
    "summary": "department_summary",
    "spending": "month_spending",
    "paid_month": "paid_history",
    "stats": "monthly_stats",
    "departments": "departments_stats",
    "budget": "budget_status",
    "details": "payment_details",
    "responsible": "find_responsible",
    "person": "person_payments",
    "templates": "list_templates",
    "people": "list_people",
    "help": "product_help",
    "mark_paid": "propose_mark_paid",
    "mark_unpaid": "propose_mark_unpaid",
    "update": "propose_update_payment",
    "archive": "propose_archive_payment",
}


def allowed(ctx: TeamContext, tool: Tool) -> bool:
    return bool(ctx.user.is_active) and RANK[ctx.role] >= RANK[tool.role]


def functions_for(ctx: TeamContext) -> list[dict]:
    return [
        {"name": tool.name, "description": tool.description, "parameters": tool.parameters}
        for tool in TOOLS
        if allowed(ctx, tool)
    ]


def run(db: Session, ctx: TeamContext, name: str, arguments: dict) -> Result:
    tool = BY_NAME.get(name)
    if tool is None:
        return "Не понял запрос. Сформулируйте проще или спросите, что я умею.", None
    if not allowed(ctx, tool):
        return ADMIN_ONLY, None
    return tool.run(db, ctx, arguments if isinstance(arguments, dict) else {})


def run_intent(db: Session, ctx: TeamContext, kind: str, slots: dict) -> Result:
    if kind == "capabilities":
        return capabilities(ctx.role), None
    if kind == "create":
        # Создание идёт через plan: там понятный отказ участнику и проверка полей.
        if not any(allowed(ctx, tool) for tool in TOOLS if tool.name == "propose_create_payment"):
            return ADMIN_ONLY, None
        return plan(db, ctx, "create", slots)
    if kind in {"clarify", "unsupported_frequency"}:
        return plan(db, ctx, kind, slots)
    name = INTENT_TOOL.get(kind)
    if name is None:
        return "Не понял запрос. Сформулируйте проще или спросите, что я умею.", None
    return run(db, ctx, name, slots)

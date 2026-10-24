"""Инструменты Кипа: одно место, где решается, что можно этому человеку.

Чтение возвращает компактный JSON для модели (query.py, карточка платежа, бюджет,
люди, логи, справка). Изменения — только карточкой с подтверждением (actions.plan).
Модель видит только инструменты своей роли, а run() ещё раз проверяет роль и
отделы: вызов чужого инструмента по имени ничего не даст.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from decimal import Decimal
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.assistant import match as names
from app.assistant.actions import plan
from app.assistant.answers import ROLE_RU, template_cadence
from app.assistant.dates import parse_day, resolve_period
from app.assistant.guide import capabilities, help_text
from app.assistant.query import Scope, query_operations
from app.models import AssistantAction
from app.services import time as clock
from app.services.access import RANK, TeamContext
from app.services.budgets import report as budget_report
from app.services.teams import list_member_rows

ADMIN_ONLY = "Это может админ отдела или владелец. Отметить счёт оплаченным или вернуть в неоплаченные можете вы сами."
_QUERY = {"type": "string", "description": "Название платежа или его часть, как сказал человек."}
_MONTH = {"type": "string", "description": "Месяц периода YYYY-MM. Пусто — самый ранний неоплаченный."}
_DEPT = {"type": "string", "description": "Название отдела. Пусто — текущий отдел."}

Card = tuple[str, AssistantAction | None]


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    role: str
    run: Callable[[Session, TeamContext, dict, Scope], Any]
    action: bool = False
    examples: list[dict] = field(default_factory=list)


@dataclass
class Turn:
    """Кеш на один ход: доступ к отделам и выборка периодов считаются один раз."""

    db: Session
    ctx: TeamContext
    scope: Scope | None = None

    def get_scope(self) -> Scope:
        if self.scope is None:
            self.scope = Scope(self.db, self.ctx)
        return self.scope


def _text(arguments: dict, key: str) -> str:
    value = arguments.get(key)
    return str(value).strip() if value is not None else ""


def _money(value: Any) -> str:
    return f"{Decimal(str(value)):.2f}"


# ---------- чтение ----------

_OPS_QUERY: dict = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "description": "Короткая подпись подвопроса, например «просрочки за сентябрь»."},
        "period": {
            "type": "string",
            "description": (
                "today, tomorrow, yesterday, this_week, next_week, last_week, this_month, last_month, next_month, "
                "this_quarter, last_quarter, this_year, last_year, all, YYYY-MM, YYYY или YYYY-MM-DD. "
                "Пусто и нет date_from/date_to — без ограничения по дате."
            ),
        },
        "date_from": {"type": "string", "description": "YYYY-MM-DD включительно, вместо period."},
        "date_to": {"type": "string", "description": "YYYY-MM-DD включительно."},
        "date_field": {"type": "string", "description": "due — по сроку оплаты (по умолчанию), paid — по дате фактической оплаты."},
        "status": {
            "type": "array",
            "items": {"type": "string"},
            "description": "paid, overdue (просрочено сейчас), due_soon, upcoming, unpaid (всё неоплаченное), late (оплачено с опозданием), on_time.",
        },
        "department": {
            "type": "array",
            "items": {"type": "string"},
            "description": "Отделы по названию. [\"all\"] — все доступные. Пусто — текущий отдел.",
        },
        "currency": {"type": "array", "items": {"type": "string"}, "description": "RUB, USD, EUR"},
        "responsible": {"type": "string", "description": "Ответственный: имя или «me»."},
        "payment": {"type": "string", "description": "Название платежа или часть."},
        "group_by": {"type": "string", "description": "none, payment, department, status, currency, responsible, month, day"},
        "metrics": {"type": "array", "items": {"type": "string"}, "description": "count, sum, avg (средний чек), min, max. По умолчанию count, sum."},
        "convert_to_rub": {"type": "boolean", "description": "Добавить итог в рублях по курсу ЦБ."},
        "sort": {"type": "string", "description": "amount_desc, amount_asc, date_asc, date_desc — вместе со строками."},
        "limit": {"type": "integer", "description": "Сколько строк вернуть, до 30."},
        "include_rows": {"type": "boolean", "description": "Вернуть сами операции (название, срок, сумма, статус, кто оплатил)."},
    },
}


def _ops(db: Session, ctx: TeamContext, arguments: dict, scope: Scope) -> dict:
    return query_operations(db, ctx, arguments, scope)


def _teams(scope: Scope, department: str) -> tuple[list, list[str], list[str]]:
    wanted = [department] if department else []
    ids, denied, unknown = scope.departments(wanted)
    return [scope.access[team_id] for team_id in ids], denied, unknown


def _payment(db: Session, ctx: TeamContext, arguments: dict, scope: Scope) -> dict:
    query = _text(arguments, "query")
    if not query:
        return {"error": "не названо, какой платёж"}
    seats, denied, unknown = _teams(scope, _text(arguments, "department"))
    found = []
    for seat in seats:
        found += [(seat, row) for row in names.match_templates(db, query, seat.team_id, include_archived=True)]
    if not found and not _text(arguments, "department"):
        # В текущем отделе нет — ищем по всем доступным, чтобы не отвечать «не нашёл» зря.
        for seat in scope.access.values():
            if seat.team_id == ctx.team.id:
                continue
            found += [(seat, row) for row in names.match_templates(db, query, seat.team_id, include_archived=True)]
    out: dict[str, Any] = {}
    if denied:
        out["denied"] = denied
    if unknown:
        out["unknown_departments"] = unknown
    if not found:
        titles = [row.title for seat in seats for row in names.list_active(db, seat.team_id)][:40]
        out.update({"error": f"платёж «{query}» не найден", "available": titles})
        return out
    active = [pair for pair in found if not pair[1].is_archived]
    if len(found) > 1 and len(active) == 1:
        found = active
    if len(found) > 1:
        out["ambiguous"] = [f"{row.title} ({seat.team.name})" for seat, row in found[:10]]
        return out
    seat, template = found[0]
    periods = [item for item in scope.items() if item.recurring_payment_id == template.id]
    periods.sort(key=lambda item: item.due_date, reverse=True)
    history = []
    for item in periods[:12]:
        row: dict[str, Any] = {"period": item.period, "due": item.due_date.isoformat(), "amount": _money(item.amount), "status": item.status}
        if item.status == "paid":
            row.update(
                paid_on=item.paid_on.isoformat() if item.paid_on else None,
                paid_amount=_money(item.paid_amount) if item.paid_amount is not None else None,
                paid_by=item.paid_by.full_name if item.paid_by is not None else None,
                on_time=item.paid_on_time,
                receipt=item.receipt is not None,
            )
        elif item.status == "overdue":
            row["overdue_days"] = abs(item.days_delta)
        if item.planned:
            row["planned"] = True
        history.append(row)
    out.update(
        {
            "title": template.title,
            "department": seat.team.name,
            "amount": _money(template.amount),
            "currency": template.currency,
            "schedule": template_cadence(template),
            "responsible": template.responsible.full_name if template.responsible is not None else None,
            "archived": template.is_archived,
            "description": (template.description or None) if hasattr(template, "description") else None,
            "periods": history,
            "unpaid_count": sum(1 for item in periods if item.status != "paid"),
        }
    )
    return out


def _budget(db: Session, ctx: TeamContext, arguments: dict, scope: Scope) -> dict:
    today = clock.today()
    raw = _text(arguments, "period") or today.strftime("%Y-%m")
    if raw in {"this_year", "last_year"}:
        raw = str(today.year - (1 if raw == "last_year" else 0))
    elif not re.fullmatch(r"\d{4}(-\d{2})?", raw):
        start, _end = resolve_period(raw, today)
        raw = (start or today).strftime("%Y-%m")
    period_type = "year" if len(raw) == 4 else "month"
    department = _text(arguments, "department")
    seats, denied, unknown = _teams(scope, department)
    result: dict[str, Any] = {"period": raw, "departments": []}
    for seat in seats:
        report = budget_report(db, period_type, raw, seat.team_id)
        lines = []
        for line in report.rows:
            fact, expected = Decimal(str(line.fact_amount)), Decimal(str(line.expected_amount))
            if line.plan_amount is None and not fact and not expected:
                continue
            row: dict[str, Any] = {"currency": line.currency, "plan": None, "paid": _money(fact), "to_pay": _money(expected)}
            if line.plan_amount is not None:
                plan_amount = Decimal(str(line.plan_amount))
                row["plan"] = _money(plan_amount)
                row["left"] = _money(plan_amount - fact - expected)
            lines.append(row)
        result["departments"].append({"department": seat.team.name, "lines": lines})
    if denied:
        result["denied"] = denied
    if unknown:
        result["unknown_departments"] = unknown
    return result


def _people(db: Session, ctx: TeamContext, arguments: dict, scope: Scope) -> dict:
    seats, denied, unknown = _teams(scope, _text(arguments, "department"))
    open_by: dict = {}
    for item in scope.items():
        if item.status != "paid" and item.responsible is not None:
            open_by[(item.team_id, item.responsible.id)] = open_by.get((item.team_id, item.responsible.id), 0) + 1
    result: dict[str, Any] = {"departments": []}
    for seat in seats:
        if RANK[seat.role] < RANK["admin"]:
            denied.append(seat.team.name)
            continue
        people = []
        for row in list_member_rows(db, seat.team_id):
            person = row.user
            if person is None:
                continue
            people.append(
                {
                    "name": person.full_name,
                    "email": person.email,
                    "role": ROLE_RU.get(row.role, row.role),
                    "active": bool(person.is_active),
                    "telegram": person.telegram_user_id is not None,
                    "open_payments": open_by.get((seat.team_id, person.id), 0),
                }
            )
        result["departments"].append({"department": seat.team.name, "people": people})
    if denied:
        result["denied"] = sorted(set(denied))
    if unknown:
        result["unknown_departments"] = unknown
    return result


def _audit(db: Session, ctx: TeamContext, arguments: dict, scope: Scope) -> dict:
    from app.api.v1.audit import list_audit_logs

    today = clock.today()
    start, end = resolve_period(_text(arguments, "period"), today)
    start = parse_day(arguments.get("date_from")) or start
    end = parse_day(arguments.get("date_to")) or end
    actor = _text(arguments, "actor")
    actor_id = None
    if actor:
        found = names.match_users(db, actor, ctx.team.id)
        if fold_me(actor):
            found = [ctx.user]
        if len(found) != 1:
            return {"error": f"не понял, кто такой «{actor}»"}
        actor_id = found[0].id
    try:
        limit = max(1, min(int(arguments.get("limit") or 15), 30))
    except (TypeError, ValueError):
        limit = 15
    data = list_audit_logs(limit=limit, offset=0, date_from=start, date_to=end, actor_user_id=actor_id, action=None, ctx=ctx, db=db)
    zone = clock.zone()
    rows = []
    for item in data.items:
        meta = {key: value for key, value in (item.meta or {}).items() if key in {"title", "email", "amount", "currency", "period", "name", "role", "team", "fields"}}
        rows.append(
            {
                "at": item.at.astimezone(zone).strftime("%Y-%m-%d %H:%M"),
                "who": item.actor_name or item.actor_email or "система",
                "action": item.action,
                "details": meta,
            }
        )
    return {"total": data.total, "department": ctx.team.name, "from": start.isoformat() if start else None, "to": end.isoformat() if end else None, "rows": rows}


def fold_me(text: str) -> bool:
    return names.fold(text).strip() in {"me", "я", "мне", "меня", "__self__"}


def _help(db: Session, ctx: TeamContext, arguments: dict, scope: Scope) -> dict:
    return {"markdown": help_text(_text(arguments, "topic") or _text(arguments, "question"), ctx.role)}


# ---------- карточки (ничего не пишут до подтверждения) ----------


def _paid_slots(arguments: dict) -> dict:
    slots: dict = {"query": arguments.get("query")}
    month = arguments.get("month")
    if isinstance(month, str) and re.fullmatch(r"\d{4}-\d{2}", month.strip()):
        year, mon = month.strip().split("-")
        slots["year"], slots["month"] = int(year), int(mon)
    elif isinstance(arguments.get("year"), int) and isinstance(month, int):
        slots["year"], slots["month"] = arguments["year"], month
    return slots


def _create(db: Session, ctx: TeamContext, arguments: dict, scope: Scope | None = None) -> Card:
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
        "query_operations",
        (
            "Главный инструмент по данным: счета (периоды платежей) с фильтрами по датам, статусу, отделу, валюте, "
            "ответственному и платежу; группировка и метрики count/sum/avg/min/max по каждой валюте; пересчёт в рубли по ЦБ; "
            "сами строки. Несколько подвопросов — одним вызовом через queries: [..]."
        ),
        {
            "type": "object",
            "properties": {
                "queries": {"type": "array", "items": _OPS_QUERY, "description": "Пакет запросов, по одному на подвопрос."},
                **_OPS_QUERY["properties"],
            },
        },
        "member",
        _ops,
        examples=[
            {
                "request": "Что просрочено и сколько оплатили за прошлый месяц, средний чек?",
                "params": {
                    "queries": [
                        {"label": "просрочено сейчас", "status": ["overdue"], "include_rows": True},
                        {"label": "оплачено в прошлом месяце", "status": ["paid"], "period": "last_month", "metrics": ["count", "sum", "avg"], "group_by": "payment"},
                    ]
                },
            },
            {"request": "Что оплатить завтра?", "params": {"status": ["unpaid"], "period": "tomorrow", "include_rows": True}},
            {"request": "Сколько всего долга в рублях?", "params": {"status": ["unpaid"], "period": "all", "convert_to_rub": True}},
            {"request": "Сравни отделы за октябрь", "params": {"department": ["all"], "period": "2026-10", "group_by": "department", "metrics": ["count", "sum"]}},
        ],
    ),
    Tool(
        "get_payment",
        "Карточка регулярного платежа: сумма, расписание, ответственный, архив, история последних периодов (кто, когда и сколько оплатил, есть ли чек).",
        {"type": "object", "properties": {"query": _QUERY, "department": _DEPT}, "required": ["query"]},
        "member",
        _payment,
        examples=[{"request": "Кто отвечает за аренду и когда её платили?", "params": {"query": "аренда"}}],
    ),
    Tool(
        "get_budget",
        "Бюджет: план, оплачено, ещё к оплате и остаток по валютам за месяц или год.",
        {
            "type": "object",
            "properties": {
                "period": {"type": "string", "description": "YYYY-MM, YYYY, this_month, last_month, next_month, this_year. Пусто — текущий месяц."},
                "department": {"type": "string", "description": "Название отдела, «all» — все доступные. Пусто — текущий."},
            },
        },
        "member",
        _budget,
        examples=[{"request": "Сколько осталось бюджета?", "params": {"period": "this_month"}}],
    ),
    Tool(
        "product_help",
        "Как пользоваться rekeeper: разделы, кнопки, настройки, роли, Telegram, почта, вебхук, напоминания, чеки, CSV, пароль, курсы ЦБ, логи.",
        {"type": "object", "properties": {"topic": {"type": "string", "description": "Тема или сам вопрос человека."}}, "required": ["topic"]},
        "member",
        _help,
        examples=[{"request": "Как приложить чек?", "params": {"topic": "чек"}}],
    ),
    Tool(
        "list_people",
        "Люди отдела: роль, почта, активен ли, привязан ли Telegram, сколько открытых платежей.",
        {"type": "object", "properties": {"department": _DEPT}},
        "admin",
        _people,
    ),
    Tool(
        "get_audit",
        "Логи (журнал действий): кто, когда и что сделал. Фильтр по периоду и человеку.",
        {
            "type": "object",
            "properties": {
                "period": {"type": "string", "description": "today, yesterday, this_week, this_month, YYYY-MM-DD…"},
                "date_from": {"type": "string"},
                "date_to": {"type": "string"},
                "actor": {"type": "string", "description": "Кто сделал: имя или «me»."},
                "limit": {"type": "integer"},
            },
        },
        "admin",
        _audit,
        examples=[{"request": "Кто что менял сегодня?", "params": {"period": "today"}}],
    ),
    Tool(
        "propose_mark_paid",
        "Карточка «отметить счёт оплаченным». Ничего не записывает до подтверждения человеком.",
        {"type": "object", "properties": {"query": _QUERY, "month": _MONTH}, "required": ["query"]},
        "member",
        lambda db, ctx, a, s: plan(db, ctx, "mark_paid", _paid_slots(a)),
        action=True,
    ),
    Tool(
        "propose_mark_unpaid",
        "Карточка «вернуть оплаченный счёт в неоплаченные». Ничего не меняет до подтверждения.",
        {"type": "object", "properties": {"query": _QUERY, "month": _MONTH}, "required": ["query"]},
        "member",
        lambda db, ctx, a, s: plan(db, ctx, "mark_unpaid", _paid_slots(a)),
        action=True,
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
        action=True,
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
        lambda db, ctx, a, s: plan(db, ctx, "update", dict(a)),
        action=True,
    ),
    Tool(
        "propose_archive_payment",
        "Карточка архивации шаблона. Новые счета перестанут появляться после подтверждения.",
        {"type": "object", "properties": {"query": _QUERY}, "required": ["query"]},
        "admin",
        lambda db, ctx, a, s: plan(db, ctx, "archive", {"query": a.get("query")}),
        action=True,
    ),
)

BY_NAME = {tool.name: tool for tool in TOOLS}

# Явные команды (intents.py) идут через те же карточки и ту же проверку роли.
INTENT_TOOL = {
    "mark_paid": "propose_mark_paid",
    "mark_unpaid": "propose_mark_unpaid",
    "update": "propose_update_payment",
    "archive": "propose_archive_payment",
}


def allowed(ctx: TeamContext, tool: Tool) -> bool:
    return bool(ctx.user.is_active) and RANK[ctx.role] >= RANK[tool.role]


def functions_for(ctx: TeamContext) -> list[dict]:
    out = []
    for tool in TOOLS:
        if not allowed(ctx, tool):
            continue
        item: dict[str, Any] = {"name": tool.name, "description": tool.description, "parameters": tool.parameters}
        if tool.examples:
            item["few_shot_examples"] = tool.examples
        out.append(item)
    return out


def call(turn: Turn, name: str, arguments: dict) -> tuple[dict | None, Card | None]:
    """(данные для модели, None) у чтения или (None, карточка) у действия."""
    tool = BY_NAME.get(name)
    if tool is None:
        return {"error": f"нет инструмента {name}"}, None
    if not allowed(turn.ctx, tool):
        if tool.action:
            return None, (ADMIN_ONLY, None)
        return {"denied_role": ADMIN_ONLY}, None
    args = arguments if isinstance(arguments, dict) else {}
    if tool.action:
        return None, tool.run(turn.db, turn.ctx, args, turn.get_scope())
    return tool.run(turn.db, turn.ctx, args, turn.get_scope()), None


def run(db: Session, ctx: TeamContext, name: str, arguments: dict) -> tuple[str, AssistantAction | None]:
    """Один вызов вне цикла (команды, тесты): чтение отдаётся JSON-текстом."""
    import json

    data, card = call(Turn(db, ctx), name, arguments)
    if card is not None:
        return card
    if isinstance(data, dict) and set(data) == {"denied_role"}:
        return ADMIN_ONLY, None
    if isinstance(data, dict) and set(data) == {"markdown"}:
        return data["markdown"], None
    return json.dumps(data, ensure_ascii=False), None


def run_intent(db: Session, ctx: TeamContext, kind: str, slots: dict) -> tuple[str, AssistantAction | None]:
    if kind == "capabilities":
        return capabilities(ctx.role), None
    if kind == "create":
        if not allowed(ctx, BY_NAME["propose_create_payment"]):
            return ADMIN_ONLY, None
        return plan(db, ctx, "create", slots)
    if kind in {"clarify", "unsupported_frequency"}:
        return plan(db, ctx, kind, slots)
    name = INTENT_TOOL.get(kind)
    if name is None:
        return "Не понял запрос. Сформулируйте проще или спросите, что я умею.", None
    return run(db, ctx, name, slots)



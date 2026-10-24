"""query_operations: выборка и агрегаты по периодам платежей для Кипа.

Данные берутся тем же list_views, что у REST (статусы, скрытые архивные сроки, план),
и режутся отделами, к которым у человека есть доступ (department_access).
Итоги считаются по каждой валюте отдельно; рубли по ЦБ — только по просьбе.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.assistant.dates import parse_day, resolve_period
from app.assistant.match import fold, similar
from app.models import Team
from app.services import rates as cbr
from app.services import time as clock
from app.services.access import TeamContext, department_access
from app.services.occurrences import list_views

STATUSES = {"paid", "overdue", "due_soon", "upcoming", "unpaid", "late", "on_time"}
GROUPS = {"none", "payment", "department", "status", "currency", "responsible", "month", "day"}
METRICS = ("count", "sum", "avg", "min", "max")
SORTS = {"amount_desc", "amount_asc", "date_asc", "date_desc"}
ALL_WORDS = {"*", "all", "все", "всё", "все отделы", "всех"}
MAX_ROWS = 30
MAX_GROUPS = 20
CENT = Decimal("0.01")


def _q(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def _list(value: Any) -> list[str]:
    if value is None or value == "":
        return []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return [part.strip() for part in str(value).split(",") if part.strip()]


class Scope:
    """Отделы человека и все отделы организации — один раз на ход."""

    def __init__(self, db: Session, ctx: TeamContext) -> None:
        self.ctx = ctx
        self.access = {row.team_id: row for row in department_access(db, ctx.user)}
        self.all_teams = list(db.scalars(select(Team)).all())
        self._items: list | None = None
        self.db = db
        self.today = clock.today()

    def items(self) -> list:
        if self._items is None:
            today, rows = list_views(self.db, view="all")
            self.today = today
            self._items = [row for row in rows if row.team_id in self.access]
        return self._items

    def name(self, team_id) -> str:
        row = self.access.get(team_id)
        return row.team.name if row is not None else "?"

    def departments(self, wanted: list[str]) -> tuple[set, list[str], list[str]]:
        """Запрошенные отделы → (id доступных, denied, unknown). Пусто — текущий отдел."""
        if not wanted:
            return {self.ctx.team.id}, [], []
        if any(fold(item) in ALL_WORDS for item in wanted):
            return set(self.access), [], []
        chosen: set = set()
        denied: list[str] = []
        unknown: list[str] = []
        for item in wanted:
            hits = [team for team in self.all_teams if str(team.id) == item or fold(team.name) == fold(item)]
            if not hits:
                hits = [team for team in self.all_teams if similar(item, team.name)]
            if not hits:
                unknown.append(item)
                continue
            for team in hits:
                if team.id in self.access:
                    chosen.add(team.id)
                else:
                    denied.append(team.name)
        return chosen, sorted(set(denied)), unknown


def _value(item) -> Decimal:
    if item.status == "paid" and item.paid_amount is not None:
        return Decimal(str(item.paid_amount))
    return Decimal(str(item.amount))


def _status_ok(item, statuses: set[str]) -> bool:
    if not statuses:
        return True
    for status in statuses:
        if status == "unpaid" and item.status != "paid":
            return True
        if status == "late" and item.status == "paid" and item.paid_on_time is False:
            return True
        if status == "on_time" and item.status == "paid" and item.paid_on_time:
            return True
        if status == item.status:
            return True
    return False


def _totals(items: list, metrics: tuple[str, ...]) -> list[dict]:
    by: dict[str, list[Decimal]] = defaultdict(list)
    for item in items:
        by[item.currency].append(_value(item))
    out = []
    for currency in sorted(by, key=lambda code: ("RUB", "USD", "EUR").index(code) if code in ("RUB", "USD", "EUR") else 9):
        values = by[currency]
        row: dict[str, Any] = {"currency": currency}
        if "count" in metrics:
            row["count"] = len(values)
        if "sum" in metrics:
            row["sum"] = _q(sum(values, Decimal(0)))
        if "avg" in metrics:
            row["avg"] = _q(sum(values, Decimal(0)) / len(values))
        if "min" in metrics:
            row["min"] = _q(min(values))
        if "max" in metrics:
            row["max"] = _q(max(values))
        out.append(row)
    return out


def _rub(items: list) -> dict:
    rates = cbr.current()
    if rates is None:
        return {"error": "курс ЦБ сейчас недоступен"}
    total = Decimal(0)
    missing: set[str] = set()
    for item in items:
        if item.currency == "RUB":
            total += _value(item)
        elif item.currency in rates.values:
            total += _value(item) * rates.values[item.currency]
        else:
            missing.add(item.currency)
    out: dict[str, Any] = {
        "total_rub": _q(total),
        "rates_on": rates.on.isoformat(),
        "rates": {code: _q(value) for code, value in rates.values.items()},
        "note": "пересчёт по курсу ЦБ на дату курса, справочно",
    }
    if items:
        out["avg_rub"] = _q(total / len(items))
    if missing:
        out["not_converted"] = sorted(missing)
    return out


def _key(item, group: str, scope: Scope, date_field: str) -> str:
    if group == "payment":
        return item.title
    if group == "department":
        return scope.name(item.team_id)
    if group == "status":
        if item.status == "paid":
            return "paid_late" if item.paid_on_time is False else "paid"
        return item.status
    if group == "currency":
        return item.currency
    if group == "responsible":
        return item.responsible.full_name if item.responsible is not None else "не назначен"
    day = item.paid_on if date_field == "paid" and item.paid_on else item.due_date
    if group == "month":
        return day.strftime("%Y-%m")
    return day.isoformat()


def _row(item, scope: Scope) -> dict:
    row: dict[str, Any] = {
        "title": item.title,
        "department": scope.name(item.team_id),
        "period": item.period,
        "due": item.due_date.isoformat(),
        "amount": _q(Decimal(str(item.amount))),
        "currency": item.currency,
        "status": item.status,
        "responsible": item.responsible.full_name if item.responsible is not None else None,
    }
    if item.status == "paid":
        row["paid_on"] = item.paid_on.isoformat() if item.paid_on else None
        if item.paid_amount is not None:
            row["paid_amount"] = _q(Decimal(str(item.paid_amount)))
        row["paid_by"] = item.paid_by.full_name if item.paid_by is not None else None
        row["on_time"] = item.paid_on_time
        if item.lateness_days:
            row["late_days"] = item.lateness_days
        row["receipt"] = item.receipt is not None
    elif item.status == "overdue":
        row["overdue_days"] = abs(item.days_delta)
    else:
        row["days_left"] = item.days_delta
    if item.planned:
        row["planned"] = True
    return row


def run_query(scope: Scope, args: dict) -> dict:
    today = scope.today
    statuses = {fold(item) for item in _list(args.get("status")) if fold(item) in STATUSES}
    date_field = "paid" if str(args.get("date_field") or "").lower() == "paid" else "due"
    if statuses and statuses <= {"paid", "late", "on_time"} and not args.get("date_field"):
        date_field = "paid"
    start, end = resolve_period(str(args.get("period") or ""), today)
    start = parse_day(args.get("date_from")) or start
    end = parse_day(args.get("date_to")) or end
    teams, denied, unknown = scope.departments(_list(args.get("department")))
    currencies = {item.upper() for item in _list(args.get("currency")) if item.upper() in {"RUB", "USD", "EUR"}}
    responsible = str(args.get("responsible") or "").strip()
    payment = str(args.get("payment") or "").strip()
    group = str(args.get("group_by") or "none").lower()
    group = group if group in GROUPS else "none"
    metrics = tuple(item for item in METRICS if item in {fold(m) for m in _list(args.get("metrics"))}) or ("count", "sum")
    sort = str(args.get("sort") or "").lower()
    try:
        limit = max(1, min(int(args.get("limit") or 10), MAX_ROWS))
    except (TypeError, ValueError):
        limit = 10

    picked = []
    for item in scope.items():
        if item.team_id not in teams:
            continue
        if not _status_ok(item, statuses):
            continue
        if date_field == "paid":
            if item.status != "paid" or item.paid_on is None:
                continue
            day = item.paid_on
        else:
            day = item.due_date
        if start is not None and day < start:
            continue
        if end is not None and day > end:
            continue
        if currencies and item.currency not in currencies:
            continue
        if responsible:
            who = item.responsible.full_name if item.responsible is not None else ""
            if fold(responsible) in {"me", "я", "__self__", "мне", "меня"}:
                if item.responsible is None or item.responsible.id != scope.ctx.user.id:
                    continue
            elif not who or not similar(responsible, who):
                continue
        if payment and not similar(payment, item.title):
            continue
        picked.append(item)

    result: dict[str, Any] = {
        "label": str(args.get("label") or "")[:80] or None,
        "applied": {
            "date_field": date_field,
            "from": start.isoformat() if start else None,
            "to": end.isoformat() if end else None,
            "departments": sorted(scope.name(team) for team in teams),
            "status": sorted(statuses) or None,
            "currency": sorted(currencies) or None,
            "responsible": responsible or None,
            "payment": payment or None,
        },
        "count": len(picked),
        "totals": _totals(picked, metrics),
    }
    if denied:
        result["denied"] = denied
    if unknown:
        result["unknown_departments"] = unknown
    if args.get("convert_to_rub"):
        result["rub"] = _rub(picked)
    if group != "none":
        buckets: dict[str, list] = defaultdict(list)
        for item in picked:
            buckets[_key(item, group, scope, date_field)].append(item)
        groups = [{"key": key, "count": len(rows), "totals": _totals(rows, metrics)} for key, rows in buckets.items()]
        if group in {"month", "day"}:
            groups.sort(key=lambda row: row["key"])
        else:
            groups.sort(key=lambda row: (-row["count"], row["key"]))
        result["group_by"] = group
        result["groups"] = groups[:MAX_GROUPS]
        if len(groups) > MAX_GROUPS:
            result["groups_truncated"] = len(groups) - MAX_GROUPS
    if args.get("include_rows") or sort:
        ordered = list(picked)
        if sort == "amount_desc":
            ordered.sort(key=lambda item: (item.currency, -_value(item)))
        elif sort == "amount_asc":
            ordered.sort(key=lambda item: (item.currency, _value(item)))
        elif sort == "date_desc":
            ordered.sort(key=lambda item: item.due_date, reverse=True)
        else:
            ordered.sort(key=lambda item: item.due_date)
        result["rows"] = [_row(item, scope) for item in ordered[:limit]]
        if len(ordered) > limit:
            result["rows_more"] = len(ordered) - limit
    return result


def query_operations(db: Session, ctx: TeamContext, arguments: dict, scope: Scope | None = None) -> dict:
    """Один запрос или пакет `queries` — по результату на каждый."""
    scope = scope or Scope(db, ctx)
    batch = arguments.get("queries")
    if isinstance(batch, list) and batch:
        return {"results": [run_query(scope, item if isinstance(item, dict) else {}) for item in batch[:6]]}
    return run_query(scope, arguments)


def today_of(scope: Scope) -> date:
    return scope.today

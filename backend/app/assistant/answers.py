"""Тексты ответов строго из периодов. Модель эти цифры не придумывает."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy.orm import Session

from app.assistant import match as names
from app.assistant.dates import week_bounds
from app.services.occurrences import list_views
from app.services.schedule import period_label

STATUS_WORD = {
    "overdue": "просрочено",
    "due_soon": "скоро",
    "upcoming": "впереди",
    "paid": "оплачено",
}
GROUP_RU = {
    "overdue": "Просрочено",
    "due_soon": "Скоро",
    "upcoming": "Впереди",
    "paid": "Оплачено",
}
GROUP_ORDER = ("overdue", "due_soon", "upcoming", "paid")


def _money(amount) -> str:
    return f"{Decimal(amount):.2f}"


def _item_md(item) -> str:
    due = item.due_date.strftime("%d.%m.%Y")
    who = item.responsible.full_name if item.responsible is not None else "не назначен"
    title = str(item.title).replace("*", "").replace("\n", " ").strip()
    status = STATUS_WORD.get(item.status, item.status)
    return f"**{title}** — {_money(item.amount)} {item.currency}\nдо {due} · {status} · {who}"


def _grouped(items) -> str:
    buckets: dict[str, list] = {key: [] for key in GROUP_ORDER}
    extra: list = []
    for item in items:
        if item.status in buckets:
            buckets[item.status].append(item)
        else:
            extra.append(item)
    groups: list[tuple[str, list]] = [(GROUP_RU[key], buckets[key]) for key in GROUP_ORDER if buckets[key]]
    if extra:
        groups.append(("Прочее", extra))
    show_heads = len(items) > 1
    blocks: list[str] = []
    for label, rows in groups:
        body = "\n\n".join(_item_md(row) for row in rows)
        blocks.append(f"{label}\n\n{body}" if show_heads else body)
    return "\n\n".join(blocks)


def _totals(items) -> list[str]:
    sums: dict[str, Decimal] = {}
    for item in items:
        sums[item.currency] = sums.get(item.currency, Decimal("0.00")) + Decimal(item.amount)
    return [f"{currency} {_money(amount)}" for currency, amount in sorted(sums.items())]


def catalog(db: Session, team_id: uuid.UUID) -> str:
    rows = names.list_active(db, team_id)
    if not rows:
        return "активных платежей нет"
    return ", ".join(f"«{row.title}»" for row in rows)


def week_text(db: Session, team_id: uuid.UUID) -> str:
    today, items = list_views(db, view="inbox", team_id=team_id)
    start, end = week_bounds(today)
    burning = [
        item
        for item in items
        if item.status == "overdue" or start <= item.due_date <= end
    ]
    if not burning:
        return f"На этой неделе ничего не горит: просрочек нет, до {end.strftime('%d.%m.%Y')} сроков нет."
    return f"Горит на этой неделе, до {end.strftime('%d.%m.%Y')}.\n\n" + _grouped(burning)


def overdue_text(db: Session, team_id: uuid.UUID) -> str:
    _today, items = list_views(db, view="inbox", team_id=team_id, status="overdue")
    if not items:
        return "Просроченных платежей нет."
    body = _grouped(items)
    if body.startswith("Просрочено"):
        return body
    return "Просрочено\n\n" + body


def spending_text(db: Session, team_id: uuid.UUID, year: int, month: int) -> str:
    _today, items = list_views(db, view="all", team_id=team_id)
    key = f"{year:04d}-{month:02d}"
    chosen = [item for item in items if item.period == key]
    title = period_label(year, month).capitalize()
    if not chosen:
        return f"За {title.lower()} периодов нет."
    paid = [item for item in chosen if item.status == "paid"]
    open_items = [item for item in chosen if item.status != "paid"]
    lines = [f"{title}."]
    if paid:
        lines.append("Уже оплачено: " + ", ".join(_totals(paid)) + ".")
    else:
        lines.append("Оплат пока нет.")
    if open_items:
        lines.append("Ещё не оплачено: " + ", ".join(_totals(open_items)) + ".")
        return "\n".join(lines) + "\n\n" + _grouped(open_items)
    return "\n".join(lines)


def paid_month_text(db: Session, team_id: uuid.UUID, year: int, month: int) -> str:
    _today, items = list_views(db, view="history", team_id=team_id)
    key = f"{year:04d}-{month:02d}"
    chosen = [item for item in items if item.period == key]
    title = period_label(year, month)
    if not chosen:
        return f"За {title} оплаченных периодов нет."
    head = f"Оплачено за {title}: " + ", ".join(_totals(chosen)) + "."
    return head + "\n\n" + _grouped(chosen)


def open_text(db: Session, team_id: uuid.UUID) -> str:
    _today, items = list_views(db, view="inbox", team_id=team_id)
    if not items:
        return "Инбокс пуст: открытых платежей нет."
    shown = items[:12]
    tail = f"\n\nИ ещё {len(items) - len(shown)}." if len(items) > len(shown) else ""
    return "Открытые платежи: " + ", ".join(_totals(items)) + ".\n\n" + _grouped(shown) + tail


def responsible_text(db: Session, team_id: uuid.UUID, query: str) -> str:
    found = names.match_templates(db, query, team_id)
    if not found:
        return f"Платежа «{query}» не нашёл. Сейчас есть: {catalog(db, team_id)}."
    if len(found) > 1:
        titles = ", ".join(f"«{row.title}»" for row in found)
        return f"Нашёл несколько платежей: {titles}. Уточни название."
    row = found[0]
    who = row.responsible.full_name if row.responsible is not None else "не назначен"
    return (
        f"«{row.title}» — {who}, {_money(row.amount)} {row.currency}, "
        f"каждое {row.day_of_month}-е."
    )


def person_text(db: Session, team_id: uuid.UUID, name: str) -> str:
    found = names.match_users(db, name, team_id)
    if not found:
        people = ", ".join(user.full_name for user in names.active_users(db, team_id)) or "никого"
        return f"Человека «{name}» не нашёл. Сейчас в отделе: {people}."
    if len(found) > 1:
        return "Нашёл несколько людей: " + ", ".join(user.full_name for user in found) + ". Уточни имя."
    person = found[0]
    _today, items = list_views(db, view="inbox", team_id=team_id, responsible_id=person.id)
    if not items:
        return f"У {person.full_name} нет открытых платежей."
    return f"Открыто у {person.full_name}:\n\n" + _grouped(items[:12])


def answer_read(db: Session, team_id: uuid.UUID, kind: str, slots: dict) -> str:
    if kind == "week":
        return week_text(db, team_id)
    if kind == "overdue":
        return overdue_text(db, team_id)
    if kind == "spending":
        return spending_text(db, team_id, int(slots["year"]), int(slots["month"]))
    if kind == "paid_month":
        return paid_month_text(db, team_id, int(slots["year"]), int(slots["month"]))
    if kind == "open":
        return open_text(db, team_id)
    if kind == "responsible":
        return responsible_text(db, team_id, str(slots.get("query") or ""))
    if kind == "person":
        return person_text(db, team_id, str(slots.get("name") or ""))
    return "Не понял вопрос. Спроси, что горит на этой неделе."

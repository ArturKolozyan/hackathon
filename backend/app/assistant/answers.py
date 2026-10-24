"""Ответы ассистента из данных отдела. Цифры считает код, модель их не придумывает.

Markdown для веба: заголовок ###, короткая сводка, таблицы и группы платежей.
Строка платежа — «**Название** — сумма» и под ней «до срока, статус, ответственный: имя»:
из этой пары виджет рисует карточку (frontend/src/markdown.ts). Telegram получает
тот же текст через telegram_html.markdown_to_html.

Данные — только отдела из TeamContext (тот же list_views, что у REST) и отделов
из department_access для сводки по отделам. Чужих отделов здесь нет.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.assistant import match as names
from app.assistant.dates import week_bounds
from app.services import humanize
from app.services import time as clock
from app.services.access import TeamContext, department_access
from app.services.budgets import report as budget_report
from app.services.occurrences import list_views
from app.services.schedule import period_label
from app.services.teams import list_member_rows

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
ROLE_RU = {"owner": "владелец", "admin": "админ", "member": "участник"}
LIST_LIMIT = 12


# ---------- форматирование ----------


def clean(text: object) -> str:
    """Название из базы не должно ломать markdown ответа."""
    return " ".join(str(text).replace("*", "").replace("|", "/").replace("#", "").replace("`", "").split())


def due_text(value: date, today: date | None = None) -> str:
    current = today or clock.today()
    return humanize.ru_date(value, year=value.year != current.year)


def money(amount: object, currency: str) -> str:
    return humanize.money(amount, currency)


def sums(items, *, paid: bool = False) -> dict[str, Decimal]:
    out: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for item in items:
        value = item.paid_amount if paid and getattr(item, "paid_amount", None) is not None else item.amount
        out[item.currency] += Decimal(value)
    return dict(out)


def sums_text(totals: dict[str, Decimal]) -> str:
    if not totals:
        return "—"
    return ", ".join(money(amount, currency) for currency, amount in sorted(totals.items()))


def count_text(count: int) -> str:
    return f"{count} {humanize.plural(count, 'платёж', 'платежа', 'платежей')}"


def table(head: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(head) + " |", "|" + "|".join("---" for _ in head) + "|"]
    lines.extend("| " + " | ".join(cell or "—" for cell in row) + " |" for row in rows)
    return "\n".join(lines)


def _who(item) -> str:
    return clean(item.responsible.full_name) if item.responsible is not None else "не назначен"


def item_md(item, today: date | None = None) -> str:
    status = STATUS_WORD.get(item.status, item.status)
    return (
        f"**{clean(item.title)}** — {money(item.amount, item.currency)}\n"
        f"до {due_text(item.due_date, today)}, {status}, ответственный: {_who(item)}"
    )


def grouped(items, today: date | None = None, *, limit: int = LIST_LIMIT) -> str:
    shown = list(items)[:limit]
    buckets: dict[str, list] = {key: [] for key in GROUP_ORDER}
    for item in shown:
        buckets.setdefault(item.status, []).append(item)
    groups = [(GROUP_RU.get(key, "Прочее"), rows) for key, rows in buckets.items() if rows]
    heads = len(groups) > 1
    blocks: list[str] = []
    for label, rows in groups:
        body = "\n\n".join(item_md(row, today) for row in rows)
        blocks.append(f"{label}\n\n{body}" if heads else body)
    rest = len(list(items)) - len(shown)
    if rest > 0:
        blocks.append(f"И ещё {count_text(rest)}. Полный список — в разделе «Инбокс».")
    return "\n\n".join(blocks)


CADENCE = {
    "quarterly": "раз в квартал",
    "semiannual": "раз в полгода",
    "yearly": "раз в год",
}


def cadence(periodicity: str | None, interval: int | None, day: int | None) -> str:
    """«каждое 5-е число», «раз в квартал, 5-го», «разово»."""
    kind = periodicity or "monthly"
    if kind == "once":
        return "разово"
    if kind == "monthly":
        return f"каждое {day}-е число"
    label = CADENCE.get(kind) or f"раз в {interval} {humanize.plural(int(interval or 1), 'месяц', 'месяца', 'месяцев')}"
    return f"{label}, {day}-го числа"


def template_cadence(row) -> str:
    return cadence(getattr(row, "periodicity", None), getattr(row, "interval_months", None), row.day_of_month)


def catalog(db: Session, team_id) -> str:
    rows = names.list_active(db, team_id)
    if not rows:
        return "активных платежей нет"
    return ", ".join(f"«{clean(row.title)}»" for row in rows)


def _month_name(year: int, month: int) -> str:
    return period_label(year, month)


def _views(db: Session, ctx: TeamContext, **filters):
    return list_views(db, team_id=ctx.team.id, **filters)


# ---------- очередь ----------


def week_text(db: Session, ctx: TeamContext) -> str:
    today, items = _views(db, ctx, view="inbox")
    start, end = week_bounds(today)
    burning = [item for item in items if item.status == "overdue" or start <= item.due_date <= end]
    sunday = due_text(end, today)
    if not burning:
        return f"### На этой неделе спокойно\n\nПросрочек нет, до воскресенья, {sunday}, сроков нет."
    late = [item for item in burning if item.status == "overdue"]
    head = f"До воскресенья, {sunday}: **{count_text(len(burning))}** на {sums_text(sums(burning))}."
    if late and len(late) == len(burning):
        head += " Все уже просрочены."
    elif late:
        head += f" Из них просрочено {len(late)}."
    return f"### Горит на этой неделе\n\n{head}\n\n{grouped(burning, today)}"


def overdue_text(db: Session, ctx: TeamContext) -> str:
    today, items = _views(db, ctx, view="inbox", status="overdue")
    if not items:
        return "### Просрочек нет\n\nВсе периоды со сроком до сегодня оплачены."
    oldest = max((today - item.due_date).days for item in items)
    head = (
        f"**{count_text(len(items))}** на {sums_text(sums(items))}. "
        f"Самая давняя просрочка — {humanize.days(oldest)}."
    )
    return f"### Просрочено\n\n{head}\n\n{grouped(items, today)}"


def open_text(db: Session, ctx: TeamContext, *, person=None, currency: str | None = None) -> str:
    today, items = _views(
        db,
        ctx,
        view="inbox",
        responsible_id=person.id if person is not None else None,
        currency=currency,
    )
    whose = f" у {clean(person.full_name)}" if person is not None else ""
    if not items:
        return f"### Открытых платежей{whose} нет\n\nИнбокс пуст: всё оплачено."
    rows: list[list[str]] = []
    for code in sorted({item.currency for item in items}):
        same = [item for item in items if item.currency == code]
        part = lambda status: sums_text(sums([item for item in same if item.status == status]))  # noqa: E731
        rows.append([code, part("overdue"), part("due_soon"), part("upcoming"), f"**{sums_text(sums(same))}**"])
    summary = table(["Валюта", "Просрочено", "Скоро", "Позже", "Всего"], rows)
    return (
        f"### Открытые платежи{whose}\n\n**{count_text(len(items))}** к оплате.\n\n{summary}\n\n{grouped(items, today)}"
    )


def upcoming_text(db: Session, ctx: TeamContext, days: int) -> str:
    horizon = max(1, min(int(days or 14), 92))
    today, items = _views(db, ctx, view="inbox")
    end = today + timedelta(days=horizon)
    chosen = [item for item in items if today <= item.due_date <= end]
    title = f"Сроки на {humanize.days(horizon)} вперёд"
    if not chosen:
        return f"### {title}\n\nДо {due_text(end, today)} сроков нет."
    head = f"До {due_text(end, today)}: **{count_text(len(chosen))}** на {sums_text(sums(chosen))}."
    return f"### {title}\n\n{head}\n\n{grouped(chosen, today)}"


def totals_text(db: Session, ctx: TeamContext) -> str:
    today, items = _views(db, ctx, view="all")
    month_key = f"{today.year:04d}-{today.month:02d}"
    open_items = [item for item in items if item.status != "paid"]
    paid_now = [item for item in items if item.status == "paid" and item.paid_on and item.paid_on.strftime("%Y-%m") == month_key]
    codes = sorted({item.currency for item in open_items + paid_now})
    if not codes:
        return f"### Сводка отдела «{clean(ctx.team.name)}»\n\nПлатежей пока нет."
    rows = []
    for code in codes:
        rows.append(
            [
                code,
                sums_text(sums([i for i in open_items if i.currency == code and i.status == "overdue"])),
                sums_text(sums([i for i in open_items if i.currency == code and i.status != "overdue"])),
                sums_text(sums([i for i in paid_now if i.currency == code], paid=True)),
            ]
        )
    month = _month_name(today.year, today.month)
    lines = [
        f"### Сводка отдела «{clean(ctx.team.name)}»",
        "",
        table(["Валюта", "Просрочено", "К оплате", f"Оплачено за {month}"], rows),
    ]
    nearest = next((item for item in open_items if item.status != "overdue"), None)
    if nearest is not None:
        lines += ["", f"Ближайший срок: **{clean(nearest.title)}**, {due_text(nearest.due_date, today)}, {money(nearest.amount, nearest.currency)}."]
    return "\n".join(lines)


# ---------- деньги за период ----------


def spending_text(db: Session, ctx: TeamContext, year: int, month: int) -> str:
    today, items = _views(db, ctx, view="all")
    key = f"{year:04d}-{month:02d}"
    chosen = [item for item in items if item.period == key]
    title = _month_name(year, month).capitalize()
    if not chosen:
        return f"### {title}\n\nЗа {_month_name(year, month)} периодов нет."
    paid = [item for item in chosen if item.status == "paid"]
    open_items = [item for item in chosen if item.status != "paid"]
    rows = []
    for code in sorted({item.currency for item in chosen}):
        rows.append(
            [
                code,
                sums_text(sums([i for i in paid if i.currency == code], paid=True)),
                sums_text(sums([i for i in open_items if i.currency == code])),
                sums_text(sums([i for i in chosen if i.currency == code])),
            ]
        )
    head = f"Оплачено {len(paid)} из {len(chosen)}."
    parts = [f"### {title}", "", head, "", table(["Валюта", "Оплачено", "Ещё не оплачено", "По плану"], rows)]
    if open_items:
        parts += ["", "**Ещё не оплачено**", "", grouped(open_items, today)]
    return "\n".join(parts)


def paid_month_text(db: Session, ctx: TeamContext, year: int, month: int) -> str:
    today, items = _views(db, ctx, view="history")
    key = f"{year:04d}-{month:02d}"
    chosen = [item for item in items if item.period == key]
    title = f"Оплачено за {_month_name(year, month)}"
    if not chosen:
        return f"### {title}\n\nОплаченных периодов нет."
    rows = [
        [
            clean(item.title),
            money(item.paid_amount if item.paid_amount is not None else item.amount, item.currency),
            due_text(item.paid_on, today) if item.paid_on else "—",
            clean(item.paid_by.full_name) if item.paid_by is not None else "—",
        ]
        for item in chosen[:20]
    ]
    head = f"**{count_text(len(chosen))}** на {sums_text(sums(chosen, paid=True))}."
    return f"### {title}\n\n{head}\n\n" + table(["Платёж", "Сумма", "Дата оплаты", "Кто отметил"], rows)


def months_text(db: Session, ctx: TeamContext, months: int) -> str:
    count = max(1, min(int(months or 6), 12))
    today, items = _views(db, ctx, view="all")
    keys: list[tuple[int, int]] = []
    year, month = today.year, today.month
    for _ in range(count):
        keys.append((year, month))
        month -= 1
        if month == 0:
            year, month = year - 1, 12
    keys.reverse()
    rows = []
    for year, month in keys:
        key = f"{year:04d}-{month:02d}"
        chosen = [item for item in items if item.period == key]
        paid = [item for item in chosen if item.status == "paid"]
        late = [item for item in paid if item.lateness_days]
        rows.append(
            [
                _month_name(year, month).capitalize(),
                sums_text(sums(paid, paid=True)) if paid else "—",
                sums_text(sums([item for item in chosen if item.status != "paid"])) if len(paid) < len(chosen) else "—",
                f"{len(paid)} из {len(chosen)}" if chosen else "—",
                str(len(late)) if paid else "—",
            ]
        )
    return (
        f"### Статистика за {count} {humanize.plural(count, 'месяц', 'месяца', 'месяцев')}\n\n"
        f"Отдел «{clean(ctx.team.name)}», по сроку периода.\n\n"
        + table(["Месяц", "Оплачено", "Не оплачено", "Периодов оплачено", "С опозданием"], rows)
        + "\n\nГрафики и фильтры — в разделе «Статистика»."
    )


def departments_text(db: Session, ctx: TeamContext) -> str:
    """Отделы, которые видит этот человек: владелец — все, остальные — свои."""
    today = clock.today()
    month_key = f"{today.year:04d}-{today.month:02d}"
    rows = []
    for access in department_access(db, ctx.user):
        _today, items = list_views(db, view="all", team_id=access.team_id)
        open_items = [item for item in items if item.status != "paid"]
        paid_now = [item for item in items if item.status == "paid" and item.paid_on and item.paid_on.strftime("%Y-%m") == month_key]
        rows.append(
            [
                clean(access.team.name),
                ROLE_RU.get(access.role, access.role),
                sums_text(sums([item for item in open_items if item.status == "overdue"])),
                sums_text(sums([item for item in open_items if item.status != "overdue"])),
                sums_text(sums(paid_now, paid=True)),
            ]
        )
    if not rows:
        return "### Отделов нет\n\nВас ещё не добавили ни в один отдел."
    month = _month_name(today.year, today.month)
    return "### Статистика по отделам\n\n" + table(
        ["Отдел", "Ваша роль", "Просрочено", "К оплате", f"Оплачено за {month}"], rows
    )


def budget_text(db: Session, ctx: TeamContext, year: int, month: int | None) -> str:
    period_type = "month" if month else "year"
    key = f"{year:04d}-{month:02d}" if month else f"{year:04d}"
    title = _month_name(year, month) if month else f"{year} год"
    data = budget_report(db, period_type, key, ctx.team.id)
    planned = [row for row in data.rows if row.plan_amount is not None]
    used = [row for row in data.rows if row.plan_amount is not None or row.fact_amount or row.expected_amount]
    if not used:
        return f"### Бюджет: {title}\n\nНи плана, ни платежей за этот период нет."
    rows = []
    for row in used:
        plan = Decimal(row.plan_amount) if row.plan_amount is not None else None
        fact = Decimal(row.fact_amount)
        expected = Decimal(row.expected_amount)
        if plan is None:
            left = "—"
        else:
            rest = plan - fact - expected
            left = money(rest, row.currency) if rest >= 0 else f"**перерасход {money(-rest, row.currency)}**"
        rows.append(
            [
                row.currency,
                money(plan, row.currency) if plan is not None else "не задан",
                money(fact, row.currency),
                money(expected, row.currency),
                left,
            ]
        )
    note = "" if planned else "\n\nПлан не задан. Задать его может админ в разделе «Бюджет»."
    return f"### Бюджет: {title}\n\n" + table(["Валюта", "План", "Оплачено", "Ещё к оплате", "Остаток"], rows) + note


# ---------- платежи и люди ----------


def _one_template(db: Session, ctx: TeamContext, query: str):
    found = names.match_templates(db, query, ctx.team.id, include_archived=True)
    if not found:
        return None, f"Платежа «{clean(query)}» не нашёл. Сейчас есть: {catalog(db, ctx.team.id)}."
    active = [row for row in found if not row.is_archived]
    if len(found) > 1 and len(active) == 1:
        return active[0], None
    if len(found) > 1:
        titles = ", ".join(f"«{clean(row.title)}»" for row in found)
        return None, f"Нашёл несколько платежей: {titles}. Уточните название."
    return found[0], None


def payment_text(db: Session, ctx: TeamContext, query: str) -> str:
    template, error = _one_template(db, ctx, query)
    if template is None:
        return error or "Какой платёж показать?"
    today, items = _views(db, ctx, view="all", recurring_payment_id=template.id)
    who = clean(template.responsible.full_name) if template.responsible is not None else "не назначен"
    lines = [
        f"### {clean(template.title)}",
        "",
        f"- Сумма: **{money(template.amount, template.currency)}**",
        f"- Срок: {template_cadence(template)}",
        f"- Ответственный: {who}",
    ]
    if template.is_archived:
        lines.append("- В архиве: новые периоды не создаются")
    open_items = [item for item in items if item.status != "paid"]
    if open_items:
        lines.append(f"- Не оплачено: {len(open_items)} на {sums_text(sums(open_items))}")
    history = sorted(items, key=lambda item: item.due_date, reverse=True)[:6]
    if history:
        rows = [
            [
                item.period_label.capitalize(),
                due_text(item.due_date, today),
                money(item.amount, item.currency),
                STATUS_WORD.get(item.status, item.status),
                (
                    f"{due_text(item.paid_on, today)}, {clean(item.paid_by.full_name)}"
                    if item.paid_on and item.paid_by is not None
                    else (due_text(item.paid_on, today) if item.paid_on else "—")
                ),
            ]
            for item in history
        ]
        lines += ["", "**Последние периоды**", "", table(["Период", "Срок", "Сумма", "Статус", "Оплата"], rows)]
    return "\n".join(lines)


def responsible_text(db: Session, ctx: TeamContext, query: str) -> str:
    found = names.match_templates(db, query, ctx.team.id)
    if not found:
        return f"Платежа «{clean(query)}» не нашёл. Сейчас есть: {catalog(db, ctx.team.id)}."
    if len(found) > 1:
        titles = ", ".join(f"«{clean(row.title)}»" for row in found)
        return f"Нашёл несколько платежей: {titles}. Уточните название."
    row = found[0]
    who = clean(row.responsible.full_name) if row.responsible is not None else "не назначен"
    return (
        f"### {clean(row.title)}\n\n"
        f"- Ответственный: **{who}**\n"
        f"- Сумма: {money(row.amount, row.currency)}\n"
        f"- Срок: {template_cadence(row)}"
    )


def person_text(db: Session, ctx: TeamContext, name: str) -> str:
    found = names.match_users(db, name, ctx.team.id)
    if not found:
        people = ", ".join(clean(user.full_name) for user in names.active_users(db, ctx.team.id)) or "никого"
        return f"Человека «{clean(name)}» не нашёл. Сейчас в отделе: {people}."
    if len(found) > 1:
        return "Нашёл несколько людей: " + ", ".join(clean(user.full_name) for user in found) + ". Уточните имя."
    return open_text(db, ctx, person=found[0])


def templates_text(db: Session, ctx: TeamContext, *, archived: bool = False) -> str:
    rows = [row for row in _all_templates(db, ctx) if row.is_archived == archived]
    title = "Платежи в архиве" if archived else "Регулярные платежи отдела"
    if not rows:
        return f"### {title}\n\n" + ("Архив пуст." if archived else "Шаблонов пока нет. Создать платёж может админ.")
    body = table(
        ["Платёж", "Сумма", "Срок", "Ответственный"],
        [
            [
                clean(row.title),
                money(row.amount, row.currency),
                template_cadence(row),
                clean(row.responsible.full_name) if row.responsible is not None else "не назначен",
            ]
            for row in rows
        ],
    )
    return f"### {title}\n\n**{count_text(len(rows))}**.\n\n{body}"


def _all_templates(db: Session, ctx: TeamContext):
    from sqlalchemy import select
    from sqlalchemy.orm import joinedload

    from app.models import RecurringPayment

    stmt = (
        select(RecurringPayment)
        .options(joinedload(RecurringPayment.responsible))
        .where(RecurringPayment.team_id == ctx.team.id)
        .order_by(RecurringPayment.title)
    )
    return list(db.scalars(stmt).unique().all())


def people_text(db: Session, ctx: TeamContext) -> str:
    """Только для админа и владельца: проверка в tools.run."""
    _today, items = _views(db, ctx, view="inbox")
    load: dict = defaultdict(int)
    for item in items:
        if item.responsible is not None:
            load[item.responsible.id] += 1
    rows = []
    for seat in list_member_rows(db, ctx.team.id):
        person = seat.user
        if person is None or not person.is_active:
            continue
        rows.append(
            [
                clean(person.full_name),
                ROLE_RU.get(seat.role, seat.role),
                "привязан" if person.telegram_user_id is not None else "нет",
                str(load.get(person.id, 0)),
            ]
        )
    if not rows:
        return "### Люди отдела\n\nВ отделе пока никого."
    return (
        f"### Люди отдела «{clean(ctx.team.name)}»\n\n"
        + table(["Человек", "Роль", "Telegram", "Открытых платежей"], rows)
        + "\n\nДобавить человека или поменять роль — раздел «Люди»."
    )

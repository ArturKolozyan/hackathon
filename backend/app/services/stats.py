"""Сводка по всем командам человека. Инбокс одной команды живёт отдельно."""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models import Membership, PaymentOccurrence, RecurringPayment, User
from app.schemas.stats import (
    MoneyBucket,
    StatsDepartment,
    StatsItem,
    StatsMonth,
    StatsOperation,
    StatsOperations,
    StatsOut,
    StatsTeam,
)
from app.services import time as clock
from app.services.access import department_access
from app.services.occurrences import ensure_all, hidden, planned_rows
from app.services.present import user_brief
from app.services.schedule import classify, period_label, shift_month

CURRENCIES = ("RUB", "USD", "EUR")
PAGE_SIZE = 20
STATUS_RANK = {"overdue": 0, "due_soon": 1, "upcoming": 2, "paid": 3}
MONTHS_BACK = 6
MONTHS_AHEAD = 5


def _month_keys(today: date) -> list[str]:
    keys = []
    for delta in range(-MONTHS_BACK, MONTHS_AHEAD + 1):
        year, month = shift_month(today.year, today.month, delta)
        keys.append(f"{year:04d}-{month:02d}")
    return keys


def _month_bounds(today: date) -> tuple[date, date]:
    import calendar

    last = calendar.monthrange(today.year, today.month)[1]
    return date(today.year, today.month, 1), date(today.year, today.month, last)


def _parse_month(value: str) -> tuple[date, date]:
    import calendar

    text = value.strip()
    parts = text.split("-")
    if len(parts) != 2 or len(parts[0]) != 4 or len(parts[1]) != 2:
        raise HTTPException(status_code=422, detail="Месяц записывается как ГГГГ-ММ")
    year, month = int(parts[0]), int(parts[1])
    if year < 2000 or year > 2100 or month < 1 or month > 12:
        raise HTTPException(status_code=422, detail="Месяц записывается как ГГГГ-ММ")
    last = calendar.monthrange(year, month)[1]
    return date(year, month, 1), date(year, month, last)


def _buckets(sums: dict[str, list]) -> list[MoneyBucket]:
    result = []
    for currency in CURRENCIES:
        if currency not in sums:
            continue
        amount, count = sums[currency]
        if count == 0:
            continue
        result.append(MoneyBucket(currency=currency, amount=amount, count=count))
    return result


def _add(sums: dict[str, list], currency: str, amount: Decimal) -> None:
    if currency not in sums:
        sums[currency] = [Decimal("0.00"), 0]
    sums[currency][0] += Decimal(amount)
    sums[currency][1] += 1


def build_stats(
    db: Session,
    user: User,
    *,
    team_ids: list[uuid.UUID] | None,
    status: str | None,
    currency: str | None,
    month: str | None,
    date_from: date | None,
    date_to: date | None,
    responsible_id: uuid.UUID | None,
    page: int = 1,
) -> StatsOut:
    # Владелец видит все отделы без членства, остальные — свои.
    allowed = {row.team_id: row for row in department_access(db, user)}
    if team_ids:
        if any(item not in allowed for item in team_ids):
            raise HTTPException(status_code=403, detail="Вы не в этом отделе")
        scope = list(dict.fromkeys(team_ids))
    else:
        scope = list(allowed)
    if month and (date_from is not None or date_to is not None):
        raise HTTPException(status_code=422, detail="Укажите либо месяц, либо диапазон")
    today = clock.today()
    if month:
        due_from, due_to = _parse_month(month)
        paid_from, paid_to = due_from, due_to
    elif date_from is not None or date_to is not None:
        if date_from is None or date_to is None:
            raise HTTPException(status_code=422, detail="Укажите начало и конец периода")
        if date_from > date_to:
            raise HTTPException(status_code=422, detail="Начало периода позже конца")
        due_from, due_to = date_from, date_to
        paid_from, paid_to = date_from, date_to
    else:
        due_from = due_to = None
        paid_from, paid_to = _month_bounds(today)

    if scope:
        ensure_all(db, today)
        db.commit()
        db.expire_all()
    settings = get_settings()
    zone = clock.zone()
    occurrences: list[PaymentOccurrence] = []
    if scope:
        occurrences = list(
            db.scalars(
                select(PaymentOccurrence)
                .where(PaymentOccurrence.team_id.in_(scope))
                .options(
                    joinedload(PaymentOccurrence.template).joinedload(RecurringPayment.responsible),
                    joinedload(PaymentOccurrence.payer),
                )
            )
            .unique()
            .all()
        )
    occurrences = [row for row in occurrences if not hidden(row, today)]
    planned_ids: set[uuid.UUID] = set()
    if scope:
        # Будущие месяцы графика и выбранного периода: сроки по расписанию, в базу не пишутся.
        last_key = _month_keys(today)[-1]
        horizon_end = _parse_month(last_key)[1]
        future = planned_rows(db, team_ids=scope, start=today, end=max(horizon_end, due_to or horizon_end), today=today)
        planned_ids = {row.id for row in future}
        occurrences += future
    teams = {row.team_id: row.team for row in allowed.values()}
    to_pay: dict[str, list] = {}
    overdue: dict[str, list] = {}
    paid: dict[str, list] = {}
    per_team: dict[uuid.UUID, dict[str, dict[str, list]]] = {
        team_id: {"to_pay": {}, "overdue": {}, "paid": {}} for team_id in scope
    }
    nearest: list[tuple[date, StatsItem]] = []
    operations: list[tuple[tuple, StatsOperation]] = []
    month_keys = _month_keys(today)
    zero = Decimal("0.00")
    monthly: dict[tuple[str, str], dict[str, Decimal]] = {}
    paid_count = 0
    paid_on_time = 0

    def bump(key: str, cur: str, field: str, value: Decimal) -> None:
        if key not in month_keys:
            return
        slot = monthly.setdefault((key, cur), {"paid": zero, "overdue": zero, "planned": zero})
        slot[field] += Decimal(value)

    def wanted(item_status: str) -> bool:
        return status is None or status == item_status

    for row in occurrences:
        template = row.template
        if template is None:
            continue
        if currency is not None and row.currency != currency:
            continue
        if responsible_id is not None and template.responsible_user_id != responsible_id:
            continue
        item_status = classify(row.due_date, row.paid_at, today, settings.soon_days)
        in_due = due_from is None or due_from <= row.due_date <= due_to
        paid_on = row.paid_at.astimezone(zone).date() if row.paid_at is not None else None
        in_paid = paid_on is not None and paid_from <= paid_on <= paid_to
        team_name = teams[row.team_id].name if row.team_id in teams else ""
        actual = row.paid_amount if row.paid_amount is not None else row.amount
        if paid_on is not None:
            bump(f"{paid_on:%Y-%m}", row.currency, "paid", actual)
        elif row.due_date < today:
            bump(f"{row.due_date:%Y-%m}", row.currency, "overdue", row.amount)
        else:
            bump(f"{row.due_date:%Y-%m}", row.currency, "planned", row.amount)
        listed = (item_status != "paid" and in_due and wanted(item_status)) or (
            item_status == "paid" and in_paid and wanted("paid")
        )
        if listed:
            if item_status == "paid":
                order = (STATUS_RANK["paid"], -paid_on.toordinal(), row.title)
            else:
                order = (STATUS_RANK.get(item_status, 9), row.due_date.toordinal(), row.title)
            operations.append(
                (
                    order,
                    StatsOperation(
                        occurrence_id=row.id,
                        team_id=row.team_id,
                        team_name=team_name,
                        title=row.title,
                        period_label=period_label(row.period_year, row.period_month),
                        due_date=row.due_date,
                        amount=row.amount,
                        paid_amount=row.paid_amount,
                        currency=row.currency,
                        status=item_status,
                        paid_on=paid_on,
                        lateness_days=(paid_on - row.due_date).days if paid_on is not None else None,
                        has_receipt=bool(row.receipt_file),
                        planned=row.id in planned_ids,
                        responsible=user_brief(template.responsible) if template.responsible is not None else None,
                    ),
                )
            )
        if item_status != "paid" and in_due and wanted(item_status):
            _add(to_pay, row.currency, row.amount)
            _add(per_team[row.team_id]["to_pay"], row.currency, row.amount)
            if item_status == "overdue":
                _add(overdue, row.currency, row.amount)
                _add(per_team[row.team_id]["overdue"], row.currency, row.amount)
            responsible = user_brief(template.responsible) if template.responsible is not None else None
            nearest.append(
                (
                    row.due_date,
                    StatsItem(
                        occurrence_id=row.id,
                        team_id=row.team_id,
                        team_name=team_name,
                        title=row.title,
                        due_date=row.due_date,
                        amount=row.amount,
                        currency=row.currency,
                        status=item_status,
                        responsible=responsible,
                    ),
                )
            )
        if item_status == "paid" and in_paid and wanted("paid"):
            _add(paid, row.currency, actual)
            _add(per_team[row.team_id]["paid"], row.currency, actual)
            paid_count += 1
            if paid_on <= row.due_date:
                paid_on_time += 1

    nearest.sort(key=lambda item: (item[0], item[1].title))
    operations.sort(key=lambda item: item[0])
    total = len(operations)
    pages = max(1, -(-total // PAGE_SIZE))
    page = min(max(1, page), pages)
    window = [item for _, item in operations[(page - 1) * PAGE_SIZE : page * PAGE_SIZE]]
    month_rows = [
        StatsMonth(month=key, currency=cur, **monthly[(key, cur)])
        for cur in CURRENCIES
        for key in month_keys
        if (key, cur) in monthly
    ]
    used = {cur for _key, cur in monthly}
    for cur in used:
        present = {row.month for row in month_rows if row.currency == cur}
        for key in month_keys:
            if key not in present:
                month_rows.append(StatsMonth(month=key, currency=cur, paid=zero, overdue=zero, planned=zero))
    month_rows.sort(key=lambda row: (CURRENCIES.index(row.currency), row.month))
    people_rows = []
    if scope:
        people_rows = list(
            db.scalars(
                select(User)
                .join(Membership, Membership.user_id == User.id)
                .where(Membership.team_id.in_(scope))
                .order_by(User.full_name)
            )
            .unique()
            .all()
        )
    seen: set[uuid.UUID] = set()
    people = []
    for person in people_rows:
        if person.id in seen:
            continue
        seen.add(person.id)
        people.append(user_brief(person))
    by_team = [
        StatsTeam(
            team_id=team_id,
            team_name=teams[team_id].name,
            role=allowed[team_id].role,
            to_pay=_buckets(per_team[team_id]["to_pay"]),
            overdue=_buckets(per_team[team_id]["overdue"]),
            paid=_buckets(per_team[team_id]["paid"]),
        )
        for team_id in sorted(scope, key=lambda item: teams[item].name.lower())
    ]
    return StatsOut(
        timezone=clock.zone().key,
        today=today,
        paid_from=paid_from,
        paid_to=paid_to,
        due_from=due_from,
        due_to=due_to,
        to_pay=_buckets(to_pay),
        overdue=_buckets(overdue),
        paid=_buckets(paid),
        nearest=[item for _, item in nearest[:8]],
        by_team=by_team,
        people=people,
        departments=[
            StatsDepartment(id=row.team_id, name=row.team.name)
            for row in sorted(allowed.values(), key=lambda item: item.team.name.lower())
        ],
        paid_count=paid_count,
        paid_on_time=paid_on_time,
        monthly=month_rows,
        operations=StatsOperations(items=window, total=total, page=page, page_size=PAGE_SIZE),
    )

"""Сводка по всем командам человека. Инбокс одной команды живёт отдельно."""

import uuid
from datetime import date
from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models import Membership, PaymentOccurrence, RecurringPayment, User
from app.schemas.stats import MoneyBucket, StatsItem, StatsOut, StatsTeam
from app.services import time as clock
from app.services.access import memberships_of
from app.services.occurrences import ensure_all
from app.services.present import user_brief
from app.services.schedule import classify

CURRENCIES = ("RUB", "USD", "EUR")


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
) -> StatsOut:
    rows_m = memberships_of(db, user)
    allowed = {row.team_id: row for row in rows_m}
    if team_ids:
        if any(item not in allowed for item in team_ids):
            raise HTTPException(status_code=403, detail="Вы не в этой команде")
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
    zone = settings.zone
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
    teams = {row.team_id: row.team for row in allowed.values()}
    to_pay: dict[str, list] = {}
    overdue: dict[str, list] = {}
    paid: dict[str, list] = {}
    per_team: dict[uuid.UUID, dict[str, dict[str, list]]] = {
        team_id: {"to_pay": {}, "overdue": {}, "paid": {}} for team_id in scope
    }
    nearest: list[tuple[date, StatsItem]] = []

    def wanted(item_status: str) -> bool:
        return status is None or status == item_status

    for row in occurrences:
        template = row.template
        if template is None:
            continue
        if template.is_archived and row.paid_at is None:
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
            _add(paid, row.currency, row.amount)
            _add(per_team[row.team_id]["paid"], row.currency, row.amount)

    nearest.sort(key=lambda item: (item[0], item[1].title))
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
        timezone=settings.timezone,
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
    )

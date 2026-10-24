from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models import PaymentOccurrence, RecurringPayment
from app.schemas.summary import CurrencyTotals, SummaryOut
from app.services import time as clock
from app.services.occurrences import ensure_all, hidden, planned_rows
from app.services.schedule import add_months, classify

CURRENCIES = ("RUB", "USD", "EUR")


def _paid_as_of(paid_at, as_of: date | None, zone):
    if paid_at is None or as_of is None:
        return paid_at
    if paid_at.astimezone(zone).date() <= as_of:
        return paid_at
    return None


def _in_snapshot(row: PaymentOccurrence, ref: date, horizon: int) -> bool:
    """На дату видны периоды не дальше горизонта от этой даты. Прошлые остаются."""
    end = add_months(ref, horizon)
    return (row.period_year, row.period_month) <= (end.year, end.month)


def build_summary(db: Session, as_of: date | None = None, team_id=None) -> SummaryOut:
    settings = get_settings()
    real_today = clock.today()
    ref = as_of or real_today
    # Дата в будущем не пишет периоды в базу: недостающие сроки считаются на лету.
    ensure_all(db, real_today)
    db.commit()
    db.expire_all()
    stmt = select(PaymentOccurrence).options(
        joinedload(PaymentOccurrence.template).joinedload(RecurringPayment.responsible),
        joinedload(PaymentOccurrence.payer),
    )
    if team_id is not None:
        stmt = stmt.where(PaymentOccurrence.team_id == team_id)
    rows = [row for row in db.scalars(stmt).unique().all() if not hidden(row, real_today)]
    if as_of is not None and as_of > real_today:
        rows += planned_rows(
            db,
            team_ids=[team_id] if team_id is not None else None,
            start=real_today,
            end=add_months(ref, settings.horizon_months),
            today=real_today,
        )
    counts = {"overdue": 0, "due_soon": 0, "upcoming": 0, "paid": 0}
    totals = {currency: {key: Decimal("0.00") for key in counts} for currency in CURRENCIES}
    seen: set[str] = set()
    zone = clock.zone()
    for row in rows:
        if as_of is not None and not _in_snapshot(row, ref, settings.horizon_months):
            continue
        status = classify(row.due_date, _paid_as_of(row.paid_at, as_of, zone), ref, settings.soon_days)
        counts[status] += 1
        seen.add(row.currency)
        # «Оплачено» — фактически заплаченная сумма, если её указали.
        value = row.paid_amount if status == "paid" and row.paid_amount is not None else row.amount
        totals[row.currency][status] += Decimal(value)
    result: list[CurrencyTotals] = []
    for currency in CURRENCIES:
        if currency not in seen:
            continue
        sums = totals[currency]
        open_amount = sums["overdue"] + sums["due_soon"] + sums["upcoming"]
        result.append(
            CurrencyTotals(
                currency=currency,
                overdue_amount=sums["overdue"],
                due_soon_amount=sums["due_soon"],
                upcoming_amount=sums["upcoming"],
                paid_amount=sums["paid"],
                open_amount=open_amount,
            )
        )
    return SummaryOut(
        timezone=clock.zone().key,
        today=real_today,
        as_of=as_of,
        soon_days=settings.soon_days,
        counts=counts,
        by_currency=result,
    )

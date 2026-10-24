import uuid
from calendar import monthrange
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.services import time as clock
from app.models import Budget, PaymentOccurrence
from app.schemas.budget import CURRENCIES, BudgetLine, BudgetReport
from app.services.occurrences import ensure_all, hidden, planned_rows


def parse_period(period_type: str, period_key: str) -> tuple[int, int | None]:
    if period_type == "year":
        return int(period_key), None
    year_text, month_text = period_key.split("-")
    return int(year_text), int(month_text)


def ensure_period(db: Session, period_type: str, period_key: str) -> None:
    from app.services import time as clock

    # Будущий месяц или год не пишет периоды в базу: report досчитывает их через planned_rows.
    ensure_all(db, clock.today())
    db.commit()
    db.expire_all()


def add_budget(db: Session, team_id: uuid.UUID, period_type: str, period_key: str, currency: str, amount: Decimal) -> Budget:
    row = Budget(team_id=team_id, period_type=period_type, period_key=period_key, currency=currency, amount=amount)
    db.add(row)
    db.flush()
    return row


def report(db: Session, period_type: str, period_key: str, team_id: uuid.UUID | None = None) -> BudgetReport:
    ensure_period(db, period_type, period_key)
    year, month = parse_period(period_type, period_key)
    stmt = select(PaymentOccurrence).options(joinedload(PaymentOccurrence.template)).where(PaymentOccurrence.period_year == year)
    if month is not None:
        stmt = stmt.where(PaymentOccurrence.period_month == month)
    if team_id is not None:
        stmt = stmt.where(PaymentOccurrence.team_id == team_id)
    today = clock.today()
    rows = [row for row in db.scalars(stmt).unique().all() if not hidden(row, today)]
    first = date(year, month or 1, 1)
    last = date(year, month, monthrange(year, month)[1]) if month is not None else date(year, 12, 31)
    rows += [
        row
        for row in planned_rows(db, team_ids=[team_id] if team_id is not None else None, start=first, end=last, today=today)
        if (row.period_year, row.period_month if month is not None else None) == (year, month)
    ]
    fact = {currency: Decimal("0.00") for currency in CURRENCIES}
    expected = {currency: Decimal("0.00") for currency in CURRENCIES}
    for row in rows:
        if row.currency not in fact:
            continue
        if row.paid_at is None:
            expected[row.currency] += Decimal(row.amount)
        else:
            fact_amount = row.paid_amount if row.paid_amount is not None else row.amount
            fact[row.currency] += Decimal(fact_amount)
    plan_stmt = select(Budget).where(Budget.period_type == period_type, Budget.period_key == period_key)
    if team_id is not None:
        plan_stmt = plan_stmt.where(Budget.team_id == team_id)
    plans = db.scalars(plan_stmt).all()
    by_currency = {plan.currency: plan for plan in plans}
    lines = [
        BudgetLine(
            id=by_currency[currency].id if currency in by_currency else None,
            currency=currency,
            plan_amount=by_currency[currency].amount if currency in by_currency else None,
            fact_amount=fact[currency],
            expected_amount=expected[currency],
        )
        for currency in CURRENCIES
    ]
    return BudgetReport(
        period_type=period_type,
        period_key=period_key,
        timezone=clock.zone().key,
        rows=lines,
    )

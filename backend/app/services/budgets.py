import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models import Budget, PaymentOccurrence
from app.schemas.budget import CURRENCIES, BudgetLine, BudgetReport
from app.services.occurrences import ensure_all


def parse_period(period_type: str, period_key: str) -> tuple[int, int | None]:
    if period_type == "year":
        return int(period_key), None
    year_text, month_text = period_key.split("-")
    return int(year_text), int(month_text)


def ensure_period(db: Session, period_type: str, period_key: str) -> None:
    from app.services import time as clock

    today = clock.today()
    if period_type == "month":
        year, month = parse_period(period_type, period_key)
        anchor = date(year, month or 1, 1)
    else:
        year, _month = parse_period(period_type, period_key)
        anchor = date(year, 12, 1)
    ensure_all(db, anchor if anchor > today else today)
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
    rows = db.scalars(stmt).unique().all()
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
        timezone=get_settings().timezone,
        rows=lines,
    )

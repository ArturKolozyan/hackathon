import uuid
from datetime import date

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.models import PaymentOccurrence, RecurringPayment, User
from app.schemas.occurrence import OccurrenceOut
from app.services import time as clock
from app.services.present import occurrence_out
from app.services.schedule import add_months, due_date, iter_months

BUCKET_RANK = {"overdue": 0, "soon": 1, "rest": 2, "history": 3}


def ensure_template(db: Session, template: RecurringPayment, today: date) -> int:
    """Архивный шаблон не рожает новые периоды. Неоплаченные живые — обновляются из шаблона."""
    if template.is_archived:
        return 0
    end = add_months(today, get_settings().horizon_months)
    rows = db.scalars(
        select(PaymentOccurrence).where(PaymentOccurrence.recurring_payment_id == template.id)
    ).all()
    existing = {(row.period_year, row.period_month): row for row in rows}
    created = 0
    for year, month in iter_months(template.starts_on, end):
        period_due = due_date(year, month, template.day_of_month)
        if period_due < template.starts_on:
            continue
        current = existing.get((year, month))
        if current is None:
            current = PaymentOccurrence(
                recurring_payment_id=template.id,
                period_year=year,
                period_month=month,
                due_date=period_due,
                title=template.title,
                description=template.description,
                amount=template.amount,
                currency=template.currency,
            )
            try:
                with db.begin_nested():
                    db.add(current)
                    db.flush()
            except IntegrityError:
                db.expunge(current)
                continue
            existing[(year, month)] = current
            created += 1
            continue
        if current.paid_at is None:
            current.due_date = period_due
            current.amount = template.amount
            current.currency = template.currency
            current.title = template.title
            current.description = template.description
    return created


def ensure_all(db: Session, today: date | None = None) -> int:
    current = today or clock.today()
    templates = db.scalars(select(RecurringPayment).where(RecurringPayment.is_archived.is_(False))).all()
    created = 0
    for template in templates:
        created += ensure_template(db, template, current)
    return created


def _load_stmt():
    return select(PaymentOccurrence).options(
        joinedload(PaymentOccurrence.template).joinedload(RecurringPayment.responsible),
        joinedload(PaymentOccurrence.payer),
    )


def load_occurrence(db: Session, occurrence_id: uuid.UUID) -> PaymentOccurrence | None:
    return db.scalars(_load_stmt().where(PaymentOccurrence.id == occurrence_id)).unique().one_or_none()


def list_views(
    db: Session,
    *,
    view: str = "all",
    responsible_id: uuid.UUID | None = None,
    recurring_payment_id: uuid.UUID | None = None,
    status: str | None = None,
) -> tuple[date, list[OccurrenceOut]]:
    current = clock.today()
    ensure_all(db, current)
    db.commit()
    # expire_on_commit выключен: без expire связь paid_by остаётся пустой в identity map.
    db.expire_all()
    stmt = _load_stmt()
    if recurring_payment_id is not None:
        stmt = stmt.where(PaymentOccurrence.recurring_payment_id == recurring_payment_id)
    rows = db.scalars(stmt).unique().all()
    items = [occurrence_out(row, row.template, current) for row in rows]
    if responsible_id is not None:
        items = [item for item in items if item.responsible.id == responsible_id]
    if view == "inbox":
        items = [item for item in items if item.status != "paid"]
    elif view == "history":
        items = [item for item in items if item.status == "paid"]
    if status is not None:
        items = [item for item in items if item.status == status]
    if view == "history":
        items.sort(key=lambda item: (item.paid_at is None, -(item.paid_at.timestamp() if item.paid_at else 0), item.title))
    else:
        items.sort(key=lambda item: (BUCKET_RANK[item.bucket], item.due_date.toordinal(), item.title))
    return current, items


def require_occurrence(db: Session, occurrence_id: uuid.UUID) -> PaymentOccurrence:
    row = load_occurrence(db, occurrence_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Период не найден")
    return row


def view_one(db: Session, occurrence_id: uuid.UUID) -> OccurrenceOut:
    db.expire_all()
    row = require_occurrence(db, occurrence_id)
    return occurrence_out(row, row.template, clock.today())

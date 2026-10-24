import uuid

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.models import PaymentOccurrence, RecurringPayment, User
from app.schemas.recurring import RecurringOut
from app.services import time as clock
from app.services.occurrences import ensure_template
from app.services.present import recurring_out


def load_template(db: Session, payment_id: uuid.UUID, team_id: uuid.UUID | None = None) -> RecurringPayment:
    stmt = (
        select(RecurringPayment)
        .where(RecurringPayment.id == payment_id)
        .options(joinedload(RecurringPayment.responsible))
    )
    row = db.scalars(stmt).unique().one_or_none()
    if row is None or (team_id is not None and row.team_id != team_id):
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    return row


def occurrences_for(db: Session, template_id: uuid.UUID) -> list[PaymentOccurrence]:
    return list(
        db.scalars(select(PaymentOccurrence).where(PaymentOccurrence.recurring_payment_id == template_id)).all()
    )


def to_out(db: Session, template: RecurringPayment) -> RecurringOut:
    if template.responsible is None and template.responsible_user_id is not None:
        template.responsible = db.get(User, template.responsible_user_id)
    return recurring_out(template, occurrences_for(db, template.id))


def touch(entity) -> None:
    entity.updated_at = clock.now()

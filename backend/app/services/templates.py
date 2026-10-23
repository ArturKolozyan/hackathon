import uuid

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.models import PaymentOccurrence, RecurringPayment, User
from app.schemas.recurring import RecurringOut
from app.services import time as clock
from app.services.occurrences import ensure_template
from app.services.present import recurring_out


def require_active_user(db: Session, user_id: uuid.UUID) -> User:
    user = db.get(User, user_id)
    if user is None or not user.is_active:
        raise HTTPException(status_code=400, detail="Ответственный не найден или отключён")
    return user


def load_template(db: Session, payment_id: uuid.UUID) -> RecurringPayment:
    stmt = (
        select(RecurringPayment)
        .where(RecurringPayment.id == payment_id)
        .options(joinedload(RecurringPayment.responsible))
    )
    row = db.scalars(stmt).unique().one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail="Шаблон не найден")
    return row


def occurrences_for(db: Session, template_id: uuid.UUID) -> list[PaymentOccurrence]:
    return list(
        db.scalars(select(PaymentOccurrence).where(PaymentOccurrence.recurring_payment_id == template_id)).all()
    )


def to_out(db: Session, template: RecurringPayment) -> RecurringOut:
    if template.responsible is None:
        template.responsible = db.get(User, template.responsible_user_id)
    return recurring_out(template, occurrences_for(db, template.id))


def active_admin_count(db: Session) -> int:
    value = db.scalar(select(func.count()).select_from(User).where(User.role == "admin", User.is_active.is_(True)))
    return int(value or 0)


def touch(entity) -> None:
    entity.updated_at = clock.now()

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import get_current_user, require_admin
from app.models import RecurringPayment, User
from app.schemas.recurring import RecurringCreate, RecurringOut, RecurringUpdate
from app.services import time as clock
from app.services.occurrences import ensure_template
from app.services.templates import load_template, require_active_user, to_out, touch

router = APIRouter(prefix="/recurring-payments", tags=["recurring-payments"])


@router.get("", response_model=list[RecurringOut], summary="Шаблоны регулярных платежей")
def list_payments(
    include_archived: bool = False,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[RecurringOut]:
    stmt = select(RecurringPayment).options(joinedload(RecurringPayment.responsible)).order_by(RecurringPayment.title)
    if not include_archived:
        stmt = stmt.where(RecurringPayment.is_archived.is_(False))
    rows = db.scalars(stmt).unique().all()
    return [to_out(db, row) for row in rows]


@router.post("", response_model=RecurringOut, status_code=201, summary="Создать шаблон")
def create_payment(
    payload: RecurringCreate,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RecurringOut:
    responsible = require_active_user(db, payload.responsible_user_id)
    template = RecurringPayment(
        title=payload.title,
        description=payload.description,
        amount=payload.amount,
        currency=payload.currency,
        day_of_month=payload.day_of_month,
        starts_on=payload.starts_on,
        responsible_user_id=responsible.id,
        created_by_id=actor.id,
        is_archived=False,
        responsible=responsible,
    )
    db.add(template)
    db.flush()
    ensure_template(db, template, clock.today())
    db.commit()
    db.refresh(template)
    return to_out(db, load_template(db, template.id))


@router.get("/{payment_id}", response_model=RecurringOut, summary="Карточка шаблона")
def get_payment(payment_id: UUID, _: User = Depends(get_current_user), db: Session = Depends(get_db)) -> RecurringOut:
    return to_out(db, load_template(db, payment_id))


@router.patch("/{payment_id}", response_model=RecurringOut, summary="Изменить шаблон")
def update_payment(
    payment_id: UUID,
    payload: RecurringUpdate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> RecurringOut:
    template = load_template(db, payment_id)
    data = payload.model_dump(exclude_unset=True)
    if "responsible_user_id" in data and data["responsible_user_id"] != template.responsible_user_id:
        responsible = require_active_user(db, data["responsible_user_id"])
        template.responsible = responsible
    for key, value in data.items():
        setattr(template, key, value)
    touch(template)
    db.flush()
    ensure_template(db, template, clock.today())
    db.commit()
    return to_out(db, load_template(db, template.id))


@router.delete("/{payment_id}", response_model=RecurringOut, summary="Архивировать шаблон")
def archive_payment(payment_id: UUID, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> RecurringOut:
    template = load_template(db, payment_id)
    if template.is_archived:
        return to_out(db, template)
    template.is_archived = True
    touch(template)
    db.commit()
    return to_out(db, load_template(db, template.id))

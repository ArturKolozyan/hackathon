from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import get_team_context, require_manager
from app.models import RecurringPayment
from app.schemas.recurring import RecurringCreate, RecurringOut, RecurringUpdate
from app.services import time as clock
from app.services.access import TeamContext
from app.services.audit import record
from app.services.occurrences import ensure_template
from app.services.teams import require_participant
from app.services.templates import load_template, to_out, touch

router = APIRouter(prefix="/recurring-payments", tags=["recurring-payments"])


@router.get("", response_model=list[RecurringOut], summary="Шаблоны регулярных платежей")
def list_payments(
    include_archived: bool = False,
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> list[RecurringOut]:
    stmt = (
        select(RecurringPayment)
        .where(RecurringPayment.team_id == ctx.team.id)
        .options(joinedload(RecurringPayment.responsible))
        .order_by(RecurringPayment.title)
    )
    if not include_archived:
        stmt = stmt.where(RecurringPayment.is_archived.is_(False))
    rows = db.scalars(stmt).unique().all()
    return [to_out(db, row) for row in rows]


@router.post("", response_model=RecurringOut, status_code=201, summary="Создать шаблон")
def create_payment(
    payload: RecurringCreate,
    ctx: TeamContext = Depends(require_manager),
    db: Session = Depends(get_db),
) -> RecurringOut:
    responsible = None
    if payload.responsible_user_id is not None:
        responsible = require_participant(db, ctx.team.id, payload.responsible_user_id)
    template = RecurringPayment(
        team_id=ctx.team.id,
        title=payload.title,
        description=payload.description,
        amount=payload.amount,
        currency=payload.currency,
        day_of_month=payload.day_of_month,
        starts_on=payload.starts_on,
        responsible_user_id=responsible.id if responsible is not None else None,
        created_by_id=ctx.user.id,
        is_archived=False,
        responsible=responsible,
    )
    db.add(template)
    db.flush()
    ensure_template(db, template, clock.today())
    record(
        db,
        action="template.create",
        actor=ctx.user,
        entity_type="recurring_payment",
        entity_id=template.id,
        team_id=ctx.team.id,
        meta={"title": template.title, "currency": template.currency, "amount": f"{template.amount:.2f}"},
    )
    db.commit()
    db.refresh(template)
    return to_out(db, load_template(db, template.id, ctx.team.id))


@router.get("/{payment_id}", response_model=RecurringOut, summary="Карточка шаблона")
def get_payment(
    payment_id: UUID,
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> RecurringOut:
    return to_out(db, load_template(db, payment_id, ctx.team.id))


@router.patch("/{payment_id}", response_model=RecurringOut, summary="Изменить шаблон")
def update_payment(
    payment_id: UUID,
    payload: RecurringUpdate,
    ctx: TeamContext = Depends(require_manager),
    db: Session = Depends(get_db),
) -> RecurringOut:
    template = load_template(db, payment_id, ctx.team.id)
    data = payload.model_dump(exclude_unset=True)
    if "responsible_user_id" in data:
        raw = data["responsible_user_id"]
        if raw is None:
            template.responsible = None
        else:
            template.responsible = require_participant(db, ctx.team.id, raw)
    for key, value in data.items():
        setattr(template, key, value)
    touch(template)
    db.flush()
    ensure_template(db, template, clock.today())
    record(
        db,
        action="template.update",
        actor=ctx.user,
        entity_type="recurring_payment",
        entity_id=template.id,
        team_id=ctx.team.id,
        meta={"title": template.title, "fields": sorted(data.keys())},
    )
    db.commit()
    return to_out(db, load_template(db, template.id, ctx.team.id))


@router.delete("/{payment_id}", response_model=RecurringOut, summary="Архивировать шаблон")
def archive_payment(
    payment_id: UUID,
    ctx: TeamContext = Depends(require_manager),
    db: Session = Depends(get_db),
) -> RecurringOut:
    template = load_template(db, payment_id, ctx.team.id)
    if template.is_archived:
        return to_out(db, template)
    template.is_archived = True
    touch(template)
    record(
        db,
        action="template.delete",
        actor=ctx.user,
        entity_type="recurring_payment",
        entity_id=template.id,
        team_id=ctx.team.id,
        meta={"title": template.title},
    )
    db.commit()
    return to_out(db, load_template(db, template.id, ctx.team.id))

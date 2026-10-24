from datetime import date
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import get_team_context, require_manager
from app.models import RecurringPayment
from app.schemas.recurring import RecurringCreate, RecurringOut, RecurringUpdate
from app.services import time as clock
from app.services.access import TeamContext
from app.services.audit import record
from app.services.notify import dispatch_due_reminders
from app.services.occurrences import ensure_template
from app.services.teams import require_participant
from app.services.templates import load_template, to_out, touch

router = APIRouter(prefix="/recurring-payments", tags=["recurring-payments"])


def _shown(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _changes(before: dict, template: RecurringPayment) -> dict:
    changed: dict[str, dict[str, str]] = {}
    for key, old in before.items():
        if key == "next_payment_date":
            continue
        current = getattr(template, key, None)
        if key == "responsible_user_id":
            current = template.responsible_user_id
        if _shown(old) == _shown(current):
            continue
        changed[key] = {"was": _shown(old), "became": _shown(current)}
    return changed


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
        day_of_month=int(payload.day_of_month or 1),
        starts_on=payload.starts_on or clock.today(),
        periodicity=payload.periodicity,
        interval_months=payload.interval_months,
        responsible_user_id=responsible.id if responsible is not None else None,
        created_by_id=ctx.user.id,
        is_archived=False,
        responsible=responsible,
    )
    db.add(template)
    db.flush()
    ensure_template(db, template, clock.today(), sync_future=True)
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
    dispatch_due_reminders(db)
    db.commit()
    return to_out(db, load_template(db, template.id, ctx.team.id))


@router.get("/{id}", response_model=RecurringOut, summary="Карточка шаблона")
def get_payment(
    id: UUID,
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> RecurringOut:
    return to_out(db, load_template(db, id, ctx.team.id))


@router.patch("/{id}", response_model=RecurringOut, summary="Изменить шаблон")
def update_payment(
    id: UUID,
    payload: RecurringUpdate,
    ctx: TeamContext = Depends(require_manager),
    db: Session = Depends(get_db),
) -> RecurringOut:
    template = load_template(db, id, ctx.team.id)
    data = payload.model_dump(exclude_unset=True)
    if "periodicity" in data or "interval_months" in data:
        data["periodicity"] = payload.periodicity
        data["interval_months"] = payload.interval_months
    if data.get("next_payment_date") is not None:
        data["day_of_month"] = data["next_payment_date"].day
        data["starts_on"] = data["next_payment_date"]
    data.pop("next_payment_date", None)
    before = {key: getattr(template, key) for key in data if key != "responsible_user_id"}
    if "responsible_user_id" in data:
        before["responsible_user_id"] = template.responsible_user_id
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
    ensure_template(db, template, clock.today(), sync_future=True)
    record(
        db,
        action="template.update",
        actor=ctx.user,
        entity_type="recurring_payment",
        entity_id=template.id,
        team_id=ctx.team.id,
        meta={
            "title": template.title,
            "fields": sorted(key for key in data if key != "next_payment_date"),
            "changes": _changes(before, template),
        },
    )
    db.commit()
    dispatch_due_reminders(db)
    db.commit()
    return to_out(db, load_template(db, template.id, ctx.team.id))


@router.delete("/{id}", response_model=RecurringOut, summary="Архивировать шаблон")
def archive_payment(
    id: UUID,
    ctx: TeamContext = Depends(require_manager),
    db: Session = Depends(get_db),
    remind_overdue: bool | None = Query(default=None),
) -> RecurringOut:
    template = load_template(db, id, ctx.team.id)
    if isinstance(remind_overdue, bool):
        template.remind_archived_overdue = remind_overdue
    if template.is_archived:
        touch(template)
        db.commit()
        return to_out(db, load_template(db, template.id, ctx.team.id))
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

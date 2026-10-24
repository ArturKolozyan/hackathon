from datetime import date
from decimal import Decimal
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
from app.services.notify import dispatch_due_reminders
from app.services.occurrences import drop_archived_future, ensure_template, resume_from_today
from app.services.schedule import due_date
from app.services.present import next_due
from app.services.templates import occurrences_for
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
    today = clock.today()
    nxt = data.pop("next_payment_date", None)
    if nxt is not None and nxt != next_due(template, occurrences_for(db, template.id), today):
        day = data.get("day_of_month") or nxt.day
        # Платёж «31-го» в коротком месяце показывается 30-м или 28-м. Тот же конец месяца — якорь не теряем.
        if nxt == due_date(nxt.year, nxt.month, 31) and template.day_of_month > nxt.day and "day_of_month" not in data:
            day = template.day_of_month
        data["day_of_month"] = day
        data["starts_on"] = nxt
    reopening = data.get("is_archived") is False and template.is_archived
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
    if reopening:
        resume_from_today(template, today)
    touch(template)
    db.flush()
    if template.is_archived:
        drop_archived_future(db, template, today)
    ensure_template(db, template, today, sync_future=True)
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
) -> RecurringOut:
    template = load_template(db, id, ctx.team.id)
    if template.is_archived:
        touch(template)
        db.commit()
        return to_out(db, load_template(db, template.id, ctx.team.id))
    template.is_archived = True
    touch(template)
    drop_archived_future(db, template, clock.today())
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

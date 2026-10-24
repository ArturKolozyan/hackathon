from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_team_context
from app.models import PaymentOccurrence
from app.services.access import TeamContext
from app.schemas.occurrence import ConfirmIn, InboxOut, OccurrenceList, OccurrenceOut, OccurrencePatch
from app.services import time as clock
from app.services.audit import record
from app.services.notify import PAID, UNPAID, notify_event
from app.services.occurrences import list_views, require_occurrence, view_one
from app.services.schedule import parse_paid_at
from app.services.templates import touch

router = APIRouter(prefix="/payment-occurrences", tags=["payment-occurrences"])


def _filters(user_id: UUID, mine: bool, responsible_id: UUID | None) -> UUID | None:
    if mine:
        return user_id
    return responsible_id


@router.get("/inbox", response_model=InboxOut, summary="Инбокс: просрочено, скоро, остальное")
def inbox(
    mine: bool = False,
    responsible_id: UUID | None = None,
    recurring_payment_id: UUID | None = None,
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> InboxOut:
    today, items = list_views(
        db,
        view="inbox",
        team_id=ctx.team.id,
        responsible_id=_filters(ctx.user.id, mine, responsible_id),
        recurring_payment_id=recurring_payment_id,
    )
    settings = get_settings()
    return InboxOut(
        timezone=settings.timezone,
        today=today,
        soon_days=settings.soon_days,
        overdue=[item for item in items if item.bucket == "overdue"],
        soon=[item for item in items if item.bucket == "soon"],
        rest=[item for item in items if item.bucket == "rest"],
    )


@router.get("", response_model=OccurrenceList, summary="Периоды")
def list_occurrences(
    view: str = Query(default="all", pattern="^(inbox|history|all)$"),
    mine: bool = False,
    responsible_id: UUID | None = None,
    recurring_payment_id: UUID | None = None,
    status: str | None = Query(default=None, pattern="^(overdue|due_soon|upcoming|paid)$"),
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> OccurrenceList:
    today, items = list_views(
        db,
        view=view,
        team_id=ctx.team.id,
        responsible_id=_filters(ctx.user.id, mine, responsible_id),
        recurring_payment_id=recurring_payment_id,
        status=status,
    )
    settings = get_settings()
    return OccurrenceList(timezone=settings.timezone, today=today, soon_days=settings.soon_days, items=items)


@router.get("/{occurrence_id}", response_model=OccurrenceOut, summary="Карточка периода")
def get_occurrence(
    occurrence_id: UUID,
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> OccurrenceOut:
    return view_one(db, occurrence_id, ctx.team.id)


def _apply_paid_at(raw: str | None) -> datetime:
    try:
        value = parse_paid_at(raw, now=clock.now(), zone=clock.zone())
    except ValueError:
        raise HTTPException(status_code=422, detail="Некорректная дата оплаты") from None
    if value.astimezone(clock.zone()).date() > clock.today():
        raise HTTPException(status_code=422, detail="Дата оплаты не может быть в будущем")
    return value


def _paid_on(value: datetime) -> str:
    return value.astimezone(clock.zone()).date().isoformat()


def _audit_paid_change(db: Session, occurrence: PaymentOccurrence, actor, previous: datetime | None) -> None:
    current = occurrence.paid_at
    if previous is None and current is not None:
        record(
            db,
            action="occurrence.paid",
            actor=actor,
            entity_type="payment_occurrence",
            entity_id=occurrence.id,
            meta={"paid_on": _paid_on(current), "title": occurrence.title},
            team_id=occurrence.team_id,
        )
        notify_event(db, occurrence, PAID)
        return
    if previous is not None and current is None:
        record(
            db,
            action="occurrence.unpaid",
            actor=actor,
            entity_type="payment_occurrence",
            entity_id=occurrence.id,
            meta={"title": occurrence.title},
            team_id=occurrence.team_id,
        )
        notify_event(db, occurrence, UNPAID)
        return
    if previous is not None and current is not None and previous != current:
        record(
            db,
            action="occurrence.paid_at",
            actor=actor,
            entity_type="payment_occurrence",
            entity_id=occurrence.id,
            meta={"paid_on": _paid_on(current), "title": occurrence.title},
            team_id=occurrence.team_id,
        )


def _apply_receipt(occurrence: PaymentOccurrence, data: dict) -> list[str]:
    changed: list[str] = []
    if "receipt_url" in data:
        occurrence.receipt_url = data["receipt_url"]
        changed.append("receipt_url")
    if "receipt_note" in data:
        occurrence.receipt_note = data["receipt_note"]
        changed.append("receipt_note")
    return changed


@router.post(
    "/{occurrence_id}/confirm",
    response_model=OccurrenceOut,
    summary="Подтвердить оплату",
    description=(
        "Веб: paid_by — текущий пользователь. "
        "Кнопка «Оплачено» в Telegram этот метод не вызывает; worker пишет тот же paid_at "
        "(сейчас в TIMEZONE) и paid_by того пользователя rekeeper, чей Telegram нажал."
    ),
)
def confirm(
    occurrence_id: UUID,
    payload: ConfirmIn,
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> OccurrenceOut:
    occurrence = require_occurrence(db, occurrence_id, ctx.team.id)
    previous = occurrence.paid_at
    occurrence.paid_at = _apply_paid_at(payload.paid_at)
    occurrence.paid_by_id = ctx.user.id
    data = payload.model_dump(exclude_unset=True)
    if "note" in data and data["note"] is not None:
        occurrence.note = data["note"]
    receipt_fields = _apply_receipt(occurrence, data)
    touch(occurrence)
    _audit_paid_change(db, occurrence, ctx.user, previous)
    if receipt_fields:
        record(
            db,
            action="occurrence.receipt",
            actor=ctx.user,
            entity_type="payment_occurrence",
            entity_id=occurrence.id,
            meta={"fields": receipt_fields, "title": occurrence.title},
            team_id=occurrence.team_id,
        )
    db.commit()
    return view_one(db, occurrence_id, ctx.team.id)


@router.post("/{occurrence_id}/revoke", response_model=OccurrenceOut, summary="Вернуть период в инбокс")
def revoke(
    occurrence_id: UUID,
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> OccurrenceOut:
    occurrence = require_occurrence(db, occurrence_id, ctx.team.id)
    previous = occurrence.paid_at
    occurrence.paid_at = None
    occurrence.paid_by_id = None
    touch(occurrence)
    _audit_paid_change(db, occurrence, ctx.user, previous)
    db.commit()
    return view_one(db, occurrence_id, ctx.team.id)


@router.patch("/{occurrence_id}", response_model=OccurrenceOut, summary="Дата, заметка или чек периода")
def patch_occurrence(
    occurrence_id: UUID,
    payload: OccurrencePatch,
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> OccurrenceOut:
    occurrence = require_occurrence(db, occurrence_id, ctx.team.id)
    data = payload.model_dump(exclude_unset=True)
    previous = occurrence.paid_at
    if "paid_at" in data:
        raw = data["paid_at"]
        if raw is None:
            occurrence.paid_at = None
            occurrence.paid_by_id = None
        else:
            if not str(raw).strip():
                raise HTTPException(status_code=422, detail="Некорректная дата оплаты")
            occurrence.paid_at = _apply_paid_at(str(raw))
            occurrence.paid_by_id = ctx.user.id
    if "note" in data:
        occurrence.note = data["note"]
    receipt_fields = _apply_receipt(occurrence, data)
    touch(occurrence)
    if "paid_at" in data:
        _audit_paid_change(db, occurrence, ctx.user, previous)
    if receipt_fields:
        record(
            db,
            action="occurrence.receipt",
            actor=ctx.user,
            entity_type="payment_occurrence",
            entity_id=occurrence.id,
            meta={"fields": receipt_fields, "title": occurrence.title},
            team_id=occurrence.team_id,
        )
    db.commit()
    return view_one(db, occurrence_id, ctx.team.id)

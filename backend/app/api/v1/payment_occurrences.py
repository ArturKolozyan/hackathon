from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.occurrence import ConfirmIn, InboxOut, OccurrenceList, OccurrenceOut, OccurrencePatch
from app.services import time as clock
from app.services.occurrences import list_views, require_occurrence, view_one
from app.services.schedule import parse_paid_at
from app.services.templates import touch

router = APIRouter(prefix="/payment-occurrences", tags=["payment-occurrences"])


def _filters(user: User, mine: bool, responsible_id: UUID | None) -> UUID | None:
    if mine:
        return user.id
    return responsible_id


@router.get("/inbox", response_model=InboxOut, summary="Инбокс: просрочено, скоро, остальное")
def inbox(
    mine: bool = False,
    responsible_id: UUID | None = None,
    recurring_payment_id: UUID | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> InboxOut:
    today, items = list_views(
        db,
        view="inbox",
        responsible_id=_filters(user, mine, responsible_id),
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
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OccurrenceList:
    today, items = list_views(
        db,
        view=view,
        responsible_id=_filters(user, mine, responsible_id),
        recurring_payment_id=recurring_payment_id,
        status=status,
    )
    settings = get_settings()
    return OccurrenceList(timezone=settings.timezone, today=today, soon_days=settings.soon_days, items=items)


@router.get("/{occurrence_id}", response_model=OccurrenceOut, summary="Карточка периода")
def get_occurrence(
    occurrence_id: UUID,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OccurrenceOut:
    return view_one(db, occurrence_id)


def _apply_paid_at(raw: str | None) -> datetime:
    try:
        return parse_paid_at(raw, now=clock.now(), zone=clock.zone())
    except ValueError:
        raise HTTPException(status_code=422, detail="Некорректная дата оплаты") from None


@router.post(
    "/{occurrence_id}/confirm",
    response_model=OccurrenceOut,
    summary="Подтвердить оплату",
    description=(
        "Веб: paid_by — текущий пользователь. "
        "Кнопка «Оплачено» в Telegram этот метод не вызывает; worker пишет тот же paid_at "
        "(сейчас в TIMEZONE) и paid_by = активный администратор ADMIN_EMAIL."
    ),
)
def confirm(
    occurrence_id: UUID,
    payload: ConfirmIn,
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OccurrenceOut:
    occurrence = require_occurrence(db, occurrence_id)
    occurrence.paid_at = _apply_paid_at(payload.paid_at)
    occurrence.paid_by_id = actor.id
    if payload.note is not None:
        occurrence.note = payload.note
    touch(occurrence)
    db.commit()
    return view_one(db, occurrence_id)


@router.post("/{occurrence_id}/revoke", response_model=OccurrenceOut, summary="Вернуть период в инбокс")
def revoke(
    occurrence_id: UUID,
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OccurrenceOut:
    occurrence = require_occurrence(db, occurrence_id)
    occurrence.paid_at = None
    occurrence.paid_by_id = None
    touch(occurrence)
    db.commit()
    return view_one(db, occurrence_id)


@router.patch("/{occurrence_id}", response_model=OccurrenceOut, summary="Поправить фактическую дату или заметку")
def patch_occurrence(
    occurrence_id: UUID,
    payload: OccurrencePatch,
    actor: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> OccurrenceOut:
    occurrence = require_occurrence(db, occurrence_id)
    data = payload.model_dump(exclude_unset=True)
    if "paid_at" in data:
        raw = data["paid_at"]
        if raw is None:
            occurrence.paid_at = None
            occurrence.paid_by_id = None
        else:
            if not str(raw).strip():
                raise HTTPException(status_code=422, detail="Некорректная дата оплаты")
            occurrence.paid_at = _apply_paid_at(str(raw))
            occurrence.paid_by_id = actor.id
    if "note" in data:
        occurrence.note = data["note"]
    touch(occurrence)
    db.commit()
    return view_one(db, occurrence_id)

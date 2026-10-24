import csv
import io
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_team_context
from app.models import PaymentOccurrence
from app.services.access import TeamContext, require_role
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
    date_from: date | None = None,
    date_to: date | None = None,
    currency: str | None = Query(default=None, pattern="^(RUB|USD|EUR)$"),
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> InboxOut:
    today, items = list_views(
        db,
        view="inbox",
        team_id=ctx.team.id,
        responsible_id=_filters(ctx.user.id, mine, responsible_id),
        recurring_payment_id=recurring_payment_id,
        date_from=date_from,
        date_to=date_to,
        currency=currency,
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
    date_from: date | None = None,
    date_to: date | None = None,
    currency: str | None = Query(default=None, pattern="^(RUB|USD|EUR)$"),
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
        date_from=date_from,
        date_to=date_to,
        currency=currency,
    )
    settings = get_settings()
    return OccurrenceList(timezone=settings.timezone, today=today, soon_days=settings.soon_days, items=items)


def _csv_money(value: Decimal | None) -> str:
    if value is None:
        return ""
    return f"{Decimal(value):.2f}".replace(".", ",")


def _csv_status(status: str) -> str:
    if status == "paid":
        return "оплачен"
    if status == "overdue":
        return "просрочен"
    return "не оплачен"


def _overdue_days(item: OccurrenceOut, today: date) -> int:
    if item.status == "overdue":
        return (today - item.due_date).days
    if item.lateness_days is not None and item.lateness_days > 0:
        return item.lateness_days
    return 0


@router.get("/export.csv", summary="CSV для бухгалтера")
def export_csv(
    view: str = Query(default="all", pattern="^(inbox|history|all)$"),
    mine: bool = False,
    responsible_id: UUID | None = None,
    recurring_payment_id: UUID | None = None,
    status: str | None = Query(default=None, pattern="^(overdue|due_soon|upcoming|paid)$"),
    date_from: date | None = None,
    date_to: date | None = None,
    currency: str | None = Query(default=None, pattern="^(RUB|USD|EUR)$"),
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> Response:
    today, items = list_views(
        db,
        view=view,
        team_id=ctx.team.id,
        responsible_id=_filters(ctx.user.id, mine, responsible_id),
        recurring_payment_id=recurring_payment_id,
        status=status,
        date_from=date_from,
        date_to=date_to,
        currency=currency,
    )
    buffer = io.StringIO()
    writer = csv.writer(buffer, delimiter=";", lineterminator="\r\n")
    writer.writerow(
        [
            "отдел",
            "платёж",
            "период",
            "срок",
            "статус",
            "плановая сумма",
            "фактическая сумма",
            "валюта",
            "дата оплаты",
            "кто оплатил",
            "дней просрочки",
            "ссылка на чек",
            "комментарий",
        ]
    )
    for item in items:
        actual = item.paid_amount if item.paid_amount is not None else (item.amount if item.status == "paid" else None)
        writer.writerow(
            [
                ctx.team.name,
                item.title,
                item.period_label,
                item.due_date.isoformat(),
                _csv_status(item.status),
                _csv_money(item.amount),
                _csv_money(actual),
                item.currency,
                item.paid_on.isoformat() if item.paid_on else "",
                item.paid_by.full_name if item.paid_by else "",
                _overdue_days(item, today),
                item.receipt_url or "",
                item.note or item.receipt_note or "",
            ]
        )
    body = "\ufeff" + buffer.getvalue()
    return Response(
        content=body.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="occurrences.csv"'},
    )


@router.get("/{id}", response_model=OccurrenceOut, summary="Карточка периода")
def get_occurrence(
    id: UUID,
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> OccurrenceOut:
    return view_one(db, id, ctx.team.id)


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


def _shown(value) -> str:
    if value is None:
        return "—"
    if isinstance(value, Decimal):
        return f"{value:.2f}"
    if isinstance(value, datetime):
        return value.astimezone(clock.zone()).date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _pair(was, became) -> dict[str, str]:
    return {"was": _shown(was), "became": _shown(became)}


def _audit_paid_change(db: Session, occurrence: PaymentOccurrence, actor, previous: datetime | None) -> None:
    current = occurrence.paid_at
    if previous is None and current is not None:
        record(
            db,
            action="occurrence.paid",
            actor=actor,
            entity_type="payment_occurrence",
            entity_id=occurrence.id,
            meta={
                "paid_on": _paid_on(current),
                "title": occurrence.title,
                "changes": {"paid_at": _pair(previous, current)},
            },
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
            meta={"title": occurrence.title, "changes": {"paid_at": _pair(previous, current)}},
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
            meta={
                "paid_on": _paid_on(current),
                "title": occurrence.title,
                "changes": {"paid_at": _pair(previous, current)},
            },
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
    if previous is None:
        occurrence.paid_by_id = ctx.user.id
    data = payload.model_dump(exclude_unset=True)
    if "paid_amount" in data and data["paid_amount"] is not None:
        occurrence.paid_amount = data["paid_amount"]
    elif occurrence.paid_amount is None:
        occurrence.paid_amount = occurrence.amount
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
    occurrence.paid_amount = None
    touch(occurrence)
    _audit_paid_change(db, occurrence, ctx.user, previous)
    db.commit()
    return view_one(db, occurrence_id, ctx.team.id)


@router.patch("/{id}", response_model=OccurrenceOut, summary="Дата, заметка или чек периода")
def patch_occurrence(
    id: UUID,
    payload: OccurrencePatch,
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> OccurrenceOut:
    occurrence = require_occurrence(db, id, ctx.team.id)
    data = payload.model_dump(exclude_unset=True)
    snapshot_keys = {"title", "amount", "currency", "due_date"}
    if snapshot_keys & data.keys():
        require_role(ctx, "admin")
    previous = occurrence.paid_at
    changes: dict[str, dict[str, str]] = {}
    if "paid_at" in data:
        raw = data["paid_at"]
        if raw is None:
            occurrence.paid_at = None
            occurrence.paid_by_id = None
            occurrence.paid_amount = None
        else:
            if not str(raw).strip():
                raise HTTPException(status_code=422, detail="Некорректная дата оплаты")
            was_unpaid = occurrence.paid_at is None
            occurrence.paid_at = _apply_paid_at(str(raw))
            if was_unpaid:
                occurrence.paid_by_id = ctx.user.id
                if occurrence.paid_amount is None and "paid_amount" not in data:
                    occurrence.paid_amount = occurrence.amount
    if "paid_amount" in data:
        old_amount = occurrence.paid_amount
        occurrence.paid_amount = data["paid_amount"]
        if _shown(old_amount) != _shown(occurrence.paid_amount):
            changes["paid_amount"] = _pair(old_amount, occurrence.paid_amount)
    if "title" in data and data["title"] is not None and data["title"] != occurrence.title:
        changes["title"] = _pair(occurrence.title, data["title"])
        occurrence.title = data["title"]
    if "amount" in data and data["amount"] is not None and data["amount"] != occurrence.amount:
        changes["amount"] = _pair(occurrence.amount, data["amount"])
        occurrence.amount = data["amount"]
    if "currency" in data and data["currency"] is not None and data["currency"] != occurrence.currency:
        changes["currency"] = _pair(occurrence.currency, data["currency"])
        occurrence.currency = data["currency"]
    if "due_date" in data and data["due_date"] is not None and data["due_date"] != occurrence.due_date:
        new_due = data["due_date"]
        if (new_due.year, new_due.month) != (occurrence.period_year, occurrence.period_month):
            clash = db.scalar(
                select(PaymentOccurrence.id).where(
                    PaymentOccurrence.recurring_payment_id == occurrence.recurring_payment_id,
                    PaymentOccurrence.period_year == new_due.year,
                    PaymentOccurrence.period_month == new_due.month,
                    PaymentOccurrence.id != occurrence.id,
                )
            )
            if clash is not None:
                raise HTTPException(status_code=409, detail="В этом месяце у платежа уже есть период")
            occurrence.period_year = new_due.year
            occurrence.period_month = new_due.month
        changes["due_date"] = _pair(occurrence.due_date, new_due)
        occurrence.due_date = new_due
    if "note" in data and data["note"] != occurrence.note:
        changes["note"] = _pair(occurrence.note, data["note"])
        occurrence.note = data["note"]
    receipt_fields = _apply_receipt(occurrence, data)
    touch(occurrence)
    if "paid_at" in data:
        _audit_paid_change(db, occurrence, ctx.user, previous)
    if changes:
        record(
            db,
            action="occurrence.update",
            actor=ctx.user,
            entity_type="payment_occurrence",
            entity_id=occurrence.id,
            meta={"title": occurrence.title, "changes": changes},
            team_id=occurrence.team_id,
        )
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
    return view_one(db, id, ctx.team.id)

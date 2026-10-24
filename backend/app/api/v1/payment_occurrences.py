import csv
import io
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.database import get_db
from app.core.deps import get_active_user, get_team_context
from app.models import PaymentOccurrence, User
from app.services import receipts
from app.services.access import TeamContext, department_access, require_role
from app.schemas.occurrence import ConfirmIn, InboxOut, OccurrenceList, OccurrenceOut, OccurrencePatch
from app.services import time as clock
from app.services.audit import record
from app.services.notify import PAID, UNPAID, notify_event
from app.services.occurrences import list_views, require_occurrence, view_one
from app.services.schedule import parse_paid_at, shift_month
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
        timezone=clock.zone().key,
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
    return OccurrenceList(timezone=clock.zone().key, today=today, soon_days=settings.soon_days, items=items)


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


def _csv_text(value: str) -> str:
    """Текст из формы не должен стать формулой в Excel: =, +, -, @ в начале экранируем."""
    if value and value[0] in "=+-@\t\r":
        return "'" + value
    return value


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
            "чек",
            "комментарий",
        ]
    )
    for item in items:
        actual = item.paid_amount if item.paid_amount is not None else (item.amount if item.status == "paid" else None)
        writer.writerow(
            [
                _csv_text(ctx.team.name),
                _csv_text(item.title),
                item.period_label,
                item.due_date.isoformat(),
                _csv_status(item.status),
                _csv_money(item.amount),
                _csv_money(actual),
                item.currency,
                item.paid_on.isoformat() if item.paid_on else "",
                _csv_text(item.paid_by.full_name if item.paid_by else ""),
                _overdue_days(item, today),
                _csv_text(item.receipt.name if item.receipt else ""),
                _csv_text(item.note or item.receipt_note or ""),
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
    if "receipt_note" in data and data["receipt_note"] != occurrence.receipt_note:
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


def _receipt_audit(db: Session, occurrence: PaymentOccurrence, actor, action: str, name: str | None) -> None:
    record(
        db,
        action=action,
        actor=actor,
        entity_type="payment_occurrence",
        entity_id=occurrence.id,
        meta={"title": occurrence.title, "file": name or ""},
        team_id=occurrence.team_id,
    )


@router.post(
    "/{occurrence_id}/receipt",
    response_model=OccurrenceOut,
    summary="Прикрепить файл чека",
    description=(
        "multipart/form-data: file и необязательный note (комментарий к чеку). "
        "PDF, JPG/JPEG, PNG, HEIC/HEIF или WebP, проверка по расширению и по содержимому. "
        "Размер — до RECEIPT_MAX_MB (по умолчанию 10 МБ). Новый файл заменяет прежний."
    ),
)
def upload_receipt(
    occurrence_id: UUID,
    file: UploadFile = File(...),
    note: str | None = Form(default=None, max_length=2000),
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> OccurrenceOut:
    occurrence = require_occurrence(db, occurrence_id, ctx.team.id)
    data, family, content_type, name = receipts.read_upload(file)
    key = receipts.store(data, family)
    try:
        old_key = receipts.attach(occurrence, key, name, content_type, len(data), clock.now())
        if note is not None:
            occurrence.receipt_note = note.strip() or None
        touch(occurrence)
        _receipt_audit(db, occurrence, ctx.user, "occurrence.receipt_attach", name)
        db.commit()
    except Exception:
        db.rollback()
        receipts.discard(key)
        raise
    if old_key and old_key != key:
        receipts.discard(old_key)
    return view_one(db, occurrence_id, ctx.team.id)


@router.delete("/{occurrence_id}/receipt", response_model=OccurrenceOut, summary="Убрать файл чека")
def delete_receipt(
    occurrence_id: UUID,
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> OccurrenceOut:
    occurrence = require_occurrence(db, occurrence_id, ctx.team.id)
    if not occurrence.receipt_file:
        return view_one(db, occurrence_id, ctx.team.id)
    name = occurrence.receipt_name
    old_key = receipts.detach(occurrence)
    touch(occurrence)
    _receipt_audit(db, occurrence, ctx.user, "occurrence.receipt_remove", name)
    db.commit()
    receipts.discard(old_key)
    return view_one(db, occurrence_id, ctx.team.id)


@router.get(
    "/{occurrence_id}/receipt",
    summary="Файл чека",
    description=(
        "Открыть или скачать чек (?download=1). Работает по cookie без X-Team-Id: "
        "доступ есть у тех, кто видит отдел периода, и у владельца."
    ),
    response_class=FileResponse,
)
def get_receipt(
    occurrence_id: UUID,
    download: bool = False,
    user: User = Depends(get_active_user),
    db: Session = Depends(get_db),
) -> FileResponse:
    occurrence = db.get(PaymentOccurrence, occurrence_id)
    allowed = {row.team_id for row in department_access(db, user)}
    if occurrence is None or occurrence.team_id not in allowed:
        raise HTTPException(status_code=404, detail="Период не найден")
    path = receipts.path_of(occurrence.receipt_file or "")
    if path is None:
        raise HTTPException(status_code=404, detail="Чека нет")
    name = occurrence.receipt_name or path.name
    content_type = occurrence.receipt_type or "application/octet-stream"
    # HEIC/HEIF браузеры не показывают: такой чек только скачивается.
    inline = content_type == "application/pdf" or content_type in {"image/jpeg", "image/png", "image/webp"}
    disposition = "inline" if inline and not download else "attachment"
    ascii_name = name.encode("ascii", "ignore").decode() or path.name
    ascii_name = ascii_name.replace('"', "")
    return FileResponse(
        path,
        media_type=content_type,
        headers={
            "Content-Disposition": f"{disposition}; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(name)}",
            # Чек могут заменить: браузер переспрашивает каждый раз.
            "Cache-Control": "private, no-cache",
            "X-Content-Type-Options": "nosniff",
        },
    )


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
        # Перенос срока не меняет сам период (сентябрь остаётся сентябрём), иначе расписание
        # создаст его заново и платёж задвоится. Двигать можно в пределах соседних месяцев.
        lo = date(*shift_month(occurrence.period_year, occurrence.period_month, -1), 1)
        hi_year, hi_month = shift_month(occurrence.period_year, occurrence.period_month, 2)
        if not lo <= new_due < date(hi_year, hi_month, 1):
            raise HTTPException(status_code=422, detail="Срок можно перенести только в соседний месяц")
        changes["due_date"] = _pair(occurrence.due_date, new_due)
        occurrence.due_date = new_due
    if "note" in data and data["note"] != occurrence.note:
        changes["note"] = _pair(occurrence.note, data["note"])
        occurrence.note = data["note"]
    receipt_fields = _apply_receipt(occurrence, data)
    if occurrence.paid_at is None and occurrence.paid_amount is not None:
        raise HTTPException(status_code=422, detail="Фактическая сумма бывает только у оплаченного периода")
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

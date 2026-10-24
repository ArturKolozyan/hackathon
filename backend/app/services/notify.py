"""Один пайплайн событий периода для email, webhook и Telegram.

Telegram worker не вызывает: строка notification_deliveries со статусом pending.
Контейнер bot забирает очередь. Письмо и webhook уходят отсюда и помечаются sent.
"""

import logging
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

from app.core.config import get_settings
from app.integrations.email import send_reminder_email
from app.integrations.webhook import send_team_webhook, send_webhook
from app.models import Membership, NotificationDelivery, PaymentOccurrence, RecurringPayment, Team, User
from app.services import time as clock
from app.services.channels import wants_email, wants_telegram
from app.services.reminders import notification_events
from app.services.schedule import classify, period_key
from app.services.telegram_links import TEAM_RECIPIENT, resolve_team_chat_id

log = logging.getLogger("invoice_keeper.notify")

REMINDER = "occurrence.reminder"
OVERDUE = "occurrence.overdue"
PAID = "occurrence.paid"
UNPAID = "occurrence.unpaid"
_LIVE = (REMINDER, OVERDUE)


def occurrence_payload(occurrence: PaymentOccurrence, event: str) -> dict:
    settings = get_settings()
    today = clock.today()
    status = classify(occurrence.due_date, occurrence.paid_at, today, settings.soon_days)
    amount = occurrence.amount.quantize(Decimal("0.01"))
    return {
        "event": event,
        "sent_at": clock.now().isoformat(),
        "occurrence": {
            "id": str(occurrence.id),
            "title": occurrence.title,
            "amount": f"{amount:.2f}",
            "currency": occurrence.currency,
            "due_date": occurrence.due_date.isoformat(),
            "status": status,
            "period": period_key(occurrence.period_year, occurrence.period_month),
        },
    }


def _already(db: Session, occurrence_id: uuid.UUID, event: str, channel: str, recipient: str) -> bool:
    stmt = select(NotificationDelivery.id).where(
        NotificationDelivery.occurrence_id == occurrence_id,
        NotificationDelivery.event == event,
        NotificationDelivery.channel == channel,
        NotificationDelivery.recipient == recipient,
    )
    return db.scalar(stmt) is not None


def _mark(db: Session, occurrence_id: uuid.UUID, event: str, channel: str, recipient: str) -> None:
    try:
        with db.begin_nested():
            db.add(
                NotificationDelivery(
                    occurrence_id=occurrence_id,
                    event=event,
                    channel=channel,
                    recipient=recipient,
                    created_at=clock.now(),
                )
            )
            db.flush()
    except IntegrityError:
        return


def _telegram(
    db: Session,
    occurrence: PaymentOccurrence,
    event: str,
    *,
    chat_id: str,
    recipient: str,
) -> str:
    from app.services.outbox import enqueue_telegram

    return enqueue_telegram(db, occurrence, event, recipient=recipient, chat_id=chat_id)


def _team_webhook(db: Session, team_id: uuid.UUID) -> str:
    team = db.get(Team, team_id)
    if team is None or not team.webhook_url:
        return ""
    return team.webhook_url.strip()


def _user_by_recipient(db: Session, recipient: str) -> User | None:
    raw = recipient.removeprefix("user:")
    try:
        user_id = uuid.UUID(raw)
    except ValueError:
        return None
    return db.get(User, user_id)


def _personal_plan(db: Session, occurrence: PaymentOccurrence, event: str) -> list[tuple[str, str]]:
    template = occurrence.template
    responsible_id = template.responsible_user_id if template is not None else None
    seats = db.scalars(
        select(Membership)
        .where(Membership.team_id == occurrence.team_id)
        .options(joinedload(Membership.user))
    ).unique().all()
    plan: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for seat in seats:
        user = seat.user
        if user is None:
            continue
        responsible = user.id == responsible_id
        if wants_email(db, user, occurrence.team_id, responsible=responsible, event=event):
            item = ("email", f"user:{user.id}")
            if item not in seen:
                seen.add(item)
                plan.append(item)
        if wants_telegram(db, user, occurrence.team_id, responsible=responsible, event=event):
            item = ("telegram", f"user:{user.id}")
            if item not in seen:
                seen.add(item)
                plan.append(item)
    responsible = template.responsible if template is not None else None
    if responsible is not None and responsible.id == responsible_id and responsible.id not in {seat.user_id for seat in seats}:
        if wants_email(db, responsible, occurrence.team_id, responsible=True, event=event):
            item = ("email", f"user:{responsible.id}")
            if item not in seen:
                seen.add(item)
                plan.append(item)
        if wants_telegram(db, responsible, occurrence.team_id, responsible=True, event=event):
            item = ("telegram", f"user:{responsible.id}")
            if item not in seen:
                plan.append(item)
    return plan


def _plan(db: Session, occurrence: PaymentOccurrence, event: str) -> list[tuple[str, str]]:
    plan: list[tuple[str, str]] = []
    if event in _LIVE:
        plan.append(("email", ""))
    plan.append(("webhook", ""))
    if _team_webhook(db, occurrence.team_id):
        plan.append(("webhook", f"team:{occurrence.team_id}"))
    if event not in _LIVE:
        return plan
    plan.append(("telegram", TEAM_RECIPIENT))
    plan.extend(_personal_plan(db, occurrence, event))
    return plan


def _send(
    db: Session,
    channel: str,
    recipient: str,
    occurrence: PaymentOccurrence,
    event: str,
    payload: dict,
) -> str:
    if channel == "email":
        if recipient == "":
            return send_reminder_email(payload)
        user = _user_by_recipient(db, recipient)
        if user is None or not user.is_active:
            return "skipped"
        return send_reminder_email(payload, to=user.email)
    if channel == "webhook":
        if recipient == "":
            return send_webhook(payload)
        return send_team_webhook(_team_webhook(db, occurrence.team_id), payload)
    if channel != "telegram":
        return "skipped"
    if recipient == TEAM_RECIPIENT:
        chat_id, _source = resolve_team_chat_id(db, occurrence.team_id)
        return _telegram(db, occurrence, event, chat_id=chat_id or "", recipient=recipient)
    user = _user_by_recipient(db, recipient)
    if user is None or user.telegram_user_id is None:
        return "skipped"
    return _telegram(db, occurrence, event, chat_id=str(user.telegram_user_id), recipient=recipient)


def fanout(db: Session, occurrence: PaymentOccurrence, event: str) -> int:
    payload = occurrence_payload(occurrence, event)
    sent = 0
    for channel, recipient in _plan(db, occurrence, event):
        if _already(db, occurrence.id, event, channel, recipient):
            continue
        try:
            result = _send(db, channel, recipient, occurrence, event, payload)
        except Exception:
            log.exception("channel %s failed", channel)
            result = "failed"
        if result == "queued":
            sent += 1
            continue
        if result == "sent":
            _mark(db, occurrence.id, event, channel, recipient)
            sent += 1
    return sent


def notify_event(db: Session, occurrence: PaymentOccurrence, event: str) -> None:
    try:
        fanout(db, occurrence, event)
    except Exception:
        log.exception("notify %s failed", event)


def dispatch_due_reminders(db: Session) -> int:
    """Напоминания по всем периодам, которым пора. Возвращает число новых отправок."""
    settings = get_settings()
    today = clock.today()
    rows = db.scalars(
        select(PaymentOccurrence).options(
            joinedload(PaymentOccurrence.template).joinedload(RecurringPayment.responsible)
        )
    ).unique().all()
    sent = 0
    for row in rows:
        template = row.template
        archived = template is None or template.is_archived
        events = notification_events(
            due=row.due_date,
            paid_at=row.paid_at,
            archived=archived,
            today=today,
            soon_days=settings.soon_days,
        )
        for event in events:
            sent += fanout(db, row, event)
    return sent


def list_open_occurrences(db: Session, team_id: uuid.UUID) -> list[PaymentOccurrence]:
    """Неоплаченные периоды живых шаблонов. Ближайшие — первыми."""
    stmt = (
        select(PaymentOccurrence)
        .join(RecurringPayment, RecurringPayment.id == PaymentOccurrence.recurring_payment_id)
        .where(
            PaymentOccurrence.team_id == team_id,
            PaymentOccurrence.paid_at.is_(None),
            RecurringPayment.is_archived.is_(False),
        )
        .order_by(PaymentOccurrence.due_date, PaymentOccurrence.title, PaymentOccurrence.id)
    )
    return list(db.scalars(stmt).all())


def payments_phrase(count: int) -> str:
    hundred = count % 100
    ten = count % 10
    if 11 <= hundred <= 14:
        word = "платежей"
    elif ten == 1:
        word = "платёж"
    elif 2 <= ten <= 4:
        word = "платежа"
    else:
        word = "платежей"
    return f"{count} {word}"


def connect_digest(rows: list[PaymentOccurrence]) -> str:
    if not rows:
        return "Подключено. Сейчас открытых платежей нет."
    nearest = rows[:5]
    parts = [
        f"{row.title} · {row.amount:.2f} {row.currency} · до {row.due_date.strftime('%d.%m.%Y')}"
        for row in nearest
    ]
    tail = f"; и ещё {len(rows) - len(nearest)}" if len(rows) > len(nearest) else ""
    return f"Подключено. Сейчас открыто {payments_phrase(len(rows))}, ближайшие: " + "; ".join(parts) + tail


def acknowledge_team_backlog(db: Session, team_id: uuid.UUID, rows: list[PaymentOccurrence]) -> None:
    """Сводка при подключении закрывает уже назревшие карточки чата.

    Строка доставки здесь — не вторая отправка, а отметка «чат уже в курсе».
    Личка и будущие T-3 / просрочка не глушатся.
    """
    settings = get_settings()
    today = clock.today()
    for row in rows:
        if row.team_id != team_id:
            continue
        for event in notification_events(
            due=row.due_date,
            paid_at=row.paid_at,
            archived=False,
            today=today,
            soon_days=settings.soon_days,
        ):
            _mark(db, row.id, event, "telegram", TEAM_RECIPIENT)

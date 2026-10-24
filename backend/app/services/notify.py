"""Один пайплайн событий периода для email, webhook и Telegram.

Telegram worker не вызывает: строка notification_deliveries со статусом pending.
Контейнер bot забирает очередь. Письмо и webhook уходят отсюда и помечаются sent.
"""

import logging
import uuid
from datetime import timedelta
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
from app.services.org_settings import load_org
from app.services.reminders import DIGEST, is_overdue, is_reminder, notification_events
from app.services.schedule import classify, period_key, period_label
from app.services.telegram_links import TEAM_RECIPIENT, resolve_team_chat_id

log = logging.getLogger("invoice_keeper.notify")

REMINDER = "occurrence.reminder"
OVERDUE = "occurrence.overdue"
PAID = "occurrence.paid"
UNPAID = "occurrence.unpaid"


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


# Вебхук отдела: одно событие пробуем не больше стольких раз, паузы между заходами растут.
WEBHOOK_TRIES = 5
WEBHOOK_PAUSE = timedelta(minutes=1)
WEBHOOK_PAUSE_MAX = timedelta(hours=6)


def _delivery(db: Session, occurrence_id: uuid.UUID, event: str, channel: str, recipient: str):
    return db.scalar(
        select(NotificationDelivery).where(
            NotificationDelivery.occurrence_id == occurrence_id,
            NotificationDelivery.event == event,
            NotificationDelivery.channel == channel,
            NotificationDelivery.recipient == recipient,
        )
    )


def _already(db: Session, occurrence_id: uuid.UUID, event: str, channel: str, recipient: str) -> bool:
    row = _delivery(db, occurrence_id, event, channel, recipient)
    if row is None:
        return False
    # Неудачный вебхук ждёт следующей попытки. Telegram pending — это очередь бота, он уже «в работе».
    return not (row.channel == "webhook" and row.status == "pending")


def _webhook_failed(db: Session, occurrence: PaymentOccurrence, event: str, recipient: str) -> None:
    """Неудача вебхука отдела: счётчик события и пауза для всего адреса отдела."""
    now = clock.now()
    row = _delivery(db, occurrence.id, event, "webhook", recipient)
    if row is None:
        row = NotificationDelivery(
            occurrence_id=occurrence.id, event=event, channel="webhook", recipient=recipient, status="pending", created_at=now
        )
        db.add(row)
    row.attempts = (row.attempts or 0) + 1
    row.last_error = "webhook failed"
    if row.attempts >= WEBHOOK_TRIES:
        row.status = "skipped"
        log.warning("team webhook gave up on %s after %s tries", event, row.attempts)
    team = db.get(Team, occurrence.team_id)
    if team is not None:
        team.webhook_failures = (team.webhook_failures or 0) + 1
        pause = min(WEBHOOK_PAUSE * (2 ** (team.webhook_failures - 1)), WEBHOOK_PAUSE_MAX)
        team.webhook_retry_at = now + pause
    db.flush()


def _webhook_ok(db: Session, team_id: uuid.UUID) -> None:
    team = db.get(Team, team_id)
    if team is not None and (team.webhook_failures or team.webhook_retry_at is not None):
        team.webhook_failures = 0
        team.webhook_retry_at = None


def _webhook_paused(db: Session, team_id: uuid.UUID) -> bool:
    team = db.get(Team, team_id)
    return team is not None and team.webhook_retry_at is not None and clock.now() < team.webhook_retry_at


def _mark(db: Session, occurrence_id: uuid.UUID, event: str, channel: str, recipient: str) -> None:
    waiting = _delivery(db, occurrence_id, event, channel, recipient)
    if waiting is not None:
        waiting.status = "sent"
        waiting.last_error = None
        db.flush()
        return
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


def _push(plan: list[tuple[str, str]], seen: set[tuple[str, str]], item: tuple[str, str]) -> None:
    if item in seen:
        return
    seen.add(item)
    plan.append(item)


def _force_copy(user: User) -> list[tuple[str, str]]:
    if not user.is_active:
        return []
    items: list[tuple[str, str]] = []
    if user.email_reminders:
        items.append(("email", f"user:{user.id}"))
    if user.telegram_user_id is not None and user.telegram_reminders:
        items.append(("telegram", f"user:{user.id}"))
    return items


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
            _push(plan, seen, ("email", f"user:{user.id}"))
        if wants_telegram(db, user, occurrence.team_id, responsible=responsible, event=event):
            _push(plan, seen, ("telegram", f"user:{user.id}"))
    seat_ids = {seat.user_id for seat in seats}
    owner = db.scalar(select(User).where(User.is_owner.is_(True)))
    if owner is not None and owner.id not in seat_ids:
        # Владелец не в отделе: письма идут, только если он сам включил этот отдел в «Почте».
        if wants_email(db, owner, occurrence.team_id, responsible=owner.id == responsible_id, event=event):
            _push(plan, seen, ("email", f"user:{owner.id}"))
    responsible = template.responsible if template is not None else None
    if responsible is not None and responsible.id == responsible_id and responsible.id not in seat_ids:
        if wants_email(db, responsible, occurrence.team_id, responsible=True, event=event):
            _push(plan, seen, ("email", f"user:{responsible.id}"))
        if wants_telegram(db, responsible, occurrence.team_id, responsible=True, event=event):
            _push(plan, seen, ("telegram", f"user:{responsible.id}"))
    if is_overdue(event):
        for seat in seats:
            if seat.role != "admin" or seat.user is None:
                continue
            for item in _force_copy(seat.user):
                _push(plan, seen, item)
        if load_org(db).owner_overdue_copy:
            owner = db.scalar(select(User).where(User.is_owner.is_(True)))
            if owner is not None:
                for item in _force_copy(owner):
                    _push(plan, seen, item)
    return plan


def _live(event: str) -> bool:
    return is_reminder(event) or is_overdue(event)


def _plan(db: Session, occurrence: PaymentOccurrence, event: str) -> list[tuple[str, str]]:
    plan: list[tuple[str, str]] = []
    if _live(event):
        plan.append(("email", ""))
    plan.append(("webhook", ""))
    if _team_webhook(db, occurrence.team_id):
        plan.append(("webhook", f"team:{occurrence.team_id}"))
    if not _live(event):
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
        if _webhook_paused(db, occurrence.team_id):
            # Адрес отдела недавно не ответил: не держим тик воркера, ждём конца паузы.
            return "deferred"
        result = send_team_webhook(_team_webhook(db, occurrence.team_id), payload)
        if result == "sent":
            _webhook_ok(db, occurrence.team_id)
        elif result == "failed":
            _webhook_failed(db, occurrence, event, recipient)
        return result
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


def digest_payload(items: list[tuple[PaymentOccurrence, str]]) -> dict:
    primary = min(items, key=lambda item: item[0].due_date)[0]
    payload = occurrence_payload(primary, DIGEST)
    lines = [
        f"{row.title}, {period_label(row.period_year, row.period_month)}: {row.amount:.2f} {row.currency}, до {row.due_date.strftime('%d.%m.%Y')}"
        for row, _event in sorted(items, key=lambda item: (item[0].due_date, item[0].title))
    ]
    payload["lines"] = lines
    payload["occurrence"]["title"] = f"Просрочено периодов: {len(items)}"
    return payload


def _channel_quiet(db: Session, items: list[tuple[PaymentOccurrence, str]], channel: str, recipient: str) -> bool:
    return all(_already(db, row.id, event, channel, recipient) for row, event in items)


def fanout_digest(db: Session, items: list[tuple[PaymentOccurrence, str]]) -> int:
    """Несколько просроченных периодов одного платежа — одно сообщение.

    Ключ доставки с датой: сводка повторяется вместе с повтором просрочки,
    а не уходит один раз навсегда. В payload событие остаётся DIGEST.
    """
    primary = min(items, key=lambda item: item[0].due_date)[0]
    payload = digest_payload(items)
    key = f"{DIGEST}.{clock.today():%Y%m%d}"
    sent = 0
    delivered: list[tuple[str, str]] = []
    for channel, recipient in _plan(db, primary, DIGEST):
        if _channel_quiet(db, items, channel, recipient) or _already(db, primary.id, key, channel, recipient):
            continue
        try:
            result = _send(db, channel, recipient, primary, key, payload)
        except Exception:
            log.exception("digest %s failed", channel)
            result = "failed"
        if result not in {"sent", "queued"}:
            continue
        if result == "sent":
            _mark(db, primary.id, key, channel, recipient)
        delivered.append((channel, recipient))
        sent += 1
    for row, event in items:
        for channel, recipient in delivered:
            if not _already(db, row.id, event, channel, recipient):
                _mark(db, row.id, event, channel, recipient)
    return sent


def dispatch_due_reminders(db: Session) -> int:
    """Напоминания по всем периодам, которым пора. Возвращает число новых отправок."""
    org = load_org(db)
    today = clock.today()
    rows = db.scalars(
        select(PaymentOccurrence).options(
            joinedload(PaymentOccurrence.template).joinedload(RecurringPayment.responsible)
        )
    ).unique().all()
    singles: list[tuple[PaymentOccurrence, str]] = []
    grouped: dict[uuid.UUID, list[tuple[PaymentOccurrence, str]]] = {}
    for row in rows:
        template = row.template
        archived = template is None or template.is_archived
        events = notification_events(
            due=row.due_date,
            paid_at=row.paid_at,
            archived=archived,
            today=today,
            offsets=org.reminder_days,
            overdue=org.overdue_reminders,
        )
        for event in events:
            if is_overdue(event):
                grouped.setdefault(row.recurring_payment_id, []).append((row, event))
            else:
                singles.append((row, event))
    sent = 0
    for items in grouped.values():
        if len(items) >= 2:
            sent += fanout_digest(db, items)
        else:
            singles.extend(items)
    for row, event in singles:
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


def connect_digest(rows: list[PaymentOccurrence], team_name: str | None = None) -> str:
    """Первое сообщение в чате отдела: что сюда будет приходить и что уже открыто."""
    from app.services import humanize
    from app.services import telegram_html as tg

    about = [tg.field("Отдел", team_name)] if team_name else []
    about.append(
        tg.esc(
            "Сюда будут приходить напоминания о сроках и просрочках. "
            "Кнопка «Оплачено» под карточкой отмечает оплату от вашего имени, если ваш Telegram привязан к rekeeper."
        )
    )
    if not rows:
        return tg.compose("✅", "Чат подключён к rekeeper", about, tg.esc("Открытых платежей сейчас нет."))
    today = clock.today()
    nearest = rows[:5]
    lines = [tg.esc(f"Сейчас открыто {payments_phrase(len(rows))}. Ближайшие:")]
    for row in nearest:
        lines.append(
            tg.bullet(
                f"{tg.bold(row.title)}: {tg.esc(humanize.money(row.amount, row.currency))}, "
                f"до {tg.esc(humanize.ru_date(row.due_date))} ({tg.esc(humanize.due_phrase(row.due_date, today))})"
            )
        )
    if len(rows) > len(nearest):
        lines.append(tg.esc(f"И ещё {len(rows) - len(nearest)} в rekeeper."))
    return tg.compose("✅", "Чат подключён к rekeeper", about, lines)


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
        org = load_org(db)
        for event in notification_events(
            due=row.due_date,
            paid_at=row.paid_at,
            archived=False,
            today=today,
            offsets=org.reminder_days,
            overdue=org.overdue_reminders,
        ):
            _mark(db, row.id, event, "telegram", TEAM_RECIPIENT)

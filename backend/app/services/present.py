from datetime import date

from app.core.config import get_settings
from app.models import PaymentOccurrence, RecurringPayment, User
from app.schemas.common import UserBrief
from app.schemas.occurrence import OccurrenceOut
from app.schemas.recurring import RecurringOut
from app.services.schedule import bucket_for, classify, paid_on_time, period_key, period_label
from app.services import time as clock


def user_brief(user: User) -> UserBrief:
    return UserBrief(id=user.id, full_name=user.full_name, email=user.email)


def occurrence_out(occurrence: PaymentOccurrence, template: RecurringPayment, today: date) -> OccurrenceOut:
    settings = get_settings()
    status = classify(occurrence.due_date, occurrence.paid_at, today, settings.soon_days)
    on_time = None
    lateness = None
    paid_on = None
    if occurrence.paid_at is not None:
        on_time = paid_on_time(occurrence.paid_at, occurrence.due_date, settings.zone)
        paid_on = occurrence.paid_at.astimezone(settings.zone).date()
        lateness = (paid_on - occurrence.due_date).days
    responsible = template.responsible
    return OccurrenceOut(
        id=occurrence.id,
        recurring_payment_id=occurrence.recurring_payment_id,
        title=occurrence.title,
        description=occurrence.description,
        period=period_key(occurrence.period_year, occurrence.period_month),
        period_label=period_label(occurrence.period_year, occurrence.period_month),
        due_date=occurrence.due_date,
        amount=occurrence.amount,
        paid_amount=occurrence.paid_amount,
        currency=occurrence.currency,
        status=status,
        bucket=bucket_for(status),
        paid_at=occurrence.paid_at,
        paid_on=paid_on,
        paid_on_time=on_time,
        days_delta=(occurrence.due_date - today).days,
        lateness_days=lateness,
        note=occurrence.note,
        receipt_url=occurrence.receipt_url,
        receipt_note=occurrence.receipt_note,
        template_archived=template.is_archived,
        responsible=user_brief(responsible) if responsible is not None else None,
        paid_by=user_brief(occurrence.payer) if occurrence.payer is not None else None,
        telegram_reminded_at=occurrence.telegram_reminded_at,
    )


def _next_due(template: RecurringPayment, occurrences: list[PaymentOccurrence], today: date) -> date:
    from app.services.occurrences import scheduled_periods

    open_dates = [row.due_date for row in occurrences if row.paid_at is None and row.due_date >= today]
    if open_dates:
        return min(open_dates)
    ahead = [due for _year, _month, due in scheduled_periods(template, today) if due >= today]
    if ahead:
        return min(ahead)
    if occurrences:
        return max(row.due_date for row in occurrences)
    return template.starts_on


def applies_from_date(template: RecurringPayment, occurrences: list[PaymentOccurrence], today: date) -> date | None:
    """Ближайший будущий неоплаченный период: с него правка шаблона меняет снимок."""
    future = [row.due_date for row in occurrences if row.paid_at is None and row.due_date >= today]
    if future:
        return min(future)
    ahead = []
    if not template.is_archived:
        from app.services.occurrences import scheduled_periods

        ahead = [due for _year, _month, due in scheduled_periods(template, today) if due >= today]
    return min(ahead) if ahead else None


def debt_count(occurrences: list[PaymentOccurrence], today: date) -> int:
    return sum(1 for row in occurrences if row.paid_at is None and row.due_date < today)


def recurring_out(template: RecurringPayment, occurrences: list[PaymentOccurrence]) -> RecurringOut:
    today = clock.today()
    settings = get_settings()
    open_count = 0
    paid_count = 0
    for row in occurrences:
        status = classify(row.due_date, row.paid_at, today, settings.soon_days)
        if status == "paid":
            paid_count += 1
        else:
            open_count += 1
    return RecurringOut(
        id=template.id,
        title=template.title,
        description=template.description,
        amount=template.amount,
        currency=template.currency,
        day_of_month=template.day_of_month,
        starts_on=template.starts_on,
        next_payment_date=_next_due(template, occurrences, today),
        periodicity=template.periodicity,
        interval_months=template.interval_months,
        remind_archived_overdue=template.remind_archived_overdue,
        applies_from=applies_from_date(template, occurrences, today),
        debt_count=debt_count(occurrences, today),
        is_archived=template.is_archived,
        responsible=user_brief(template.responsible) if template.responsible is not None else None,
        open_count=open_count,
        paid_count=paid_count,
        created_at=template.created_at,
    )

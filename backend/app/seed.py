"""Демо только если отделов ещё нет. Владелец уже создан ensure_owner.

Бухгалтерия: аренда и электричество в рублях, подписка в евро.
Инфраструктура: сервер в долларах, домен раз в год, сертификат раз в квартал.
Текущие точки каденции помечаются доставленными, пачки писем при старте нет.
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal
from app.models import PaymentOccurrence, RecurringPayment, Team, User
from app.services import time as clock
from app.services.accounts import create_verified_user
from app.services.budgets import add_budget
from app.services.occurrences import ensure_template
from app.services.org_settings import load_org
from app.services.owner import ensure_owner
from app.services.reminders import notification_events
from app.services.teams import add_member, create_team

log = logging.getLogger("invoice_keeper.seed")

RENT_TITLE = "Аренда офиса"
POWER_TITLE = "Электричество"
SERVER_TITLE = "Сервер"
SUB_TITLE = "Подписка"
DOMAIN_TITLE = "Домен"
SSL_TITLE = "Сертификат SSL"
ACCOUNTING = "Бухгалтерия"
INFRA = "Инфраструктура"


def seed(demo: bool | None = None) -> None:
    settings = get_settings()
    ensure_owner(settings)
    if demo is None:
        demo = settings.seed_demo
    if not demo:
        return
    db = SessionLocal()
    try:
        if db.scalar(select(Team.id).limit(1)) is not None:
            return
        _demo(db, settings)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _demo(db: Session, settings: Settings) -> None:
    if len(settings.demo_user_password) < 8:
        raise RuntimeError("Пароль демо короче 8 символов")
    owner = db.scalar(select(User).where(User.is_owner.is_(True)))
    if owner is None:
        raise RuntimeError("Владелец не создан")
    ivan = create_verified_user(
        db, email=settings.demo_user_email, full_name=settings.demo_user_name, password=settings.demo_user_password
    )
    maria = create_verified_user(
        db,
        email=settings.demo_user_two_email,
        full_name=settings.demo_user_two_name,
        password=settings.demo_user_password,
    )
    studio = create_team(db, owner, ACCOUNTING)
    infra = create_team(db, owner, INFRA)
    add_member(db, studio, maria, "admin", actor=owner)
    add_member(db, studio, ivan, "member", actor=owner)
    add_member(db, infra, maria, "admin", actor=owner)
    add_member(db, infra, ivan, "member", actor=owner)
    owner.active_team_id = studio.id

    today = clock.today()
    july = date(2026, 7, 1)
    _story(
        db,
        team=studio,
        actor=owner,
        title=RENT_TITLE,
        description="Офис. Срок — 5-е число, валюта договора рубли.",
        amount=Decimal("85000.00"),
        currency="RUB",
        day=5,
        starts_on=july,
        periodicity="monthly",
        responsible=ivan,
        today=today,
        paid={(2026, 7): (None, None), (2026, 8): (None, None)},
    )
    _story(
        db,
        team=studio,
        actor=owner,
        title=POWER_TITLE,
        description="Электричество. Сумма счёта плавает, в карточке — факт.",
        amount=Decimal("12000.00"),
        currency="RUB",
        day=20,
        starts_on=july,
        periodicity="monthly",
        responsible=ivan,
        today=today,
        paid={
            (2026, 7): (None, Decimal("14150.00")),
            (2026, 8): (None, Decimal("9800.00")),
        },
    )
    _story(
        db,
        team=studio,
        actor=owner,
        title=SUB_TITLE,
        description="Подписка на дизайн. Списание в евро.",
        amount=Decimal("15.00"),
        currency="EUR",
        day=26,
        starts_on=july,
        periodicity="monthly",
        responsible=ivan,
        today=today,
        paid={(2026, 7): (None, None), (2026, 8): (None, None), (2026, 9): (None, None)},
    )
    _story(
        db,
        team=infra,
        actor=owner,
        title=SERVER_TITLE,
        description="VPS. Счёт в долларах, срок — 12-е.",
        amount=Decimal("40.00"),
        currency="USD",
        day=12,
        starts_on=july,
        periodicity="monthly",
        responsible=maria,
        today=today,
        paid={(2026, 7): (None, None), (2026, 8): (timedelta(days=3), None)},
    )
    _story(
        db,
        team=infra,
        actor=owner,
        title=DOMAIN_TITLE,
        description="Домен отдела. Оплата раз в год.",
        amount=Decimal("990.00"),
        currency="RUB",
        day=20,
        starts_on=date(2025, 11, 20),
        periodicity="yearly",
        responsible=maria,
        today=today,
        paid={(2025, 11): (None, None)},
    )
    _story(
        db,
        team=infra,
        actor=owner,
        title=SSL_TITLE,
        description="Сертификат. Раз в квартал.",
        amount=Decimal("4500.00"),
        currency="RUB",
        day=15,
        starts_on=date(2026, 4, 15),
        periodicity="quarterly",
        responsible=maria,
        today=today,
        paid={(2026, 4): (None, None), (2026, 7): (None, None)},
    )
    month_key = f"{today.year:04d}-{today.month:02d}"
    add_budget(db, studio.id, "month", month_key, "RUB", Decimal("200000.00"))
    _silence(db, today)
    log.info("демо: %s, %s", ACCOUNTING, INFRA)


def _story(
    db: Session,
    *,
    team: Team,
    actor: User,
    title: str,
    description: str,
    amount: Decimal,
    currency: str,
    day: int,
    starts_on: date,
    periodicity: str,
    responsible: User,
    today: date,
    paid: dict[tuple[int, int], tuple[timedelta | None, Decimal | None]],
) -> None:
    from app.schemas.recurring import normalize_periodicity

    kind, interval = normalize_periodicity(periodicity, None)
    template = RecurringPayment(
        team_id=team.id,
        title=title,
        description=description,
        amount=amount,
        currency=currency,
        day_of_month=day,
        starts_on=starts_on,
        periodicity=kind,
        interval_months=interval,
        responsible_user_id=responsible.id,
        created_by_id=actor.id,
        is_archived=False,
    )
    db.add(template)
    db.flush()
    ensure_template(db, template, today)
    from app.services.audit import record

    record(
        db,
        action="template.create",
        actor=actor,
        entity_type="recurring_payment",
        entity_id=template.id,
        team_id=team.id,
        meta={"title": title, "currency": currency, "amount": f"{amount:.2f}"},
    )
    rows = db.scalars(select(PaymentOccurrence).where(PaymentOccurrence.recurring_payment_id == template.id)).all()
    for occurrence in rows:
        plan = paid.get((occurrence.period_year, occurrence.period_month))
        if plan is None:
            continue
        shift, actual = plan
        when = occurrence.due_date + (shift or timedelta())
        occurrence.paid_at = datetime(when.year, when.month, when.day, 12, 0, tzinfo=clock.zone())
        occurrence.paid_by_id = responsible.id
        occurrence.paid_amount = actual if actual is not None else occurrence.amount
        occurrence.updated_at = clock.now()


def _silence(db: Session, today: date) -> None:
    """Текущая точка каденции уже «доставлена»: первый тик воркера молчит."""
    from app.services.notify import _mark, _plan

    org = load_org(db)
    rows = db.scalars(select(PaymentOccurrence)).all()
    for row in rows:
        if row.paid_at is not None:
            continue
        template = db.get(RecurringPayment, row.recurring_payment_id)
        if template is None:
            continue
        events = notification_events(
            due=row.due_date,
            paid_at=row.paid_at,
            archived=template.is_archived,
            today=today,
            offsets=org.reminder_days,
            overdue_repeat_days=org.overdue_repeat_days,
            remind_archived_overdue=template.remind_archived_overdue,
        )
        for event in events:
            for channel, recipient in _plan(db, row, event):
                _mark(db, row.id, event, channel, recipient)

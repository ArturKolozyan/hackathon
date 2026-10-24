"""Демо только на пустой базе. Пароль админа при рестарте больше не переписывается.

ADMIN_* — владелец «Студия Север», если SEED_DEMO и пользователей ещё нет.
"""

import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal
from app.models import PaymentOccurrence, RecurringPayment, User
from app.services import time as clock
from app.services.accounts import create_verified_user
from app.services.budgets import add_budget
from app.services.occurrences import ensure_template
from app.services.schedule import add_months
from app.services.teams import add_member, create_team

log = logging.getLogger("invoice_keeper.seed")

RENT_TITLE = "Аренда офиса"
SERVER_TITLE = "Сервер"
SUB_TITLE = "Подписка"
STUDIO = "Студия Север"
AEZA = "AEZA Ops"
MARKETING = "Маркетинг"


def seed(demo: bool | None = None) -> None:
    settings = get_settings()
    if demo is None:
        demo = settings.seed_demo
    db = SessionLocal()
    try:
        if db.scalar(select(User.id).limit(1)) is not None:
            return
        if not demo:
            return
        _demo(db, settings)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _demo(db: Session, settings: Settings) -> None:
    if len(settings.admin_password) < 8 or len(settings.demo_user_password) < 8:
        raise RuntimeError("Пароли демо короче 8 символов")
    emails = {
        settings.admin_email.lower(),
        settings.demo_user_email.lower(),
        settings.demo_user_two_email.lower(),
        settings.demo_user_three_email.lower(),
    }
    if len(emails) < 4:
        raise RuntimeError("Почты демо-людей должны различаться")
    admin = create_verified_user(
        db,
        email=settings.admin_email,
        full_name=settings.admin_name.strip() or "Админ",
        password=settings.admin_password,
    )
    ivan = create_verified_user(
        db, email=settings.demo_user_email, full_name=settings.demo_user_name, password=settings.demo_user_password
    )
    maria = create_verified_user(
        db,
        email=settings.demo_user_two_email,
        full_name=settings.demo_user_two_name,
        password=settings.demo_user_password,
    )
    oleg = create_verified_user(
        db,
        email=settings.demo_user_three_email,
        full_name=settings.demo_user_three_name,
        password=settings.demo_user_password,
    )
    studio = create_team(db, admin, STUDIO)
    add_member(db, studio, ivan, "member", actor=admin)
    add_member(db, studio, maria, "member", actor=admin)
    add_member(db, studio, oleg, "admin", actor=admin)
    aeza = create_team(db, ivan, AEZA)
    add_member(db, aeza, admin, "member", actor=ivan)
    add_member(db, aeza, maria, "admin", actor=ivan)
    add_member(db, aeza, oleg, "member", actor=ivan)
    marketing = create_team(db, maria, MARKETING)
    add_member(db, marketing, ivan, "member", actor=maria)
    add_member(db, marketing, oleg, "admin", actor=maria)

    today = clock.today()
    starts_on = add_months(date(today.year, today.month, 1), -3)
    soon_day = (today + timedelta(days=settings.soon_days)).day
    _story_template(
        db,
        team=studio,
        actor=admin,
        key="rent",
        title=RENT_TITLE,
        description="Офис. Срок — 5-е число, валюта договора рубли.",
        amount=Decimal("85000.00"),
        currency="RUB",
        day_of_month=5,
        starts_on=starts_on,
        responsible=ivan,
        today=today,
    )
    _story_template(
        db,
        team=studio,
        actor=admin,
        key="server",
        title=SERVER_TITLE,
        description="VPS команды. Счёт в долларах, срок — 12-е.",
        amount=Decimal("40.00"),
        currency="USD",
        day_of_month=12,
        starts_on=starts_on,
        responsible=maria,
        today=today,
    )
    _story_template(
        db,
        team=studio,
        actor=admin,
        key="sub",
        title=SUB_TITLE,
        description="Подписка на дизайн. Списание в евро, в ближайшие дни.",
        amount=Decimal("15.00"),
        currency="EUR",
        day_of_month=soon_day,
        starts_on=starts_on,
        responsible=ivan,
        today=today,
    )
    _plain(
        db,
        team=aeza,
        actor=ivan,
        title="Домен",
        description="Домен команды.",
        amount=Decimal("990.00"),
        currency="RUB",
        day=1,
        starts_on=starts_on,
        responsible=admin,
        today=today,
    )
    _plain(
        db,
        team=aeza,
        actor=ivan,
        title="VPS",
        description="Виртуальный сервер.",
        amount=Decimal("25.00"),
        currency="USD",
        day=15,
        starts_on=starts_on,
        responsible=maria,
        today=today,
    )
    _plain(
        db,
        team=aeza,
        actor=ivan,
        title="Лицензия",
        description="Лицензия на софт.",
        amount=Decimal("49.00"),
        currency="EUR",
        day=soon_day,
        starts_on=starts_on,
        responsible=oleg,
        today=today,
    )
    _plain(
        db,
        team=marketing,
        actor=maria,
        title="Реклама",
        description="Кабинет рекламы.",
        amount=Decimal("200.00"),
        currency="EUR",
        day=8,
        starts_on=starts_on,
        responsible=oleg,
        today=today,
    )
    _plain(
        db,
        team=marketing,
        actor=maria,
        title="Подрядчик",
        description="Внешний подряд.",
        amount=Decimal("60000.00"),
        currency="RUB",
        day=18,
        starts_on=starts_on,
        responsible=ivan,
        today=today,
    )
    month_key = f"{today.year:04d}-{today.month:02d}"
    add_budget(db, studio.id, "month", month_key, "RUB", Decimal("200000.00"))
    add_budget(db, aeza.id, "month", month_key, "USD", Decimal("80.00"))
    add_budget(db, marketing.id, "month", month_key, "EUR", Decimal("500.00"))
    log.info("демо: %s, %s, %s", STUDIO, AEZA, MARKETING)


def _open_template(db: Session, *, team, actor: User, title, description, amount, currency, day, starts_on, responsible, today):
    template = RecurringPayment(
        team_id=team.id,
        title=title,
        description=description,
        amount=amount,
        currency=currency,
        day_of_month=day,
        starts_on=starts_on,
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
    return template


def _story_template(db, *, team, actor, key, title, description, amount, currency, day_of_month, starts_on, responsible, today):
    template = _open_template(
        db,
        team=team,
        actor=actor,
        title=title,
        description=description,
        amount=amount,
        currency=currency,
        day=day_of_month,
        starts_on=starts_on,
        responsible=responsible,
        today=today,
    )
    _apply_story(db, template, key, responsible.id, today)


def _plain(db, *, team, actor, title, description, amount, currency, day, starts_on, responsible, today):
    _open_template(
        db,
        team=team,
        actor=actor,
        title=title,
        description=description,
        amount=amount,
        currency=currency,
        day=day,
        starts_on=starts_on,
        responsible=responsible,
        today=today,
    )


def _mark(occurrence: PaymentOccurrence, when: date, actor_id, note: str | None = None) -> None:
    occurrence.paid_at = datetime(when.year, when.month, when.day, 12, 0, tzinfo=clock.zone())
    occurrence.paid_by_id = actor_id
    occurrence.note = note
    occurrence.updated_at = clock.now()


def _apply_story(db: Session, template: RecurringPayment, key: str, actor_id, today: date) -> None:
    rows = db.scalars(select(PaymentOccurrence).where(PaymentOccurrence.recurring_payment_id == template.id)).all()
    current = today.year * 12 + today.month
    for occurrence in rows:
        delta = occurrence.period_year * 12 + occurrence.period_month - current
        if key == "sub":
            if occurrence.due_date < today:
                _mark(occurrence, occurrence.due_date, actor_id)
            continue
        if key == "server" and delta == -2:
            _mark(occurrence, occurrence.due_date + timedelta(days=3), actor_id, "Закрыли после напоминания")
            continue
        if key == "server" and delta <= -3:
            _mark(occurrence, occurrence.due_date, actor_id)
            continue
        if key == "rent" and delta <= -2:
            _mark(occurrence, occurrence.due_date, actor_id)

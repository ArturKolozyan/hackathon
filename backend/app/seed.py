"""Демо только если отделов ещё нет. Владелец уже создан ensure_owner.

Три платежа кейса лежат в отделе «Бухгалтерия». Второй отдел пустой.
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
from app.models import Team
from app.services.accounts import create_verified_user
from app.services.budgets import add_budget
from app.services.occurrences import ensure_template
from app.services.owner import ensure_owner
from app.services.schedule import add_months
from app.services.teams import add_member, create_team

log = logging.getLogger("invoice_keeper.seed")

RENT_TITLE = "Аренда офиса"
SERVER_TITLE = "Сервер"
SUB_TITLE = "Подписка"
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
    starts_on = add_months(date(today.year, today.month, 1), -3)
    soon_day = (today + timedelta(days=settings.soon_days)).day
    _story_template(
        db,
        team=studio,
        actor=owner,
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
        actor=owner,
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
        actor=owner,
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
        team=infra,
        actor=owner,
        title="Домен",
        description="Домен второго отдела.",
        amount=Decimal("990.00"),
        currency="RUB",
        day=1,
        starts_on=starts_on,
        responsible=maria,
        today=today,
    )
    month_key = f"{today.year:04d}-{today.month:02d}"
    add_budget(db, studio.id, "month", month_key, "RUB", Decimal("200000.00"))
    log.info("демо: %s, %s", ACCOUNTING, INFRA)


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

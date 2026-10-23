import logging
from datetime import date, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import PaymentOccurrence, RecurringPayment, User
from app.services import time as clock
from app.services.occurrences import ensure_template
from app.services.schedule import add_months

log = logging.getLogger("invoice_keeper.seed")

RENT_TITLE = "Аренда офиса"
SERVER_TITLE = "Сервер"
SUB_TITLE = "Подписка"


def seed(demo: bool | None = None) -> None:
    settings = get_settings()
    if demo is None:
        demo = settings.seed_demo
    if len(settings.admin_password) < 8:
        raise RuntimeError("ADMIN_PASSWORD должен быть не короче 8 символов")
    db = SessionLocal()
    try:
        admin = _upsert_admin(db, settings)
        if demo:
            _ensure_demo(db, settings, admin)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _upsert_admin(db: Session, settings: Settings) -> User:
    email = settings.admin_email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(
            email=email,
            full_name=settings.admin_name.strip() or "Админ",
            password_hash=hash_password(settings.admin_password),
            role="admin",
            is_active=True,
        )
        db.add(user)
        db.flush()
        log.info("создан админ %s", email)
        return user
    user.full_name = settings.admin_name.strip() or user.full_name
    user.password_hash = hash_password(settings.admin_password)
    user.role = "admin"
    user.is_active = True
    user.updated_at = clock.now()
    db.flush()
    return user


def _ensure_user(db: Session, email: str, full_name: str, password: str) -> User:
    normalized = email.strip().lower()
    found = db.scalar(select(User).where(User.email == normalized))
    if found is not None:
        return found
    user = User(
        email=normalized,
        full_name=full_name.strip(),
        password_hash=hash_password(password),
        role="user",
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _ensure_demo(db: Session, settings: Settings, admin: User) -> None:
    if len(settings.demo_user_password) < 8:
        raise RuntimeError("DEMO_USER_PASSWORD должен быть не короче 8 символов")
    emails = {settings.admin_email.lower(), settings.demo_user_email.lower(), settings.demo_user_two_email.lower()}
    if len(emails) < 3:
        raise RuntimeError("Почты админа и демо-пользователей должны различаться")
    if db.scalar(select(RecurringPayment.id).where(RecurringPayment.title == RENT_TITLE)) is not None:
        log.info("демо-шаблоны уже есть, повторно не создаю")
        return
    ivan = _ensure_user(db, settings.demo_user_email, settings.demo_user_name, settings.demo_user_password)
    maria = _ensure_user(db, settings.demo_user_two_email, settings.demo_user_two_name, settings.demo_user_password)
    today = clock.today()
    starts_on = add_months(date(today.year, today.month, 1), -3)
    soon_day = (today + timedelta(days=settings.soon_days)).day
    specs = [
        {
            "key": "rent",
            "title": RENT_TITLE,
            "description": "Офис. Срок — 5-е число, валюта договора рубли.",
            "amount": Decimal("85000.00"),
            "currency": "RUB",
            "day_of_month": 5,
            "responsible": ivan,
        },
        {
            "key": "server",
            "title": SERVER_TITLE,
            "description": "VPS команды. Счёт в долларах, срок — 12-е.",
            "amount": Decimal("40.00"),
            "currency": "USD",
            "day_of_month": 12,
            "responsible": maria,
        },
        {
            "key": "sub",
            "title": SUB_TITLE,
            "description": "Подписка на дизайн. Списание в евро, в ближайшие дни.",
            "amount": Decimal("15.00"),
            "currency": "EUR",
            "day_of_month": soon_day,
            "responsible": ivan,
        },
    ]
    for spec in specs:
        template = RecurringPayment(
            title=spec["title"],
            description=spec["description"],
            amount=spec["amount"],
            currency=spec["currency"],
            day_of_month=spec["day_of_month"],
            starts_on=starts_on,
            responsible_user_id=spec["responsible"].id,
            created_by_id=admin.id,
            is_archived=False,
        )
        db.add(template)
        db.flush()
        ensure_template(db, template, today)
        _apply_story(db, template, spec["key"], spec["responsible"].id, today)
    log.info("демо-инбокс: аренда RUB, сервер USD, подписка EUR")


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

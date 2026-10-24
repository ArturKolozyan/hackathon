"""Демо-кабинет хостинг-провайдера для показа. Запуск вручную:

    docker compose exec api python -m app.demo_data [--force] [--quiet]

Без --force ничего не трогает, если отделы, платежи или демо-люди уже есть.
--force стирает отделы, платежи, бюджеты, журнал и всех людей, кроме владельца, и сеет заново.
Даты считаются от сегодня: история за 8 месяцев, просрочки, сроки сегодня, через 3 и 7 дней.
Пароль у всех демо-людей один, печатается один раз и нигде не хранится.
Почта демо-людей — зарезервированный домен .example, личные письма выключены.
Уже прошедшие точки каденции помечаются доставленными: воркер шлёт только сегодняшние
напоминания. --quiet глушит и их.
"""

import argparse
import random
import secrets
import sys
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from app.core.database import SessionLocal
from app.models import (
    AuditLog,
    PaymentOccurrence,
    RecurringPayment,
    Team,
    User,
)
from app.services import receipts
from app.services import time as clock
from app.services.accounts import create_verified_user
from app.services.audit import record
from app.services.budgets import add_budget
from app.services.notify import _mark, _plan
from app.services.occurrences import ensure_template, step_months
from app.services.org_settings import load_org
from app.services.reminders import notification_events
from app.services.schedule import due_date, shift_month
from app.services.teams import add_member, create_team

DOMAIN = "hosting.example"
HISTORY_MONTHS = 8

PEOPLE = {
    "vorontsov": ("Алексей Воронцов", "a.vorontsov", "department", True),
    "kovalev": ("Дмитрий Ковалёв", "d.kovalev", "mine", True),
    "belov": ("Сергей Белов", "s.belov", "mine", False),
    "kuznetsova": ("Анна Кузнецова", "a.kuznetsova", "department", True),
    "sokolova": ("Мария Соколова", "m.sokolova", "department", True),
    "petrov": ("Иван Петров", "i.petrov", "mine", True),
    "orlov": ("Кирилл Орлов", "k.orlov", "mine", False),
    "morozova": ("Елена Морозова", "e.morozova", "department", True),
    "lebedeva": ("Наталья Лебедева", "n.lebedeva", "department", True),
    "egorov": ("Павел Егоров", "p.egorov", "mine", True),
    "fedorov": ("Игорь Фёдоров", "i.fedorov", "department", True),
    "volkova": ("Татьяна Волкова", "t.volkova", "mine", True),
    "zaitsev": ("Максим Зайцев", "m.zaitsev", "mine", False),
}


@dataclass(frozen=True)
class Item:
    title: str
    amount: str
    currency: str
    every: str
    due: int  # один из сроков: сегодня + due дней
    who: str
    payers: tuple[str, ...]
    description: str = ""
    months: int | None = None  # для every_n
    vary: float = 0.0  # разброс фактической суммы
    unpaid: int = 0  # последних прошедших сроков без оплаты
    prepaid: int = 0  # будущих сроков, оплаченных заранее
    archived: int | None = None  # дней назад ушёл в архив


TEAMS: list[tuple[str, tuple[str, ...], tuple[str, ...], list[Item]]] = [
    (
        "Инфраструктура",
        ("vorontsov",),
        ("kovalev", "belov", "kuznetsova"),
        [
            Item("Аренда стоек в ЦОД (Москва), 6 стоек", "540000", "RUB", "monthly", -19, "vorontsov",
                 ("kuznetsova", "vorontsov"), "Стойки 42U, до 5 кВт на стойку. Электричество — отдельным счётом по счётчику."),
            Item("Электроэнергия стоек, ЦОД Москва", "186000", "RUB", "monthly", 3, "kovalev",
                 ("kuznetsova", "kovalev"), "Оплата по факту потребления, сумма меняется каждый месяц.", vary=0.12),
            Item("Аренда стоек в ЦОД (Санкт-Петербург), 2 стойки", "210000", "RUB", "monthly", -2, "belov",
                 ("kuznetsova", "belov"), unpaid=1),
            Item("IP-транзит 10 Гбит/с, апстрим", "145000", "RUB", "monthly", -9, "vorontsov",
                 ("kuznetsova", "vorontsov"), "Коммит 10 Гбит/с, сверх коммита — по 95-му перцентилю.", vary=0.08),
            Item("Защита от DDoS на апстриме, 40 Гбит/с очистки", "160000", "RUB", "monthly", -5, "vorontsov",
                 ("kuznetsova", "vorontsov"), "Фильтрация трафика клиентов у внешнего провайдера."),
            Item("Резервные копии в S3 за пределами ЦОД", "52000", "RUB", "monthly", 1, "belov",
                 ("belov", "kuznetsova"), "Холодное хранилище, оплата за объём — сумма растёт вместе с клиентами.", vary=0.1),
            Item("Выделенный сервер во Франкфурте (резервный биллинг)", "189", "USD", "monthly", 7, "kovalev",
                 ("kovalev", "vorontsov"), "Счёт в долларах, оплата картой."),
            Item("Аренда IPv4 /22 (1024 адреса)", "1536", "USD", "quarterly", -31, "vorontsov",
                 ("vorontsov",), "Лизинг адресов, счёт поквартально.", unpaid=1),
            Item("Членство RIPE NCC (LIR)", "1550", "EUR", "yearly", 70, "vorontsov",
                 ("vorontsov",), "Ежегодный взнос LIR."),
            Item("SSL-сертификаты wildcard (3 шт.)", "74000", "RUB", "yearly", 0, "belov",
                 ("belov",), "Панель, биллинг, API."),
            Item("Продление доменов (12 зон)", "18400", "RUB", "yearly", 41, "belov", ("belov",)),
            Item("Сервисный контракт на СХД", "420000", "RUB", "semiannual", 18, "vorontsov",
                 ("kuznetsova",), "Поддержка 24/7, замена дисков в течение 4 часов."),
            Item("Обслуживание ИБП и замена батарей", "38000", "RUB", "every_n", -1, "kovalev",
                 ("kovalev",), "Подрядчик выезжает раз в 2 месяца.", months=2, unpaid=1),
            Item("Монтаж оптики между залами (разово)", "96000", "RUB", "once", -64, "kovalev", ("kuznetsova",)),
            Item("Закупка NVMe 7,68 ТБ × 12", "1290000", "RUB", "once", 12, "vorontsov", ("kuznetsova",),
                 "Расширение облачного кластера."),
            Item("Аренда стоек в ЦОД (Екатеринбург)", "95000", "RUB", "monthly", -14, "belov",
                 ("kuznetsova",), "Площадку закрыли, оборудование перевезли в Москву.", archived=50),
        ],
    ),
    (
        "Разработка",
        ("sokolova",),
        ("petrov", "orlov"),
        [
            Item("GitHub Team, 25 мест", "100", "USD", "monthly", -21, "sokolova", ("sokolova", "petrov")),
            Item("JetBrains All Products Pack, 8 лицензий", "6232", "USD", "yearly", 95, "sokolova", ("sokolova",)),
            Item("Sentry Business", "80", "USD", "monthly", 3, "petrov", ("petrov", "sokolova")),
            Item("Figma Professional, 4 редактора", "60", "USD", "monthly", -6, "orlov", ("orlov", "sokolova")),
            Item("Стенды разработки в облаке (staging)", "64000", "RUB", "monthly", -12, "petrov",
                 ("petrov", "sokolova"), "Почасовая тарификация, сумма плавает.", vary=0.15),
            Item("Apple Developer Program", "99", "USD", "yearly", 133, "orlov", ("orlov",)),
            Item("Пентест панели управления (разово)", "450000", "RUB", "once", -97, "sokolova", ("sokolova",)),
        ],
    ),
    (
        "Офис",
        ("morozova",),
        ("kuznetsova",),
        [
            Item("Аренда офиса, Москва", "385000", "RUB", "monthly", -19, "morozova",
                 ("kuznetsova", "morozova"), "Договор аренды на 3 года, 420 м², оплата помесячно вперёд.", prepaid=1),
            Item("Электроэнергия офиса", "18000", "RUB", "monthly", -4, "kuznetsova",
                 ("kuznetsova",), "Счёт от арендодателя по счётчику.", vary=0.2),
            Item("Интернет в офис, 1 Гбит/с", "9500", "RUB", "monthly", 0, "morozova", ("kuznetsova", "morozova")),
            Item("Клининг офиса", "42000", "RUB", "monthly", -7, "morozova", ("kuznetsova",), unpaid=1),
            Item("Microsoft 365 Business, 30 мест", "330", "EUR", "monthly", -15, "morozova",
                 ("morozova",), "Подписка, списание в евро."),
            Item("Яндекс 360 для бизнеса", "9600", "RUB", "monthly", -11, "morozova", ("morozova", "kuznetsova")),
            Item("Вода и кофе в офис", "27000", "RUB", "quarterly", 25, "kuznetsova", ("kuznetsova",), vary=0.1),
        ],
    ),
    (
        "Маркетинг",
        ("lebedeva",),
        ("egorov", "kuznetsova"),
        [
            Item("Яндекс Директ, пополнение", "250000", "RUB", "monthly", 7, "lebedeva",
                 ("kuznetsova", "lebedeva"), "Бюджет на месяц, фактический расход по кабинету.", vary=0.25),
            Item("CRM, 15 мест", "67500", "RUB", "quarterly", -40, "egorov", ("egorov", "lebedeva")),
            Item("Сервис email-рассылок", "5800", "RUB", "monthly", -3, "egorov", ("egorov",), unpaid=2),
            Item("SEO-подрядчик", "90000", "RUB", "monthly", -8, "lebedeva", ("kuznetsova",)),
            Item("Стенд на конференции (разово)", "380000", "RUB", "once", 26, "lebedeva", ("kuznetsova",)),
            Item("Таргетированная реклама ВКонтакте", "60000", "RUB", "monthly", -10, "egorov", ("egorov",),
                 "Канал отключили, остался неоплаченный счёт.", archived=25, unpaid=1),
        ],
    ),
    (
        "Финансы",
        ("kuznetsova",),
        ("morozova",),
        [
            Item("Обслуживание расчётного счёта", "4900", "RUB", "monthly", -13, "kuznetsova", ("kuznetsova",)),
            Item("1С:Бухгалтерия в облаке, 5 пользователей", "8900", "RUB", "monthly", -20, "kuznetsova", ("kuznetsova",)),
            Item("ЭДО с контрагентами (Диадок)", "21600", "RUB", "yearly", 58, "kuznetsova", ("kuznetsova",),
                 "Счета и акты от ЦОД и провайдеров приходят через ЭДО."),
            Item("Юридическое сопровождение (абонентское)", "70000", "RUB", "monthly", -6, "morozova",
                 ("kuznetsova",), "Договоры с клиентами, претензии, ответы на запросы."),
            Item("Страхование оборудования в ЦОД", "310000", "RUB", "yearly", -45, "kuznetsova", ("kuznetsova",),
                 "Полис на серверы и СХД в Москве и Санкт-Петербурге."),
        ],
    ),
    (
        "Поддержка",
        ("fedorov",),
        ("volkova", "zaitsev", "petrov"),
        [
            Item("Хелпдеск-система, 12 операторов", "30000", "RUB", "monthly", -16, "fedorov", ("fedorov", "volkova")),
            Item("Виртуальная АТС и номер 8-800", "14500", "RUB", "monthly", 3, "volkova",
                 ("volkova", "fedorov"), "Минуты 8-800 оплачиваются по факту.", vary=0.3),
            Item("Онлайн-чат на сайте", "36000", "RUB", "every_n", 34, "zaitsev", ("fedorov",),
                 "Оплата раз в 4 месяца.", months=4),
        ],
    ),
]

TEAMS_ADMIN = {name: admins[0] for name, admins, _members, _items in TEAMS}

BUDGETS = {
    "Инфраструктура": [("RUB", "1750000"), ("USD", "2500")],
    "Разработка": [("RUB", "120000"), ("USD", "400")],
    "Офис": [("RUB", "520000"), ("EUR", "400")],
    "Маркетинг": [("RUB", "420000")],
    "Финансы": [("RUB", "100000")],
    "Поддержка": [("RUB", "60000")],
}


def _back(day: date, months: int) -> date:
    year, month = shift_month(day.year, day.month, -months)
    return due_date(year, month, day.day)


def _starts_on(anchor: date, step: int | None, origin: date, today: date) -> date:
    """Самый ранний срок от начала истории; хотя бы один срок уже прошёл."""
    if step is None:
        return anchor
    back = 0
    while _back(anchor, back + step) >= origin:
        back += step
    if _back(anchor, back) >= today:
        back += step
    return _back(anchor, back)


def _at(day: date, rng: random.Random) -> datetime:
    return datetime.combine(day, time(rng.randint(9, 18), rng.randint(0, 59)), tzinfo=clock.zone())


def _paid_amount(item: Item, rng: random.Random) -> Decimal:
    base = Decimal(item.amount)
    if not item.vary:
        return base
    value = base * Decimal(str(1 + rng.uniform(-item.vary, item.vary)))
    step = Decimal("10") if item.currency == "RUB" else Decimal("0.01")
    return value.quantize(step)


def _pay(db: Session, row: PaymentOccurrence, payer: User, when: datetime, amount: Decimal, rng: random.Random) -> None:
    row.paid_at = when
    row.paid_by_id = payer.id
    row.paid_amount = amount
    if row.currency == "RUB" and rng.random() < 0.35:
        row.note = f"Счёт № {rng.randint(120, 9800)} от {(row.due_date - timedelta(days=rng.randint(5, 12))):%d.%m.%Y}"
    row.updated_at = when
    paid_on = when.date().isoformat()
    record(
        db,
        action="occurrence.paid",
        actor=payer,
        entity_type="payment_occurrence",
        entity_id=row.id,
        meta={"paid_on": paid_on, "title": row.title, "changes": {"paid_at": {"was": "—", "became": paid_on}}},
        team_id=row.team_id,
        at=when,
    )


def _payment(db: Session, team: Team, item: Item, people: dict[str, User], origin: date, today: date, rng: random.Random) -> None:
    from app.schemas.recurring import normalize_periodicity

    kind, interval = normalize_periodicity(item.every, item.months)
    anchor = today + timedelta(days=item.due)
    creator = people[TEAMS_ADMIN[team.name]]
    template = RecurringPayment(
        team_id=team.id,
        title=item.title,
        description=item.description or None,
        amount=Decimal(item.amount),
        currency=item.currency,
        day_of_month=anchor.day,
        periodicity=kind,
        interval_months=interval,
        starts_on=anchor,
        responsible_user_id=people[item.who].id,
        created_by_id=creator.id,
        is_archived=False,
    )
    template.starts_on = _starts_on(anchor, step_months(template), origin, today)
    created = _at(max(min(template.starts_on, today) - timedelta(days=rng.randint(3, 12)), origin - timedelta(days=19)), rng)
    template.created_at = created
    template.updated_at = created
    db.add(template)
    db.flush()
    record(
        db,
        action="template.create",
        actor=creator,
        entity_type="recurring_payment",
        entity_id=template.id,
        team_id=team.id,
        meta={"title": item.title, "currency": item.currency, "amount": f"{Decimal(item.amount):.2f}"},
        at=created,
    )
    cutoff = today - timedelta(days=item.archived) if item.archived is not None else today
    ensure_template(db, template, cutoff)
    rows = sorted(
        db.scalars(select(PaymentOccurrence).where(PaymentOccurrence.recurring_payment_id == template.id)).all(),
        key=lambda row: row.due_date,
    )
    past = [row for row in rows if row.due_date < cutoff]
    ahead = [row for row in rows if row.due_date >= cutoff]
    settled = past[: len(past) - item.unpaid] if item.unpaid else past
    for row in settled:
        shift = rng.randint(1, 8) if rng.random() < 0.18 else -rng.randint(0, 4)
        day = min(row.due_date + timedelta(days=shift), today - timedelta(days=1))
        _pay(db, row, people[rng.choice(item.payers)], _at(day, rng), _paid_amount(item, rng), rng)
    for row in ahead[: item.prepaid]:
        _pay(db, row, people[item.payers[0]], _at(today - timedelta(days=rng.randint(1, 3)), rng), Decimal(item.amount), rng)
    if item.archived is None:
        return
    for row in ahead:
        db.delete(row)
    template.is_archived = True
    archived_at = _at(cutoff, rng)
    template.updated_at = archived_at
    record(
        db,
        action="template.delete",
        actor=creator,
        entity_type="recurring_payment",
        entity_id=template.id,
        team_id=team.id,
        meta={"title": item.title},
        at=archived_at,
    )


def has_data(db: Session) -> bool:
    emails = [f"{login}@{DOMAIN}" for _name, login, _scope, _overdue in PEOPLE.values()]
    return any(
        db.scalar(stmt) is not None
        for stmt in (
            select(Team.id).limit(1),
            select(RecurringPayment.id).limit(1),
            select(User.id).where(User.email.in_(emails)).limit(1),
        )
    )


def wipe(db: Session) -> None:
    """Всё, кроме владельца, его входов в журнале и настроек организации. Файлы чеков — после commit."""
    for key in db.scalars(select(PaymentOccurrence.receipt_file).where(PaymentOccurrence.receipt_file.is_not(None))):
        receipts.discard_after_commit(db, key)
    db.execute(delete(PaymentOccurrence))
    db.execute(delete(RecurringPayment))
    db.execute(delete(Team))
    db.execute(delete(AuditLog).where(AuditLog.action.not_like("auth.%")))
    db.execute(delete(User).where(User.is_owner.is_(False)))
    db.flush()


def silence(db: Session, today: date, *, keep_today: bool) -> None:
    """Уже наступившие точки каденции — «доставлены», первый тик воркера их не шлёт.

    keep_today — точка, которая наступила именно сегодня (T-7, T-3, T-1, просрочка),
    остаётся воркеру.
    """
    org = load_org(db)
    rows = db.scalars(select(PaymentOccurrence).where(PaymentOccurrence.paid_at.is_(None))).all()
    for row in rows:
        template = db.get(RecurringPayment, row.recurring_payment_id)
        if template is None:
            continue
        events = notification_events(
            due=row.due_date,
            paid_at=row.paid_at,
            archived=template.is_archived,
            today=today,
            offsets=org.reminder_days,
            overdue=org.overdue_reminders,
        )
        days_until = (row.due_date - today).days
        for event in events:
            if keep_today and _fresh(event, days_until):
                continue
            for channel, recipient in _plan(db, row, event):
                _mark(db, row.id, event, channel, recipient)


def _fresh(event: str, days_until: int) -> bool:
    """Точка наступила именно сегодня. Просрочка напоминает каждый день."""
    if days_until < 0:
        return True
    return event.endswith(f".d{days_until}")


def build(db: Session, owner: User, password: str, *, quiet: bool) -> None:
    clock.bind_zone(load_org(db).timezone)
    today = clock.today()
    rng = random.Random(404)
    origin = _back(today.replace(day=1), HISTORY_MONTHS)
    since = clock.now()
    joined = _at(origin - timedelta(days=20), rng)
    people: dict[str, User] = {}
    for key, (name, login, scope, overdue) in PEOPLE.items():
        user = create_verified_user(db, email=f"{login}@{DOMAIN}", full_name=name, password=password)
        user.email_reminders = False
        user.notify_scope = scope
        user.notify_overdue = overdue
        user.created_at = joined
        user.updated_at = joined
        people[key] = user
    owner.active_team_id = None
    for name, admins, members, items in TEAMS:
        team = create_team(db, owner, name)
        team.created_at = joined
        for key in admins:
            add_member(db, team, people[key], "admin", actor=owner)
        for key in members:
            add_member(db, team, people[key], "member", actor=owner)
        for item in items:
            _payment(db, team, item, people, origin, today, rng)
        for currency, amount in BUDGETS.get(name, []):
            add_budget(db, team.id, "month", f"{today:%Y-%m}", currency, Decimal(amount))
    db.execute(update(AuditLog).where(AuditLog.at >= since).values(at=joined))
    db.flush()
    silence(db, today, keep_today=not quiet)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.demo_data", description="Демо-данные хостинг-компании")
    parser.add_argument("--force", action="store_true", help="стереть отделы, платежи и людей, кроме владельца")
    parser.add_argument("--quiet", action="store_true", help="не слать даже сегодняшние напоминания")
    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        owner = db.scalar(select(User).where(User.is_owner.is_(True)))
        if owner is None:
            print("Владельца нет: сначала запустите api, он создаёт владельца из .env.", file=sys.stderr)
            return 1
        if has_data(db):
            if not args.force:
                print("В базе уже есть отделы, платежи или демо-люди. Ничего не менял. Пересоздать: --force.", file=sys.stderr)
                return 1
            wipe(db)
        password = secrets.token_urlsafe(9)
        build(db, owner, password, quiet=args.quiet)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
    print(f"Готово: {len(TEAMS)} отделов, {len(PEOPLE)} человек. Владелец не тронут.")
    print(f"Пароль демо-людей: {password}")
    for name, login, _scope, _overdue in PEOPLE.values():
        print(f"  {login}@{DOMAIN}  {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

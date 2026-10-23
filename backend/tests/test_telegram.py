import socket
import uuid
from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.core.config import get_settings
from app.integrations.telegram import TelegramClient, TelegramError, deliver, describe_transport, make_bot
from app.main import app
from app.models import AuditLog, NotificationDelivery, PaymentOccurrence, RecurringPayment, User
from app.seed import seed
from app.services.notify import dispatch_due_reminders
from app.services.occurrences import ensure_template
from app.services.telegram_cards import handle_callback, sync_telegram_cards
from app.worker import tick

CHAT = "-100"
MOSCOW = ZoneInfo("Europe/Moscow")
FROZEN = datetime(2026, 10, 23, 12, 0, tzinfo=MOSCOW)


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.edits: list[dict] = []
        self.answers: list[tuple[str, str]] = []
        self.fail_sends = 0
        self.edit_error: str | None = None
        self._seq = 100

    def close(self) -> None:
        return None

    def send_message(self, chat_id: str, text: str, reply_markup: dict) -> int:
        if self.fail_sends:
            self.fail_sends -= 1
            raise TelegramError("sendMessage", "timeout")
        self._seq += 1
        self.sent.append({"chat_id": chat_id, "text": text, "reply_markup": reply_markup})
        return self._seq

    def edit_message(self, chat_id: str, message_id: int, text: str, reply_markup: dict) -> None:
        self.edits.append(
            {"chat_id": chat_id, "message_id": message_id, "text": text, "reply_markup": reply_markup}
        )
        if self.edit_error:
            message = self.edit_error
            self.edit_error = None
            raise TelegramError("editMessageText", message)

    def answer_callback(self, callback_query_id: str, text: str) -> None:
        self.answers.append((callback_query_id, text))


@pytest.fixture
def tg_bot(monkeypatch):
    bot = FakeBot()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "12345:TESTTOKEN")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT)
    get_settings.cache_clear()
    monkeypatch.setattr("app.integrations.telegram.make_bot", lambda settings=None: bot)
    yield bot
    get_settings.cache_clear()


def _admin(db) -> User:
    found = db.scalar(select(User).where(User.email == "admin@invoice.local"))
    if found is not None:
        return found
    user = User(
        email="admin@invoice.local",
        full_name="Админ",
        password_hash="x",
        role="admin",
        is_active=True,
    )
    db.add(user)
    db.flush()
    return user


def _template(db, *, title: str, day: int, archived: bool = False, note: str | None = None) -> RecurringPayment:
    admin = _admin(db)
    template = RecurringPayment(
        title=title,
        amount=Decimal("40.00"),
        currency="USD",
        day_of_month=day,
        starts_on=date(2026, 10, 1),
        responsible_user_id=admin.id,
        created_by_id=admin.id,
        is_archived=False,
    )
    db.add(template)
    db.flush()
    ensure_template(db, template, date(2026, 10, 23))
    template.is_archived = archived
    if note is not None:
        row = _october(db, template)
        row.note = note
    db.commit()
    return template


def _october(db, template: RecurringPayment) -> PaymentOccurrence:
    row = db.scalar(
        select(PaymentOccurrence).where(
            PaymentOccurrence.recurring_payment_id == template.id,
            PaymentOccurrence.period_year == 2026,
            PaymentOccurrence.period_month == 10,
        )
    )
    assert row is not None
    return row


def _reload(db, row: PaymentOccurrence) -> PaymentOccurrence:
    db.expire_all()
    fresh = db.get(PaymentOccurrence, row.id)
    assert fresh is not None
    return fresh


def _callback(occurrence_id, *, chat: str = CHAT, data: str | None = None, message_id: int = 7) -> dict:
    return {
        "id": "cb-1",
        "data": f"paid:{occurrence_id}" if data is None else data,
        "message": {"message_id": message_id, "chat": {"id": int(chat)}},
    }


def _channel(db, occurrence_id, channel: str) -> NotificationDelivery | None:
    return db.scalar(
        select(NotificationDelivery).where(
            NotificationDelivery.occurrence_id == occurrence_id,
            NotificationDelivery.channel == channel,
            NotificationDelivery.event == "occurrence.reminder",
        )
    )


def test_transport_skips_without_token_and_hides_it(monkeypatch):
    get_settings.cache_clear()
    assert make_bot() is None
    skipped = describe_transport()
    assert skipped["sender"] == "skipped"
    assert skipped["token_configured"] is False
    assert skipped["force_ipv6"] is True
    with pytest.raises(NotImplementedError):
        deliver("текст", chat_id=CHAT, occurrence_id=str(uuid.uuid4()), event="occurrence.reminder")

    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "12345:SUPERSECRET")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT)
    get_settings.cache_clear()
    try:
        described = describe_transport()
        assert described["sender"] == "long_poll"
        assert described["token_configured"] is True
        assert described["chat_configured"] is True
        assert "SUPERSECRET" not in str(described)
    finally:
        get_settings.cache_clear()


def test_force_ipv6_binds_v6_and_does_not_leak_token(monkeypatch):
    seen: dict[str, object] = {}

    def fake_connect(address, timeout=None, source_address=None):
        seen["host"] = address[0]
        seen["source"] = source_address
        raise OSError("stop")

    monkeypatch.setattr(socket, "create_connection", fake_connect)
    client = TelegramClient("12345:SUPERSECRET", force_ipv6=True)
    try:
        try:
            client.get_me()
        except TelegramError as exc:
            assert "SUPERSECRET" not in str(exc)
        else:
            raise AssertionError("get_me must not reach the network")
    finally:
        client.close()
    assert seen["host"] == "api.telegram.org"
    assert seen["source"] == ("::", 0)

    seen.clear()
    plain = TelegramClient("12345:SUPERSECRET", force_ipv6=False)
    try:
        try:
            plain.get_me()
        except TelegramError:
            pass
    finally:
        plain.close()
    assert seen["source"] is None


def test_remind_window_dedup_archive_and_paid(db_session, tg_bot):
    soon = _template(db_session, title="Сервер", day=26)
    later = _template(db_session, title="Рано", day=27)
    late = _template(db_session, title="Аренда", day=20)
    closed = _template(db_session, title="Закрыт", day=26)
    archived = _template(db_session, title="Архив", day=20, archived=True)
    paid = _october(db_session, closed)
    paid.paid_at = FROZEN
    db_session.commit()

    assert dispatch_due_reminders(db_session) == 2
    titles = {item["text"].splitlines()[0] for item in tg_bot.sent}
    assert titles == {"Сервер", "Аренда"}
    server = next(item for item in tg_bot.sent if item["text"].startswith("Сервер"))
    assert "40.00 USD" in server["text"]
    assert "Срок: 26.10.2026" in server["text"]
    assert "Статус: скоро" in server["text"]
    assert server["reply_markup"]["inline_keyboard"][0][0]["callback_data"] == f"paid:{_october(db_session, soon).id}"
    rent = next(item for item in tg_bot.sent if item["text"].startswith("Аренда"))
    assert "Статус: просрочено" in rent["text"]
    assert all(not item["text"].startswith("Рано") for item in tg_bot.sent)
    assert all(not item["text"].startswith("Закрыт") for item in tg_bot.sent)
    assert all(not item["text"].startswith("Архив") for item in tg_bot.sent)

    assert dispatch_due_reminders(db_session) == 0
    assert len(tg_bot.sent) == 2
    assert _reload(db_session, _october(db_session, soon)).telegram_reminded_at == FROZEN
    assert _channel(db_session, _october(db_session, soon).id, "telegram") is not None
    assert _reload(db_session, _october(db_session, later)).telegram_reminded_at is None
    assert _reload(db_session, _october(db_session, archived)).telegram_reminded_at is None
    assert _reload(db_session, paid).telegram_message_id is None


def test_failed_send_retries_once(db_session, tg_bot):
    template = _template(db_session, title="Сервер", day=26)
    tg_bot.fail_sends = 1
    assert dispatch_due_reminders(db_session) == 0
    fresh = _reload(db_session, _october(db_session, template))
    assert fresh.telegram_reminded_at is None
    assert _channel(db_session, fresh.id, "telegram") is None
    assert dispatch_due_reminders(db_session) == 1
    assert len(tg_bot.sent) == 1
    assert _channel(db_session, fresh.id, "telegram") is not None


def test_email_does_not_block_telegram(db_session, tg_bot, monkeypatch):
    monkeypatch.setenv("EMAIL_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.test")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_FROM", "keeper@test.local")
    monkeypatch.setenv("SMTP_TO", "team@test.local")
    monkeypatch.setenv("SMTP_TLS", "true")
    get_settings.cache_clear()
    sent: list = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            self.host = host

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            return None

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setattr("app.integrations.email.smtplib.SMTP", FakeSMTP)
    template = _template(db_session, title="Сервер", day=26)
    row = _october(db_session, template)
    tg_bot.fail_sends = 1
    assert dispatch_due_reminders(db_session) == 1
    db_session.commit()
    assert len(sent) == 1
    assert _channel(db_session, row.id, "email") is not None
    assert _channel(db_session, row.id, "telegram") is None

    assert dispatch_due_reminders(db_session) == 1
    db_session.commit()
    assert len(tg_bot.sent) == 1
    assert _channel(db_session, row.id, "telegram") is not None
    assert dispatch_due_reminders(db_session) == 0


def test_button_marks_paid_as_env_admin_and_keeps_note(db_session):
    template = _template(db_session, title="Сервер", day=20, note="не трогать")
    row = _october(db_session, template)
    bot = FakeBot()
    handle_callback(db_session, bot, _callback(row.id), expected_chat_id=CHAT)
    fresh = _reload(db_session, row)
    assert fresh.paid_at == FROZEN
    assert fresh.note == "не трогать"
    payer = db_session.get(User, fresh.paid_by_id)
    assert payer is not None
    assert payer.email == "admin@invoice.local"
    assert bot.answers == [("cb-1", "Оплачено")]
    assert "Оплачено: 23.10.2026" in bot.edits[-1]["text"]
    assert bot.edits[-1]["reply_markup"] == {"inline_keyboard": []}
    assert fresh.telegram_message_id == 7
    action = db_session.scalar(select(AuditLog.action).where(AuditLog.entity_id == row.id))
    assert action == "occurrence.paid"

    handle_callback(db_session, bot, _callback(row.id, message_id=7), expected_chat_id=CHAT)
    again = _reload(db_session, row)
    assert again.paid_at == FROZEN
    assert bot.answers[-1] == ("cb-1", "Уже оплачено")
    assert again.paid_by_id == payer.id


def test_button_without_admin_still_sets_paid_at(db_session):
    template = _template(db_session, title="Сервер", day=20)
    admin = _admin(db_session)
    admin.is_active = False
    db_session.commit()
    row = _october(db_session, template)
    bot = FakeBot()
    handle_callback(db_session, bot, _callback(row.id), expected_chat_id=CHAT)
    fresh = _reload(db_session, row)
    assert fresh.paid_at == FROZEN
    assert fresh.paid_by_id is None
    assert bot.answers[-1][1] == "Оплачено"


def test_button_ignores_other_chat_bad_payload_and_missing_period(db_session):
    template = _template(db_session, title="Сервер", day=20)
    row = _october(db_session, template)
    bot = FakeBot()
    handle_callback(db_session, bot, _callback(row.id, chat="-200"), expected_chat_id=CHAT)
    handle_callback(db_session, bot, _callback(row.id, data="paid:nope"), expected_chat_id=CHAT)
    handle_callback(db_session, bot, _callback(uuid.uuid4()), expected_chat_id=CHAT)
    handle_callback(db_session, bot, _callback(row.id), expected_chat_id="")
    fresh = _reload(db_session, row)
    assert fresh.paid_at is None
    assert [item[1] for item in bot.answers] == [
        "Чат не подключён к инбоксу",
        "Некорректная кнопка",
        "Период не найден",
        "Чат не настроен",
    ]


def test_archived_period_can_still_be_paid_from_the_button(db_session, tg_bot):
    template = _template(db_session, title="Архив", day=20, archived=True)
    row = _october(db_session, template)
    assert dispatch_due_reminders(db_session) == 0
    handle_callback(db_session, tg_bot, _callback(row.id), expected_chat_id=CHAT)
    assert _reload(db_session, row).paid_at == FROZEN


def test_web_pay_and_revoke_edit_the_same_message(db_session, tg_bot):
    template = _template(db_session, title="Сервер", day=26)
    assert dispatch_due_reminders(db_session) == 1
    row = _reload(db_session, _october(db_session, template))
    row.paid_at = FROZEN
    row.paid_by_id = _admin(db_session).id
    db_session.commit()
    assert sync_telegram_cards(db_session, tg_bot) == 1
    assert tg_bot.edits[-1]["reply_markup"] == {"inline_keyboard": []}
    assert "Оплачено: 23.10.2026" in tg_bot.edits[-1]["text"]
    assert sync_telegram_cards(db_session, tg_bot) == 0

    row = _reload(db_session, row)
    row.paid_at = None
    row.paid_by_id = None
    db_session.commit()
    assert sync_telegram_cards(db_session, tg_bot) == 1
    assert len(tg_bot.sent) == 1
    assert tg_bot.edits[-1]["reply_markup"]["inline_keyboard"][0][0]["text"] == "Оплачено"


def test_status_change_edits_message_lost_message_does_not_resend(db_session, tg_bot, monkeypatch):
    template = _template(db_session, title="Сервер", day=26)
    dispatch_due_reminders(db_session)
    monkeypatch.setattr("app.services.time.today", lambda: date(2026, 10, 27))
    assert sync_telegram_cards(db_session, tg_bot) == 1
    assert "Статус: просрочено" in tg_bot.edits[-1]["text"]

    row = _reload(db_session, _october(db_session, template))
    row.telegram_fingerprint = "force-edit"
    db_session.commit()
    tg_bot.edit_error = "Bad Request: message to edit not found"
    assert sync_telegram_cards(db_session, tg_bot) == 0
    fresh = _reload(db_session, _october(db_session, template))
    assert fresh.telegram_message_id is None
    assert _channel(db_session, fresh.id, "telegram") is not None
    assert dispatch_due_reminders(db_session) == 0
    assert len(tg_bot.sent) == 1


def test_not_modified_is_success(db_session, tg_bot):
    template = _template(db_session, title="Сервер", day=26)
    dispatch_due_reminders(db_session)
    row = _reload(db_session, _october(db_session, template))
    row.telegram_fingerprint = "stale"
    db_session.commit()
    tg_bot.edit_error = "Bad Request: message is not modified"
    assert sync_telegram_cards(db_session, tg_bot) == 0
    assert len(tg_bot.edits) == 1
    assert sync_telegram_cards(db_session, tg_bot) == 0
    assert len(tg_bot.edits) == 1


def test_tick_without_token_keeps_horizon_and_with_token_sends_once(db_session, monkeypatch):
    template = _template(db_session, title="Сервер", day=26)
    tick()
    row = _reload(db_session, _october(db_session, template))
    assert row.telegram_reminded_at is None
    assert _channel(db_session, row.id, "telegram") is None

    bot = FakeBot()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "12345:TESTTOKEN")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT)
    get_settings.cache_clear()
    monkeypatch.setattr("app.integrations.telegram.make_bot", lambda settings=None: bot)
    try:
        tick()
        tick()
    finally:
        get_settings.cache_clear()
    assert len(bot.sent) == 1
    assert _reload(db_session, row).telegram_reminded_at == FROZEN


def test_api_shows_reminder_and_button_leaves_inbox(client, db_session, tg_bot):
    seed(demo=False)
    login = client.post("/api/v1/auth/login", json={"email": "admin@invoice.local", "password": "change-me"})
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
    created = client.post(
        "/api/v1/recurring-payments",
        headers=headers,
        json={
            "title": "Сервер",
            "amount": "40.00",
            "currency": "USD",
            "day_of_month": 20,
            "starts_on": "2026-10-01",
            "responsible_user_id": login.json()["user"]["id"],
        },
    )
    assert created.status_code == 201, created.text
    listed = client.get(
        f"/api/v1/payment-occurrences?recurring_payment_id={created.json()['id']}",
        headers=headers,
    ).json()["items"]
    october = next(item for item in listed if item["period"] == "2026-10")
    assert october["telegram_reminded_at"] is None

    assert dispatch_due_reminders(db_session) == 1
    reminded = client.get(f"/api/v1/payment-occurrences/{october['id']}", headers=headers)
    assert reminded.status_code == 200, reminded.text
    assert reminded.json()["telegram_reminded_at"].startswith("2026-10-23")

    handle_callback(db_session, tg_bot, _callback(october["id"]), expected_chat_id=CHAT)
    inbox = client.get("/api/v1/payment-occurrences/inbox", headers=headers).json()
    left = {item["id"] for name in ("overdue", "soon", "rest") for item in inbox[name]}
    assert october["id"] not in left
    paid = client.get(f"/api/v1/payment-occurrences/{october['id']}", headers=headers).json()
    assert paid["status"] == "paid"
    assert paid["paid_on"] == "2026-10-23"
    assert paid["paid_by"]["email"] == "admin@invoice.local"
    assert paid["note"] is None


def test_openapi_documents_telegram_actor():
    schema = app.openapi()["components"]["schemas"]["OccurrenceOut"]["properties"]
    assert "telegram_reminded_at" in schema
    assert "ADMIN_EMAIL" in schema["paid_by"]["description"]
    assert "ADMIN_EMAIL" in app.openapi()["info"]["description"]

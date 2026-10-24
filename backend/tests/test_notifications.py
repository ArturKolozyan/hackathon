"""Уведомления: два события, дедуп, скоупы, права, сводка при подключении чата."""

import uuid
from datetime import date

import pytest
from sqlalchemy import func, select

from app.core.config import get_settings
from app.models import ChannelSubscription, NotificationDelivery, PaymentOccurrence, User
from app.services.notify import OVERDUE, dispatch_due_reminders
from app.services.reminders import notification_events, should_remind
from app.services.telegram_cards import handle_callback
from app.services.telegram_links import issue_token
from app.services.telegram_updates import handle_update
from tests.support import add_person, bootstrap_owner
from tests.test_telegram import CHAT, FakeBot, _admin, _bind, _callback, _october, _reload, _template
from tests.test_telegram_link import _message


@pytest.fixture
def tg_bot(monkeypatch):
    from tests.test_telegram import _sent_delta

    bot = FakeBot()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "12345:TESTTOKEN")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT)
    get_settings.cache_clear()
    monkeypatch.setattr("app.integrations.telegram.make_bot", lambda settings=None: bot)
    import app.services.notify as notify

    original = notify.dispatch_due_reminders

    def wrapped(db):
        before = _sent_delta(db)
        original(db)
        from app.services.outbox import drain_telegram

        drain_telegram(db, bot)
        db.expire_all()
        return _sent_delta(db) - before

    import sys

    monkeypatch.setattr(notify, "dispatch_due_reminders", wrapped)
    monkeypatch.setattr(sys.modules[__name__], "dispatch_due_reminders", wrapped)
    yield bot
    get_settings.cache_clear()


def test_events_split_reminder_and_overdue():
    today = date(2026, 10, 23)
    base = {"paid_at": None, "archived": False, "today": today, "soon_days": 3}
    assert notification_events(due=date(2026, 10, 26), **base) == ["occurrence.reminder.d3"]
    assert notification_events(due=date(2026, 10, 23), **base) == ["occurrence.reminder.d3"]
    assert notification_events(due=date(2026, 10, 27), **base) == []
    assert notification_events(due=date(2026, 10, 22), **base) == [OVERDUE]
    assert notification_events(due=date(2026, 10, 1), **base) == ["occurrence.overdue.r21"]
    assert notification_events(due=date(2026, 10, 21), **base) == ["occurrence.overdue.r1"]
    assert notification_events(due=date(2026, 10, 25), paid_at=None, archived=False, today=today) == ["occurrence.reminder.d3"]
    assert notification_events(due=date(2026, 10, 30), paid_at=None, archived=False, today=today) == ["occurrence.reminder.d7"]
    assert notification_events(due=date(2026, 10, 1), **base, overdue_repeat_days=3) == ["occurrence.overdue.r7"]
    assert notification_events(due=date(2026, 10, 26), paid_at=object(), archived=False, today=today, soon_days=3) == []
    assert (
        notification_events(
            due=date(2026, 10, 22),
            paid_at=None,
            archived=True,
            today=today,
            soon_days=3,
            remind_archived_overdue=False,
        )
        == []
    )
    assert notification_events(due=date(2026, 10, 22), paid_at=None, archived=True, today=today, soon_days=3) == [OVERDUE]
    for due in (date(2026, 10, 26), date(2026, 10, 23), date(2026, 10, 22), date(2026, 10, 27)):
        args = {"due": due, "paid_at": None, "archived": False, "today": today, "soon_days": 3}
        assert bool(notification_events(**args)) is should_remind(**args)


def test_dispatch_dedups_t3_and_overdue(db_session, tg_bot):
    soon = _template(db_session, title="Скоро", day=26)
    late = _template(db_session, title="Долг", day=22)
    early = _template(db_session, title="Рано", day=31)
    assert dispatch_due_reminders(db_session) == 2
    assert dispatch_due_reminders(db_session) == 0

    def rows(template, event):
        occurrence = _october(db_session, template)
        return list(
            db_session.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.occurrence_id == occurrence.id,
                    NotificationDelivery.event == event,
                )
            ).all()
        )

    soon_rows = rows(soon, "occurrence.reminder.d3")
    late_rows = rows(late, OVERDUE)
    assert len(soon_rows) == 1
    assert soon_rows[0].channel == "telegram"
    assert soon_rows[0].recipient == "team"
    assert len(late_rows) == 1
    assert late_rows[0].event == OVERDUE
    assert rows(early, "occurrence.reminder.d7") == []
    assert rows(early, OVERDUE) == []
    assert rows(soon, OVERDUE) == []
    assert rows(late, "occurrence.reminder.d0") == []
    counted = db_session.scalar(select(func.count()).select_from(NotificationDelivery))
    assert counted == 2


def test_personal_scope_follows_responsibility_and_telegram_toggle(db_session, tg_bot, monkeypatch):
    sent: list = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            return None

        def send_message(self, message):
            sent.append(message)

    monkeypatch.setenv("EMAIL_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.beget.com")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_FROM", "keeper@rekeeper.ru")
    monkeypatch.setenv("SMTP_TO", "")
    monkeypatch.setenv("SMTP_TLS", "true")
    get_settings.cache_clear()
    monkeypatch.setattr("app.integrations.email.smtplib.SMTP", FakeSMTP)

    admin = _admin(db_session)
    admin.email_reminders = False
    from app.services.teams import create_team

    other = create_team(db_session, admin, "Вторая")
    ivan = User(
        email="ivan@invoice.local",
        full_name="Иван",
        password_hash="x",
        is_active=True,
        telegram_user_id=777,
        telegram_reminders=False,
        telegram_scope_set=True,
        email_reminders=True,
        email_scope_set=True,
        notify_scope="mine",
    )
    db_session.add(ivan)
    db_session.flush()
    from app.services.teams import add_member

    home = db_session.get(type(other), admin.active_team_id)
    add_member(db_session, home, ivan, "member", actor=admin)
    add_member(db_session, other, ivan, "member", actor=admin)
    db_session.add(ChannelSubscription(user_id=ivan.id, channel="email", team_id=home.id))
    db_session.add(ChannelSubscription(user_id=ivan.id, channel="telegram", team_id=home.id))
    db_session.commit()

    admin.active_team_id = home.id
    db_session.commit()
    here = _template(db_session, title="Своя", day=26)
    admin.active_team_id = other.id
    db_session.commit()
    there = _template(db_session, title="Чужая", day=26)
    there.responsible_user_id = ivan.id
    db_session.commit()

    try:
        # mine + Telegram выключен: письмо только за свой платёж, лички нет.
        # Подписки на отделы больше не расширяют скоуп.
        assert dispatch_due_reminders(db_session) == 1
        assert len(sent) == 1
        assert sent[0]["To"] == "ivan@invoice.local"
        assert "Чужая" in sent[0].get_content()
        assert "Своя" not in sent[0].get_content()
        assert tg_bot.sent == []

        ivan.notify_scope = "department"
        ivan.telegram_reminders = True
        db_session.commit()
        assert dispatch_due_reminders(db_session) == 3
        assert any("Своя" in item.get_content() for item in sent)
        assert {item["text"].splitlines()[0] for item in tg_bot.sent} == {"Своя", "Чужая"}
        assert {item["chat_id"] for item in tg_bot.sent} == {"777"}
    finally:
        get_settings.cache_clear()

    here_mail = db_session.scalar(
        select(NotificationDelivery).where(
            NotificationDelivery.occurrence_id == _october(db_session, here).id,
            NotificationDelivery.channel == "email",
            NotificationDelivery.recipient == f"user:{ivan.id}",
        )
    )
    there_mail = db_session.scalar(
        select(NotificationDelivery).where(
            NotificationDelivery.occurrence_id == _october(db_session, there).id,
            NotificationDelivery.channel == "email",
            NotificationDelivery.recipient == f"user:{ivan.id}",
        )
    )
    assert here_mail is not None
    assert there_mail is not None


def test_connect_sends_summary_not_cards(db_session, tg_bot, monkeypatch):
    admin = _admin(db_session)
    _bind(db_session, admin, 501)
    _template(db_session, title="Долг", day=22)
    _template(db_session, title="Скоро", day=26)
    _template(db_session, title="Потом", day=31)
    bot = FakeBot()
    token = issue_token(db_session, purpose="team", user=admin)
    handle_update(
        db_session,
        bot,
        _message(f"/start {token.token}", chat_id=-100500, chat_type="group", title="404 mercy"),
    )
    assert len(bot.sent) == 1
    text = bot.sent[0]["text"]
    assert text.startswith("Подключено. Сейчас открыто ")
    assert "ближайшие:" in text
    assert "Долг" in text
    open_count = db_session.scalar(
        select(func.count()).select_from(PaymentOccurrence).where(PaymentOccurrence.paid_at.is_(None))
    )
    assert str(open_count) in text.split("ближайшие:", 1)[0]
    assert bot.sent[0]["reply_markup"]["inline_keyboard"] == []

    monkeypatch.setattr("app.integrations.telegram.make_bot", lambda settings=None: tg_bot)
    assert dispatch_due_reminders(db_session) == 2
    cards = [item for item in tg_bot.sent if item["reply_markup"]["inline_keyboard"]]
    group_cards = [item for item in cards if item["chat_id"] == "-100500"]
    direct = [item for item in cards if item["chat_id"] == "501"]
    assert group_cards == []
    assert len(direct) == 2

    monkeypatch.setattr("app.services.time.today", lambda: date(2026, 10, 24))
    assert dispatch_due_reminders(db_session) == 2
    group_cards = [item for item in tg_bot.sent if item["chat_id"] == "-100500" and item["reply_markup"]["inline_keyboard"]]
    assert len(group_cards) == 1
    assert "Потом" in group_cards[0]["text"]
    assert "31.10.2026" in group_cards[0]["text"]
    assert dispatch_due_reminders(db_session) == 0


def test_unlinked_and_outsider_cannot_mark_paid(db_session, monkeypatch):
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT)
    get_settings.cache_clear()
    template = _template(db_session, title="Сервер", day=20)
    outsider = User(
        email="out@invoice.local",
        full_name="Чужой",
        password_hash="x",
        is_active=True,
        telegram_user_id=404,
    )
    db_session.add(outsider)
    db_session.commit()
    row = _october(db_session, template)
    bot = FakeBot()
    handle_callback(db_session, bot, _callback(row.id, sender=404))
    assert _reload(db_session, row).paid_at is None
    assert bot.answers[-1][1] == "Нет доступа к этому отделу"
    handle_callback(db_session, bot, _callback(row.id, sender=909))
    assert _reload(db_session, row).paid_at is None
    assert "привяжи Telegram" in bot.answers[-1][1]
    get_settings.cache_clear()


def _headers(client, email: str, password: str, team_id: str | None = None) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    body = response.json()
    headers = {"Authorization": f"Bearer {body['access_token']}"}
    headers["X-Team-Id"] = team_id or body["user"]["active_team_id"]
    return headers


def test_member_reads_team_channels_but_cannot_change_them(client, db_session, monkeypatch):
    bootstrap_owner()
    member = add_person(db_session, email="member@invoice.local", name="Участник")
    db_session.commit()
    owner = _headers(client, "admin@invoice.local", "change-me")
    person = _headers(client, "member@invoice.local", "change-me-user")
    viewed = client.get("/api/v1/notifications", headers=person)
    assert viewed.status_code == 200, viewed.text
    assert viewed.json()["team"]["can_manage"] is False
    assert viewed.json()["email"]["address"] == "member@invoice.local"
    blocked = client.put("/api/v1/notifications/team/webhook", headers=person, json={"url": "https://hooks.example/in"})
    assert blocked.status_code == 403
    assert client.post("/api/v1/notifications/team/webhook/test", headers=person).status_code == 403
    assert client.post("/api/v1/telegram/team-chat/test", headers=person).status_code == 403

    saved = client.put(
        "/api/v1/notifications/team/webhook",
        headers=owner,
        json={"url": "https://hooks.example/in"},
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["team"]["webhook_url"] == "https://hooks.example/in"
    again = client.get("/api/v1/notifications", headers=person)
    assert again.json()["team"]["webhook_url"] == "https://hooks.example/in"
    assert again.json()["team"]["can_manage"] is False

    foreign = str(uuid.uuid4())
    bad = client.patch(
        "/api/v1/notifications/personal",
        headers=person,
        json={
            "email_enabled": True,
            "email_team_ids": [foreign],
            "telegram_enabled": True,
            "telegram_team_ids": [],
        },
    )
    assert bad.status_code == 422

    seen: list[str] = []

    def fake_post(url, body, headers):
        seen.append(url)
        return 204

    monkeypatch.setattr("app.integrations.webhook._post", fake_post)
    checked = client.post("/api/v1/notifications/team/webhook/test", headers=owner)
    assert checked.status_code == 200, checked.text
    assert checked.json()["detail"] == "Ответ 204"
    assert seen == ["https://hooks.example/in"]
    assert member.email == "member@invoice.local"


def test_smtp_2525_uses_starttls(monkeypatch):
    calls: dict[str, object] = {}

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            calls["smtp"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            calls["tls"] = True

        def login(self, user, password):
            calls["login"] = user

        def send_message(self, message):
            calls["sent"] = True

    class FakeSSL:
        def __init__(self, host, port, timeout=None):
            calls["ssl"] = (host, port)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def login(self, user, password):
            return None

        def send_message(self, message):
            calls["ssl_sent"] = True

    monkeypatch.setattr("app.integrations.email.smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr("app.integrations.email.smtplib.SMTP_SSL", FakeSSL)
    monkeypatch.setenv("EMAIL_ENABLED", "true")
    monkeypatch.setenv("SMTP_HOST", "smtp.beget.com")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_USER", "mailer")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM", "keeper@rekeeper.ru")
    monkeypatch.setenv("SMTP_TLS", "true")
    get_settings.cache_clear()
    try:
        from app.integrations.email import send_test_email

        assert send_test_email("a@b.c") == "sent"
        assert calls["smtp"] == ("smtp.beget.com", 2525)
        assert calls.get("tls") is True
        assert "ssl" not in calls

        calls.clear()
        monkeypatch.setenv("SMTP_PORT", "465")
        get_settings.cache_clear()
        assert send_test_email("a@b.c") == "sent"
        assert calls["ssl"] == ("smtp.beget.com", 465)
        assert "smtp" not in calls
    finally:
        get_settings.cache_clear()

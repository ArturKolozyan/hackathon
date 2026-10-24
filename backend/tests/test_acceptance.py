"""Приёмка кейса: права, напоминания, фичи, ассистент не блокирует API."""

import pytest
from sqlalchemy import select

from app.assistant.telegram_bridge import OFF, UNAVAILABLE, handle_private_message
from app.core.config import get_settings
from app.models import NotificationDelivery, User
from app.seed import seed
from app.services.notify import dispatch_due_reminders
from tests.test_telegram import CHAT, FakeBot, _october, _sent_delta, _template


@pytest.fixture
def tg_bot(monkeypatch):
    import sys

    import app.services.notify as notify

    bot = FakeBot()
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "12345:TESTTOKEN")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT)
    get_settings.cache_clear()
    monkeypatch.setattr("app.integrations.telegram.make_bot", lambda settings=None: bot)
    original = notify.dispatch_due_reminders

    def wrapped(db):
        before = _sent_delta(db)
        original(db)
        from app.services.outbox import drain_telegram

        drain_telegram(db, bot)
        db.expire_all()
        return _sent_delta(db) - before

    monkeypatch.setattr(notify, "dispatch_due_reminders", wrapped)
    monkeypatch.setattr(sys.modules[__name__], "dispatch_due_reminders", wrapped)
    yield bot
    get_settings.cache_clear()


def _login(client, email: str, password: str) -> dict[str, str]:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


def test_user_cannot_do_admin_actions(client, db_session):
    seed(demo=True)
    ivan = _login(client, "ivan@invoice.local", "change-me-user")
    assert client.get("/api/v1/users", headers=ivan).status_code == 403
    assert client.post(
        "/api/v1/users",
        headers=ivan,
        json={"email": "x@invoice.local", "full_name": "Х", "password": "change-me-user", "role": "user"},
    ).status_code == 403
    assert client.post("/api/v1/teams", headers=ivan, json={"name": "Чужой"}).status_code == 403
    created = client.post(
        "/api/v1/recurring-payments",
        headers=ivan,
        json={
            "title": "Левый",
            "amount": "10.00",
            "currency": "RUB",
            "next_payment_date": "2026-11-04",
            "periodicity": "monthly",
        },
    )
    assert created.status_code == 403


def test_owner_account_is_immutable(client, db_session):
    seed(demo=True)
    owner = db_session.scalar(select(User).where(User.is_owner.is_(True)))
    assert owner is not None
    headers = _login(client, "admin@invoice.local", "change-me")
    patched = client.patch(f"/api/v1/users/{owner.id}", headers=headers, json={"full_name": "Другой"})
    assert patched.status_code == 403
    assert "нельзя" in patched.json()["detail"]
    assert client.delete(f"/api/v1/users/{owner.id}", headers=headers).status_code == 403


def test_archived_overdue_reminds_until_silenced(db_session, tg_bot):
    _template(db_session, title="Архив", day=20, archived=True)
    quiet = _template(db_session, title="Тихий", day=20, archived=True)
    quiet.remind_archived_overdue = False
    db_session.commit()
    dispatch_due_reminders(db_session)
    titles = {item["text"].splitlines()[0] for item in tg_bot.sent}
    assert "Архив" in titles
    assert "Тихий" not in titles
    assert dispatch_due_reminders(db_session) == 0


def test_reminder_is_once_and_create_inside_window_enqueues(client, db_session, tg_bot):
    from tests.support import bootstrap_owner

    bootstrap_owner()
    headers = _login(client, "admin@invoice.local", "change-me")
    me = client.get("/api/v1/auth/me", headers=headers).json()
    created = client.post(
        "/api/v1/recurring-payments",
        headers=headers,
        json={
            "title": "Срочный",
            "amount": "10.00",
            "currency": "RUB",
            "next_payment_date": "2026-10-26",
            "periodicity": "monthly",
            "responsible_user_id": me["id"],
        },
    )
    assert created.status_code == 201, created.text
    row = db_session.scalar(
        select(NotificationDelivery).where(
            NotificationDelivery.channel == "telegram",
            NotificationDelivery.event == "occurrence.reminder.d3",
        )
    )
    assert row is not None
    assert row.status == "pending"
    assert dispatch_due_reminders(db_session) == 1
    assert dispatch_due_reminders(db_session) == 0
    assert len(tg_bot.sent) == 1


def test_features_hide_assistant_without_keys(client, db_session):
    seed(demo=True)
    assert client.get("/api/v1/features").status_code == 401
    headers = _login(client, "admin@invoice.local", "change-me")
    body = client.get("/api/v1/features", headers=headers)
    assert body.status_code == 200, body.text
    data = body.json()
    assert data["assistant"] is False
    assert data["assistant_available"] is False
    assert data["voice"] is False
    assert "key" not in body.text.lower()


def test_public_config_hides_passwords_until_asked(client, monkeypatch):
    hidden = client.get("/api/v1/public-config")
    assert hidden.status_code == 200
    assert hidden.json() == {"show_demo_credentials": False, "accounts": []}
    assert "change-me" not in hidden.text

    monkeypatch.setenv("SHOW_DEMO_CREDENTIALS", "true")
    monkeypatch.setenv("OWNER_EMAIL", "owner@invoice.local")
    monkeypatch.setenv("OWNER_PASSWORD", "owner-secret")
    monkeypatch.setenv("SEED_DEMO", "false")
    get_settings.cache_clear()
    try:
        owner_only = client.get("/api/v1/public-config").json()
    finally:
        get_settings.cache_clear()
    assert owner_only["show_demo_credentials"] is True
    assert owner_only["accounts"] == [
        {"label": "Владелец", "email": "owner@invoice.local", "password": "owner-secret"}
    ]

    monkeypatch.delenv("OWNER_EMAIL", raising=False)
    monkeypatch.delenv("OWNER_PASSWORD", raising=False)
    monkeypatch.setenv("SEED_DEMO", "true")
    get_settings.cache_clear()
    try:
        aliased = client.get("/api/v1/public-config").json()
    finally:
        get_settings.cache_clear()
    assert aliased["accounts"][0] == {
        "label": "Владелец",
        "email": "admin@invoice.local",
        "password": "change-me",
    }
    assert aliased["accounts"][1:] == [
        {"label": "Пользователь", "email": "ivan@invoice.local", "password": "change-me-user"},
        {"label": "Админ отдела", "email": "maria@invoice.local", "password": "change-me-user"},
    ]


def test_features_report_assistant_down(client, db_session, monkeypatch):
    seed(demo=True)
    monkeypatch.setenv("GIGACHAT_AUTH_KEY", "present")
    monkeypatch.setenv("ASSISTANT_URL", "http://127.0.0.1:9")
    get_settings.cache_clear()
    headers = _login(client, "admin@invoice.local", "change-me")
    try:
        body = client.get("/api/v1/features", headers=headers)
    finally:
        get_settings.cache_clear()
    assert body.status_code == 200, body.text
    assert body.json()["assistant"] is True
    assert body.json()["assistant_available"] is False


def test_bot_says_off_or_unavailable(db_session, monkeypatch):
    seed(demo=True)
    user = db_session.scalar(select(User).where(User.email == "ivan@invoice.local"))
    assert user is not None
    user.telegram_user_id = 42
    db_session.commit()

    class Bot:
        def __init__(self) -> None:
            self.sent: list[str] = []

        def send_message(self, chat_id, text, reply_markup):
            self.sent.append(text)
            return 1

    monkeypatch.delenv("GIGACHAT_AUTH_KEY", raising=False)
    monkeypatch.setenv("GIGACHAT_AUTH_KEY", "")
    get_settings.cache_clear()
    bot = Bot()
    handle_private_message(db_session, bot, {"text": "что горит", "chat": {"id": 42, "type": "private"}, "from": {"id": 42}})
    assert bot.sent[-1] == OFF

    monkeypatch.setenv("GIGACHAT_AUTH_KEY", "present")
    monkeypatch.setenv("ASSISTANT_URL", "http://127.0.0.1:9")
    get_settings.cache_clear()
    try:
        handle_private_message(
            db_session, bot, {"text": "что горит", "chat": {"id": 42, "type": "private"}, "from": {"id": 42}}
        )
    finally:
        get_settings.cache_clear()
    assert bot.sent[-1] == UNAVAILABLE


def test_dispatch_does_not_call_telegram(db_session, monkeypatch):
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "12345:TESTTOKEN")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", CHAT)
    get_settings.cache_clear()

    def boom(*_args, **_kwargs):
        raise AssertionError("worker не должен звать Telegram")

    monkeypatch.setattr("app.integrations.telegram.deliver", boom)
    template = _template(db_session, title="Сервер", day=26)
    try:
        dispatch_due_reminders(db_session)
    finally:
        get_settings.cache_clear()
    row = db_session.scalar(
        select(NotificationDelivery).where(
            NotificationDelivery.occurrence_id == _october(db_session, template).id,
            NotificationDelivery.channel == "telegram",
        )
    )
    assert row is not None
    assert row.status == "pending"

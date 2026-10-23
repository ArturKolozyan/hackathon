import json
import os
from datetime import date, datetime

import httpx
import pytest

from app.seed import seed
from app.services.audit import sanitize
from app.services.reminders import should_remind


def _login(client, email: str, password: str) -> dict:
    response = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return response.json()


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _admin(client) -> dict[str, str]:
    seed(demo=False)
    admin = _login(client, "admin@invoice.local", "change-me")
    return _auth(admin["access_token"])


def _template(client, headers, **overrides) -> str:
    payload = {
        "title": "Домен",
        "amount": "10.00",
        "currency": "USD",
        "day_of_month": 12,
        "starts_on": "2026-10-01",
        "responsible_user_id": client.get("/api/v1/auth/me", headers=headers).json()["id"],
    }
    payload.update(overrides)
    created = client.post("/api/v1/recurring-payments", headers=headers, json=payload)
    assert created.status_code == 201, created.text
    return created.json()["id"]


def _periods(client, headers, payment_id: str) -> list[dict]:
    response = client.get(f"/api/v1/payment-occurrences?recurring_payment_id={payment_id}", headers=headers)
    assert response.status_code == 200, response.text
    return response.json()["items"]


@pytest.fixture
def settings_guard():
    from app.core.config import get_settings

    keys = [
        "EMAIL_ENABLED",
        "SMTP_HOST",
        "SMTP_PORT",
        "SMTP_USER",
        "SMTP_PASSWORD",
        "SMTP_FROM",
        "SMTP_TO",
        "SMTP_TLS",
        "WEBHOOK_ENABLED",
        "WEBHOOK_URL",
        "WEBHOOK_SECRET",
        "WEBHOOK_ATTEMPTS",
        "WEBHOOK_BACKOFF_SECONDS",
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_CHAT_ID",
    ]
    saved = {key: os.environ.get(key) for key in keys}
    get_settings.cache_clear()
    yield
    for key, value in saved.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    get_settings.cache_clear()


def _use_env(**values: str) -> None:
    from app.core.config import get_settings

    for key, value in values.items():
        os.environ[key] = value
    get_settings.cache_clear()


def test_should_remind_window_matches_inbox_rule():
    today = date(2026, 10, 23)
    args = {"paid_at": None, "archived": False, "today": today, "soon_days": 3}
    assert should_remind(due=date(2026, 10, 26), **args)
    assert should_remind(due=date(2026, 10, 23), **args)
    assert should_remind(due=date(2026, 10, 1), **args)
    assert not should_remind(due=date(2026, 10, 27), **args)
    assert not should_remind(due=date(2026, 10, 26), paid_at=datetime(2026, 10, 23), archived=False, today=today, soon_days=3)
    assert not should_remind(due=date(2026, 10, 23), paid_at=None, archived=True, today=today, soon_days=3)


def test_sanitize_drops_secrets():
    clean = sanitize({"email": "a@b.c", "password": "x", "nested": {"access_token": "y", "smtp_password": "z", "ok": 1}})
    assert clean == {"email": "a@b.c", "nested": {"ok": 1}}


def test_receipt_on_period(client):
    headers = _admin(client)
    payment_id = _template(client, headers)
    october = next(item for item in _periods(client, headers, payment_id) if item["period"] == "2026-10")
    assert october["receipt_url"] is None
    bad = client.patch(
        f"/api/v1/payment-occurrences/{october['id']}",
        headers=headers,
        json={"receipt_url": "http://files.example/receipt"},
    )
    assert bad.status_code == 422
    saved = client.patch(
        f"/api/v1/payment-occurrences/{october['id']}",
        headers=headers,
        json={"receipt_url": "https://files.example/receipt", "receipt_note": "счёт №14"},
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["receipt_url"] == "https://files.example/receipt"
    assert body["receipt_note"] == "счёт №14"
    assert body["status"] != "paid"
    paid = client.post(
        f"/api/v1/payment-occurrences/{october['id']}/confirm",
        headers=headers,
        json={"paid_at": "2026-10-12", "receipt_note": "оплатили с чеком"},
    )
    assert paid.status_code == 200, paid.text
    assert paid.json()["status"] == "paid"
    assert paid.json()["receipt_url"] == "https://files.example/receipt"
    assert paid.json()["receipt_note"] == "оплатили с чеком"
    cleared = client.patch(
        f"/api/v1/payment-occurrences/{october['id']}",
        headers=headers,
        json={"receipt_url": None, "receipt_note": None},
    )
    assert cleared.json()["receipt_url"] is None
    assert cleared.json()["receipt_note"] is None


def test_calendar_groups_by_due_date(client):
    headers = _admin(client)
    payment_id = _template(client, headers, title="Календарь", day_of_month=12)
    alone = client.get("/api/v1/payments/calendar?year=2026&month=10", headers=headers)
    assert alone.status_code == 200, alone.text
    body = alone.json()
    assert body["year"] == 2026 and body["month"] == 10
    october = next(day for day in body["days"] if day["date"] == "2026-10-12")
    assert october["items"][0]["title"] == "Календарь"
    assert october["items"][0]["status"] == "overdue"
    assert client.get("/api/v1/payments/calendar?year=2026", headers=headers).status_code == 422
    paid = client.post(
        f"/api/v1/payment-occurrences/{october['items'][0]['id']}/confirm",
        headers=headers,
        json={"paid_at": "2026-10-12"},
    )
    assert paid.status_code == 200
    again = client.get("/api/v1/payments/calendar?year=2026&month=10", headers=headers).json()
    refreshed = next(day for day in again["days"] if day["date"] == "2026-10-12")
    assert refreshed["items"][0]["status"] == "paid"


def test_summary_as_of_keeps_today_and_shifts_status(client):
    headers = _admin(client)
    payment_id = _template(client, headers, amount="10.00", currency="USD", day_of_month=12)
    october = next(item for item in _periods(client, headers, payment_id) if item["period"] == "2026-10")
    paid = client.post(
        f"/api/v1/payment-occurrences/{october['id']}/confirm",
        headers=headers,
        json={"paid_at": "2026-10-20"},
    )
    assert paid.status_code == 200
    current = client.get("/api/v1/payments/summary", headers=headers)
    assert current.status_code == 200
    now = current.json()
    assert now["as_of"] is None
    assert now["today"] == "2026-10-23"
    same_day = client.get("/api/v1/payments/summary?as_of=2026-10-23", headers=headers).json()
    assert same_day["counts"] == now["counts"]
    assert same_day["by_currency"] == now["by_currency"]
    assert same_day["as_of"] == "2026-10-23"

    def usd(payload: dict, key: str) -> str:
        row = next(item for item in payload["by_currency"] if item["currency"] == "USD")
        return row[key]

    mid = client.get("/api/v1/payments/summary?as_of=2026-10-15", headers=headers).json()
    assert usd(mid, "overdue_amount") == "10.00"
    assert usd(mid, "paid_amount") == "0.00"
    on_due = client.get("/api/v1/payments/summary?as_of=2026-10-12", headers=headers).json()
    assert usd(on_due, "due_soon_amount") == "10.00"
    assert usd(on_due, "overdue_amount") == "0.00"
    after = client.get("/api/v1/payments/summary?as_of=2026-10-20", headers=headers).json()
    assert usd(after, "paid_amount") == "10.00"
    assert client.get("/api/v1/payments/summary?as_of=2026-13-01", headers=headers).status_code == 422


def test_budget_plan_versus_fact(client):
    headers = _admin(client)
    ivan = client.post(
        "/api/v1/users",
        headers=headers,
        json={"email": "ivan@invoice.local", "full_name": "Иван", "password": "s3cret-pass", "role": "user"},
    )
    assert ivan.status_code == 201, ivan.text
    user_headers = _auth(_login(client, "ivan@invoice.local", "s3cret-pass")["access_token"])
    payment_id = _template(client, headers, amount="40.00", currency="USD", day_of_month=12)
    october = next(item for item in _periods(client, headers, payment_id) if item["period"] == "2026-10")
    november = next(item for item in _periods(client, headers, payment_id) if item["period"] == "2026-11")
    assert client.post(
        f"/api/v1/payment-occurrences/{october['id']}/confirm",
        headers=headers,
        json={"paid_at": "2026-10-12"},
    ).status_code == 200
    denied = client.post(
        "/api/v1/budgets",
        headers=user_headers,
        json={"period_type": "month", "period_key": "2026-10", "currency": "USD", "amount": "100.00"},
    )
    assert denied.status_code == 403
    created = client.post(
        "/api/v1/budgets",
        headers=headers,
        json={"period_type": "month", "period_key": "2026-10", "currency": "USD", "amount": "100.00"},
    )
    assert created.status_code == 201, created.text
    report = client.get("/api/v1/budgets/report?period_type=month&period_key=2026-10", headers=user_headers)
    assert report.status_code == 200, report.text
    usd = next(row for row in report.json()["rows"] if row["currency"] == "USD")
    assert usd["plan_amount"] == "100.00"
    assert usd["fact_amount"] == "40.00"
    assert usd["expected_amount"] == "0.00"
    november_report = client.get("/api/v1/budgets/report?period_type=month&period_key=2026-11", headers=headers).json()
    november_usd = next(row for row in november_report["rows"] if row["currency"] == "USD")
    assert november_usd["fact_amount"] == "0.00"
    assert november_usd["expected_amount"] == "40.00"
    assert november["due_date"].startswith("2026-11")
    year = client.post(
        "/api/v1/budgets",
        headers=headers,
        json={"period_type": "year", "period_key": "2026", "currency": "EUR", "amount": "50.00"},
    )
    assert year.status_code == 201, year.text
    yearly = client.get("/api/v1/budgets/report?period_type=year&period_key=2026", headers=headers).json()
    year_usd = next(row for row in yearly["rows"] if row["currency"] == "USD")
    year_eur = next(row for row in yearly["rows"] if row["currency"] == "EUR")
    assert year_usd["fact_amount"] == "40.00"
    assert year_eur["plan_amount"] == "50.00"
    updated = client.patch(f"/api/v1/budgets/{created.json()['id']}", headers=headers, json={"amount": "80.00"})
    assert updated.status_code == 200
    assert updated.json()["amount"] == "80.00"
    duplicate = client.post(
        "/api/v1/budgets",
        headers=headers,
        json={"period_type": "month", "period_key": "2026-10", "currency": "USD", "amount": "1.00"},
    )
    assert duplicate.status_code == 409
    assert client.delete(f"/api/v1/budgets/{created.json()['id']}", headers=headers).status_code == 204


def test_audit_log_is_admin_only_and_hides_secrets(client):
    seed(demo=False)
    failed = client.post("/api/v1/auth/login", json={"email": "admin@invoice.local", "password": "wrong-pass-1"})
    assert failed.status_code == 401
    admin = _login(client, "admin@invoice.local", "change-me")
    headers = _auth(admin["access_token"])
    created = client.post(
        "/api/v1/users",
        headers=headers,
        json={"email": "ivan@invoice.local", "full_name": "Иван", "password": "s3cret-pass", "role": "user"},
    )
    assert created.status_code == 201, created.text
    user_headers = _auth(_login(client, "ivan@invoice.local", "s3cret-pass")["access_token"])
    assert client.get("/api/v1/audit-logs", headers=user_headers).status_code == 403
    assert client.post("/api/v1/auth/logout", headers=user_headers).status_code == 204
    payment_id = _template(client, headers, title="Журнал")
    october = next(item for item in _periods(client, headers, payment_id) if item["period"] == "2026-10")
    assert client.post(
        f"/api/v1/payment-occurrences/{october['id']}/confirm",
        headers=headers,
        json={"paid_at": "2026-10-12"},
    ).status_code == 200
    assert client.post(
        f"/api/v1/payment-occurrences/{october['id']}/revoke",
        headers=headers,
        json={},
    ).status_code == 200
    assert client.post(
        "/api/v1/budgets",
        headers=headers,
        json={"period_type": "month", "period_key": "2026-10", "currency": "RUB", "amount": "10.00"},
    ).status_code == 201
    logs = client.get("/api/v1/audit-logs?limit=100", headers=headers)
    assert logs.status_code == 200, logs.text
    payload = logs.json()
    assert payload["total"] >= payload["items"].__len__()
    actions = [item["action"] for item in payload["items"]]
    times = [item["at"] for item in payload["items"]]
    assert times == sorted(times, reverse=True)
    assert "auth.login.failure" in actions
    assert "auth.login.success" in actions
    assert "auth.logout" in actions
    assert "user.create" in actions
    assert "template.create" in actions
    assert "occurrence.paid" in actions
    assert "occurrence.unpaid" in actions
    assert "budget.create" in actions
    blob = json.dumps(payload, ensure_ascii=False)
    assert "s3cret-pass" not in blob
    assert "wrong-pass-1" not in blob
    assert "change-me" not in blob
    assert admin["access_token"] not in blob
    failure = next(item for item in payload["items"] if item["action"] == "auth.login.failure")
    assert failure["actor_user_id"] is None
    assert "password" not in failure["meta"]


def test_notify_channels_share_one_rule(client, monkeypatch, settings_guard):
    headers = _admin(client)
    messages: list = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            self.host = host

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            return None

        def login(self, user, password):
            return None

        def send_message(self, message):
            messages.append(message)

    posts: list[tuple[bytes, dict]] = []

    def fake_post(url, body, headers_map):
        posts.append((body, headers_map))
        return 204

    monkeypatch.setattr("app.integrations.email.smtplib.SMTP", FakeSMTP)
    monkeypatch.setattr("app.integrations.webhook._post", fake_post)
    monkeypatch.setattr("app.integrations.webhook.time.sleep", lambda *_args, **_kwargs: None)
    _use_env(
        EMAIL_ENABLED="true",
        SMTP_HOST="smtp.test",
        SMTP_PORT="587",
        SMTP_FROM="keeper@test.local",
        SMTP_TO="team@test.local",
        SMTP_TLS="true",
        WEBHOOK_ENABLED="true",
        WEBHOOK_URL="https://hooks.example/rekeeper",
        WEBHOOK_SECRET="super-secret-value",
        WEBHOOK_ATTEMPTS="3",
        WEBHOOK_BACKOFF_SECONDS="0",
        TELEGRAM_BOT_TOKEN="",
        TELEGRAM_CHAT_ID="",
    )
    from app.services.notify import dispatch_due_reminders
    from app.core.database import SessionLocal

    payment_id = _template(client, headers, title="Сервер Aeza", amount="40.00", currency="USD", day_of_month=1)
    db = SessionLocal()
    try:
        assert dispatch_due_reminders(db) == 2
        db.commit()
    finally:
        db.close()
    assert len(messages) == 1
    text = messages[0].get_content()
    assert "Сервер Aeza" in text
    assert "40.00" in text
    assert "USD" in text
    assert "2026-10-01" in text
    assert len(posts) == 1
    reminder = json.loads(posts[0][0].decode())
    assert reminder["event"] == "occurrence.reminder"
    assert posts[0][1]["X-Rekeeper-Event"] == "occurrence.reminder"
    import hashlib
    import hmac

    digest = hmac.new(b"super-secret-value", posts[0][0], hashlib.sha256).hexdigest()
    assert posts[0][1]["X-Rekeeper-Signature"] == f"sha256={digest}"
    assert b"super-secret-value" not in posts[0][0]
    db = SessionLocal()
    try:
        assert dispatch_due_reminders(db) == 0
        db.commit()
    finally:
        db.close()
    assert len(messages) == 1
    assert len(posts) == 1

    far_id = _template(client, headers, title="Далеко", day_of_month=31, amount="3.00", currency="EUR")
    db = SessionLocal()
    try:
        assert dispatch_due_reminders(db) == 0
        db.commit()
    finally:
        db.close()
    assert len(messages) == 1

    archived = client.delete(f"/api/v1/recurring-payments/{payment_id}", headers=headers)
    assert archived.status_code == 200
    db = SessionLocal()
    try:
        from app.models import NotificationDelivery
        from sqlalchemy import delete

        db.execute(delete(NotificationDelivery))
        db.commit()
        assert dispatch_due_reminders(db) == 0
        db.commit()
    finally:
        db.close()
    assert len(messages) == 1

    october = next(item for item in _periods(client, headers, far_id) if item["period"] == "2026-10")
    paid = client.post(
        f"/api/v1/payment-occurrences/{october['id']}/confirm",
        headers=headers,
        json={"paid_at": "2026-10-23"},
    )
    assert paid.status_code == 200
    paid_events = [json.loads(body.decode())["event"] for body, _headers in posts]
    assert paid_events[-1] == "occurrence.paid"
    again = client.post(
        f"/api/v1/payment-occurrences/{october['id']}/confirm",
        headers=headers,
        json={"paid_at": "2026-10-22"},
    )
    assert again.status_code == 200
    paid_events = [json.loads(body.decode())["event"] for body, _headers in posts]
    assert paid_events.count("occurrence.paid") == 1
    revoked = client.post(f"/api/v1/payment-occurrences/{october['id']}/revoke", headers=headers)
    assert revoked.status_code == 200
    events = [json.loads(body.decode())["event"] for body, _headers in posts]
    assert events[-1] == "occurrence.unpaid"


def test_webhook_retries_then_gives_up(monkeypatch, settings_guard):
    attempts = {"n": 0}

    def flaky(url, body, headers):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise httpx.ConnectError("down")
        return 200

    monkeypatch.setattr("app.integrations.webhook._post", flaky)
    monkeypatch.setattr("app.integrations.webhook.time.sleep", lambda *_args, **_kwargs: None)
    _use_env(
        WEBHOOK_ENABLED="true",
        WEBHOOK_URL="https://hooks.example/rekeeper",
        WEBHOOK_SECRET="",
        WEBHOOK_ATTEMPTS="3",
        WEBHOOK_BACKOFF_SECONDS="0.4",
    )
    from app.integrations.webhook import send_webhook

    assert send_webhook({"event": "occurrence.reminder", "occurrence": {}}) == "sent"
    assert attempts["n"] == 3
    attempts["n"] = 0

    def always_down(url, body, headers):
        attempts["n"] += 1
        raise httpx.ConnectError("down")

    monkeypatch.setattr("app.integrations.webhook._post", always_down)
    assert send_webhook({"event": "occurrence.paid"}) == "failed"
    assert attempts["n"] == 3
    _use_env(WEBHOOK_ENABLED="false", WEBHOOK_URL="")
    assert send_webhook({"event": "occurrence.unpaid"}) == "skipped"


def test_email_disabled_is_noop(monkeypatch, settings_guard):
    called = {"n": 0}

    class Boom:
        def __init__(self, *args, **kwargs):
            called["n"] += 1

    monkeypatch.setattr("app.integrations.email.smtplib.SMTP", Boom)
    _use_env(EMAIL_ENABLED="false", SMTP_HOST="smtp.test", SMTP_FROM="a@b.c", SMTP_TO="c@d.e")
    from app.integrations.email import send_reminder_email

    assert send_reminder_email({"occurrence": {"title": "X", "amount": "1.00", "currency": "RUB", "due_date": "2026-10-01", "status": "overdue"}}) == "skipped"
    assert called["n"] == 0


def test_telegram_hook_skipped_until_implemented(client, monkeypatch, settings_guard):
    headers = _admin(client)
    calls = {"n": 0}

    def not_ready(text, *, chat_id, occurrence_id, event):
        calls["n"] += 1
        raise NotImplementedError

    monkeypatch.setattr("app.integrations.telegram.deliver", not_ready)
    _use_env(TELEGRAM_BOT_TOKEN="token", TELEGRAM_CHAT_ID="100", EMAIL_ENABLED="false", WEBHOOK_ENABLED="false")
    _template(client, headers, title="Ждёт бота", day_of_month=1, amount="5.00", currency="EUR")
    from app.core.database import SessionLocal
    from app.services.notify import dispatch_due_reminders

    db = SessionLocal()
    try:
        assert dispatch_due_reminders(db) == 0
        db.commit()
    finally:
        db.close()
    assert calls["n"] == 1
    calls["n"] = 0

    def ready(text, *, chat_id, occurrence_id, event):
        calls["n"] += 1
        assert chat_id == "100"
        assert event == "occurrence.reminder"
        assert "Ждёт бота" in text

    monkeypatch.setattr("app.integrations.telegram.deliver", ready)
    db = SessionLocal()
    try:
        assert dispatch_due_reminders(db) == 1
        assert dispatch_due_reminders(db) == 0
        db.commit()
    finally:
        db.close()
    assert calls["n"] == 1


def test_worker_tick_runs(client, settings_guard):
    headers = _admin(client)
    _template(client, headers, title="Тик", day_of_month=20, amount="2.00", currency="RUB")
    from app.worker import tick

    tick()
    inbox = client.get("/api/v1/payment-occurrences/inbox", headers=headers)
    assert inbox.status_code == 200
    titles = {item["title"] for bucket in ("overdue", "soon", "rest") for item in inbox.json()[bucket]}
    assert "Тик" in titles


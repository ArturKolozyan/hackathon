import logging
import time

from app.core.config import get_settings
from app.integrations.email import SMTP_TIMEOUT, deliver_auth_now, flush_auth_mail


def _auth(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _code(caplog, email: str, purpose: str = "register") -> str:
    found = None
    for record in caplog.records:
        if (
            record.name == "invoice_keeper.mail"
            and record.args
            and len(record.args) >= 3
            and record.args[1] == email
            and record.args[2] == purpose
        ):
            found = str(record.args[0])
    if found is None:
        raise AssertionError(caplog.text or "код не попал в лог")
    return found


def test_register_confirm_and_block_until_then(client, caplog):
    caplog.set_level(logging.WARNING, logger="invoice_keeper.mail")
    payload = {"email": "new@invoice.local", "full_name": "Новый", "password": "change-me-user"}
    created = client.post("/api/v1/auth/register", json=payload)
    assert created.status_code == 201, created.text
    assert created.json()["delivery"] == "log"
    blocked = client.post("/api/v1/auth/login", json={"email": payload["email"], "password": payload["password"]})
    assert blocked.status_code == 403
    confirmed = client.post(
        "/api/v1/auth/register/confirm",
        json={"email": payload["email"], "code": _code(caplog, payload["email"])},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["user"]["email_verified"] is True
    assert client.get("/api/v1/auth/me", headers=_auth(confirmed.json()["access_token"])).status_code == 200


def test_resend_waits_and_codes_burn(client, caplog, monkeypatch):
    caplog.set_level(logging.WARNING, logger="invoice_keeper.mail")
    email = "wait@invoice.local"
    assert client.post(
        "/api/v1/auth/register",
        json={"email": email, "full_name": "Жду", "password": "change-me-user"},
    ).status_code == 201
    assert client.post("/api/v1/auth/register/resend", json={"email": email}).status_code == 429
    from datetime import datetime
    from zoneinfo import ZoneInfo

    later = datetime(2026, 10, 23, 12, 2, tzinfo=ZoneInfo("Europe/Moscow"))
    monkeypatch.setattr("app.services.time.now", lambda: later)
    resent = client.post("/api/v1/auth/register/resend", json={"email": email})
    assert resent.status_code == 200, resent.text
    fresh = _code(caplog, email)
    for _ in range(4):
        bad = client.post("/api/v1/auth/register/confirm", json={"email": email, "code": "000000"})
        assert bad.status_code == 400
    burned = client.post("/api/v1/auth/register/confirm", json={"email": email, "code": "000000"})
    assert burned.status_code == 400
    assert "много" in burned.json()["detail"]
    missed = client.post("/api/v1/auth/register/confirm", json={"email": email, "code": fresh})
    assert missed.status_code == 400


def test_code_expires(client, caplog, monkeypatch):
    caplog.set_level(logging.WARNING, logger="invoice_keeper.mail")
    email = "old@invoice.local"
    client.post("/api/v1/auth/register", json={"email": email, "full_name": "Старый", "password": "change-me-user"})
    code = _code(caplog, email)
    from datetime import datetime
    from zoneinfo import ZoneInfo

    monkeypatch.setattr("app.services.time.now", lambda: datetime(2026, 10, 23, 12, 20, tzinfo=ZoneInfo("Europe/Moscow")))
    expired = client.post("/api/v1/auth/register/confirm", json={"email": email, "code": code})
    assert expired.status_code == 400


def test_reset_clears_lock(client, caplog, monkeypatch):
    caplog.set_level(logging.WARNING, logger="invoice_keeper.mail")
    email = "reset@invoice.local"
    password = "change-me-user"
    client.post("/api/v1/auth/register", json={"email": email, "full_name": "Сброс", "password": password})
    client.post("/api/v1/auth/register/confirm", json={"email": email, "code": _code(caplog, email)})
    for _ in range(5):
        assert client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-pass"}).status_code == 401
    locked = client.post("/api/v1/auth/login", json={"email": email, "password": password})
    assert locked.status_code == 429
    client.post("/api/v1/auth/password/forgot", json={"email": email})
    code = _code(caplog, email, "reset_password")
    assert client.post(
        "/api/v1/auth/password/reset",
        json={"email": email, "code": code, "password": "fresh-pass-1"},
    ).status_code == 204
    assert client.post("/api/v1/auth/login", json={"email": email, "password": password}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "fresh-pass-1"}).status_code == 200
    from datetime import datetime
    from zoneinfo import ZoneInfo

    monkeypatch.setattr("app.services.time.now", lambda: datetime(2026, 10, 23, 12, 20, tzinfo=ZoneInfo("Europe/Moscow")))
    # lock already cleared by reset; a fresh lock still lifts after 15 minutes
    for _ in range(5):
        client.post("/api/v1/auth/login", json={"email": email, "password": "wrong-pass"})
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "fresh-pass-1"}).status_code == 429
    monkeypatch.setattr("app.services.time.now", lambda: datetime(2026, 10, 23, 12, 36, tzinfo=ZoneInfo("Europe/Moscow")))
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "fresh-pass-1"}).status_code == 200


def test_profile_name_password_email(client, caplog):
    caplog.set_level(logging.WARNING, logger="invoice_keeper.mail")
    email = "profile@invoice.local"
    client.post("/api/v1/auth/register", json={"email": email, "full_name": "Профиль", "password": "change-me-user"})
    token = client.post(
        "/api/v1/auth/register/confirm",
        json={"email": email, "code": _code(caplog, email)},
    ).json()["access_token"]
    headers = _auth(token)
    renamed = client.patch("/api/v1/me", headers=headers, json={"full_name": "Другое имя"})
    assert renamed.status_code == 200
    assert renamed.json()["full_name"] == "Другое имя"
    assert client.post(
        "/api/v1/me/password",
        headers=headers,
        json={"current_password": "nope-nope", "new_password": "another-pass"},
    ).status_code == 401
    changed = client.post(
        "/api/v1/me/password",
        headers=headers,
        json={"current_password": "change-me-user", "new_password": "another-pass"},
    )
    assert changed.status_code == 204, changed.text
    assert client.get("/api/v1/auth/me", headers=headers).status_code == 401
    fresh = client.post("/api/v1/auth/login", json={"email": email, "password": "another-pass"})
    headers = _auth(fresh.json()["access_token"])
    sent = client.post("/api/v1/me/email", headers=headers, json={"email": "next@invoice.local"})
    assert sent.status_code == 200, sent.text
    assert sent.json()["delivery"] == "log"
    confirmed = client.post(
        "/api/v1/me/email/confirm",
        headers=headers,
        json={"code": _code(caplog, "next@invoice.local", "change_email")},
    )
    assert confirmed.status_code == 200, confirmed.text
    assert confirmed.json()["email"] == "next@invoice.local"
    assert client.post("/api/v1/auth/login", json={"email": email, "password": "another-pass"}).status_code == 401
    assert client.post("/api/v1/auth/login", json={"email": "next@invoice.local", "password": "another-pass"}).status_code == 200


def test_register_does_not_wait_on_smtp(client, monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.beget.com")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_TLS", "true")
    monkeypatch.setenv("SMTP_FROM", "rekeeper <noreply@rekeeper.ru>")
    monkeypatch.setenv("EMAIL_ENABLED", "false")
    monkeypatch.setenv("SMTP_TO", "shared@example.com")
    get_settings.cache_clear()
    seen: dict = {}

    class Slow:
        def __init__(self, host, port, timeout=None):
            seen["port"] = port
            seen["timeout"] = timeout
            time.sleep(1.2)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            seen["tls"] = True

        def send_message(self, message):
            seen["to"] = message["To"]

    monkeypatch.setattr("app.integrations.email.smtplib.SMTP", Slow)

    def refuse_ssl(*_args, **_kwargs):
        raise AssertionError("порт 465 не используется")

    monkeypatch.setattr("app.integrations.email.smtplib.SMTP_SSL", refuse_ssl)
    started = time.perf_counter()
    created = client.post(
        "/api/v1/auth/register",
        json={"email": "bg@invoice.local", "full_name": "Фон", "password": "change-me-user"},
    )
    elapsed = time.perf_counter() - started
    assert created.status_code == 201, created.text
    assert created.json()["delivery"] == "smtp"
    assert elapsed < 1
    flush_auth_mail(3)
    assert seen["port"] == 2525
    assert seen["timeout"] == SMTP_TIMEOUT
    assert seen["tls"] is True
    assert seen["to"] == "bg@invoice.local"
    get_settings.cache_clear()


def test_auth_mail_uses_starttls_and_person(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.beget.com")
    monkeypatch.setenv("SMTP_PORT", "2525")
    monkeypatch.setenv("SMTP_TLS", "true")
    monkeypatch.setenv("SMTP_USER", "noreply@rekeeper.ru")
    monkeypatch.setenv("SMTP_PASSWORD", "secret")
    monkeypatch.setenv("SMTP_FROM", "rekeeper <noreply@rekeeper.ru>")
    monkeypatch.setenv("EMAIL_ENABLED", "false")
    monkeypatch.setenv("SMTP_TO", "shared@example.com")
    get_settings.cache_clear()
    box: dict = {}

    class Capture:
        def __init__(self, host, port, timeout=None):
            box["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def starttls(self):
            box["tls"] = True

        def login(self, user, password):
            box["user"] = user

        def send_message(self, message):
            box["message"] = message

    monkeypatch.setattr("app.integrations.email.smtplib.SMTP", Capture)
    monkeypatch.setattr("app.integrations.email.smtplib.SMTP_SSL", lambda *a, **k: (_ for _ in ()).throw(AssertionError("ssl")))
    deliver_auth_now(to="person@example.com", subject="Код", text="код", html="<p>код</p>")
    assert box["tls"] is True
    assert box["port"] == 2525
    assert box["user"] == "noreply@rekeeper.ru"
    assert box["message"]["To"] == "person@example.com"
    assert box["message"]["From"] == "rekeeper <noreply@rekeeper.ru>"
    get_settings.cache_clear()

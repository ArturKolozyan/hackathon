import os
from datetime import datetime
from zoneinfo import ZoneInfo

os.environ["SECRET_KEY"] = "test-secret-key"
os.environ["ADMIN_EMAIL"] = "admin@invoice.local"
os.environ["ADMIN_PASSWORD"] = "change-me"
os.environ["ADMIN_NAME"] = "Админ"
os.environ["DEMO_USER_EMAIL"] = "ivan@invoice.local"
os.environ["DEMO_USER_NAME"] = "Иван Петров"
os.environ["DEMO_USER_TWO_EMAIL"] = "maria@invoice.local"
os.environ["DEMO_USER_TWO_NAME"] = "Мария Соколова"
os.environ["DEMO_USER_PASSWORD"] = "change-me-user"
os.environ["SEED_DEMO"] = "false"
os.environ["BCRYPT_ROUNDS"] = "4"
os.environ["TIMEZONE"] = "Europe/Moscow"
os.environ["SOON_DAYS"] = "3"
os.environ["HORIZON_MONTHS"] = "2"
os.environ["SESSION_DAYS"] = "14"
os.environ["EMAIL_ENABLED"] = "false"
os.environ["WEBHOOK_ENABLED"] = "false"
os.environ["WEBHOOK_URL"] = ""
os.environ["SMTP_HOST"] = ""
os.environ["TELEGRAM_BOT_TOKEN"] = ""
os.environ["TELEGRAM_CHAT_ID"] = ""


def _with_db(url: str, name: str) -> str:
    head, _, tail = url.rpartition("/")
    if "?" in tail:
        _, query = tail.split("?", 1)
        return f"{head}/{name}?{query}"
    return f"{head}/{name}"


_RAW_URL = os.environ.get(
    "DATABASE_URL",
    "postgresql+psycopg://invoice:change-me@localhost:5432/invoice_keeper",
)
os.environ["DATABASE_URL"] = _with_db(_RAW_URL, "invoice_keeper_test")

try:
    import psycopg

    admin_url = _with_db(_RAW_URL, "postgres").replace("postgresql+psycopg://", "postgresql://", 1)
    with psycopg.connect(admin_url, autocommit=True) as connection:
        exists = connection.execute(
            "SELECT 1 FROM pg_database WHERE datname = %s",
            ("invoice_keeper_test",),
        ).fetchone()
        if not exists:
            connection.execute("CREATE DATABASE invoice_keeper_test")
    os.environ["DB_READY"] = "1"
except Exception as exc:
    os.environ["DB_READY"] = "0"
    os.environ["DB_ERROR"] = str(exc)

import pytest


@pytest.fixture(autouse=True)
def freeze_clock(monkeypatch):
    zone = ZoneInfo("Europe/Moscow")
    frozen_now = datetime(2026, 10, 23, 12, 0, tzinfo=zone)
    monkeypatch.setattr("app.services.time.today", lambda: frozen_now.date())
    monkeypatch.setattr("app.services.time.now", lambda: frozen_now)


@pytest.fixture(scope="session")
def migrated():
    if os.environ.get("DB_READY") != "1":
        pytest.skip(os.environ.get("DB_ERROR", "PostgreSQL недоступен"))
    from alembic import command
    from alembic.config import Config

    command.upgrade(Config("alembic.ini"), "head")


@pytest.fixture
def db_session(migrated):
    from sqlalchemy import text

    from app.core.database import SessionLocal

    db = SessionLocal()
    db.execute(
        text(
            "TRUNCATE telegram_link_tokens, telegram_integration, notification_deliveries, audit_logs, "
            "budgets, payment_occurrences, recurring_payments, auth_sessions, users "
            "RESTART IDENTITY CASCADE"
        )
    )
    db.commit()
    yield db
    db.close()


@pytest.fixture
def client(db_session):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client

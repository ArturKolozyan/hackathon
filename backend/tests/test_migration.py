import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone

import pytest


def _migrate_url() -> str:
    raw = os.environ.get("DATABASE_URL", "")
    head, _, tail = raw.rpartition("/")
    if "?" in tail:
        _, query = tail.split("?", 1)
        return f"{head}/invoice_keeper_migrate?{query}"
    return f"{head}/invoice_keeper_migrate"


def test_existing_rows_become_one_team():
    if os.environ.get("DB_READY") != "1":
        pytest.skip(os.environ.get("DB_ERROR", "PostgreSQL недоступен"))
    import psycopg

    url = _migrate_url()
    admin = url.replace("postgresql+psycopg://", "postgresql://", 1)
    maintenance = admin.rsplit("/", 1)[0] + "/postgres"
    with psycopg.connect(maintenance, autocommit=True) as connection:
        connection.execute("DROP DATABASE IF EXISTS invoice_keeper_migrate")
        connection.execute("CREATE DATABASE invoice_keeper_migrate")
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "20261023_0004"], check=True, env=env)
    member_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    template_id = uuid.uuid4()
    paid_id = uuid.uuid4()
    open_id = uuid.uuid4()
    budget_id = uuid.uuid4()
    audit_id = uuid.uuid4()
    with psycopg.connect(admin) as connection:
        connection.execute(
            """
            INSERT INTO users (id, email, full_name, password_hash, role, is_active, created_at, updated_at)
            VALUES (%s, 'old@invoice.local', 'Старый', 'x', 'user', true, %s, %s),
                   (%s, 'boss@invoice.local', 'Босс', 'x', 'admin', true, %s, %s)
            """,
            (
                member_id,
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 1, 1, tzinfo=timezone.utc),
                admin_id,
                datetime(2026, 6, 1, tzinfo=timezone.utc),
                datetime(2026, 6, 1, tzinfo=timezone.utc),
            ),
        )
        connection.execute(
            """
            INSERT INTO recurring_payments (
                id, title, amount, currency, day_of_month, starts_on, responsible_user_id, created_by_id, is_archived
            ) VALUES (%s, 'Аренда', 85000, 'RUB', 5, '2026-07-01', %s, %s, false)
            """,
            (template_id, member_id, admin_id),
        )
        connection.execute(
            """
            INSERT INTO payment_occurrences (
                id, recurring_payment_id, period_year, period_month, due_date, title, amount, currency, paid_at
            ) VALUES
                (%s, %s, 2026, 8, '2026-08-05', 'Аренда', 85000, 'RUB', %s),
                (%s, %s, 2026, 10, '2026-10-05', 'Аренда', 85000, 'RUB', NULL)
            """,
            (paid_id, template_id, datetime(2026, 8, 5, 9, tzinfo=timezone.utc), open_id, template_id),
        )
        connection.execute(
            """
            INSERT INTO budgets (id, period_type, period_key, currency, amount)
            VALUES (%s, 'month', '2026-10', 'RUB', 200000)
            """,
            (budget_id,),
        )
        connection.execute(
            """
            INSERT INTO telegram_integration (id, bot_username, team_status)
            VALUES (1, 'rekeeper_bot', 'connected')
            """
        )
        connection.execute(
            """
            INSERT INTO audit_logs (id, at, actor_user_id, action, meta)
            VALUES (%s, now(), %s, 'template.create', '{}'::jsonb)
            """,
            (audit_id, admin_id),
        )
        connection.commit()
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=env)
    with psycopg.connect(admin) as connection:
        team = connection.execute("SELECT id, name FROM teams").fetchone()
        assert team[1] == "Команда"
        owner = connection.execute(
            "SELECT u.email FROM memberships m JOIN users u ON u.id = m.user_id WHERE m.role = 'owner'"
        ).fetchone()
        assert owner[0] == "boss@invoice.local"
        role = connection.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'role'"
        ).fetchone()
        assert role is None
        verified = connection.execute("SELECT count(*) FROM users WHERE email_verified_at IS NULL").fetchone()
        assert verified[0] == 0
        amount = connection.execute("SELECT amount FROM recurring_payments WHERE id = %s", (template_id,)).fetchone()
        assert str(amount[0]) == "85000.00"
        teams = connection.execute(
            "SELECT count(DISTINCT team_id) FROM payment_occurrences WHERE id IN (%s, %s)",
            (paid_id, open_id),
        ).fetchone()
        assert teams[0] == 1
        bot = connection.execute("SELECT bot_username FROM telegram_bot WHERE id = 1").fetchone()
        assert bot[0] == "rekeeper_bot"
        budget = connection.execute("SELECT team_id FROM budgets WHERE id = %s", (budget_id,)).fetchone()
        assert budget[0] == team[0]

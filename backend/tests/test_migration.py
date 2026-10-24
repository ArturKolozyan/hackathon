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
        owner = connection.execute("SELECT email FROM users WHERE is_owner").fetchone()
        assert owner[0] == "admin@invoice.local"
        boss = connection.execute(
            "SELECT m.role FROM memberships m JOIN users u ON u.id = m.user_id WHERE u.email = 'boss@invoice.local'"
        ).fetchone()
        assert boss[0] == "admin"
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


def test_prod_head_promotes_matching_user_and_keeps_payments():
    """Срез как на rekeeper: отдел «Команда», четыре человека, три валюты, привязка Telegram."""
    if os.environ.get("DB_READY") != "1":
        pytest.skip(os.environ.get("DB_ERROR", "PostgreSQL недоступен"))
    import psycopg

    raw = os.environ.get("DATABASE_URL", "")
    head, _, tail = raw.rpartition("/")
    name = "invoice_keeper_prodlike"
    if "?" in tail:
        _, query = tail.split("?", 1)
        url = f"{head}/{name}?{query}"
    else:
        url = f"{head}/{name}"
    admin = url.replace("postgresql+psycopg://", "postgresql://", 1)
    maintenance = admin.rsplit("/", 1)[0] + "/postgres"
    with psycopg.connect(maintenance, autocommit=True) as connection:
        connection.execute(f"DROP DATABASE IF EXISTS {name}")
        connection.execute(f"CREATE DATABASE {name}")
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    env["OWNER_EMAIL"] = "qa+1@rekeeper.ru"
    env["OWNER_PASSWORD"] = "change-me-owner"
    env["OWNER_NAME"] = "Владелец"
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "20261024_0007"], check=True, env=env)

    team_id = uuid.uuid4()
    owner_id = uuid.uuid4()
    ids = [uuid.uuid4() for _ in range(3)]
    payment_ids = [uuid.uuid4() for _ in range(3)]
    occurrence_ids = [uuid.uuid4() for _ in range(3)]
    now = datetime(2026, 10, 1, tzinfo=timezone.utc)
    with psycopg.connect(admin) as connection:
        connection.execute(
            "INSERT INTO teams (id, name, created_at, updated_at) VALUES (%s, 'Команда', %s, %s)",
            (team_id, now, now),
        )
        people = [
            (owner_id, "qa+1@rekeeper.ru", "Кьюэй"),
            (ids[0], "a@rekeeper.ru", "А"),
            (ids[1], "b@rekeeper.ru", "Б"),
            (ids[2], "c@rekeeper.ru", "В"),
        ]
        for person_id, email, person_name in people:
            connection.execute(
                """
                INSERT INTO users (id, email, full_name, password_hash, is_active, email_verified_at, active_team_id, created_at, updated_at)
                VALUES (%s, %s, %s, 'hash-keep', true, %s, %s, %s, %s)
                """,
                (person_id, email, person_name, now, team_id, now, now),
            )
            connection.execute(
                """
                INSERT INTO memberships (id, team_id, user_id, role, created_at)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (uuid.uuid4(), team_id, person_id, "owner" if person_id == owner_id else "member", now),
            )
        connection.execute(
            "UPDATE users SET telegram_user_id = 4242, telegram_username = 'qa' WHERE id = %s",
            (owner_id,),
        )
        specs = [
            (payment_ids[0], occurrence_ids[0], "Аренда", "85000.00", "RUB", 5),
            (payment_ids[1], occurrence_ids[1], "Сервер", "40.00", "USD", 12),
            (payment_ids[2], occurrence_ids[2], "Подписка", "15.00", "EUR", 20),
        ]
        for payment_id, occurrence_id, title, amount, currency, day in specs:
            connection.execute(
                """
                INSERT INTO recurring_payments (
                    id, team_id, title, amount, currency, day_of_month, starts_on,
                    responsible_user_id, created_by_id, is_archived
                ) VALUES (%s, %s, %s, %s, %s, %s, '2026-07-01', %s, %s, false)
                """,
                (payment_id, team_id, title, amount, currency, day, ids[0], owner_id),
            )
            paid_at = now if currency == "RUB" else None
            connection.execute(
                """
                INSERT INTO payment_occurrences (
                    id, team_id, recurring_payment_id, period_year, period_month, due_date,
                    title, amount, currency, paid_at, paid_by_id
                ) VALUES (%s, %s, %s, 2026, 10, %s, %s, %s, %s, %s, %s)
                """,
                (
                    occurrence_id,
                    team_id,
                    payment_id,
                    f"2026-10-{day:02d}",
                    title,
                    amount,
                    currency,
                    paid_at,
                    owner_id if paid_at else None,
                ),
            )
        connection.execute(
            """
            INSERT INTO telegram_integration (team_id, team_chat_id, team_status, team_chat_title)
            VALUES (%s, '-100', 'connected', 'Бухгалтерия')
            """,
            (team_id,),
        )
        connection.execute(
            "INSERT INTO telegram_bot (id, bot_username, updated_at) VALUES (1, 'rekeeperbot', %s)",
            (now,),
        )
        connection.commit()
        before = connection.execute("SELECT password_hash FROM users WHERE email = 'qa+1@rekeeper.ru'").fetchone()[0]

    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=env)
    with psycopg.connect(admin) as connection:
        owner = connection.execute(
            "SELECT is_owner, password_hash, telegram_user_id FROM users WHERE email = 'qa+1@rekeeper.ru'"
        ).fetchone()
        assert owner[0] is True
        assert owner[1] == before
        assert owner[2] == 4242
        assert connection.execute("SELECT count(*) FROM users WHERE is_owner").fetchone()[0] == 1
        role = connection.execute(
            """
            SELECT role FROM memberships m JOIN users u ON u.id = m.user_id
            WHERE u.email = 'qa+1@rekeeper.ru'
            """
        ).fetchone()
        assert role[0] == "admin"
        assert connection.execute("SELECT count(*) FROM recurring_payments").fetchone()[0] == 3
        paid = connection.execute(
            "SELECT count(*) FROM payment_occurrences WHERE paid_at IS NOT NULL"
        ).fetchone()[0]
        assert paid == 1
        chat = connection.execute("SELECT team_chat_id FROM telegram_integration").fetchone()
        assert chat[0] == "-100"
        assert connection.execute("SELECT name FROM teams").fetchone()[0] == "Команда"

    subprocess.run([sys.executable, "-m", "alembic", "downgrade", "20261024_0007"], check=True, env=env)
    with psycopg.connect(admin) as connection:
        column = connection.execute(
            "SELECT 1 FROM information_schema.columns WHERE table_name = 'users' AND column_name = 'is_owner'"
        ).fetchone()
        assert column is None
        assert connection.execute("SELECT count(*) FROM recurring_payments").fetchone()[0] == 3
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], check=True, env=env)
    with psycopg.connect(admin) as connection:
        assert connection.execute("SELECT email FROM users WHERE is_owner").fetchone()[0] == "qa+1@rekeeper.ru"
        assert connection.execute("SELECT count(*) FROM payment_occurrences").fetchone()[0] == 3

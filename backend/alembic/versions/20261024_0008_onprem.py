"""on-prem: владелец, отделы, периодичность, outbox, пульс бота

Существующая команда остаётся отделом. Членство owner становится admin.
Если OWNER_EMAIL или ADMIN_EMAIL совпадает с человеком — он владелец,
пароль не трогаем. Иначе создаём владельца. Платежи, периоды и привязки
Telegram не переписываются.
"""

from typing import Sequence, Union
import os
import uuid

import sqlalchemy as sa
from alembic import op

revision: str = "20261024_0008"
down_revision: Union[str, None] = "20261024_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("is_owner", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column(
        "users", sa.Column("must_change_password", sa.Boolean(), nullable=False, server_default=sa.false())
    )
    op.add_column(
        "users",
        sa.Column("telegram_onboarding_done", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "users", sa.Column("notify_scope", sa.String(length=16), nullable=False, server_default="mine")
    )
    op.add_column(
        "users", sa.Column("notify_overdue", sa.Boolean(), nullable=False, server_default=sa.true())
    )
    op.create_check_constraint(
        "ck_users_notify_scope", "users", "notify_scope in ('mine', 'department')"
    )
    op.create_index(
        "uq_users_one_owner",
        "users",
        ["is_owner"],
        unique=True,
        postgresql_where=sa.text("is_owner"),
    )

    op.execute("UPDATE memberships SET role = 'admin' WHERE role = 'owner'")
    op.drop_index("uq_memberships_one_owner", table_name="memberships")
    op.drop_constraint("ck_memberships_role", "memberships", type_="check")
    op.create_check_constraint("ck_memberships_role", "memberships", "role in ('admin', 'member')")

    op.add_column(
        "recurring_payments",
        sa.Column("periodicity", sa.String(length=16), nullable=False, server_default="monthly"),
    )
    op.create_check_constraint(
        "ck_recurring_payments_periodicity", "recurring_payments", "periodicity = 'monthly'"
    )

    op.add_column(
        "notification_deliveries",
        sa.Column("status", sa.String(length=16), nullable=False, server_default="sent"),
    )
    op.add_column(
        "notification_deliveries",
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column("notification_deliveries", sa.Column("last_error", sa.String(length=500), nullable=True))
    op.create_check_constraint(
        "ck_notification_deliveries_status",
        "notification_deliveries",
        "status in ('pending', 'sent', 'skipped')",
    )

    op.add_column("telegram_bot", sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "telegram_bot",
        sa.Column("status", sa.String(length=16), nullable=False, server_default="unknown"),
    )
    op.add_column("telegram_bot", sa.Column("last_error", sa.String(length=500), nullable=True))

    _promote_or_create_owner()


def _promote_or_create_owner() -> None:
    email = (os.environ.get("OWNER_EMAIL") or os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    password = os.environ.get("OWNER_PASSWORD") or os.environ.get("ADMIN_PASSWORD") or ""
    name = (os.environ.get("OWNER_NAME") or os.environ.get("ADMIN_NAME") or "Владелец").strip() or "Владелец"
    if "@" not in email or len(password) < 8:
        return
    bind = op.get_bind()
    bind.execute(sa.text("UPDATE users SET is_owner = false WHERE is_owner AND email <> :email"), {"email": email})
    found = bind.execute(sa.text("SELECT id FROM users WHERE email = :email"), {"email": email}).fetchone()
    if found is not None:
        bind.execute(
            sa.text(
                """
                UPDATE users
                SET is_owner = true,
                    is_active = true,
                    must_change_password = false,
                    telegram_onboarding_done = true,
                    email_verified_at = COALESCE(email_verified_at, now())
                WHERE email = :email
                """
            ),
            {"email": email},
        )
        return
    from app.core.security import hash_password

    bind.execute(
        sa.text(
            """
            INSERT INTO users (
                id, email, full_name, password_hash, is_active, email_verified_at,
                is_owner, must_change_password, telegram_onboarding_done,
                notify_scope, notify_overdue, created_at, updated_at
            ) VALUES (
                :id, :email, :name, :password_hash, true, now(),
                true, false, true, 'mine', true, now(), now()
            )
            """
        ),
        {
            "id": uuid.uuid4(),
            "email": email,
            "name": name[:200],
            "password_hash": hash_password(password),
        },
    )


def downgrade() -> None:
    op.drop_constraint("ck_memberships_role", "memberships", type_="check")
    op.create_check_constraint(
        "ck_memberships_role", "memberships", "role in ('owner', 'admin', 'member')"
    )
    op.execute(
        """
        UPDATE memberships AS m
        SET role = 'owner'
        WHERE m.id = (
            SELECT id FROM memberships
            WHERE team_id = m.team_id
            ORDER BY CASE role WHEN 'admin' THEN 0 ELSE 1 END, created_at
            LIMIT 1
        )
        AND NOT EXISTS (
            SELECT 1 FROM memberships AS o WHERE o.team_id = m.team_id AND o.role = 'owner'
        )
        """
    )
    op.create_index(
        "uq_memberships_one_owner",
        "memberships",
        ["team_id"],
        unique=True,
        postgresql_where=sa.text("role = 'owner'"),
    )

    op.drop_index("uq_users_one_owner", table_name="users")
    op.drop_constraint("ck_users_notify_scope", "users", type_="check")
    op.drop_column("users", "notify_overdue")
    op.drop_column("users", "notify_scope")
    op.drop_column("users", "telegram_onboarding_done")
    op.drop_column("users", "must_change_password")
    op.drop_column("users", "is_owner")

    op.drop_constraint("ck_recurring_payments_periodicity", "recurring_payments", type_="check")
    op.drop_column("recurring_payments", "periodicity")

    op.drop_constraint("ck_notification_deliveries_status", "notification_deliveries", type_="check")
    op.drop_column("notification_deliveries", "last_error")
    op.drop_column("notification_deliveries", "attempts")
    op.drop_column("notification_deliveries", "status")

    op.drop_column("telegram_bot", "last_error")
    op.drop_column("telegram_bot", "status")
    op.drop_column("telegram_bot", "heartbeat_at")

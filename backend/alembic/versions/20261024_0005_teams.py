"""аккаунты, команды, team_id у платежей

Существующие пользователи и платежи складываются в одну команду «Команда».
Прежний admin становится владельцем, остальные — участниками.
Почты, которые уже были, считаются подтверждёнными: вход не ломается.
"""

from typing import Sequence, Union
import secrets
import uuid

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261024_0005"
down_revision: Union[str, None] = "20261023_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("invite_token", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("invite_token", name="uq_teams_invite_token"),
    )
    op.create_table(
        "memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role in ('owner', 'admin', 'member')", name="ck_memberships_role"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name="fk_memberships_team_id_teams", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_memberships_user_id_users", ondelete="CASCADE"),
        sa.UniqueConstraint("team_id", "user_id", name="uq_memberships_team_user"),
    )
    op.create_index(
        "uq_memberships_one_owner",
        "memberships",
        ["team_id"],
        unique=True,
        postgresql_where=sa.text("role = 'owner'"),
    )
    op.create_table(
        "email_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("purpose", sa.String(length=32), nullable=False),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("payload", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "purpose in ('register', 'reset_password', 'change_email')",
            name="ck_email_codes_purpose",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_email_codes_user_id_users", ondelete="CASCADE"),
    )
    op.create_index("ix_email_codes_email", "email_codes", ["email"])
    op.create_table(
        "login_attempts",
        sa.Column("email", sa.String(length=320), primary_key=True),
        sa.Column("failed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "team_invites",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role in ('admin', 'member')", name="ck_team_invites_role"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name="fk_team_invites_team_id_teams", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name="fk_team_invites_created_by_id_users", ondelete="SET NULL"
        ),
        sa.UniqueConstraint("token_hash", name="uq_team_invites_token_hash"),
    )
    op.create_table(
        "telegram_bot",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("bot_username", sa.String(length=64), nullable=True),
        sa.Column("bot_user_id", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.add_column("users", sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("active_team_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_users_active_team_id_teams", "users", "teams", ["active_team_id"], ["id"], ondelete="SET NULL"
    )

    op.add_column("recurring_payments", sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("payment_occurrences", sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("budgets", sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("audit_logs", sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("telegram_integration", sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("telegram_link_tokens", sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True))

    _backfill()

    op.alter_column("recurring_payments", "team_id", nullable=False)
    op.alter_column("payment_occurrences", "team_id", nullable=False)
    op.alter_column("budgets", "team_id", nullable=False)
    op.alter_column("telegram_integration", "team_id", nullable=False)
    op.alter_column("recurring_payments", "responsible_user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)

    op.create_foreign_key(
        "fk_recurring_payments_team_id_teams",
        "recurring_payments",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_recurring_payments_team_id", "recurring_payments", ["team_id"])
    op.create_foreign_key(
        "fk_payment_occurrences_team_id_teams",
        "payment_occurrences",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_payment_occurrences_team_id", "payment_occurrences", ["team_id"])
    op.drop_constraint("uq_budgets_period_currency", "budgets", type_="unique")
    op.create_foreign_key(
        "fk_budgets_team_id_teams", "budgets", "teams", ["team_id"], ["id"], ondelete="CASCADE"
    )
    op.create_unique_constraint(
        "uq_budgets_team_period_currency", "budgets", ["team_id", "period_type", "period_key", "currency"]
    )
    op.create_index("ix_budgets_team_id", "budgets", ["team_id"])
    op.create_foreign_key(
        "fk_audit_logs_team_id_teams", "audit_logs", "teams", ["team_id"], ["id"], ondelete="SET NULL"
    )
    op.create_index("ix_audit_logs_team_id", "audit_logs", ["team_id"])
    op.create_foreign_key(
        "fk_telegram_integration_team_id_teams",
        "telegram_integration",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint("uq_telegram_integration_team_id", "telegram_integration", ["team_id"])
    op.create_foreign_key(
        "fk_telegram_link_tokens_team_id_teams",
        "telegram_link_tokens",
        "teams",
        ["team_id"],
        ["id"],
        ondelete="CASCADE",
    )

    op.drop_constraint("fk_recurring_payments_responsible_user_id_users", "recurring_payments", type_="foreignkey")
    op.alter_column("recurring_payments", "responsible_user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=True)
    op.create_foreign_key(
        "fk_recurring_payments_responsible_user_id_users",
        "recurring_payments",
        "users",
        ["responsible_user_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.execute("CREATE SEQUENCE IF NOT EXISTS telegram_integration_id_seq")
    op.execute(
        "SELECT setval('telegram_integration_id_seq', "
        "COALESCE((SELECT MAX(id) FROM telegram_integration), 0) + 1, false)"
    )
    op.execute(
        "ALTER TABLE telegram_integration ALTER COLUMN id SET DEFAULT nextval('telegram_integration_id_seq')"
    )
    op.execute("ALTER SEQUENCE telegram_integration_id_seq OWNED BY telegram_integration.id")

    op.drop_constraint("ck_users_role", "users", type_="check")
    op.drop_column("users", "role")


def _backfill() -> None:
    conn = op.get_bind()
    users = conn.execute(sa.text("SELECT id, role FROM users ORDER BY created_at, id")).fetchall()
    team_id = None
    if users:
        team_id = uuid.uuid4()
        conn.execute(
            sa.text(
                "INSERT INTO teams (id, name, invite_token, created_at, updated_at) "
                "VALUES (:id, :name, :token, now(), now())"
            ),
            {"id": team_id, "name": "Команда", "token": secrets.token_urlsafe(24)},
        )
        owner_id = next((row.id for row in users if row.role == "admin"), users[0].id)
        for row in users:
            conn.execute(
                sa.text(
                    "INSERT INTO memberships (id, team_id, user_id, role, created_at) "
                    "VALUES (:id, :team_id, :user_id, :role, now())"
                ),
                {
                    "id": uuid.uuid4(),
                    "team_id": team_id,
                    "user_id": row.id,
                    "role": "owner" if row.id == owner_id else "member",
                },
            )
        conn.execute(
            sa.text("UPDATE users SET email_verified_at = now(), active_team_id = :team"),
            {"team": team_id},
        )
        conn.execute(sa.text("UPDATE recurring_payments SET team_id = :team"), {"team": team_id})
        conn.execute(
            sa.text(
                "UPDATE payment_occurrences AS o SET team_id = r.team_id "
                "FROM recurring_payments AS r WHERE o.recurring_payment_id = r.id"
            )
        )
        conn.execute(sa.text("UPDATE budgets SET team_id = :team"), {"team": team_id})
        conn.execute(sa.text("UPDATE audit_logs SET team_id = :team"), {"team": team_id})
        conn.execute(
            sa.text("UPDATE telegram_integration SET team_id = :team WHERE team_id IS NULL"),
            {"team": team_id},
        )

    bot = conn.execute(
        sa.text(
            "SELECT bot_username, bot_user_id FROM telegram_integration "
            "WHERE bot_username IS NOT NULL ORDER BY id LIMIT 1"
        )
    ).first()
    if bot is not None:
        conn.execute(
            sa.text(
                "INSERT INTO telegram_bot (id, bot_username, bot_user_id, updated_at) "
                "VALUES (1, :name, :uid, now())"
            ),
            {"name": bot.bot_username, "uid": bot.bot_user_id},
        )
    conn.execute(sa.text("DELETE FROM payment_occurrences WHERE team_id IS NULL"))
    conn.execute(sa.text("DELETE FROM recurring_payments WHERE team_id IS NULL"))
    conn.execute(sa.text("DELETE FROM budgets WHERE team_id IS NULL"))
    conn.execute(sa.text("DELETE FROM telegram_integration WHERE team_id IS NULL"))


def downgrade() -> None:
    conn = op.get_bind()
    teams = conn.execute(sa.text("SELECT count(*) FROM teams")).scalar()
    if teams and int(teams) > 1:
        raise RuntimeError("Откат невозможен: в базе больше одной команды")

    op.add_column("users", sa.Column("role", sa.String(length=16), nullable=True))
    op.execute(
        sa.text(
            "UPDATE users SET role = 'admin' WHERE id IN ("
            "SELECT user_id FROM memberships WHERE role IN ('owner', 'admin'))"
        )
    )
    op.execute(sa.text("UPDATE users SET role = 'user' WHERE role IS NULL"))
    op.alter_column("users", "role", nullable=False)
    op.create_check_constraint("ck_users_role", "users", "role in ('admin', 'user')")

    op.execute("ALTER TABLE telegram_integration ALTER COLUMN id DROP DEFAULT")
    op.execute("DROP SEQUENCE IF EXISTS telegram_integration_id_seq")

    op.drop_constraint("fk_recurring_payments_responsible_user_id_users", "recurring_payments", type_="foreignkey")
    op.execute(sa.text("UPDATE recurring_payments SET responsible_user_id = created_by_id WHERE responsible_user_id IS NULL"))
    op.alter_column("recurring_payments", "responsible_user_id", existing_type=postgresql.UUID(as_uuid=True), nullable=False)
    op.create_foreign_key(
        "fk_recurring_payments_responsible_user_id_users",
        "recurring_payments",
        "users",
        ["responsible_user_id"],
        ["id"],
    )

    op.drop_constraint("fk_telegram_link_tokens_team_id_teams", "telegram_link_tokens", type_="foreignkey")
    op.drop_column("telegram_link_tokens", "team_id")
    op.drop_constraint("uq_telegram_integration_team_id", "telegram_integration", type_="unique")
    op.drop_constraint("fk_telegram_integration_team_id_teams", "telegram_integration", type_="foreignkey")
    op.drop_column("telegram_integration", "team_id")
    op.drop_index("ix_audit_logs_team_id", table_name="audit_logs")
    op.drop_constraint("fk_audit_logs_team_id_teams", "audit_logs", type_="foreignkey")
    op.drop_column("audit_logs", "team_id")
    op.drop_constraint("uq_budgets_team_period_currency", "budgets", type_="unique")
    op.drop_index("ix_budgets_team_id", table_name="budgets")
    op.drop_constraint("fk_budgets_team_id_teams", "budgets", type_="foreignkey")
    op.drop_column("budgets", "team_id")
    op.create_unique_constraint("uq_budgets_period_currency", "budgets", ["period_type", "period_key", "currency"])
    op.drop_index("ix_payment_occurrences_team_id", table_name="payment_occurrences")
    op.drop_constraint("fk_payment_occurrences_team_id_teams", "payment_occurrences", type_="foreignkey")
    op.drop_column("payment_occurrences", "team_id")
    op.drop_index("ix_recurring_payments_team_id", table_name="recurring_payments")
    op.drop_constraint("fk_recurring_payments_team_id_teams", "recurring_payments", type_="foreignkey")
    op.drop_column("recurring_payments", "team_id")
    op.drop_constraint("fk_users_active_team_id_teams", "users", type_="foreignkey")
    op.drop_column("users", "active_team_id")
    op.drop_column("users", "email_verified_at")
    op.drop_table("telegram_bot")
    op.drop_table("team_invites")
    op.drop_table("login_attempts")
    op.drop_index("ix_email_codes_email", table_name="email_codes")
    op.drop_table("email_codes")
    op.drop_index("uq_memberships_one_owner", table_name="memberships")
    op.drop_table("memberships")
    op.drop_table("teams")

"""telegram account and team chat links"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261023_0004"
down_revision: Union[str, None] = "20261023_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("telegram_user_id", sa.BigInteger(), nullable=True))
    op.add_column("users", sa.Column("telegram_username", sa.String(length=32), nullable=True))
    op.add_column("users", sa.Column("telegram_display_name", sa.String(length=200), nullable=True))
    op.add_column(
        "users",
        sa.Column("telegram_reminders", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.create_unique_constraint("uq_users_telegram_user_id", "users", ["telegram_user_id"])

    op.add_column("payment_occurrences", sa.Column("dm_chat_id", sa.String(length=64), nullable=True))
    op.add_column("payment_occurrences", sa.Column("dm_message_id", sa.BigInteger(), nullable=True))
    op.add_column("payment_occurrences", sa.Column("dm_fingerprint", sa.String(length=64), nullable=True))

    op.add_column(
        "notification_deliveries",
        sa.Column("recipient", sa.String(length=80), nullable=False, server_default=""),
    )
    op.execute(
        "UPDATE notification_deliveries SET recipient = 'team' "
        "WHERE channel = 'telegram' AND recipient = ''"
    )
    op.drop_constraint("uq_notification_deliveries_once", "notification_deliveries", type_="unique")
    op.create_unique_constraint(
        "uq_notification_deliveries_once",
        "notification_deliveries",
        ["occurrence_id", "event", "channel", "recipient"],
    )

    op.create_table(
        "telegram_integration",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=False),
        sa.Column("bot_username", sa.String(length=64), nullable=True),
        sa.Column("bot_user_id", sa.BigInteger(), nullable=True),
        sa.Column("team_chat_id", sa.String(length=64), nullable=True),
        sa.Column("team_chat_title", sa.String(length=255), nullable=True),
        sa.Column("team_chat_type", sa.String(length=32), nullable=True),
        sa.Column("team_status", sa.String(length=16), nullable=False, server_default="absent"),
        sa.Column("team_connected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("team_disconnected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("test_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("test_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("test_error", sa.String(length=200), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "team_status in ('absent', 'connected', 'disconnected')",
            name="ck_telegram_integration_team_status",
        ),
    )
    op.create_table(
        "telegram_link_tokens",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("token", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=16), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_telegram_link_tokens_user_id_users",
            ondelete="SET NULL",
        ),
        sa.UniqueConstraint("token", name="uq_telegram_link_tokens_token"),
        sa.CheckConstraint("purpose in ('team', 'user')", name="ck_telegram_link_tokens_purpose"),
    )


def downgrade() -> None:
    op.drop_table("telegram_link_tokens")
    op.drop_table("telegram_integration")
    op.drop_constraint("uq_notification_deliveries_once", "notification_deliveries", type_="unique")
    op.create_unique_constraint(
        "uq_notification_deliveries_once",
        "notification_deliveries",
        ["occurrence_id", "event", "channel"],
    )
    op.drop_column("notification_deliveries", "recipient")
    op.drop_column("payment_occurrences", "dm_fingerprint")
    op.drop_column("payment_occurrences", "dm_message_id")
    op.drop_column("payment_occurrences", "dm_chat_id")
    op.drop_constraint("uq_users_telegram_user_id", "users", type_="unique")
    op.drop_column("users", "telegram_reminders")
    op.drop_column("users", "telegram_display_name")
    op.drop_column("users", "telegram_username")
    op.drop_column("users", "telegram_user_id")

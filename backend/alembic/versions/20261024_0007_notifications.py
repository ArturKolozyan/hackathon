"""личные скоупы уведомлений и webhook команды"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261024_0007"
down_revision: Union[str, None] = "20261024_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("telegram_scope_set", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("users", sa.Column("telegram_test_requested_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("telegram_test_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("telegram_test_error", sa.String(length=200), nullable=True))
    op.add_column(
        "users",
        sa.Column("email_reminders", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.add_column(
        "users",
        sa.Column("email_scope_set", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.add_column("teams", sa.Column("webhook_url", sa.String(length=500), nullable=True))
    op.add_column("teams", sa.Column("webhook_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("teams", sa.Column("webhook_check_error", sa.String(length=200), nullable=True))
    op.create_table(
        "channel_subscriptions",
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.CheckConstraint("channel in ('email', 'telegram')", name="ck_channel_subscriptions_channel"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name="fk_channel_subscriptions_team_id", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_channel_subscriptions_user_id", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("user_id", "channel", "team_id", name="pk_channel_subscriptions"),
    )


def downgrade() -> None:
    op.drop_table("channel_subscriptions")
    op.drop_column("teams", "webhook_check_error")
    op.drop_column("teams", "webhook_checked_at")
    op.drop_column("teams", "webhook_url")
    op.drop_column("users", "email_scope_set")
    op.drop_column("users", "email_reminders")
    op.drop_column("users", "telegram_test_error")
    op.drop_column("users", "telegram_test_sent_at")
    op.drop_column("users", "telegram_test_requested_at")
    op.drop_column("users", "telegram_scope_set")

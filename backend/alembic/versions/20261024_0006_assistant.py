"""assistant chat history and confirmation cards"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261024_0006"
down_revision: Union[str, None] = "20261024_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "assistant_actions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False, server_default="pending"),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("result_text", sa.Text(), nullable=True),
        sa.Column("telegram_chat_id", sa.String(length=64), nullable=True),
        sa.Column("telegram_message_id", sa.BigInteger(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "kind in ('create_payment', 'update_payment', 'archive_payment', 'mark_paid')",
            name="ck_assistant_actions_kind",
        ),
        sa.CheckConstraint(
            "status in ('pending', 'running', 'confirmed', 'cancelled', 'failed')",
            name="ck_assistant_actions_status",
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_assistant_actions_user_id_users", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name="fk_assistant_actions_team_id_teams", ondelete="CASCADE"),
    )
    op.create_index("ix_assistant_actions_user_id", "assistant_actions", ["user_id"])
    op.create_index("ix_assistant_actions_team_id", "assistant_actions", ["team_id"])
    op.create_table(
        "assistant_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("action_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("role in ('user', 'assistant')", name="ck_assistant_messages_role"),
        sa.ForeignKeyConstraint(
            ["user_id"], ["users.id"], name="fk_assistant_messages_user_id_users", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["team_id"], ["teams.id"], name="fk_assistant_messages_team_id_teams", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["action_id"],
            ["assistant_actions.id"],
            name="fk_assistant_messages_action_id_assistant_actions",
            ondelete="SET NULL",
        ),
    )
    op.create_index("ix_assistant_messages_user_id", "assistant_messages", ["user_id"])
    op.create_index("ix_assistant_messages_team_id", "assistant_messages", ["team_id"])
    op.create_index("ix_assistant_messages_created_at", "assistant_messages", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_assistant_messages_created_at", table_name="assistant_messages")
    op.drop_index("ix_assistant_messages_team_id", table_name="assistant_messages")
    op.drop_index("ix_assistant_messages_user_id", table_name="assistant_messages")
    op.drop_table("assistant_messages")
    op.drop_index("ix_assistant_actions_team_id", table_name="assistant_actions")
    op.drop_index("ix_assistant_actions_user_id", table_name="assistant_actions")
    op.drop_table("assistant_actions")

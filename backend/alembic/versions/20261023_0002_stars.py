"""receipts, budgets, audit logs, notification deliveries"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261023_0002"
down_revision: Union[str, None] = "20261023_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payment_occurrences", sa.Column("receipt_url", sa.Text(), nullable=True))
    op.add_column("payment_occurrences", sa.Column("receipt_note", sa.Text(), nullable=True))
    op.create_table(
        "budgets",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("period_type", sa.String(length=8), nullable=False),
        sa.Column("period_key", sa.String(length=7), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("period_type in ('month', 'year')", name="ck_budgets_period_type"),
        sa.CheckConstraint("currency in ('RUB', 'USD', 'EUR')", name="ck_budgets_currency"),
        sa.CheckConstraint("amount > 0", name="ck_budgets_amount"),
        sa.UniqueConstraint("period_type", "period_key", "currency", name="uq_budgets_period_currency"),
    )
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity_type", sa.String(length=64), nullable=True),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("meta", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name="fk_audit_logs_actor_user_id_users", ondelete="SET NULL"),
    )
    op.create_index("ix_audit_logs_at", "audit_logs", ["at"])
    op.create_table(
        "notification_deliveries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("occurrence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event", sa.String(length=64), nullable=False),
        sa.Column("channel", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(
            ["occurrence_id"],
            ["payment_occurrences.id"],
            name="fk_notification_deliveries_occurrence_id",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("occurrence_id", "event", "channel", name="uq_notification_deliveries_once"),
    )


def downgrade() -> None:
    op.drop_table("notification_deliveries")
    op.drop_index("ix_audit_logs_at", table_name="audit_logs")
    op.drop_table("audit_logs")
    op.drop_table("budgets")
    op.drop_column("payment_occurrences", "receipt_note")
    op.drop_column("payment_occurrences", "receipt_url")

"""каденция, снимки периодов, настройки организации, без приглашений

Периоды уже хранят название, сумму, валюту и срок. Неоплаченные снимки
ещё раз копируются из текущего шаблона. Оплаченные не трогаем: у них
фактическая сумма становится равной плановой. Приглашения удаляются,
платежи, люди и периоды остаются.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20261024_0009"
down_revision: Union[str, None] = "20261024_0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "organization_settings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="Europe/Moscow"),
        sa.Column("reminder_days", sa.String(length=64), nullable=False, server_default="7,3,0"),
        sa.Column("overdue_repeat_days", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("owner_overdue_copy", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("id = 1", name="ck_organization_settings_singleton"),
        sa.CheckConstraint("overdue_repeat_days >= 1", name="ck_organization_settings_repeat"),
    )
    op.add_column("payment_occurrences", sa.Column("paid_amount", sa.Numeric(12, 2), nullable=True))
    op.create_check_constraint(
        "ck_payment_occurrences_paid_amount",
        "payment_occurrences",
        "paid_amount is null or paid_amount > 0",
    )
    op.execute(
        """
        UPDATE payment_occurrences AS o
        SET title = r.title,
            description = r.description,
            amount = r.amount,
            currency = r.currency
        FROM recurring_payments AS r
        WHERE o.recurring_payment_id = r.id
          AND o.paid_at IS NULL
        """
    )
    op.execute("UPDATE payment_occurrences SET paid_amount = amount WHERE paid_at IS NOT NULL")

    op.add_column("recurring_payments", sa.Column("interval_months", sa.Integer(), nullable=True))
    op.add_column(
        "recurring_payments",
        sa.Column("remind_archived_overdue", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.execute("UPDATE recurring_payments SET interval_months = 1 WHERE periodicity = 'monthly'")
    op.drop_constraint("ck_recurring_payments_periodicity", "recurring_payments", type_="check")
    op.create_check_constraint(
        "ck_recurring_payments_periodicity",
        "recurring_payments",
        "periodicity in ('monthly', 'quarterly', 'semiannual', 'yearly', 'once', 'every_n')",
    )
    op.create_check_constraint(
        "ck_recurring_payments_interval",
        "recurring_payments",
        "interval_months is null or interval_months between 1 and 36",
    )
    op.drop_table("team_invites")


def downgrade() -> None:
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
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role in ('admin', 'member')", name="ck_team_invites_role"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], name="fk_team_invites_team_id_teams", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["users.id"], name="fk_team_invites_created_by_id_users", ondelete="SET NULL"
        ),
        sa.UniqueConstraint("token_hash", name="uq_team_invites_token_hash"),
    )
    op.drop_constraint("ck_recurring_payments_interval", "recurring_payments", type_="check")
    op.drop_constraint("ck_recurring_payments_periodicity", "recurring_payments", type_="check")
    op.execute("UPDATE recurring_payments SET periodicity = 'monthly'")
    op.create_check_constraint(
        "ck_recurring_payments_periodicity", "recurring_payments", "periodicity = 'monthly'"
    )
    op.drop_column("recurring_payments", "remind_archived_overdue")
    op.drop_column("recurring_payments", "interval_months")
    op.drop_constraint("ck_payment_occurrences_paid_amount", "payment_occurrences", type_="check")
    op.drop_column("payment_occurrences", "paid_amount")
    op.drop_table("organization_settings")

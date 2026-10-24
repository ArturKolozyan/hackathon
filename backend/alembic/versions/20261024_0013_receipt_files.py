"""чек — файл, письма — по отделам

Чек периода теперь файл на томе receipts: имя, тип, размер и ключ хранилища.
Ссылки receipt_url уходят. Если ссылка была, она дописывается в комментарий
к чеку, чтобы ничего не потерялось.

Подписка на письма по отделу получает свой охват: только мои платежи или весь отдел.
Существующие строки берут охват из личной настройки человека.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261024_0013"
down_revision: Union[str, None] = "20261024_0012"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payment_occurrences", sa.Column("receipt_file", sa.String(80), nullable=True))
    op.add_column("payment_occurrences", sa.Column("receipt_name", sa.String(255), nullable=True))
    op.add_column("payment_occurrences", sa.Column("receipt_type", sa.String(64), nullable=True))
    op.add_column("payment_occurrences", sa.Column("receipt_size", sa.Integer(), nullable=True))
    op.add_column(
        "payment_occurrences",
        sa.Column("receipt_uploaded_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.execute(
        """
        UPDATE payment_occurrences
        SET receipt_note = CASE
            WHEN receipt_note IS NULL OR receipt_note = '' THEN 'Ссылка на чек: ' || receipt_url
            ELSE receipt_note || E'\\nСсылка на чек: ' || receipt_url
        END
        WHERE receipt_url IS NOT NULL AND receipt_url <> ''
        """
    )
    op.drop_column("payment_occurrences", "receipt_url")

    op.add_column(
        "channel_subscriptions",
        sa.Column("scope", sa.String(16), nullable=False, server_default="mine"),
    )
    op.execute(
        """
        UPDATE channel_subscriptions AS sub
        SET scope = users.notify_scope
        FROM users
        WHERE users.id = sub.user_id AND users.notify_scope IN ('mine', 'department')
        """
    )
    op.create_check_constraint(
        "ck_channel_subscriptions_scope", "channel_subscriptions", "scope in ('mine', 'department')"
    )


def downgrade() -> None:
    op.drop_constraint("ck_channel_subscriptions_scope", "channel_subscriptions", type_="check")
    op.drop_column("channel_subscriptions", "scope")
    op.add_column("payment_occurrences", sa.Column("receipt_url", sa.Text(), nullable=True))
    op.drop_column("payment_occurrences", "receipt_uploaded_at")
    op.drop_column("payment_occurrences", "receipt_size")
    op.drop_column("payment_occurrences", "receipt_type")
    op.drop_column("payment_occurrences", "receipt_name")
    op.drop_column("payment_occurrences", "receipt_file")

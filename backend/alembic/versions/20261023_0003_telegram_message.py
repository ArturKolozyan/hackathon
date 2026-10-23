"""telegram message id on a period"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261023_0003"
down_revision: Union[str, None] = "20261023_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("payment_occurrences", sa.Column("telegram_chat_id", sa.String(length=64), nullable=True))
    op.add_column("payment_occurrences", sa.Column("telegram_message_id", sa.BigInteger(), nullable=True))
    op.add_column("payment_occurrences", sa.Column("telegram_fingerprint", sa.String(length=64), nullable=True))
    op.add_column(
        "payment_occurrences",
        sa.Column("telegram_reminded_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payment_occurrences", "telegram_reminded_at")
    op.drop_column("payment_occurrences", "telegram_fingerprint")
    op.drop_column("payment_occurrences", "telegram_message_id")
    op.drop_column("payment_occurrences", "telegram_chat_id")

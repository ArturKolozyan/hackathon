"""Кип только в веб-версии: у карточек ассистента больше нет сообщения в Telegram.

Revision ID: 20261024_0016
Revises: 20261024_0015
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261024_0016"
down_revision: Union[str, None] = "20261024_0015"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("assistant_actions", "telegram_message_id")
    op.drop_column("assistant_actions", "telegram_chat_id")


def downgrade() -> None:
    op.add_column("assistant_actions", sa.Column("telegram_chat_id", sa.String(length=64), nullable=True))
    op.add_column("assistant_actions", sa.Column("telegram_message_id", sa.BigInteger(), nullable=True))

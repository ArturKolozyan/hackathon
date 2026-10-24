"""приглашения людей и бессрочные ссылки привязки Telegram

users.invite_token — личная ссылка-приглашение: человек сам задаёт пароль.
telegram_link_tokens.expires_at может быть пустым: ссылка живёт до
использования или до новой ссылки.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261024_0011"
down_revision: Union[str, None] = "20261024_0010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("users", sa.Column("invite_token", sa.String(length=64), nullable=True))
    op.create_unique_constraint("uq_users_invite_token", "users", ["invite_token"])
    op.alter_column("telegram_link_tokens", "expires_at", existing_type=sa.DateTime(timezone=True), nullable=True)


def downgrade() -> None:
    op.execute("UPDATE telegram_link_tokens SET expires_at = now() WHERE expires_at IS NULL")
    op.alter_column("telegram_link_tokens", "expires_at", existing_type=sa.DateTime(timezone=True), nullable=False)
    op.drop_constraint("uq_users_invite_token", "users", type_="unique")
    op.drop_column("users", "invite_token")

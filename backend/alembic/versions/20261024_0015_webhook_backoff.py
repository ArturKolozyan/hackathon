"""вебхук отдела: пауза после неудач; архив молчит всегда

Сломанный адрес отдела больше не держит воркер: после неудачи отдел ждёт
1, 2, 4… минут (не больше 6 часов), одно событие пробуется не больше 5 раз.

Архивный платёж больше не шлёт ни напоминаний, ни просрочек: флаг remind_archived_overdue уходит.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261024_0015"
down_revision: Union[str, None] = "20261024_0014"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("teams", sa.Column("webhook_failures", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("teams", sa.Column("webhook_retry_at", sa.DateTime(timezone=True), nullable=True))
    op.drop_column("recurring_payments", "remind_archived_overdue")


def downgrade() -> None:
    op.add_column(
        "recurring_payments",
        sa.Column("remind_archived_overdue", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    op.drop_column("teams", "webhook_retry_at")
    op.drop_column("teams", "webhook_failures")

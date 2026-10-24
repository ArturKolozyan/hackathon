"""каденция по умолчанию: за 7 и 3 дня, просрочка каждый день

Строка организации, где остались старые значения по умолчанию,
переходит на новые. Значения, которые владелец менял сам, не трогаем.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20261024_0010"
down_revision: Union[str, None] = "20261024_0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column("organization_settings", "reminder_days", server_default="7,3")
    op.alter_column("organization_settings", "overdue_repeat_days", server_default="1")
    op.execute("UPDATE organization_settings SET reminder_days = '7,3' WHERE reminder_days = '7,3,0'")
    op.execute("UPDATE organization_settings SET overdue_repeat_days = 1 WHERE overdue_repeat_days = 3")


def downgrade() -> None:
    op.alter_column("organization_settings", "reminder_days", server_default="7,3,0")
    op.alter_column("organization_settings", "overdue_repeat_days", server_default="3")

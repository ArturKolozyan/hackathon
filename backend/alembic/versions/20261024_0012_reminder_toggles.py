"""напоминания тумблерами: за 7, 3 и 1 день и о просрочке каждый день

Свободный список дней и интервал повтора просрочки уходят.
reminder_days хранит включённые дни из 7, 3, 1. Старое значение по умолчанию
«7,3» становится «7,3,1»; своё значение владельца сужается до этих трёх дней.
Повтор просрочки становится тумблером overdue_reminders, включён.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "20261024_0012"
down_revision: Union[str, None] = "20261024_0011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _narrow(raw: str) -> str:
    if raw.replace(" ", "") in {"7,3", "7,3,0"}:
        return "7,3,1"
    days = set()
    for part in raw.replace(";", ",").split(","):
        part = part.strip()
        if part.isdigit() and int(part) in (7, 3, 1):
            days.add(int(part))
    return ",".join(str(day) for day in sorted(days, reverse=True))


def upgrade() -> None:
    op.add_column(
        "organization_settings",
        sa.Column("overdue_reminders", sa.Boolean(), nullable=False, server_default=sa.true()),
    )
    bind = op.get_bind()
    for row_id, raw in bind.execute(sa.text("SELECT id, reminder_days FROM organization_settings")).all():
        bind.execute(
            sa.text("UPDATE organization_settings SET reminder_days = :days WHERE id = :id"),
            {"days": _narrow(raw or ""), "id": row_id},
        )
    op.alter_column("organization_settings", "reminder_days", server_default="7,3,1")
    op.drop_constraint("ck_organization_settings_repeat", "organization_settings", type_="check")
    op.drop_column("organization_settings", "overdue_repeat_days")


def downgrade() -> None:
    op.add_column(
        "organization_settings",
        sa.Column("overdue_repeat_days", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_check_constraint("ck_organization_settings_repeat", "organization_settings", "overdue_repeat_days >= 1")
    op.execute("UPDATE organization_settings SET reminder_days = '7,3' WHERE reminder_days NOT LIKE '%3%' AND reminder_days NOT LIKE '%7%'")
    op.alter_column("organization_settings", "reminder_days", server_default="7,3")
    op.drop_column("organization_settings", "overdue_reminders")

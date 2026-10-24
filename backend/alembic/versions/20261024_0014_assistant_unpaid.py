"""ассистент: карточка «вернуть период в неоплаченные»

Новый вид черновика mark_unpaid. Исполняется тем же revoke, что и кнопка в панели.
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20261024_0014"
down_revision: Union[str, None] = "20261024_0013"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OLD = "kind in ('create_payment', 'update_payment', 'archive_payment', 'mark_paid')"
# 0006 создала имя с двойным префиксом (naming convention поверх полного имени). Его и держим.
NAME = "ck_assistant_actions_ck_assistant_actions_kind"
NEW = "kind in ('create_payment', 'update_payment', 'archive_payment', 'mark_paid', 'mark_unpaid')"


def _replace(check: str) -> None:
    op.execute(f"ALTER TABLE assistant_actions DROP CONSTRAINT IF EXISTS {NAME}")
    op.execute("ALTER TABLE assistant_actions DROP CONSTRAINT IF EXISTS ck_assistant_actions_kind")
    op.execute(f"ALTER TABLE assistant_actions ADD CONSTRAINT {NAME} CHECK ({check})")


def upgrade() -> None:
    _replace(NEW)


def downgrade() -> None:
    op.execute("DELETE FROM assistant_actions WHERE kind = 'mark_unpaid'")
    _replace(OLD)

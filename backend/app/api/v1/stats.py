from datetime import date
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.stats import StatsOut
from app.services.stats import build_stats

router = APIRouter(prefix="/stats", tags=["stats"])


@router.get("", response_model=StatsOut, summary="Статистика по всем отделам")
def stats(
    team_id: list[UUID] | None = Query(default=None),
    status: str | None = Query(default=None, pattern="^(overdue|due_soon|upcoming|paid)$"),
    currency: str | None = Query(default=None, pattern="^(RUB|USD|EUR)$"),
    month: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    responsible_id: UUID | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StatsOut:
    return build_stats(
        db,
        user,
        team_ids=team_id,
        status=status,
        currency=currency,
        month=month,
        date_from=date_from,
        date_to=date_to,
        responsible_id=responsible_id,
    )

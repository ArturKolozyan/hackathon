from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import require_admin
from app.models import AuditLog, User
from app.schemas.audit import AuditList, AuditOut

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("", response_model=AuditList, summary="Журнал действий")
def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> AuditList:
    total = int(db.scalar(select(func.count()).select_from(AuditLog)) or 0)
    rows = db.scalars(
        select(AuditLog)
        .options(joinedload(AuditLog.actor))
        .order_by(AuditLog.at.desc(), AuditLog.id.desc())
        .offset(offset)
        .limit(limit)
    ).unique().all()
    items = [
        AuditOut(
            id=row.id,
            at=row.at,
            actor_user_id=row.actor_user_id,
            actor_name=row.actor.full_name if row.actor is not None else None,
            actor_email=row.actor.email if row.actor is not None else None,
            action=row.action,
            entity_type=row.entity_type,
            entity_id=row.entity_id,
            meta=row.meta or {},
        )
        for row in rows
    ]
    return AuditList(items=items, total=total)

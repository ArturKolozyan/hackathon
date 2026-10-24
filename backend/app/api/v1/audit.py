from datetime import date, datetime, time, timedelta
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, func, or_, select, true
from sqlalchemy.orm import Session, joinedload

from app.core.database import get_db
from app.core.deps import require_manager
from app.models import AuditLog, Membership, User
from app.schemas.audit import AuditList, AuditOut
from app.services import time as clock
from app.services.access import TeamContext

router = APIRouter(prefix="/audit-logs", tags=["audit"])


def _team_filter(db: Session, ctx: TeamContext):
    if ctx.user.is_owner:
        return true()
    member_ids = list(db.scalars(select(Membership.user_id).where(Membership.team_id == ctx.team.id)).all())
    emails = []
    if member_ids:
        emails = list(db.scalars(select(User.email).where(User.id.in_(member_ids))).all())
    personal = []
    if member_ids:
        personal.append(AuditLog.actor_user_id.in_(member_ids))
    if emails:
        personal.append(AuditLog.meta["email"].astext.in_(emails))
    if not personal:
        return AuditLog.team_id == ctx.team.id
    return or_(AuditLog.team_id == ctx.team.id, and_(AuditLog.team_id.is_(None), or_(*personal)))


@router.get("", response_model=AuditList, summary="Журнал действий")
def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    date_from: date | None = Query(default=None, description="С этой даты включительно (часовой пояс организации)"),
    date_to: date | None = Query(default=None, description="По эту дату включительно"),
    actor_user_id: UUID | None = Query(default=None, description="Кто сделал"),
    action: list[str] | None = Query(default=None, description="Коды действий, например occurrence.paid"),
    ctx: TeamContext = Depends(require_manager),
    db: Session = Depends(get_db),
) -> AuditList:
    scope = _team_filter(db, ctx)
    zone = clock.zone()
    if date_from is not None:
        scope = and_(scope, AuditLog.at >= datetime.combine(date_from, time.min, tzinfo=zone))
    if date_to is not None:
        scope = and_(scope, AuditLog.at < datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=zone))
    if actor_user_id is not None:
        scope = and_(scope, AuditLog.actor_user_id == actor_user_id)
    if action:
        scope = and_(scope, AuditLog.action.in_(action))
    total = int(db.scalar(select(func.count()).select_from(AuditLog).where(scope)) or 0)
    rows = db.scalars(
        select(AuditLog)
        .where(scope)
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

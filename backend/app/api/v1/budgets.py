from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_team_context, require_manager
from app.models import Budget
from app.schemas.budget import BudgetCreate, BudgetOut, BudgetReport, BudgetUpdate
from app.services.access import TeamContext
from app.services.audit import record
from app.services.budgets import report
from app.services.templates import touch

router = APIRouter(prefix="/budgets", tags=["budgets"])


def _period_or_422(period_type: str, period_key: str) -> None:
    from app.schemas.budget import _period_key

    try:
        _period_key(period_type, period_key)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from None


@router.get("", response_model=list[BudgetOut], summary="Планы бюджета")
def list_budgets(
    period_type: str | None = Query(default=None, pattern="^(month|year)$"),
    period_key: str | None = None,
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> list[Budget]:
    stmt = select(Budget).where(Budget.team_id == ctx.team.id).order_by(Budget.period_type, Budget.period_key, Budget.currency)
    if period_type is not None:
        stmt = stmt.where(Budget.period_type == period_type)
    if period_key is not None:
        stmt = stmt.where(Budget.period_key == period_key)
    return list(db.scalars(stmt).all())


@router.get("/report", response_model=BudgetReport, summary="План, факт и ожидается")
def budget_report(
    period_type: str = Query(pattern="^(month|year)$"),
    period_key: str = Query(min_length=4, max_length=7),
    ctx: TeamContext = Depends(get_team_context),
    db: Session = Depends(get_db),
) -> BudgetReport:
    _period_or_422(period_type, period_key)
    from app.schemas.budget import _period_key

    normalized = _period_key(period_type, period_key)
    return report(db, period_type, normalized, ctx.team.id)


@router.post("", response_model=BudgetOut, status_code=201, summary="Задать план")
def create_budget(
    payload: BudgetCreate,
    ctx: TeamContext = Depends(require_manager),
    db: Session = Depends(get_db),
) -> Budget:
    row = Budget(
        team_id=ctx.team.id,
        period_type=payload.period_type,
        period_key=payload.period_key,
        currency=payload.currency,
        amount=payload.amount,
    )
    db.add(row)
    try:
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="План на эту валюту и период уже есть") from None
    record(
        db,
        action="budget.create",
        actor=ctx.user,
        entity_type="budget",
        entity_id=row.id,
        team_id=ctx.team.id,
        meta={
            "period_type": row.period_type,
            "period_key": row.period_key,
            "currency": row.currency,
            "amount": f"{row.amount:.2f}",
        },
    )
    db.commit()
    db.refresh(row)
    return row


def _budget(db: Session, budget_id: UUID, team_id: UUID) -> Budget:
    row = db.get(Budget, budget_id)
    if row is None or row.team_id != team_id:
        raise HTTPException(status_code=404, detail="План не найден")
    return row


@router.patch("/{budget_id}", response_model=BudgetOut, summary="Изменить план")
def update_budget(
    budget_id: UUID,
    payload: BudgetUpdate,
    ctx: TeamContext = Depends(require_manager),
    db: Session = Depends(get_db),
) -> Budget:
    row = _budget(db, budget_id, ctx.team.id)
    row.amount = payload.amount
    touch(row)
    record(
        db,
        action="budget.update",
        actor=ctx.user,
        entity_type="budget",
        entity_id=row.id,
        team_id=ctx.team.id,
        meta={
            "period_type": row.period_type,
            "period_key": row.period_key,
            "currency": row.currency,
            "amount": f"{row.amount:.2f}",
        },
    )
    db.commit()
    db.refresh(row)
    return row


@router.delete("/{budget_id}", status_code=204, summary="Удалить план")
def delete_budget(
    budget_id: UUID,
    ctx: TeamContext = Depends(require_manager),
    db: Session = Depends(get_db),
) -> None:
    row = _budget(db, budget_id, ctx.team.id)
    record(
        db,
        action="budget.delete",
        actor=ctx.user,
        entity_type="budget",
        entity_id=row.id,
        team_id=ctx.team.id,
        meta={"period_type": row.period_type, "period_key": row.period_key, "currency": row.currency},
    )
    db.delete(row)
    db.commit()

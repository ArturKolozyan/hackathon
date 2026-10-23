from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user, require_admin
from app.models import Budget, User
from app.schemas.budget import BudgetCreate, BudgetOut, BudgetReport, BudgetUpdate
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
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> list[Budget]:
    stmt = select(Budget).order_by(Budget.period_type, Budget.period_key, Budget.currency)
    if period_type is not None:
        stmt = stmt.where(Budget.period_type == period_type)
    if period_key is not None:
        stmt = stmt.where(Budget.period_key == period_key)
    return list(db.scalars(stmt).all())


@router.get("/report", response_model=BudgetReport, summary="План, факт и ожидается")
def budget_report(
    period_type: str = Query(pattern="^(month|year)$"),
    period_key: str = Query(min_length=4, max_length=7),
    _: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> BudgetReport:
    _period_or_422(period_type, period_key)
    from app.schemas.budget import _period_key

    normalized = _period_key(period_type, period_key)
    return report(db, period_type, normalized)


@router.post("", response_model=BudgetOut, status_code=201, summary="Задать план")
def create_budget(
    payload: BudgetCreate,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Budget:
    row = Budget(
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
        actor=actor,
        entity_type="budget",
        entity_id=row.id,
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


@router.patch("/{budget_id}", response_model=BudgetOut, summary="Изменить план")
def update_budget(
    budget_id: UUID,
    payload: BudgetUpdate,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> Budget:
    row = db.get(Budget, budget_id)
    if row is None:
        raise HTTPException(status_code=404, detail="План не найден")
    row.amount = payload.amount
    touch(row)
    record(
        db,
        action="budget.update",
        actor=actor,
        entity_type="budget",
        entity_id=row.id,
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
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> None:
    row = db.get(Budget, budget_id)
    if row is None:
        raise HTTPException(status_code=404, detail="План не найден")
    record(
        db,
        action="budget.delete",
        actor=actor,
        entity_type="budget",
        entity_id=row.id,
        meta={"period_type": row.period_type, "period_key": row.period_key, "currency": row.currency},
    )
    db.delete(row)
    db.commit()

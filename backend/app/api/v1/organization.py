from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.organization import OrganizationOut, OrganizationPatch
from app.services import time as clock
from app.services.audit import record
from app.services.org_settings import format_reminder_days, load_org, save_org

router = APIRouter(prefix="/organization", tags=["organization"])


def require_installation_owner(user: User = Depends(get_current_user)) -> User:
    if not user.is_owner:
        raise HTTPException(status_code=403, detail="Настройки организации доступны только владельцу")
    return user


def _out(config) -> OrganizationOut:
    return OrganizationOut(
        timezone=config.timezone,
        reminder_days=format_reminder_days(config.reminder_days),
        overdue_repeat_days=config.overdue_repeat_days,
        owner_overdue_copy=config.owner_overdue_copy,
    )


@router.get("", response_model=OrganizationOut, summary="Настройки организации")
def read_organization(
    user: User = Depends(require_installation_owner),
    db: Session = Depends(get_db),
) -> OrganizationOut:
    return _out(load_org(db))


@router.patch("", response_model=OrganizationOut, summary="Изменить настройки организации")
def update_organization(
    payload: OrganizationPatch,
    user: User = Depends(require_installation_owner),
    db: Session = Depends(get_db),
) -> OrganizationOut:
    before = load_org(db)
    data = payload.model_dump(exclude_unset=True)
    saved = save_org(db, **data)
    clock.bind_zone(saved.timezone)
    changes = {}
    if before.timezone != saved.timezone:
        changes["timezone"] = {"was": before.timezone, "became": saved.timezone}
    before_days = format_reminder_days(before.reminder_days)
    after_days = format_reminder_days(saved.reminder_days)
    if before_days != after_days:
        changes["reminder_days"] = {"was": before_days, "became": after_days}
    if before.overdue_repeat_days != saved.overdue_repeat_days:
        changes["overdue_repeat_days"] = {
            "was": str(before.overdue_repeat_days),
            "became": str(saved.overdue_repeat_days),
        }
    if before.owner_overdue_copy != saved.owner_overdue_copy:
        changes["owner_overdue_copy"] = {
            "was": str(before.owner_overdue_copy).lower(),
            "became": str(saved.owner_overdue_copy).lower(),
        }
    record(
        db,
        action="organization.update",
        actor=user,
        entity_type="organization",
        entity_id=None,
        meta={"changes": changes},
    )
    db.commit()
    return _out(saved)

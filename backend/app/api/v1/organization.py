from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.organization import OrganizationOut, OrganizationPatch
from app.services import time as clock
from app.services.audit import record
from app.services.org_settings import load_org, save_org

router = APIRouter(prefix="/organization", tags=["organization"])


def require_installation_owner(user: User = Depends(get_current_user)) -> User:
    if not user.is_owner:
        raise HTTPException(status_code=403, detail="Настройки организации доступны только владельцу")
    return user


DAY_FIELDS = {7: "remind_7_days", 3: "remind_3_days", 1: "remind_1_day"}


def _out(config) -> OrganizationOut:
    return OrganizationOut(
        timezone=config.timezone,
        **{field: day in config.reminder_days for day, field in DAY_FIELDS.items()},
        remind_overdue=config.overdue_reminders,
        owner_overdue_copy=config.owner_overdue_copy,
    )


def _onoff(value: bool) -> str:
    return "вкл" if value else "выкл"


def _flags(config) -> dict[str, bool]:
    shown = _out(config).model_dump()
    return {key: value for key, value in shown.items() if isinstance(value, bool)}


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
    days = None
    if any(field in data for field in DAY_FIELDS.values()):
        days = tuple(
            day
            for day, field in DAY_FIELDS.items()
            if (data[field] if data.get(field) is not None else day in before.reminder_days)
        )
    saved = save_org(
        db,
        timezone=data.get("timezone"),
        reminder_days=days,
        overdue_reminders=data.get("remind_overdue"),
        owner_overdue_copy=data.get("owner_overdue_copy"),
    )
    clock.bind_zone(saved.timezone)
    changes = {}
    if before.timezone != saved.timezone:
        changes["timezone"] = {"was": before.timezone, "became": saved.timezone}
    was, became = _flags(before), _flags(saved)
    for key in was:
        if was[key] != became[key]:
            changes[key] = {"was": _onoff(was[key]), "became": _onoff(became[key])}
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

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import require_admin
from app.core.security import hash_password
from app.models import User
from app.schemas.common import UserOut
from app.schemas.user import UserCreate, UserUpdate
from app.services.templates import active_admin_count, touch

router = APIRouter(prefix="/users", tags=["users"])


def _get_user(db: Session, user_id: UUID) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return user


def _guard_last_admin(db: Session, user: User, *, next_role: str | None, next_active: bool | None, actor: User) -> None:
    if actor.id == user.id and (next_active is False or (next_role is not None and next_role != "admin")):
        raise HTTPException(status_code=409, detail="Нельзя снять с себя права администратора")
    losing_admin = user.role == "admin" and user.is_active and (next_role == "user" or next_active is False)
    if losing_admin and active_admin_count(db) <= 1:
        raise HTTPException(status_code=409, detail="Нельзя отключить последнего админа")


@router.get("", response_model=list[UserOut], summary="Список людей")
def list_users(_: User = Depends(require_admin), db: Session = Depends(get_db)) -> list[User]:
    return list(db.scalars(select(User).order_by(User.full_name, User.email)).all())


@router.post("", response_model=UserOut, status_code=201, summary="Создать человека")
def create_user(payload: UserCreate, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> User:
    user = User(
        email=payload.email,
        full_name=payload.full_name,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=True,
    )
    db.add(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Пользователь с такой почтой уже есть") from None
    db.refresh(user)
    return user


@router.get("/{user_id}", response_model=UserOut, summary="Карточка человека")
def get_user(user_id: UUID, _: User = Depends(require_admin), db: Session = Depends(get_db)) -> User:
    return _get_user(db, user_id)


@router.patch("/{user_id}", response_model=UserOut, summary="Изменить человека")
def update_user(
    user_id: UUID,
    payload: UserUpdate,
    actor: User = Depends(require_admin),
    db: Session = Depends(get_db),
) -> User:
    user = _get_user(db, user_id)
    data = payload.model_dump(exclude_unset=True)
    _guard_last_admin(db, user, next_role=data.get("role"), next_active=data.get("is_active"), actor=actor)
    if "password" in data:
        password = data.pop("password")
        if password:
            user.password_hash = hash_password(password)
    for key, value in data.items():
        setattr(user, key, value)
    touch(user)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Пользователь с такой почтой уже есть") from None
    db.refresh(user)
    return user


@router.delete("/{user_id}", response_model=UserOut, summary="Отключить человека")
def deactivate_user(user_id: UUID, actor: User = Depends(require_admin), db: Session = Depends(get_db)) -> User:
    user = _get_user(db, user_id)
    _guard_last_admin(db, user, next_role=None, next_active=False, actor=actor)
    user.is_active = False
    touch(user)
    db.commit()
    db.refresh(user)
    return user

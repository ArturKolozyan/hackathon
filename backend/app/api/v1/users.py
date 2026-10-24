from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.deps import get_current_user
from app.models import User
from app.schemas.telegram import TelegramLinkOut
from app.schemas.user import InviteOut, UserCreate, UserOut, UserUpdate
from app.services.directory import (
    create_user,
    delete_user,
    invite_link,
    list_users,
    person_telegram_link,
    unlink_person_telegram,
    update_user,
)

router = APIRouter(prefix="/users", tags=["users"])


def _actor(user: User) -> User:
    if user.must_change_password:
        raise HTTPException(status_code=403, detail="Сначала смените пароль")
    return user


@router.get("", response_model=list[UserOut], summary="Люди организации")
def list_people(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> list[UserOut]:
    return list_users(db, _actor(user))


@router.post("", response_model=UserOut, status_code=201, summary="Добавить человека")
def create_person(
    payload: UserCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    return create_user(db, _actor(user), payload)


@router.get("/{id}", response_model=UserOut, summary="Карточка человека")
def get_person(id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    for row in list_users(db, _actor(user)):
        if row.id == id:
            return row
    raise HTTPException(status_code=404, detail="Пользователь не найден")


@router.patch("/{id}", response_model=UserOut, summary="Изменить человека")
def patch_person(
    id: UUID,
    payload: UserUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> UserOut:
    return update_user(db, _actor(user), id, payload)


@router.delete("/{id}", status_code=204, summary="Деактивировать человека")
def remove_person(id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> None:
    delete_user(db, _actor(user), id)


@router.get("/{id}/invite", response_model=InviteOut, summary="Текущая ссылка-приглашение")
def get_invite(id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> InviteOut:
    return invite_link(db, _actor(user), id)


@router.post("/{id}/invite", response_model=InviteOut, summary="Новая ссылка-приглашение, старая гаснет")
def renew_invite(id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> InviteOut:
    return invite_link(db, _actor(user), id, renew=True)


@router.get("/{id}/telegram-link", response_model=TelegramLinkOut, summary="Текущая ссылка привязки Telegram")
def get_telegram_link(id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TelegramLinkOut:
    return person_telegram_link(db, _actor(user), id)


@router.post("/{id}/telegram-link", response_model=TelegramLinkOut, summary="Новая ссылка привязки Telegram")
def renew_telegram_link(id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> TelegramLinkOut:
    return person_telegram_link(db, _actor(user), id, renew=True)


@router.delete("/{id}/telegram", response_model=UserOut, summary="Отвязать Telegram человека")
def unlink_telegram(id: UUID, user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> UserOut:
    return unlink_person_telegram(db, _actor(user), id)

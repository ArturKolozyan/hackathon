"""Общая сборка аккаунта с командой. Сид пустой базы больше не создаёт админа сам."""

from app.core.database import SessionLocal
from app.models import Team, User
from app.services.accounts import create_verified_user
from app.services.teams import add_member, create_team


def bootstrap_owner(
    email: str = "admin@invoice.local",
    password: str = "change-me",
    name: str = "Админ",
    team: str = "Команда",
) -> User:
    db = SessionLocal()
    try:
        user = create_verified_user(db, email=email, full_name=name, password=password)
        user.is_owner = True
        user.telegram_onboarding_done = True
        db.flush()
        create_team(db, user, team)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def add_person(
    db,
    *,
    email: str,
    password: str = "change-me-user",
    name: str = "Участник",
    role: str = "member",
    team: Team | None = None,
) -> User:
    from app.models import Membership

    from sqlalchemy import select

    user = create_verified_user(db, email=email, full_name=name, password=password)
    home = team or db.query(Team).one()
    actor = db.scalar(select(User).where(User.is_owner.is_(True)))
    if actor is None:
        raise RuntimeError("нет владельца")
    add_member(db, home, user, role, actor=actor)
    db.flush()
    return user

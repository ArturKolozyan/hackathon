from typing import Annotated
from uuid import UUID

from fastapi import Cookie, Depends, Header, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import user_from_token
from app.models import User
from app.services.access import TeamContext, require_role, resolve_team

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    db: Session = Depends(get_db),
    ik_session: Annotated[str | None, Cookie()] = None,
) -> User:
    token = credentials.credentials if credentials is not None else ik_session
    user = user_from_token(db, token)
    if user is None:
        raise HTTPException(status_code=401, detail="Нужна авторизация")
    return user


def read_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    ik_session: Annotated[str | None, Cookie()] = None,
) -> str | None:
    if credentials is not None:
        return credentials.credentials
    return ik_session


def get_team_context(
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    x_team_id: Annotated[UUID | None, Header(alias="X-Team-Id")] = None,
) -> TeamContext:
    ctx = resolve_team(db, user, x_team_id)
    if ctx is None:
        raise HTTPException(status_code=409, detail="Сначала создайте или вступите в команду")
    return ctx


def require_manager(ctx: TeamContext = Depends(get_team_context)) -> TeamContext:
    return require_role(ctx, "admin")


def require_owner(ctx: TeamContext = Depends(get_team_context)) -> TeamContext:
    return require_role(ctx, "owner")

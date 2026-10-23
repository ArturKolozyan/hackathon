from typing import Annotated

from fastapi import Cookie, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import user_from_token
from app.models import User

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


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Недостаточно прав")
    return user


def read_token(
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
    ik_session: Annotated[str | None, Cookie()] = None,
) -> str | None:
    if credentials is not None:
        return credentials.credentials
    return ik_session

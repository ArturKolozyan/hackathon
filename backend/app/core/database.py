import time

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db():
    from app.services.org_settings import load_org
    from app.services.time import bind_zone, reset_zone

    db = SessionLocal()
    token = None
    try:
        token = bind_zone(load_org(db).timezone)
        yield db
    finally:
        db.close()
        if token is not None:
            reset_zone(token)


def wait_for_db(timeout: int = 60) -> None:
    deadline = time.time() + timeout
    last_error: Exception | None = None
    while time.time() < deadline:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            return
        except Exception as exc:
            last_error = exc
            time.sleep(1)
    raise RuntimeError(f"База недоступна: {last_error}")


def wait_for_schema(timeout: int = 90) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with engine.connect() as connection:
                connection.execute(text("SELECT version_num FROM alembic_version"))
            return
        except Exception:
            time.sleep(1)
    raise RuntimeError("Миграции не применились")


def session_scope() -> Session:
    return SessionLocal()

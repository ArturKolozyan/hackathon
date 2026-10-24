import time

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()
engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _org_timezone() -> str | None:
    from sqlalchemy.exc import SQLAlchemyError

    from app.services.org_settings import load_org

    try:
        with SessionLocal() as db:
            return load_org(db).timezone
    except SQLAlchemyError:
        # База недоступна: health ответит сам, пояс по умолчанию — Москва.
        return None


class OrgZoneMiddleware:
    """Часовой пояс организации на весь запрос.

    Синхронные зависимости FastAPI работают в копии контекста, поэтому привязка внутри get_db
    до обработчика не доходила. Здесь пояс ставится до роутинга и виден всем потокам запроса.
    """

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        from starlette.concurrency import run_in_threadpool

        from app.services.time import bind_zone, reset_zone

        name = await run_in_threadpool(_org_timezone)
        token = bind_zone(name) if name else None
        try:
            await self.app(scope, receive, send)
        finally:
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

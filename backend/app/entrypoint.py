import logging
import sys

from alembic import command
from alembic.config import Config


def migrate() -> None:
    command.upgrade(Config("alembic.ini"), "head")


def serve() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    from app.core.database import wait_for_db
    from app.seed import seed

    wait_for_db()
    migrate()
    seed()
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, proxy_headers=True, forwarded_allow_ips="*")


def worker() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    from app.core.database import wait_for_db, wait_for_schema
    from app.worker import run

    wait_for_db()
    wait_for_schema()
    run()


def main() -> None:
    command_name = sys.argv[1] if len(sys.argv) > 1 else "serve"
    if command_name == "serve":
        serve()
    elif command_name == "worker":
        worker()
    else:
        raise SystemExit(f"unknown command: {command_name}")


if __name__ == "__main__":
    main()

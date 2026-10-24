import logging
import sys

from alembic import command
from alembic.config import Config


def migrate() -> None:
    command.upgrade(Config("alembic.ini"), "head")


def serve() -> None:
    from app.core.logging import configure_logging, install_redaction, quiet_http_loggers

    configure_logging()
    from app.core.database import wait_for_db
    from app.seed import seed

    wait_for_db()
    migrate()
    configure_logging(force=True)
    from app.services.org_settings import ensure_organization
    from app.services.owner import ensure_owner

    ensure_owner()
    ensure_organization()
    from app.integrations.email import smtp_host_configured

    # fileConfig в alembic выключает логгеры, созданные до миграции, в том числе httpx.
    quiet_http_loggers()
    install_redaction()
    if not smtp_host_configured():
        logging.getLogger("invoice_keeper.mail").warning(
            "SMTP не настроен: коды и приглашения пишутся в лог API (dev-режим)"
        )
    seed()
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        proxy_headers=True,
        forwarded_allow_ips="*",
        log_level=logging.getLevelName(logging.getLogger().level).lower(),
    )


def _wait_and(run) -> None:
    from app.core.logging import configure_logging

    configure_logging()
    from app.core.database import wait_for_db, wait_for_schema

    wait_for_db()
    wait_for_schema()
    run()


def worker() -> None:
    from app.worker import run

    _wait_and(run)


def bot() -> None:
    from app.bot_runner import run

    _wait_and(run)


def assistant() -> None:
    from app.core.logging import configure_logging

    configure_logging()
    from app.core.database import wait_for_db, wait_for_schema

    wait_for_db()
    wait_for_schema()
    import uvicorn

    from app.core.config import get_settings

    port = get_settings().assistant_port
    uvicorn.run(
        "app.assistant_main:app",
        host="0.0.0.0",
        port=port,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )


def main() -> None:
    command_name = sys.argv[1] if len(sys.argv) > 1 else "serve"
    commands = {"serve": serve, "worker": worker, "bot": bot, "assistant": assistant}
    fn = commands.get(command_name)
    if fn is None:
        raise SystemExit(f"unknown command: {command_name}")
    fn()


if __name__ == "__main__":
    main()

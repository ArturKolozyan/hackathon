"""Чистка будущих периодов, которые когда-то создал просмотр далёких месяцев или архивный платёж.

Удаляет неоплаченные нетронутые периоды (без оплаты, заметок, чека, ручной суммы и даты),
которых нынешнее расписание не держит в базе: дальше сегодня + горизонт и будущие сроки архивных платежей.
Идемпотентна. Сначала покажите, что уйдёт: --dry-run.

    docker compose exec api python -m app.prune_periods --dry-run
    docker compose exec api python -m app.prune_periods
"""

import argparse
import sys

from app.core.database import SessionLocal
from app.services import time as clock
from app.services.occurrences import prune_future
from app.services.org_settings import bind_org_zone


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.prune_periods", description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="только посчитать, ничего не удалять")
    args = parser.parse_args(argv)
    db = SessionLocal()
    token = bind_org_zone(db)
    try:
        removed = prune_future(db, clock.today())
        if args.dry_run:
            db.rollback()
            print(f"Будет удалено периодов: {removed}")
        else:
            db.commit()
            print(f"Удалено периодов: {removed}")
    finally:
        db.close()
        clock.reset_zone(token)
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Уборка тома чеков: файлы без периода и недописанные *.part старше часа.

    docker compose exec api python -m app.receipts_sweep
"""

import sys

from app.core.database import SessionLocal
from app.services.receipts import sweep


def main() -> int:
    db = SessionLocal()
    try:
        removed = sweep(db)
    finally:
        db.close()
    print(f"Удалено файлов: {removed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

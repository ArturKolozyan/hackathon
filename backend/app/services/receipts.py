"""Файлы чеков: проверка, хранение на томе и выдача.

Принимаем только то, чем обычно бывает чек: PDF и фото (JPEG, PNG, HEIC/HEIF, WebP).
Тип проверяется и по расширению, и по первым байтам файла. Имя в хранилище — случайное,
исходное имя хранится только в базе и уходит в Content-Disposition.
"""

import logging
import secrets
import time
from datetime import datetime
from pathlib import Path

from fastapi import HTTPException, UploadFile
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models import PaymentOccurrence

log = logging.getLogger(__name__)

# расширение -> семейство
EXTENSIONS = {
    "pdf": "pdf",
    "jpg": "jpeg",
    "jpeg": "jpeg",
    "png": "png",
    "heic": "heif",
    "heif": "heif",
    "webp": "webp",
}
CONTENT_TYPES = {
    "pdf": "application/pdf",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
}
STORED_EXT = {"pdf": "pdf", "jpeg": "jpg", "png": "png", "webp": "webp", "heif": "heic"}
HEIF_BRANDS = {b"heic", b"heix", b"hevc", b"hevx", b"heim", b"heis", b"hevm", b"hevs", b"mif1", b"msf1"}
ALLOWED_HINT = "Подойдёт PDF, JPG, PNG, HEIC или WebP"


def storage_dir() -> Path:
    path = Path(get_settings().receipts_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def max_bytes() -> int:
    return get_settings().receipt_max_mb * 1024 * 1024


def sniff(head: bytes) -> tuple[str, str] | None:
    """(семейство, content-type) по первым байтам или None."""
    if head.startswith(b"%PDF-"):
        return "pdf", CONTENT_TYPES["pdf"]
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg", CONTENT_TYPES["jpeg"]
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png", CONTENT_TYPES["png"]
    if len(head) >= 12 and head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "webp", CONTENT_TYPES["webp"]
    if len(head) >= 12 and head[4:8] == b"ftyp":
        brand = head[8:12]
        compatible = {head[i : i + 4] for i in range(16, min(len(head), 64) - 3, 4)}
        if brand in HEIF_BRANDS or compatible & HEIF_BRANDS:
            heic = brand in {b"heic", b"heix", b"hevc", b"hevx"} or bool(compatible & {b"heic", b"heix"})
            return "heif", "image/heic" if heic else "image/heif"
    return None


def clean_name(raw: str | None, family: str) -> str:
    name = (raw or "").replace("\\", "/").rsplit("/", 1)[-1]
    name = "".join(char for char in name if char.isprintable() and char not in '"<>|*?:').strip(" .")
    if not name:
        name = f"чек.{STORED_EXT[family]}"
    if len(name) > 200:
        stem, dot, ext = name.rpartition(".")
        name = (stem[: 190] + dot + ext) if dot else name[:200]
    return name


def _extension(name: str | None) -> str:
    if not name or "." not in name:
        return ""
    return name.rsplit(".", 1)[-1].strip().lower()


def read_upload(upload: UploadFile) -> tuple[bytes, str, str, str]:
    """Читает и проверяет файл. Возвращает (данные, семейство, content-type, имя)."""
    ext = _extension(upload.filename)
    family = EXTENSIONS.get(ext)
    if family is None:
        raise HTTPException(status_code=415, detail=f"Такой файл не подходит. {ALLOWED_HINT}")
    limit = max_bytes()
    data = upload.file.read(limit + 1)
    if not data:
        raise HTTPException(status_code=422, detail="Файл пустой")
    if len(data) > limit:
        raise HTTPException(
            status_code=413, detail=f"Файл больше {get_settings().receipt_max_mb} МБ. Сожмите фото или PDF"
        )
    sniffed = sniff(data[:64])
    if sniffed is None or sniffed[0] != family:
        raise HTTPException(
            status_code=415, detail=f"Содержимое файла не похоже на {ext.upper()}. {ALLOWED_HINT}"
        )
    return data, family, sniffed[1], clean_name(upload.filename, family)


def store(data: bytes, family: str) -> str:
    key = f"{secrets.token_hex(16)}.{STORED_EXT[family]}"
    target = storage_dir() / key
    tmp = target.with_suffix(target.suffix + ".part")
    tmp.write_bytes(data)
    tmp.replace(target)
    return key


def path_of(key: str) -> Path | None:
    if not key or "/" in key or "\\" in key or key.startswith("."):
        return None
    path = storage_dir() / key
    return path if path.is_file() else None


def discard(key: str | None) -> None:
    if not key:
        return
    path = path_of(key)
    if path is None:
        return
    try:
        path.unlink()
    except OSError:
        log.warning("receipt file %s was not removed", key)


def attach(row: PaymentOccurrence, key: str, name: str, content_type: str, size: int, at: datetime) -> str | None:
    """Пишет новый файл в период. Возвращает ключ старого файла: его удаляют после commit."""
    previous = row.receipt_file
    row.receipt_file = key
    row.receipt_name = name
    row.receipt_type = content_type
    row.receipt_size = size
    row.receipt_uploaded_at = at
    return previous


def detach(row: PaymentOccurrence) -> str | None:
    previous = row.receipt_file
    row.receipt_file = None
    row.receipt_name = None
    row.receipt_type = None
    row.receipt_size = None
    row.receipt_uploaded_at = None
    return previous


_PENDING = "receipt_discard"


def _flush_pending(session: Session) -> None:
    for key in session.info.pop(_PENDING, []):
        discard(key)


def _drop_pending(session: Session, _previous=None) -> None:
    session.info.pop(_PENDING, None)


def discard_after_commit(db: Session, key: str | None) -> None:
    """Файл удалённого периода стирается только после commit: откат оставит и строку, и файл."""
    if not key:
        return
    pending = db.info.setdefault(_PENDING, [])
    pending.append(key)
    if not event.contains(db, "after_commit", _flush_pending):
        event.listen(db, "after_commit", _flush_pending)
        event.listen(db, "after_soft_rollback", _drop_pending)


def sweep(db: Session, *, part_age_seconds: int = 3600) -> int:
    """Стирает файлы, на которые не ссылается ни один период, и недописанные *.part старше часа.

    Свежие файлы (моложе part_age_seconds) не трогает: их, возможно, прямо сейчас прикрепляют.
    """
    folder = storage_dir()
    used = {key for key in db.scalars(select(PaymentOccurrence.receipt_file).where(PaymentOccurrence.receipt_file.is_not(None)))}
    cutoff = time.time() - part_age_seconds
    removed = 0
    for path in folder.iterdir():
        if not path.is_file() or path.name in used:
            continue
        try:
            if path.stat().st_mtime > cutoff:
                continue
            path.unlink()
            removed += 1
        except OSError:
            log.warning("receipt file %s was not swept", path.name)
    if removed:
        log.info("receipts sweep removed %s files", removed)
    return removed

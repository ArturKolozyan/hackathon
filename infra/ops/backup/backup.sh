#!/bin/sh
# Один дамп базы в custom-формате Postgres (он уже сжат, это не .sql.gz).
# Пароль только в PGPASSWORD, не в argv: его видно в ps и в docker inspect и так,
# но строка команды в лог и в `ps` без окружения его не тащит.
set -eu

HERE=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$HERE/common.sh"

DIR=${BACKUP_DIR:-/backups}
KEEP=${BACKUP_KEEP:-7}

if [ -z "${PGPASSWORD:-}" ]; then
  echo "PGPASSWORD is empty, backup refuses to prompt" >&2
  exit 1
fi
if [ -z "${PGUSER:-${POSTGRES_USER:-}}" ]; then
  echo "PGUSER is empty" >&2
  exit 1
fi
if [ -z "${PGDATABASE:-${POSTGRES_DB:-}}" ]; then
  echo "PGDATABASE is empty" >&2
  exit 1
fi

mkdir -p "$DIR"
chmod 700 "$DIR"
rm -f "$DIR"/.partial-*.dump "$DIR"/.partial-receipts-*.tar.gz

stamp=$(msk_stamp)
final="$DIR/invoice-keeper-${stamp}-$$.dump"
tmp="$DIR/.partial-$$.dump"
trap 'rm -f "$tmp"' EXIT INT TERM

export PGHOST="${PGHOST:-db}"
export PGPORT="${PGPORT:-5432}"
export PGUSER="${PGUSER:-$POSTGRES_USER}"
export PGDATABASE="${PGDATABASE:-$POSTGRES_DB}"
export PGCONNECT_TIMEOUT="${PGCONNECT_TIMEOUT:-10}"

pg_dump --format=custom --compress=6 --no-owner --no-acl --file="$tmp"
mv "$tmp" "$final"
trap - EXIT INT TERM

rotate_dumps "$DIR" "$KEEP"
bytes=$(wc -c < "$final" | tr -d ' ')
echo "backup wrote $final ($bytes bytes), keep $KEEP"

# Файлы чеков: том receipts смонтирован только на чтение. Нет тома — пропускаем.
RECEIPTS=${RECEIPTS_SRC:-/receipts}
if [ -d "$RECEIPTS" ]; then
  archive="$DIR/receipts-${stamp}-$$.tar.gz"
  part="$DIR/.partial-receipts-$$.tar.gz"
  if tar -czf "$part" -C "$RECEIPTS" .; then
    mv "$part" "$archive"
    rotate_receipts "$DIR" "$KEEP"
    echo "backup wrote $archive ($(wc -c < "$archive" | tr -d ' ') bytes)"
  else
    rm -f "$part"
    echo "ERROR: receipts archive failed, database dump is kept" >&2
  fi
fi

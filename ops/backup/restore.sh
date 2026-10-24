#!/bin/sh
# Восстановление дампа custom-формата в живую базу.
# Останавливает писателей (api, worker, backup), не останавливает Postgres.
# Запуск из любого каталога: скрипт сам переходит в корень репозитория.
#
#   ops/backup/restore.sh --yes backups/invoice-keeper-YYYYMMDDTHHMMSS-<pid>.dump
set -eu

if [ "${1:-}" != "--yes" ] || [ -z "${2:-}" ]; then
  echo "usage: ops/backup/restore.sh --yes backups/invoice-keeper-YYYYMMDDTHHMMSS-<pid>.dump" >&2
  echo "Останавливает api, worker и backup, заменяет объекты базы, запускает их снова." >&2
  exit 2
fi

ROOT=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
cd "$ROOT"

file=$2
case "$file" in
  /*) ;;
  *) file="$ROOT/$file" ;;
esac
base=$(basename "$file")
case "$base" in
  invoice-keeper-*.dump) ;;
  *)
    echo "expected invoice-keeper-*.dump, got $base" >&2
    exit 2
    ;;
esac
if [ ! -f "$file" ]; then
  echo "no such file: $file" >&2
  exit 2
fi

COMPOSE="docker compose"

echo "stopping api worker bot backup"
# shellcheck disable=SC2086
$COMPOSE stop api worker bot backup

echo "terminating other sessions"
# shellcheck disable=SC2086
$COMPOSE exec -T db sh -c 'psql -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = current_database() AND pid <> pg_backend_pid();"'

# shellcheck disable=SC2086
cid=$($COMPOSE ps -q db)
if [ -z "$cid" ]; then
  echo "db container is not running" >&2
  exit 1
fi
docker cp "$file" "$cid:/tmp/rekeeper-restore.dump"

echo "restoring $base"
set +e
# shellcheck disable=SC2086
$COMPOSE exec -T db sh -c 'pg_restore --clean --if-exists --no-owner --no-acl --exit-on-error -U "$POSTGRES_USER" -d "$POSTGRES_DB" /tmp/rekeeper-restore.dump'
status=$?
set -e
# shellcheck disable=SC2086
$COMPOSE exec -T db rm -f /tmp/rekeeper-restore.dump

echo "starting api worker bot backup"
# shellcheck disable=SC2086
$COMPOSE start api worker bot backup

if [ "$status" -ne 0 ]; then
  echo "pg_restore failed ($status)" >&2
  exit "$status"
fi

port=$(grep -E '^HTTP_PORT=' .env 2>/dev/null | tail -n 1 | cut -d= -f2- || true)
port=${port:-8080}

echo "waiting for health"
i=0
while [ "$i" -lt 36 ]; do
  if curl -fsS --max-time 5 "http://127.0.0.1:${port}/healthz" >/dev/null; then
    echo "restored $base"
    exit 0
  fi
  i=$((i + 1))
  sleep 5
done
echo "dump restored, health http://127.0.0.1:${port}/healthz did not answer" >&2
exit 1

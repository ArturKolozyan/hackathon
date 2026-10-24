#!/bin/sh
# Восстановление дампа custom-формата в живую базу и файлов чеков того же снимка.
# Останавливает писателей (api, worker, backup), не останавливает Postgres.
# Архив receipts-<stamp>-*.tar.gz рядом с дампом распаковывается в том receipts,
# пока api остановлен. Архива нет — файлы чеков остаются как есть.
# Запуск из любого каталога: скрипт сам переходит в корень репозитория, путь к дампу — от корня.
#
#   infra/ops/backup/restore.sh --yes backups/invoice-keeper-YYYYMMDDTHHMMSS-<pid>.dump
set -eu

if [ "${1:-}" != "--yes" ] || [ -z "${2:-}" ]; then
  echo "usage: infra/ops/backup/restore.sh --yes backups/invoice-keeper-YYYYMMDDTHHMMSS-<pid>.dump" >&2
  echo "Останавливает api, worker и backup, заменяет объекты базы, запускает их снова." >&2
  exit 2
fi

ROOT=$(CDPATH= cd -- "$(dirname "$0")/../../.." && pwd)
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

COMPOSE="docker compose --env-file $ROOT/.env -f $ROOT/infra/docker-compose.yml"

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

# invoice-keeper-<stamp>-<pid>.dump -> receipts-<stamp>-*.tar.gz того же прогона.
stamp=${base#invoice-keeper-}
stamp=${stamp%%-*}
archive=$(ls -1t "$(dirname "$file")"/receipts-"$stamp"-*.tar.gz 2>/dev/null | head -n 1 || true)
if [ "$status" -eq 0 ] && [ -n "$archive" ]; then
  echo "restoring receipts from $(basename "$archive")"
  # Тот же образ и пользователь, что у api: права на файлы остаются как были.
  # shellcheck disable=SC2086
  if ! $COMPOSE run --rm --no-deps -T \
    -v "$(dirname "$archive")":/restore:ro \
    --entrypoint sh api -c \
    'find /data/receipts -mindepth 1 -delete && tar -xzf "/restore/$1" -C /data/receipts' sh "$(basename "$archive")"; then
    echo "ERROR: receipts archive was not restored, database is restored" >&2
    status=1
  fi
elif [ "$status" -eq 0 ]; then
  echo "no receipts archive for $stamp, receipt files are left as is" >&2
fi

echo "starting api worker bot backup"
# shellcheck disable=SC2086
$COMPOSE start api worker bot backup

if [ "$status" -ne 0 ]; then
  echo "restore failed ($status)" >&2
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

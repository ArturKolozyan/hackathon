#!/bin/sh
# Каждый день в 00:00 по Москве. Если контейнер в этот момент не работал —
# при старте снимает дамп, когда за текущие сутки файла ещё нет.
set -eu

HERE=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$HERE/common.sh"

echo "backup loop started, 00:00 Europe/Moscow (UTC+3), keep ${BACKUP_KEEP:-7}, dir ${BACKUP_DIR:-/backups}"

while true; do
  today=$(msk_day)
  if ! has_dump_for_day "$today"; then
    if ! /bin/sh "$HERE/backup.sh"; then
      echo "backup failed, retry in 60s" >&2
      sleep 60
      continue
    fi
  fi
  remain=$(seconds_until_msk_midnight)
  echo "next backup at 00:00 Europe/Moscow in ${remain}s"
  sleep "$remain"
done

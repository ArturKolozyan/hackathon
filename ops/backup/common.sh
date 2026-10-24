# Общие куски дампа. Europe/Moscow = UTC+3 круглый год, без перехода на летнее время.
# Считаем от UTC, а не от TZ контейнера: в postgres:16-alpine нет tzdata,
# а ставить пакеты при старте — лишняя сеть с VPS.

MSK_OFFSET=10800

utc_epoch() {
  date -u +%s
}

msk_stamp_from() {
  date -u -d "@$(($1 + MSK_OFFSET))" +%Y%m%dT%H%M%S
}

msk_stamp() {
  msk_stamp_from "$(utc_epoch)"
}

msk_day() {
  msk_stamp | cut -c1-8
}

# Секунды до следующей полуночи по Москве.
# Ровно в 00:00:00 результат 86400 — это уже следующие сутки, дамп за новый день
# снимается проверкой «файла за сегодня нет» до этого sleep.
seconds_until_msk_midnight() {
  utc=${1:-$(utc_epoch)}
  sod=$(((utc + MSK_OFFSET) % 86400))
  echo $((86400 - sod))
}

has_dump_for_day() {
  day=$1
  dir=${BACKUP_DIR:-/backups}
  found=0
  for path in "$dir"/invoice-keeper-"$day"T*.dump; do
    if [ -e "$path" ]; then
      found=1
      break
    fi
  done
  [ "$found" -eq 1 ]
}

rotate_dumps() {
  dir=$1
  keep=$2
  case "$keep" in
    ''|*[!0-9]*)
      echo "BACKUP_KEEP must be a positive integer" >&2
      return 1
      ;;
  esac
  if [ "$keep" -lt 1 ]; then
    echo "BACKUP_KEEP must be >= 1" >&2
    return 1
  fi
  found=0
  for path in "$dir"/invoice-keeper-*.dump; do
    if [ -e "$path" ]; then
      found=1
      break
    fi
  done
  if [ "$found" -eq 0 ]; then
    return 0
  fi
  n=0
  ls -1t "$dir"/invoice-keeper-*.dump | while IFS= read -r old; do
    n=$((n + 1))
    if [ "$n" -gt "$keep" ]; then
      rm -f "$old"
    fi
  done
}

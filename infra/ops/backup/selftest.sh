#!/bin/sh
# Проверка расписания и ротации без Postgres.
# Реальный pg_dump гоняется отдельно, когда BACKUP_ROUNDTRIP=1 и есть сервер.
set -eu

HERE=$(CDPATH= cd -- "$(dirname "$0")" && pwd)
# shellcheck disable=SC1091
. "$HERE/common.sh"

fail() {
  echo "selftest: $*" >&2
  exit 1
}

# 1792789200 = 2026-10-23 21:00:00 UTC = 2026-10-24 00:00:00 MSK
stamp=$(msk_stamp_from 1792789200)
[ "$stamp" = "20261024T000000" ] || fail "midnight stamp $stamp"
remain=$(seconds_until_msk_midnight 1792789200)
[ "$remain" -eq 86400 ] || fail "midnight remain $remain"

# 1792778400 = 2026-10-23 18:00:00 UTC = 2026-10-23 21:00:00 MSK
stamp=$(msk_stamp_from 1792778400)
[ "$stamp" = "20261023T210000" ] || fail "evening stamp $stamp"
remain=$(seconds_until_msk_midnight 1792778400)
[ "$remain" -eq 10800 ] || fail "evening remain $remain"

# 1792789199 = 2026-10-23 20:59:59 UTC = 2026-10-23 23:59:59 MSK
remain=$(seconds_until_msk_midnight 1792789199)
[ "$remain" -eq 1 ] || fail "one second remain $remain"

dir=$(mktemp -d)
trap 'rm -rf "$dir"' EXIT INT TERM
i=1
while [ "$i" -le 9 ]; do
  printf 'x\n' > "$dir/invoice-keeper-20261023T01000$i.dump"
  touch -d "@$((1700000000 + i))" "$dir/invoice-keeper-20261023T01000$i.dump"
  i=$((i + 1))
done
BACKUP_DIR=$dir
export BACKUP_DIR
rotate_dumps "$dir" 7
count=$(find "$dir" -name 'invoice-keeper-*.dump' | wc -l | tr -d ' ')
[ "$count" -eq 7 ] || fail "rotate count $count"
[ ! -e "$dir/invoice-keeper-20261023T010001.dump" ] || fail "oldest kept"
[ ! -e "$dir/invoice-keeper-20261023T010002.dump" ] || fail "second oldest kept"
[ -e "$dir/invoice-keeper-20261023T010009.dump" ] || fail "newest dropped"
if has_dump_for_day 20261023; then
  :
else
  fail "day probe"
fi
if has_dump_for_day 19990101; then
  fail "empty day matched"
fi

rm -f "$dir"/invoice-keeper-*.dump

# Архивы чеков: остаются последние KEEP.
i=1
while [ "$i" -le 9 ]; do
  printf 'x\n' > "$dir/receipts-20261023T01000$i-1.tar.gz"
  touch -d "@$((1700000000 + i))" "$dir/receipts-20261023T01000$i-1.tar.gz"
  i=$((i + 1))
done
rotate_receipts "$dir" 7
count=$(find "$dir" -name 'receipts-*.tar.gz' | wc -l | tr -d ' ')
[ "$count" -eq 7 ] || fail "receipts rotate count $count"
[ ! -e "$dir/receipts-20261023T010001-1.tar.gz" ] || fail "oldest receipts kept"
[ -e "$dir/receipts-20261023T010009-1.tar.gz" ] || fail "newest receipts dropped"
rm -f "$dir"/receipts-*.tar.gz

receipts=$(mktemp -d)
mkdir -p "$receipts/ab"
printf 'PDF\n' > "$receipts/ab/receipt.pdf"
bindir=$(mktemp -d)
cat > "$bindir/pg_dump" << 'EOF'
#!/bin/sh
out=""
prev=""
saw_format=0
saw_compress=0
for arg in "$@"; do
  case "$arg" in
    --file=*) out=${arg#--file=} ;;
    --format=custom) saw_format=1 ;;
    --compress=6) saw_compress=1 ;;
    *change-me*|*PGPASSWORD*)
      echo "password on argv" >&2
      exit 2
      ;;
  esac
  if [ "$prev" = "--file" ]; then
    out=$arg
  fi
  prev=$arg
done
[ -n "$out" ] || exit 3
[ "$saw_format" -eq 1 ] || exit 4
[ "$saw_compress" -eq 1 ] || exit 5
printf 'PGDMP-fake\n' > "$out"
EOF
chmod +x "$bindir/pg_dump"
trap 'rm -rf "$dir" "$bindir" "$receipts"' EXIT INT TERM

set +e
run_out=$(
  PATH="$bindir:$PATH" \
    BACKUP_DIR="$dir" \
    BACKUP_KEEP=2 \
    PGHOST=db \
    PGUSER=invoice \
    PGPASSWORD=change-me \
    PGDATABASE=invoice_keeper \
    RECEIPTS_SRC="$receipts" \
    /bin/sh "$HERE/backup.sh" 2>&1
)
run_code=$?
set -e
[ "$run_code" -eq 0 ] || fail "backup.sh exited $run_code: $run_out"
case "$run_out" in
  *"change-me"*) fail "password leaked to stdout" ;;
  *"backup wrote "*) ;;
  *) fail "backup output: $run_out" ;;
esac
# Второй и третий прогон в ту же секунду различаются pid-ом процесса — pid один.
# Ротация проверяется отдельными файлами выше. Здесь достаточно одного успешного дампа.
[ -e "$dir"/.partial-*.dump ] && fail "partial left behind"
count=$(find "$dir" -name 'invoice-keeper-*.dump' | wc -l | tr -d ' ')
[ "$count" -eq 1 ] || fail "fake dump count $count"

# Рядом с дампом — архив чеков с тем же штампом, читаемый tar.
dump=$(basename "$(find "$dir" -name 'invoice-keeper-*.dump')")
stamp=${dump#invoice-keeper-}
stamp=${stamp%.dump}
[ -e "$dir/receipts-$stamp.tar.gz" ] || fail "receipts archive missing for $stamp"
tar -tzf "$dir/receipts-$stamp.tar.gz" | grep -q 'ab/receipt.pdf' || fail "receipts archive unreadable"
[ -e "$dir"/.partial-receipts-*.tar.gz ] && fail "partial receipts left behind"

# Архив не собрался — дамп остаётся, в stderr ERROR.
cat > "$bindir/tar" << 'EOF'
#!/bin/sh
exit 2
EOF
chmod +x "$bindir/tar"
fail_out=$(
  PATH="$bindir:$PATH" BACKUP_DIR="$dir" PGUSER=invoice PGPASSWORD=change-me PGDATABASE=invoice_keeper \
    RECEIPTS_SRC="$receipts" /bin/sh "$HERE/backup.sh" 2>&1 >/dev/null
) || fail "backup.sh failed on archive error"
case "$fail_out" in
  *"ERROR: receipts archive failed"*) ;;
  *) fail "archive error not reported: $fail_out" ;;
esac
rm -f "$bindir/tar"

# Пустой пароль не должен зависнуть на приглашении.
if PATH="$bindir:$PATH" BACKUP_DIR="$dir" PGUSER=invoice PGDATABASE=invoice_keeper PGPASSWORD= \
  /bin/sh "$HERE/backup.sh" >/dev/null 2>&1; then
  fail "empty password was accepted"
fi

echo "selftest ok"

#!/bin/sh
# Смоук жюри на чистой машине: без ключей ассистента, затем с остановленным assistant.
# Запуск из любого каталога: скрипт сам переходит в корень репозитория, .env там же. Требует Docker.
set -eu
# В CI запускается через bash: упавшая команда и строка сразу видны в логе.
if [ -n "${BASH_VERSION:-}" ]; then
  set -E
  trap 'echo "smoke упал: строка $LINENO: $BASH_COMMAND" >&2' ERR
fi

root=$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)
cd "$root"
dc() { docker compose --env-file "$root/.env" -f "$root/infra/docker-compose.yml" "$@"; }

cp .env.example .env
# пример уже без ключей и без профиля ассистента
dc up --build -d

port=8080
if [ -f .env ]; then
  found=$(grep -E '^HTTP_PORT=' .env | tail -n 1 | cut -d= -f2- || true)
  if [ -n "${found:-}" ]; then
    port=$found
  fi
fi
base="http://127.0.0.1:${port}"

echo "ждём $base/api/v1/health"
ok=0
for _ in $(seq 1 60); do
  if curl -fsS --max-time 5 "$base/api/v1/health" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 5
done
if [ "$ok" != 1 ]; then
  echo "health не поднялся" >&2
  dc ps >&2 || true
  dc logs --tail=80 api web caddy >&2 || true
  exit 1
fi

login() {
  curl -fsS --max-time 10 -c /tmp/rekeeper.cj -H 'Content-Type: application/json' \
    -d "{\"email\":\"$1\",\"password\":\"$2\"}" \
    "$base/api/v1/auth/login" >/tmp/rekeeper-login.json
}

auth() {
  python3 -c 'import json; print(json.load(open("/tmp/rekeeper-login.json"))["access_token"])'
}

login admin@invoice.local change-me
token=$(auth)
hdr="Authorization: Bearer $token"

curl -fsS --max-time 10 -H "$hdr" "$base/api/v1/auth/me" | grep -q admin@invoice.local
curl -fsS --max-time 10 -H "$hdr" "$base/api/v1/recurring-payments" | grep -q 'Аренда офиса'
curl -fsS --max-time 10 -H "$hdr" "$base/api/v1/recurring-payments" | grep -q 'Подписка'
curl -fsS --max-time 10 -H "$hdr" "$base/api/v1/teams" >/tmp/rekeeper-teams.json
infra=$(python3 -c 'import json; rows=json.load(open("/tmp/rekeeper-teams.json")); print(next(row["id"] for row in rows if row["name"]=="Инфраструктура"))')
accounting=$(python3 -c 'import json; rows=json.load(open("/tmp/rekeeper-teams.json")); print(next(row["id"] for row in rows if row["name"]=="Бухгалтерия"))')
curl -fsS --max-time 10 -H "$hdr" -H "X-Team-Id: $infra" "$base/api/v1/recurring-payments" | grep -q 'Сервер'
# X-Team-Id запоминает активный отдел. Дальше явно просим Бухгалтерию.
curl -fsS --max-time 10 -H "$hdr" -H "X-Team-Id: $accounting" "$base/api/v1/recurring-payments" | grep -q 'Аренда офиса'
curl -fsS --max-time 10 -H "$hdr" "$base/api/v1/payment-occurrences" >/dev/null
curl -fsS --max-time 10 -H "$hdr" "$base/api/v1/payments/summary" >/dev/null
curl -fsS --max-time 10 -H "$hdr" "$base/api/v1/users" >/dev/null
curl -fsS -o /dev/null -w '%{http_code}\n' --max-time 10 "$base/api/v1/docs" | grep -qx 200
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 "$base/api/v1/users")
test "$code" = 401
curl -fsS --max-time 10 -H "$hdr" "$base/api/v1/features" >/tmp/rekeeper-features.json
python3 - <<'PY'
import json
data = json.load(open("/tmp/rekeeper-features.json"))
assert data["assistant"] is False
assert data["assistant_available"] is False
assert data["voice"] is False
PY

login ivan@invoice.local change-me-user
ivan=$(auth)
code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -H "Authorization: Bearer $ivan" \
  -H 'Content-Type: application/json' \
  -d '{"title":"Левый","amount":"10.00","currency":"RUB","next_payment_date":"2026-11-04","periodicity":"monthly"}' \
  "$base/api/v1/recurring-payments")
test "$code" = 403

dc restart
ok=0
for _ in $(seq 1 40); do
  if curl -fsS --max-time 5 "$base/api/v1/health" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 5
done
test "$ok" = 1
login admin@invoice.local change-me
token=$(auth)
curl -fsS --max-time 10 -H "Authorization: Bearer $token" -H "X-Team-Id: $accounting" "$base/api/v1/recurring-payments" | grep -q 'Аренда офиса'

dc stop bot
curl -fsS --max-time 10 -H "Authorization: Bearer $token" "$base/api/v1/payments/summary" >/dev/null
curl -fsS --max-time 10 -H "Authorization: Bearer $token" "$base/api/v1/users" >/dev/null
curl -fsS --max-time 10 -H "Authorization: Bearer $token" "$base/api/v1/payment-occurrences" >/dev/null

# Ключ есть, контейнер остановлен: фича включена, но недоступна. Кейс жив.
printf '\nGIGACHAT_AUTH_KEY=dummy-not-a-real-key\nCOMPOSE_PROFILES=assistant\n' >> .env
dc up -d --force-recreate --no-deps api
dc up -d assistant || true
dc stop assistant || true
ok=0
for _ in $(seq 1 40); do
  if curl -fsS --max-time 5 "$base/api/v1/health" >/dev/null 2>&1; then
    ok=1
    break
  fi
  sleep 3
done
test "$ok" = 1
login admin@invoice.local change-me
token=$(auth)
curl -fsS --max-time 10 -H "Authorization: Bearer $token" "$base/api/v1/features" >/tmp/rekeeper-features.json
python3 - <<'PY'
import json
data = json.load(open("/tmp/rekeeper-features.json"))
assert data["assistant"] is True, data
assert data["assistant_available"] is False, data
PY
curl -fsS --max-time 10 -H "Authorization: Bearer $token" -H "X-Team-Id: $accounting" "$base/api/v1/recurring-payments" | grep -q 'Аренда офиса'
curl -fsS --max-time 10 -H "Authorization: Bearer $token" "$base/api/v1/users" >/dev/null

dc down -v
echo "smoke ok"

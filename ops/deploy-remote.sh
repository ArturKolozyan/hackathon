#!/usr/bin/env bash
# Деплой на VPS. Workflow передаёт этот файл в `ssh … 'bash -s'`.
# Ошибка — строка «--- отчёт об ошибке ---», за ней docker compose ps и по 100 строк логов сервисов.
set -euo pipefail

cd /opt/invoice-keeper

report() {
  local code=$?
  [ "$code" = 0 ] && return
  echo "--- отчёт об ошибке ---"
  echo "deploy упал, код $code"
  docker compose ps -a 2>&1 || true
  for service in $(docker compose config --services 2>/dev/null); do
    echo "----- $service (последние 100)"
    docker compose logs --no-color --tail=100 "$service" 2>&1 || true
  done
}
trap report EXIT

git config --global --get-all safe.directory 2>/dev/null | grep -qx /opt/invoice-keeper ||
  git config --global --add safe.directory /opt/invoice-keeper
export GIT_TERMINAL_PROMPT=0

echo "== git pull"
git pull --ff-only origin main
git log -1 --oneline

echo "== docker compose up --build -d"
docker compose up --build -d

port=$(grep -E '^HTTP_PORT=' .env | tail -n 1 | cut -d= -f2- || true)
port=${port:-8080}
echo "== healthz http://127.0.0.1:${port}/healthz"
for _ in $(seq 1 36); do
  if curl -fsS --max-time 5 "http://127.0.0.1:${port}/healthz" >/dev/null 2>&1; then
    echo "healthz ok"
    docker compose ps
    exit 0
  fi
  sleep 5
done
echo "healthz не ответил за 3 минуты"
exit 1

#!/usr/bin/env bash
# Итог упавшего job в $GITHUB_STEP_SUMMARY одним блоком: какой шаг упал, ключевые строки
# его лога (ci-logs/<id шага>.log), для smoke — docker compose ps и логи сервисов.
# STEPS — toJSON(steps) из workflow.
set -uo pipefail

# Workflow запускает скрипт из корня репозитория, compose-файл лежит в infra/.
export COMPOSE_FILE
COMPOSE_FILE="$(CDPATH= cd -- "$(dirname "$0")/../.." && pwd)/docker-compose.yml"

MARK='--- отчёт об ошибке ---'
out=${GITHUB_STEP_SUMMARY:-/dev/stdout}
steps=${STEPS:-}
[ -n "$steps" ] || steps='{}'
failed=$(jq -r 'to_entries[] | select(.value.outcome == "failure") | .key' <<<"$steps" | tr '\n' ' ')
failed=${failed% }

show() {
  local log=$1
  if grep -qxF -- "$MARK" "$log"; then
    sed -n "/^$MARK\$/,\$p" "$log" | head -n 900
  elif grep -qE '^=+ (FAILURES|ERRORS) =+$' "$log"; then
    awk '/^=+ (FAILURES|ERRORS) =+$/ {on = 1} /short test summary info/ {on = 0} on' "$log" | head -n 150
    echo '…'
    sed -n '/short test summary info/,$p' "$log"
  else
    tail -n 120 "$log"
  fi
}

{
  echo "## ${GITHUB_JOB:-job}: упал шаг ${failed:-без id, см. лог запуска}"
  sha=${GITHUB_SHA:-}
  echo "commit ${sha:0:7} · ${GITHUB_SERVER_URL:-}/${GITHUB_REPOSITORY:-}/actions/runs/${GITHUB_RUN_ID:-}"
  for id in $failed; do
    log="ci-logs/$id.log"
    [ -s "$log" ] || continue
    echo
    echo "### $id"
    echo '```text'
    show "$log"
    echo '```'
  done
  if [[ " $failed " == *" smoke "* ]] && docker compose ps -aq 2>/dev/null | grep -q .; then
    echo
    echo '### docker compose ps'
    echo '```text'
    docker compose ps -a 2>&1
    echo '```'
    for service in $(docker compose ps -a --format '{{.Service}}' | sort -u); do
      echo "### logs $service (последние 100)"
      echo '```text'
      docker compose logs --no-color --tail=100 "$service" 2>&1
      echo '```'
    done
  fi
} >> "$out"

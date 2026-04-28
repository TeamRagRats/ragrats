#!/usr/bin/env bash
# Step 9 entry point. Runs orchestrator + watchdog as siblings; restarts the
# orchestrator (up to MAX_RESTARTS times) until the queue is drained. Holds a
# flock so two terminals cannot both run compose-up against vllm and recreate
# the running container (root cause of the 137-kill at 2026-04-26 01:10).

set -e
cd "$(dirname "$0")/../../.."

LOCK_FILE="/tmp/ragrats_llm_extraction.lock"
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
  echo "Another run_llm_extraction is already active (lock: $LOCK_FILE). Exiting."
  exit 1
fi

DB_USER="${RAGRATS_DB_USER:-teamragrats}"
DB_NAME="${RAGRATS_DB_NAME:-ragrats}"
DB_CONTAINER="${RAGRATS_DB_CONTAINER:-ragrats_database}"
COMPOSE_FILE="${VLLM_COMPOSE_FILE:-docker/vllm/docker-compose.yml}"
WATCHDOG="src/preprocessing/step_08_llm_extraction/watchdog.sh"
MAX_RESTARTS="${LLM_MAX_RESTARTS:-10}"

docker compose -f "$COMPOSE_FILE" up -d

cleanup() {
  [ -n "${WD_PID:-}" ] && kill "$WD_PID" 2>/dev/null || true
  [ -n "${PY_PID:-}" ] && kill "$PY_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

remaining_pending() {
  docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
    "SELECT COUNT(*)
     FROM llm_load_queue q
     LEFT JOIN llm_logging l ON l.sha256 = q.sha256
     WHERE l.status IS NULL
        OR l.status = 'error'
        OR (l.status = 'pending' AND l.started_at < now() - INTERVAL '30 minutes');" \
    2>/dev/null || echo 0
}

count=0
while [ "$count" -lt "$MAX_RESTARTS" ]; do
  python3 src/preprocessing/run_llm_extraction.py "$@" &
  PY_PID=$!
  bash "$WATCHDOG" "$PY_PID" &
  WD_PID=$!

  set +e
  wait "$PY_PID"
  exit_code=$?
  set -e

  kill "$WD_PID" 2>/dev/null || true
  wait "$WD_PID" 2>/dev/null || true
  unset WD_PID PY_PID

  docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -c \
    "UPDATE llm_logging SET status='error', error_message='watchdog_restart'
     WHERE status='pending';" >/dev/null 2>&1 || true

  remaining=$(remaining_pending)
  if [ "$remaining" = "0" ]; then
    echo "[wrapper] queue drained — done. (orchestrator exit=$exit_code)"
    exit 0
  fi

  count=$((count + 1))
  echo "[wrapper] orchestrator exited ($exit_code); ${remaining} rows still pending. Restart $count/$MAX_RESTARTS in 15s."
  sleep 15
done

echo "[wrapper] hit MAX_RESTARTS=$MAX_RESTARTS without draining queue. Aborting."
exit 1

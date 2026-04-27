#!/usr/bin/env bash
# Step 9 watchdog. Polls every POLL_S seconds; kills the orchestrator (PID
# passed as $1) if either:
#   1. The oldest pending row in llm_logging is older than STUCK_S (orchestrator
#      hung — vLLM unresponsive, request timing out, etc.).
#   2. curl /v1/models fails API_FAIL_LIMIT times in a row (vLLM dead/hung).
#
# On detect: restart vLLM container, kill the python orchestrator. The wrapper
# in run_llm_extraction.sh respawns the orchestrator after this script exits.
#
# Exits cleanly when the watched PID exits (orchestrator finished normally).

set -u

PY_PID="${1:?usage: watchdog.sh <python-pid>}"
POLL_S="${WATCHDOG_POLL_S:-20}"
STUCK_S="${WATCHDOG_STUCK_S:-600}"        # 10 min
API_FAIL_LIMIT="${WATCHDOG_API_FAIL_LIMIT:-15}"   # 15 * POLL_S = 5 min — survives cold model load
COMPOSE_FILE="${VLLM_COMPOSE_FILE:-docker/vllm/docker-compose.yml}"
DB_USER="${RAGRATS_DB_USER:-teamragrats}"
DB_NAME="${RAGRATS_DB_NAME:-ragrats}"
DB_CONTAINER="${RAGRATS_DB_CONTAINER:-ragrats_database}"
VLLM_URL="${LLM_BASE_URL:-http://localhost:8002/v1}"

api_fail=0

log() { echo "[watchdog $(date +%H:%M:%S)] $*"; }

stale_pending_seconds() {
  docker exec "$DB_CONTAINER" psql -U "$DB_USER" -d "$DB_NAME" -tAc \
    "SELECT COALESCE(EXTRACT(EPOCH FROM (now() - MIN(started_at))), 0)::int
     FROM llm_logging WHERE status='pending';" 2>/dev/null || echo 0
}

api_alive() {
  curl -s -m 5 -f "${VLLM_URL%/}/models" >/dev/null 2>&1
}

trigger_restart() {
  local reason="$1"
  log "STUCK — $reason. Restarting vLLM and killing orchestrator (pid=$PY_PID)."
  docker compose -f "$COMPOSE_FILE" restart >/dev/null 2>&1 || \
    log "warning: 'compose restart' failed; continuing"
  kill -TERM "$PY_PID" 2>/dev/null || true
  sleep 5
  kill -KILL "$PY_PID" 2>/dev/null || true
  exit 1
}

log "started — polling every ${POLL_S}s, stuck threshold ${STUCK_S}s, watching pid=$PY_PID"

while kill -0 "$PY_PID" 2>/dev/null; do
  sleep "$POLL_S"
  kill -0 "$PY_PID" 2>/dev/null || break

  stale=$(stale_pending_seconds)
  if [ "$stale" -gt "$STUCK_S" ]; then
    trigger_restart "oldest pending row is ${stale}s old (limit ${STUCK_S}s)"
  fi

  if api_alive; then
    api_fail=0
  else
    api_fail=$((api_fail + 1))
    log "vLLM API probe failed (${api_fail}/${API_FAIL_LIMIT})"
    if [ "$api_fail" -ge "$API_FAIL_LIMIT" ]; then
      trigger_restart "vLLM API unreachable ${api_fail} consecutive probes"
    fi
  fi
done

log "orchestrator pid=$PY_PID exited; watchdog stopping cleanly."
exit 0

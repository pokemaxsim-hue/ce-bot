#!/usr/bin/env bash
set -euo pipefail

DATA_DIR="${DATA_DIR:-/data}"

mkdir -p \
  "$DATA_DIR/anuncios_empleo/imagenes" \
  "$DATA_DIR/anuncios_empleo/mensajes" \
  "$DATA_DIR/resultados" \
  "$DATA_DIR/whatsapp_session"

echo "Iniciando final.js y watcher.py"
echo "DATA_DIR=$DATA_DIR"

start_supervisor() {
  local pid_var="$1"
  local name="$2"
  shift 2

  (
    child_pid=""

    terminate() {
      if [[ -n "$child_pid" ]]; then
        kill "$child_pid" 2>/dev/null || true
        wait "$child_pid" 2>/dev/null || true
      fi
      exit 0
    }

    trap terminate SIGINT SIGTERM

    while true; do
      echo "[start.sh] Launching $name"
      "$@" &
      child_pid=$!

      if wait "$child_pid"; then
        status=0
      else
        status=$?
      fi

      child_pid=""
      echo "[start.sh] $name exited with status $status. Restarting in 3s..."
      sleep 3
    done
  ) &

  printf -v "$pid_var" '%s' "$!"
}

cleanup() {
  kill "${FINAL_SUPERVISOR_PID:-}" "${WATCHER_SUPERVISOR_PID:-}" 2>/dev/null || true
  wait "${FINAL_SUPERVISOR_PID:-}" "${WATCHER_SUPERVISOR_PID:-}" 2>/dev/null || true
}

trap cleanup SIGINT SIGTERM EXIT

start_supervisor FINAL_SUPERVISOR_PID "final.js" node /app/final.js
start_supervisor WATCHER_SUPERVISOR_PID "watcher.py" python3 /app/watcher.py

wait -n "$FINAL_SUPERVISOR_PID" "$WATCHER_SUPERVISOR_PID"
STATUS=$?

cleanup
exit "$STATUS"

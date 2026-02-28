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

node /app/final.js &
NODE_PID=$!

python3 /app/watcher.py &
PY_PID=$!

cleanup() {
  kill "$NODE_PID" "$PY_PID" 2>/dev/null || true
}

trap cleanup SIGINT SIGTERM EXIT

wait -n "$NODE_PID" "$PY_PID"
STATUS=$?

cleanup
wait || true

exit "$STATUS"

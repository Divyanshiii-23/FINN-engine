#!/usr/bin/env bash
# Starts the FINN research engine (internal, 127.0.0.1) and the web app (public) in one container or VM.
# If either process exits, the script exits non-zero so the platform restarts the container.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PY="${FINN_PYTHON:-python3}"
ENGINE_PORT="${FINN_ENGINE_PORT:-8787}"
PORT="${PORT:-3000}"

# Data must exist before the web app serves it. The image builds it; a bare checkout builds it here.
if [ ! -f "$ROOT/apps/web/data/feed.json" ] || [ ! -d "$ROOT/data/research_fixtures" ] || [ "${FINN_REBUILD_FIXTURES:-0}" = "1" ]; then
  (cd "$ROOT/engine" && "$PY" -m finn_engine fixtures && "$PY" -m finn_engine research-fixtures)
fi

engine_args=(serve --host 127.0.0.1 --port "$ENGINE_PORT")
[ "${FINN_NO_LIVE:-0}" = "1" ] && engine_args+=(--no-live)
[ -n "${GEMINI_API_KEY:-}" ] && [ -n "${FINN_EXPLAIN_MODEL:-}" ] && engine_args+=(--llm)

(cd "$ROOT/engine" && exec "$PY" -m finn_engine "${engine_args[@]}") &
ENGINE_PID=$!

# Wait for the engine before taking traffic.
for _ in $(seq 1 30); do
  if "$PY" -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:$ENGINE_PORT/health', timeout=1)" 2>/dev/null; then break; fi
  sleep 1
done

export FINN_ENGINE_URL="http://127.0.0.1:$ENGINE_PORT"
(cd "$ROOT/apps/web" && exec node node_modules/next/dist/bin/next start -H "${HOST:-0.0.0.0}" -p "$PORT") &
WEB_PID=$!

trap 'kill "$ENGINE_PID" "$WEB_PID" 2>/dev/null || true' TERM INT
wait -n "$ENGINE_PID" "$WEB_PID"
status=$?
kill "$ENGINE_PID" "$WEB_PID" 2>/dev/null || true
exit "$status"

#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_PORT="${API_PORT:-8000}"
WEB_PORT="${WEB_PORT:-3000}"
RUN_DIR="$(mktemp -d "${TMPDIR:-/tmp}/villagecoverage-demo.XXXXXX")"
APP_DB="$RUN_DIR/app.sqlite"
API_PID=""
WEB_PID=""

for executable in uv npm curl; do
  if ! command -v "$executable" >/dev/null 2>&1; then
    printf 'VillageCoverage demo needs %s on PATH.\n' "$executable" >&2
    exit 1
  fi
done

if [[ ! -d "$ROOT/frontend/node_modules" ]]; then
  printf 'Installing frontend dependencies from the lockfile...\n'
  (cd "$ROOT/frontend" && npm ci)
fi

stop_children() {
  local status=$?
  trap - EXIT INT TERM
  if [[ -n "$WEB_PID" ]]; then
    kill -TERM "$WEB_PID" 2>/dev/null || true
    wait "$WEB_PID" 2>/dev/null || true
  fi
  if [[ -n "$API_PID" ]]; then
    kill -TERM "$API_PID" 2>/dev/null || true
    wait "$API_PID" 2>/dev/null || true
  fi
  printf '\nDemo app database retained at %s\n' "$APP_DB"
  printf 'Logs: %s/backend.log and %s/frontend.log\n' "$RUN_DIR" "$RUN_DIR"
  exit "$status"
}

trap stop_children EXIT INT TERM

(
  cd "$ROOT"
  export VILLAGECOVERAGE_APP_DB="$APP_DB"
  export FRONTEND_ORIGINS="http://127.0.0.1:$WEB_PORT,http://localhost:$WEB_PORT"
  export API_HOST=127.0.0.1
  export API_PORT="$API_PORT"
  export PYTHONUNBUFFERED=1
  uv run uvicorn backend.main:app --host 127.0.0.1 --port "$API_PORT"
) >"$RUN_DIR/backend.log" 2>&1 &
API_PID=$!

(
  cd "$ROOT/frontend"
  export NEXT_PUBLIC_API_BASE_URL="http://127.0.0.1:$API_PORT"
  export NEXT_TELEMETRY_DISABLED=1
  npm run dev -- --hostname 127.0.0.1 --port "$WEB_PORT"
) >"$RUN_DIR/frontend.log" 2>&1 &
WEB_PID=$!

printf 'VillageCoverage V5.2 RC1 demo is starting.\n'
printf 'Dashboard: http://127.0.0.1:%s\n' "$WEB_PORT"
printf 'API status: http://127.0.0.1:%s/api/regions\n' "$API_PORT"
printf 'This run uses a new temporary app database; the route cache is kept separately.\n'

api_ready=0
web_ready=0
for _ in {1..90}; do
  if [[ "$api_ready" -eq 0 ]] && curl --silent --fail "http://127.0.0.1:$API_PORT/api/regions" >/dev/null; then
    api_ready=1
  fi
  if [[ "$web_ready" -eq 0 ]] && curl --silent --fail "http://127.0.0.1:$WEB_PORT/" >/dev/null; then
    web_ready=1
  fi
  if [[ "$api_ready" -eq 1 && "$web_ready" -eq 1 ]]; then
    printf 'Backend and dashboard are ready. Press Ctrl-C to stop.\n'
    break
  fi
  if ! kill -0 "$API_PID" 2>/dev/null || ! kill -0 "$WEB_PID" 2>/dev/null; then
    printf 'A demo process exited early. Review the log paths printed on exit.\n' >&2
    exit 1
  fi
  sleep 1
done

if [[ "$api_ready" -ne 1 || "$web_ready" -ne 1 ]]; then
  printf 'Demo startup timed out. Review the log paths printed on exit.\n' >&2
  exit 1
fi

while kill -0 "$API_PID" 2>/dev/null && kill -0 "$WEB_PID" 2>/dev/null; do
  sleep 1
done

printf 'A demo process stopped.\n' >&2
exit 1

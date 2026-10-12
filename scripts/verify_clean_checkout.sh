#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_ID="$(date -u +%Y%m%dT%H%M%SZ)-$$"
PLAYWRIGHT_BROWSERS_PATH="${TMPDIR:-/tmp}/village-coverage-playwright-browsers-${RUN_ID}"
mkdir "$PLAYWRIGHT_BROWSERS_PATH"
export PLAYWRIGHT_BROWSERS_PATH
cd "$ROOT"

command -v uv >/dev/null
command -v npm >/dev/null

uv sync --frozen --group dev
(
  cd frontend
  npm ci
  npx playwright install chromium
)

uv run pytest -q
uv run ruff check backend scripts tests
uv run python -m compileall -q backend scripts tests
uv run python scripts/proposal_acceptance_check.py \
  --report-path "artifacts/qa/r1-r13-clean-checkout-${RUN_ID}.json"

(
  cd frontend
  npm run lint
  npm run typecheck
  NEXT_PUBLIC_API_BASE_URL="" \
    NEXT_PUBLIC_KAKAO_MAP_JS_KEY="" \
    NEXT_PUBLIC_PUBLIC_DEMO_MODE="true" \
    VILLAGE_COVERAGE_PUBLIC_DEMO_API_ORIGIN="http://127.0.0.1:8010" \
    npm run build
  npm run test:e2e:all
  npm run test:e2e:ui-regression
)

printf 'Clean-checkout verification completed. R1-R13 report: artifacts/qa/r1-r13-clean-checkout-%s.json\n' "$RUN_ID"

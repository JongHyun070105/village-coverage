# Clean Checkout Test Guide

This guide runs the repository's automated checks without a developer's SQLite files, route cache, API keys, or `node_modules`.

## Requirements

- Python `>=3.12,<3.15` (CI uses Python 3.12)
- Node.js `>=20.9` (CI and Render use Node 22)
- `uv` 0.11.7 is the version pinned by CI; another compatible `uv` may work
- npm, provided with Node.js
- Chromium system libraries required by Playwright on Linux

The tracked dependency locks are `uv.lock` and `frontend/package-lock.json`. No live Kakao, public-data, Gemini, KOSIS, Render, or other API key is needed for these tests.

## Install and run

From a fresh clone:

```sh
uv sync --frozen --group dev
cd frontend
npm ci
npx playwright install chromium
cd ..
scripts/verify_clean_checkout.sh
```

On Linux CI, install Playwright's operating-system packages with `npx playwright install --with-deps chromium`. The repository script installs the browser binary but does not invoke `sudo` or modify system packages.

The verification script installs Chromium into a new run-specific temporary browser directory rather than relying on a developer's Playwright browser cache. It leaves this generated directory in place for inspection. It runs:

1. `uv run pytest -q`
2. Ruff and Python bytecode compilation
3. The mapped R1–R13 acceptance suite, saved to a unique artifact path
4. Frontend lint, typecheck, and production build
5. Standard and Public Demo Playwright suites

The pytest bootstrap creates deterministic route rows in a new SQLite database below the system temporary directory. Rows carry routing version `test-fixture-synthetic-v1` and source `TEST_FIXTURE / SYNTHETIC; NOT A ROAD ROUTE`. Application state uses per-test temporary DBs. The bootstrap never reads or writes `data/village_coverage.sqlite`; it creates files exclusively and does not replace existing paths. The standard Playwright config also creates unique temporary app and route DB names. Public Demo keeps its distinct, explicit straight-line estimate mode.

## Individual checks

```sh
uv run pytest -q
uv run ruff check .
uv run python -m compileall -q backend scripts tests
uv run python scripts/proposal_acceptance_check.py --report-path artifacts/qa/r1-r13-local.json
cd frontend
npm run lint
npm run typecheck
npm run build
npm run test:e2e:all
```

For a browser failure, inspect the Playwright trace under the configured temporary output directory. Do not copy a local production route cache into the checkout. A production/Pilot route miss should continue to return `ROUTE_UNAVAILABLE`; the test-only fixture flag is explicit and does not enable a straight-line fallback.

## Troubleshooting

- Check `python --version`, `uv --version`, `node --version`, and `npm --version` against the requirements above.
- Re-run `uv sync --frozen --group dev` and `npm ci` if a lockfile install was interrupted.
- On Linux, install Chromium system dependencies using the Playwright command above.
- If route fixture preparation fails, verify `data/demo.json` exists and that `VILLAGE_COVERAGE_DB` points below the system temporary directory. Never point it at the developer's route cache.
- If a test needs a real road, the missing route is a test setup or product-input issue. Do not label synthetic fixture data as Kakao road data or relax the `ROUTE_UNAVAILABLE` assertion.
- The full browser suite starts local FastAPI and Next.js servers on `127.0.0.1:8010` and `127.0.0.1:3010`; make sure these ports are free.

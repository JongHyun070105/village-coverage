# Render API 502 incident report

**Status: `RECOVERED_VERIFIED`**  
**Verified code SHA:** `7b696499c6c4b59fd613866faa89c1afe8934398`  
**Service:** `villagecoverage-public-demo-api` (Render Free)

## Finding

Render reported an HTTP 503 health-check failure while the API process was running. On the deployed code, every cookie-less `GET /health` and `GET /api/health` passed through the public-demo session middleware. Each probe therefore allocated a visitor session in SQLite. The store caps active sessions at 256, and exhaustion returns HTTP 503. Render's health probes do not retain the response body, so the production session count and specific 503 body are unavailable. The deployed timing, application logs, and exact local reproduction strongly support session exhaustion as the production cause; the mechanism itself is confirmed.

Health probes now bypass visitor-session allocation and SQLite session writes. Visitor routes retain the existing 256-session cap, 30-minute idle expiry, per-session and global request limits, and solver gate.

## Incident and verification timeline

All times are UTC unless marked KST.

| Time | Evidence |
|---|---|
| 2026-10-09 23:09 KST | Prior API deployment `32de2a38e5a9444d80d3bb497aaad9bf09c7fbbf` became live. |
| 2026-10-09 23:27 KST | Render Events: instance `gvzrf` failed its HTTP health check with status 503 while running application code. |
| 2026-10-09 23:31:14–23:39:04 KST | Render application logs repeatedly recorded `GET /health` with status 503. A 200 appeared at 23:39:40, followed by a 503 at 23:40:04. |
| 2026-10-09 23:39 KST | Render Events reported service recovery. |
| 2026-10-10 12:15:27 UTC | Initial low-frequency probes: `/health`, `/api/health`, and web `/` each returned 200. |
| 2026-10-10 12:33:19 UTC | Later probes to the same three URLs timed out after about 7 seconds (`curl` exit 28, no HTTP response). This was recorded as a timeout, not a 502. |
| 2026-10-10 12:35:33 UTC | Pre-deploy `/health` returned 200 in 0.372 seconds. |
| 2026-10-10 12:49:29 UTC | Render auto-deploy began for `7b696499c6c4b59fd613866faa89c1afe8934398`; build succeeded. |
| 2026-10-10 12:52:41 UTC | Render marked deploy `dep-db538mbrjlhs73acg680` successful and Live. |
| 2026-10-10 12:52:32 UTC | Public `/health` returned 200 in 33.604 seconds during Free-instance startup. |
| 2026-10-10 12:52:55 UTC | Public `/api/health` returned 200 in 0.244 seconds. |
| 2026-10-10 12:52:58 UTC | Public web `/` returned 200 in 0.272 seconds. The live page rendered its region list and plan dashboard in a browser. |
| 2026-10-10 12:53:38–12:54:38 UTC | Low-volume live flow passed: two separate visitor sessions, two plans, ownership check, provider decline, replan, approval, Decision Memo, CSV, PDF, and private API 404. |
| 2026-10-10 12:55:39 UTC | Follow-up `/health` returned 200 in 0.393 seconds. |

No post-deploy 502 was observed in these checks. Public high-concurrency load testing was not performed.

## Render logs and resource findings

- The dashboard confirmed the failed health check and later recovery. Application access logs showed the health response codes and Uvicorn request records, but not response bodies or the session-table count.
- Searches over the available application-log window found no `Traceback`, `OperationalError`, `database is locked`, disk-full, OOM, SIGKILL, or worker-crash entries. This is limited to the logs exposed by Render; it does not prove those conditions never occurred.
- The active start command uses Uvicorn with one worker and Render's `$PORT`. The failed health checks were logged as application responses, not process exits. No exit code was available in the dashboard evidence.
- Render Free showed limits of 512 MiB memory and 0.15 CPU. Actual memory/CPU utilization graphs were not available on this plan. Persistent disks are not supported on Free. No paid upgrade or resource purchase was made.
- Public-demo settings in code: 256 active sessions; 30-minute idle expiry; 20 plans per session; 64 MiB demo DB cap; 20 requests/minute per session; 120 requests/minute global; solver 4 active / 6 queued with 15-second queue wait.

### Hypothesis disposition

| Hypothesis | Evidence and reproduction | Result |
|---|---|---|
| Solver CPU/memory pressure | The health route does not invoke the solver. A full-session local reproduction returned 503 on the original health path without running solver work. Render usage graphs were unavailable. | `UNKNOWN` as a general contributor; not needed to reproduce the observed health-check 503. |
| 4 active / 6 queued solver capacity | The health path is outside the solver gate; no solver queue evidence was present in the incident logs. | `REJECTED` as the direct health-check failure mechanism. Resource contribution cannot be measured from Free metrics. |
| SQLite write contention | Health probes did write session rows on the original code. No lock error was exposed; local full-capacity reproduction reproduced the same 503 without a lock. | `UNKNOWN`; not required to explain the reproduced failure. |
| Session creation / validation / cleanup | Original middleware allocated a session for each cookie-less health probe. At 256 active rows, the original code returned 503. Render's 503 timeline aligns with this bounded capacity. | `CONFIRMED` mechanism; exact production row count and response body were not retained. |
| DB size / WAL | Code applies a 64 MiB cap. No disk-full or SQLite diagnostic appeared; Render Free has no persistent disk and exposes no usage graph. | `UNKNOWN` for production DB/WAL state; not reproduced locally. |
| Restart / temporary DB initialization conflict | Startup code initializes without unlinking/resetting the existing DB. A local restart on the same temporary filesystem preserved unexpired visitor data. Render Free's ephemeral filesystem can reset data on instance replacement. | `REJECTED` as an application startup-reset conflict; ephemeral-state loss remains expected platform behavior. |
| FastAPI exit / port | Uvicorn was configured for `$PORT`; Render logged HTTP 503 responses while application code was running. | `REJECTED` as the direct cause of the observed 503. |
| Render infrastructure incident | No infrastructure incident evidence was available; the API emitted application-level 503 responses and the session-capacity failure was reproducible locally. | `UNKNOWN` as an additional contributor. |

## Isolated local reproduction

The production-mode reproduction used the public-demo flags, a single local Uvicorn worker, a separate temporary filesystem and fresh app/route databases. It did not use the developer DB. The only local transport override was `PUBLIC_DEMO_COOKIE_SECURE=false` for HTTP loopback.

- Health start-up returned 200 without a session cookie or session row.
- Visitors A and B received distinct cookies. Both generated plans; B could not read A's plan (404). A's provider decline did not mark B's plan declined. A's replan returned version 2; B submitted and completed demo approval.
- Decision Memo returned 200 JSON; CSV returned 200 `text/csv`; PDF returned 200 `application/pdf`; private `/docs` returned 404.
- With 256 active session rows prefilled, the original code's health probe returned 503. With the fix, more than 300 `/health` probes and `/api/health` remained 200 with no cookie or session-row growth. A new visitor still received `DEMO_SESSION_CAPACITY` 503, preserving the limit.
- After expiring A's session and restarting on the same temporary filesystem, B's plan remained readable; A's expired session was replaced and its history was empty.
- Two-visitor SQLite storage measured 1,916,928 bytes at start and 2,121,728 bytes after flows; after restart, app plus route DBs measured 2,166,784 bytes. No WAL/SHM bytes were present at the initial post-flow capture. These are local fixture measurements, not Render DB size.
- `vmmap` physical footprint was 98.6 MiB before plan flows, 151.0 MiB after flows, and 89.8 MiB after restart. This is whole-process usage during the workflow, not per-session memory.

## Changes and regression

- `backend/public_demo.py`: skip session issuance for `/health` and `/api/health`; health responses still pass through the public-demo allowlist and existing global rate-limit behavior.
- `tests/test_public_demo_sessions.py`: add a regression that fills the 256-session store, verifies health remains 200 without cookies or new rows, and verifies normal visitor capacity remains enforced.
- `frontend/e2e/public-demo.spec.ts`: wait for the new plan ID to reach the URL after replan before reading the version-2 plan. The first E2E run exposed a timing race where the test read the old ID; the trace showed the replan response had a new ID and excluded the declined round. This test-only wait made the required flow deterministic.

## Regression results

- Backend: `582 passed, 1 skipped` (one new health-capacity regression; four existing deprecation warnings).
- Ruff: passed.
- `compileall`: passed.
- Frontend lint, typecheck, and production build: passed.
- Playwright: `17 passed` (12 standard + 5 public-demo) on the full rerun.
- R1–R13 acceptance: `112/112 passed`.
- Targeted public-demo session/concurrency tests: `7 passed`.
- Rate-limit, session expiry, A/B ownership, provider-state isolation, approval, Decision Memo, CSV/PDF, and private-route blocking were covered by local tests and/or the isolated/live flows above. Public load testing was deliberately not run.

## Deployment and Git

- Hotfix branch: `hotfix/render-api-502-20261010`.
- Commit `7b696499c6c4b59fd613866faa89c1afe8934398` was created from the expected `origin/main` `cc25a330061e36fd6b8dbab64574cb04f6203f82`.
- Render deployment branch `submission/public-demo-deploy` was at `32de2a38e5a9444d80d3bb497aaad9bf09c7fbbf`; it was an ancestor of the hotfix and was fast-forwarded. Render deployed the hotfix successfully.
- After live verification, `origin/main` was fast-forwarded to the verified hotfix SHA. At verification, `origin/main`, `origin/submission/public-demo-deploy`, and `origin/hotfix/render-api-502-20261010` all resolved to `7b696499c6c4b59fd613866faa89c1afe8934398`.
- The 14 pre-existing remote branches were checked; all are included in main after integration. The new hotfix branch makes 15 remote branches. No branch was deleted.
- `docs/GIT_BRANCH_HISTORY.md` and `artifacts/git/branch_cleanup_manifest.json` were not present in the bound checkout. No branch-cleanup records were altered and no cleanup was performed.

## Recurrence prevention and limits

Health probes are now session-free, so their cadence cannot consume visitor capacity or create SQLite session writes. Keep the active-session and request limits unchanged; use Render runtime logs and available metrics if the same health-check failure returns. Render Free does not expose utilization graphs or persistent disk, so exact production memory, CPU, DB size, WAL size, and session count remain unverified. The incident status is `RECOVERED_VERIFIED`; the specific production 503 body was not retained, so attribution is based on status/timing evidence plus the exact local reproduction.

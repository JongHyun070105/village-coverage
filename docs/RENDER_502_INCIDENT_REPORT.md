# Render API 502 incident report

**Incident recovery at deployment verification:** `RECOVERED_VERIFIED`<br>
**Latest live health status (2026-10-11):** `NOT_VERIFIABLE` (three read-only requests timed out with HTTP 000)<br>
**Last confirmed deployed code SHA:** `7b696499c6c4b59fd613866faa89c1afe8934398`<br>
**Incident fix commit, integrated into main:** `e6cff560d3f58da5e36f91e9b8d095f929bb4db2`
**Service:** `villagecoverage-public-demo-api` (Render Free)

## Finding

Render reported an HTTP 503 health-check failure while the API process was running. On the deployed code, cookie-less `GET /health` and `GET /api/health` passed through public-demo session issuance. A probe without a retained cookie could allocate a SQLite visitor session; once the 256-session cap was full, the middleware returned HTTP 503. Render did not retain the response body or session-table count, so the exact production 503 subtype is unavailable. The health logs, active demo traffic, timing, and exact local reproduction strongly support session-capacity exhaustion as the production cause; the code mechanism is confirmed, while the exact production row count is not.

Health probes now bypass visitor-session allocation and SQLite session writes. Health routes remain public-demo allowlisted but bypass visitor-session issuance, operation rate limiting, and the solver gate. Visitor operations retain the existing 256-session cap, 30-minute idle expiry, per-session/global limits, and solver gate. The observed incident was HTTP 503; no Render log in the inspected window showed an HTTP 502.

## Incident and verification timeline

All times are UTC unless marked KST.

| Time | Evidence |
|---|---|
| 2026-10-09 23:09 KST | Prior API deployment `32de2a38e5a9444d80d3bb497aaad9bf09c7fbbf` became live. |
| 2026-10-09 23:26:35 KST | First observed `GET /health` 503 in the expanded Render application-log window. Normal demo traffic was also completing requests, including a plan create at 23:26:37 and provider participation update at 23:26:42. |
| 2026-10-09 23:27 KST | Render Events: instance `gvzrf` failed its HTTP health check with status 503 while running application code. |
| 2026-10-09 23:27:35–23:27:57 KST | Logs show graceful Uvicorn shutdown (`Finished server process [63]`), Render reissued the configured start command at 23:27:43, and a new process completed startup at 23:27:57 on `$PORT` (`10000`). The dashboard did not expose an exit code or signal. Subsequent health checks still returned 503. |
| 2026-10-09 23:26:35–23:39:04 KST | Render application logs repeatedly recorded `GET /health` with status 503. The first observed 200 after the sustained failures was at 23:39:15. |
| 2026-10-09 23:39 KST | Render Events reported service recovery. |
| 2026-10-09 23:40:04–23:40:05 KST | One isolated `/health` 503 was followed by 200 one second later. Logs then showed 200 responses through 23:41:40 and graceful shutdown at 23:41:42. |
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
| 2026-10-11 10:00:03–10:00:10 UTC | One low-frequency check each: `/health` 200 (0.244s), `/api/health` 200 (0.251s), web `/` 200 (6.276s). |
| 2026-10-11 10:14:31–10:14:32 UTC | Second low-frequency check: `/health` 200 (0.520s), `/api/health` 200 (0.480s), web `/` 200 (0.390s). |

No 502 was observed in these checks; the historical Render failure was 503. The first sweep in this audit produced no endpoint-level result before the tool timeout, so it is not counted as a status observation. Public high-concurrency load testing was not performed.

## Render logs and resource findings

- The dashboard confirmed the failed health check and later recovery. Application access logs showed the health response codes and Uvicorn request records, but not response bodies or the session-table count.
- Searches over the available application-log window found no `Traceback`, `OperationalError`, `database is locked`, disk-full, OOM, SIGKILL, or worker-crash entries. This is limited to the logs exposed by Render; it does not prove those conditions never occurred.
- The active start command uses Uvicorn with one worker and Render's `$PORT`. The failed health checks were logged as application responses while the process was running. One graceful process restart is visible; the dashboard did not show its exit code or signal. Actual concurrent-request counts were unavailable.
- The service page showed Free, 512 MB memory, and a 0.15 CPU limit; its CPU/memory graphs state that viewing utilization requires a paid compute plan. Current Render compute documentation lists Free web services as 512 MB and 0.1 CPU, so the displayed CPU limit and public documentation differ. Treat the dashboard value as the service-specific display and actual utilization as unknown. Render documents Free filesystems as ephemeral, with no persistent disk support. [Compute plans](https://render.com/docs/compute-plans), [Free web service limitations](https://render.com/docs/free). No paid upgrade or resource purchase was made.
- Public-demo settings in code: 256 active sessions; 30-minute idle expiry; 30 session issuances/minute; 20 plans per session; 64 MiB demo DB cap; 20 limited operations/minute per session; 120 limited operations/minute global; solver 4 active / 6 queued with 15-second queue wait. Health endpoints are not classified as limited operations and do not enter the solver gate.

### Hypothesis disposition

| Hypothesis | Evidence and reproduction | Result |
|---|---|---|
| Solver CPU/memory pressure | The health route does not invoke the solver. A full-session local reproduction returned 503 on the original health path without running solver work. Render usage graphs were unavailable. | `UNKNOWN` as a general contributor; rejected as the direct health-check response mechanism. |
| 4 active / 6 queued solver capacity | The health path is outside the solver gate; no solver queue evidence was present in the incident logs. | `REJECTED` as the direct health-check failure mechanism. Resource contribution cannot be measured from Free metrics. |
| SQLite write contention | Health probes did write session rows on the original code. No lock error was exposed; local full-capacity reproduction reproduced the same 503 without a lock. | `UNKNOWN`; not required to explain the reproduced failure. |
| Session creation / validation / cleanup | Original middleware allocated a session for each cookie-less health probe. At 256 active rows, the original code returned 503. Render's 503 timeline aligns with this bounded capacity. | `CONFIRMED` mechanism; exact production row count and response body were not retained. |
| DB size / WAL | Code applies a 64 MiB cap. No disk-full or SQLite diagnostic appeared; Render Free has no persistent disk and exposes no usage graph. | `UNKNOWN` for production DB/WAL state; not reproduced locally. |
| Restart / temporary DB initialization conflict | Render logs show a graceful process restart at 23:27:35, followed by more `/health` 503s at 23:28:04 and later; this restart alone did not restore health. Local restart on the same temporary filesystem preserved unexpired visitor data. Render documents Free local files as ephemeral across service restarts/redeploys, but the production DB/session state during this process restart was not exposed. | `UNKNOWN` as a contributor; not sufficient to explain the continued post-restart 503s. |
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
- Fresh isolated public-demo Playwright run on 2026-10-11 passed all five public-demo scenarios, including A/B ownership, provider decline, replan, approval, memo/export behavior, and bounded error handling. Its temporary SQLite files measured 1,835,008 bytes (app DB) and 888,832 bytes (route DB) after the suite; this is a post-suite sample, not a before/after growth measurement. No developer app DB was used.

## Changes and regression

- `backend/public_demo.py`: skip session issuance for `/health` and `/api/health`; health responses remain public-demo allowlisted and bypass session issuance, operation rate limiting, and the solver gate.
- `tests/test_public_demo_sessions.py`: add a regression that fills the 256-session store, verifies health remains 200 without cookies or new rows, and verifies normal visitor capacity remains enforced.
- `frontend/e2e/public-demo.spec.ts`: wait for the new plan ID to reach the URL after replan before reading the version-2 plan. The first E2E run exposed a timing race where the test read the old ID; the trace showed the replan response had a new ID and excluded the declined round. This test-only wait made the required flow deterministic.

## Regression results

The earlier hotfix verification on the deployed code recorded the full suite results below. The first isolated baseline rerun on `origin/main` (`e6cff56`, same deployed application code as `7b69649`) omitted the ignored legacy road-route cache; the developer DB was intentionally not copied. The 26 original failure/error cases were later re-run individually and classified in `docs/CLEAN_CHECKOUT_REPRODUCIBILITY_AUDIT.md`: 23 were direct missing-cache failures/errors and three were downstream response assertions after `ROUTE_UNAVAILABLE`. A separate Public Demo storage test failed once in the full baseline run, then passed when run alone and as a full module; it is retained as unreproduced rather than grouped into the 26.

- Earlier hotfix verification: backend `582 passed, 1 skipped`; Playwright `17 passed`; R1–R13 `112/112 passed`; focused public-demo session/concurrency tests `7 passed`.
- Initial isolated baseline: backend `555 passed, 11 failed, 16 errors, 1 skipped`; ten listed route-dependent failures plus sixteen route-dependent setup errors were the original 26. The additional Public Demo failure was not reproducible in the focused module.
- Post-fixture isolated implementation run: backend `585 passed, 1 skipped`; Ruff and `compileall` passed; R1–R13 `112 passed`; frontend lint, typecheck, and production build passed; standard Playwright `12 passed`; Public Demo Playwright `5 passed`. The detailed clean-checkout acceptance artifact records the independent checkout runs and exact source fingerprints.
- Rate-limit, session expiry, A/B ownership, provider-state isolation, approval, Decision Memo, CSV/PDF, and private-route blocking were covered by local tests and/or the isolated/live flows above. Public load testing was deliberately not run.

## Deployment and Git

- Hotfix branch: `hotfix/render-api-502-20261010`.
- Commit `7b696499c6c4b59fd613866faa89c1afe8934398` was created from the expected `origin/main` `cc25a330061e36fd6b8dbab64574cb04f6203f82`.
- Render deployment branch `submission/public-demo-deploy` was at `32de2a38e5a9444d80d3bb497aaad9bf09c7fbbf`; it was an ancestor of the hotfix and was fast-forwarded. Render deployed the hotfix successfully.
- After live verification, `origin/main` was fast-forwarded past the verified hotfix code. At this audit, `origin/main` and `origin/hotfix/render-api-502-20261010` both resolve to `e6cff560d3f58da5e36f91e9b8d095f929bb4db2`; the live `origin/submission/public-demo-deploy` and Render deployment remain at `7b696499c6c4b59fd613866faa89c1afe8934398`, which contains the deployed fix. The newer `e6cff56` is a documentation-only follow-up relative to the deployed code.
- The 15 current remote branches were checked; all are ancestors of `origin/main`. `docs/GIT_BRANCH_HISTORY.md` and `artifacts/git/branch_cleanup_manifest.json` are present in `origin/main`. No branch was deleted.
- The primary checkout remains on `quality/public-demo-stability-study` at `ce3bc40a1815b59f507a7b9cf2a95d32e1567d02`. No source or tracked application files were changed in this checkout; the requested report artifacts are untracked outputs. Pre-existing unrelated untracked user files were preserved.

## Recurrence prevention and limits

Health probes are now session-free, so their cadence cannot consume visitor capacity or create SQLite session writes. Keep the active-session and request limits unchanged; use Render runtime logs and available metrics if the same health-check failure returns. Render Free does not expose utilization graphs or persistent disk, so exact production memory, CPU, DB size, WAL size, and session count remain unverified. The specific production 503 body was not retained, so attribution is based on status/timing evidence plus the exact local reproduction.

## Current status at the 2026-10-11 stabilization audit

The historical recovery above remains verified for the deployment at
`7b696499c6c4b59fd613866faa89c1afe8934398`. The retained deployment branch still
points to that SHA, and no redeployment was performed for the test-harness,
fixture, documentation, artifact, and CI changes. A later low-frequency
read-only check issued one GET each to `/health`, `/api/health`, and the public
web root; all three timed out after 20 seconds with HTTP 000 and zero response
bytes. No retries were made. Current live health is therefore
`NOT_VERIFIABLE`, not a confirmed regression or a new 502/503 observation.

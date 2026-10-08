# Public Demo Security Boundary

## Scope and status

`VILLAGE_COVERAGE_PUBLIC_DEMO=true` enables an anonymous, synthetic-only competition demo. It is not production authentication or a production security claim. The default remains `false`; pilot/local behavior keeps its existing database and route sources.

Current technical demo status: `DEPLOYED_UI_VERIFIED`; field validation remains
`NOT_STARTED` and production remains `NOT_READY`. On 2026-10-08 one
low-frequency read-only GET to the public frontend and one GET to
`/api/health` each returned HTTP 200 in 32.68 seconds. This is a basic
availability/cold-wake observation, not a full external browser journey,
account/quota check, field validation, or production acceptance. The historical
`artifacts/public_demo_security_acceptance.json` records the earlier
pre-deployment status and is preserved as historical evidence.

## Data boundary

- The checked-in `data/demo.json`, public reports/schema manifests, and deterministic demo route estimates are the public data inputs. The demo does not call KOSIS, data.go.kr, Kakao, or an LLM.
- Public mode ignores `VILLAGECOVERAGE_APP_DB` and uses a dedicated database under the operating-system temporary directory. Startup removes that demo database and its WAL/SHM files, then seeds the checked-in synthetic/public fixture and a deterministic 54 × 54 straight-line estimate matrix.
- The source label is `SIMULATED STRAIGHT-LINE MODEL ESTIMATE; NOT A ROAD ROUTE`. The estimate is not represented as Kakao road routing.
- The application and route-cache databases are separate from pilot/local files. Docker explicitly copies `data/demo.json` and public manifests; it does not copy SQLite databases. No tracked SQLite database is included in the Render build.
- The checked-in fixture contains 54 areas and 3 demo providers. The acceptance test scans seeded text values for e-mail/phone patterns and checks that survey, feedback, import, and pilot tables contain no rows. It treats only the internally generated, SHA-derived `public-facility-…` identifier as opaque, since its source hash uses public facility attributes and contains no contact field.

## Request policy

Middleware applies an explicit method/path allowlist before API handlers. Unknown methods and paths under `/api/` fail closed with 404 `DEMO_MODE_RESTRICTED`. `OPTIONS` remains available for CORS preflight. API schema/docs routes are disabled in public mode.

The complete state-changing API inventory is generated at `artifacts/public_demo_security_acceptance.json`. Current routes are classified as follows:

| Method and route | Public classification | Reason |
|---|---|---|
| `POST /api/schedules` | `PUBLIC_DEMO_SAFE_WRITE` | Create a plan from the synthetic fixture only |
| `POST /api/schedules/{schedule_id}/replan` | `PUBLIC_DEMO_SAFE_WRITE` | Replan synthetic schedule after demo decline |
| `POST /api/schedules/{schedule_id}/approval` | `PUBLIC_DEMO_SAFE_WRITE` | Only empty-comment `submit`/`approve`; UI says “데모 승인” |
| `POST /api/providers/{provider_id}/rounds/{round_id}/participation` | `PUBLIC_DEMO_SAFE_WRITE` | Only `DECLINED`/`AVAILABLE`; UI says “데모 불참/불참 되돌리기” |
| `POST /api/minimum-coverage/analysis` | `PUBLIC_DEMO_SAFE_WRITE` | Generates and saves a minimum-coverage schedule from the synthetic fixture |
| Every other current `POST`, `PUT`, `PATCH`, or `DELETE` route | `PUBLIC_DEMO_BLOCKED` | Private input, imports, evidence, calibration, preference, revision, or unneeded mutation |

The current state-changing route inventory includes calibration, survey/evidence review, provider preference, schedule creation/replan/revision, CSV/import row approval, demand structure/drafts/approval, minimum-coverage analysis, and plan approval. Tests enumerate FastAPI routes so new write routes default to blocked and an unintended safe route fails the expected allowlist assertion.

Contact retrieval (`GET /api/feedback/{feedback_id}/contact`), all feedback APIs, raw survey/evidence, audit events, pilot import/context/setup, arbitrary schedule revision, and unknown admin-like endpoints are blocked at the server boundary. Role query/body values do not grant access.

## Shared demo state and abuse limits

The demo uses one resettable synthetic SQLite sandbox per backend instance. Visitor state is **not isolated per visitor**: one visitor's demo decline, approval, or plan can be visible to another visitor until service restart/redeploy. Concurrent order is not guaranteed. This is the bounded fallback for this competition release; never use it for real residents or pilot operations. Render Free web services run one instance, and horizontal scaling is not configured.

The backend permits at most 20 requests per 60 seconds, shared across all visitors, for `/api/overview` and every allowlisted safe write. Excess requests receive 429 `DEMO_RATE_LIMITED` and `Retry-After`. A local test against the real API and isolated temporary SQLite completed full six-request workflows for 1/1 and 3/3 visitors; at 5 and 10 simultaneous visitors it produced 5 and 10 rate-limited requests respectively, with zero complete workflows. Per-action latency and counts are recorded in `artifacts/research/public_demo_rate_limit_load.json`. This process-local throttle is a low-cost abuse guard, not a distributed DDoS control; a burst can temporarily exhaust the shared visitor budget. The frontend now displays public-safe status/network guidance and a manual `Retry-After` wait hint; it does not automatically retry.

## Network and response boundary

- CORS accepts only exact configured HTTPS origins in public mode. The deployment manifest configures only `https://villagecoverage-public-demo-web.onrender.com`; wildcard origins and local origins are rejected. Localhost is enabled only for explicitly opted-in E2E runs. Public CORS exposes only `Retry-After` so browser clients can show the bounded 429 wait hint.
- FastAPI public mode adds `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Cache-Control: no-store`, and `Content-Security-Policy: frame-ancestors 'none'`. Next.js also sets `X-Frame-Options: DENY`.
- `/health` returns only `{"status":"ok"}`. Docs, ReDoc, and OpenAPI are disabled. Existing API error handlers sanitize errors; Uvicorn is started without debug mode.
- Provider/API secrets are not configured for the demo. The frontend uses a same-origin default API base, and the Render build injects only the public backend URL and demo-mode display flag. The frontend build is scanned for a non-secret marker before release.

## Hosting and limits

The current public hosts are `https://villagecoverage-public-demo-web.onrender.com` and `https://villagecoverage-public-demo-api.onrender.com`. The single read-only observation above saw a 32.68-second response, consistent with a slow wake but not enough to characterize Render's cold-start distribution. Service account quotas, persistence, payment settings, and production readiness were not inspected in this audit. The demo startup reset means SQLite state is ephemeral; existing plans can disappear after restart.

`render.yaml` remains the deployment configuration source. Public service changes
from this quality branch have not been deployed.

## Release acceptance

See [`../artifacts/public_demo_security_acceptance.json`](../artifacts/public_demo_security_acceptance.json) for the dated historical release inventory. See `artifacts/quality_longrun_acceptance.json` for the current branch's test and read-only availability evidence. These do not establish field validation, authenticated approval, or production readiness.

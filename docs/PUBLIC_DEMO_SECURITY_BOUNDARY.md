# Public Demo Security Boundary

## Scope and status

`VILLAGE_COVERAGE_PUBLIC_DEMO=true` enables an anonymous, synthetic-only competition demo. It is not production authentication or a production security claim. The default remains `false`; pilot/local behavior keeps its existing database and route sources.

Public deployment status for this release: `DEPLOYMENT_READY_NEEDS_USER_AUTH`. The Render configuration is prepared, but this task has not created or verified a service, and there is no verified public URL in the release evidence. Do not distribute the expected hostnames as test URLs until a fresh external browser verifies them.

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
| `POST /api/providers/{provider_id}/rounds/{round_id}/participation` | `PUBLIC_DEMO_SAFE_WRITE` | Only `DECLINED`/`AVAILABLE`; UI says “데모 불참/참여” |
| `POST /api/minimum-coverage/analysis` | `PUBLIC_DEMO_SAFE_WRITE` | Generates and saves a minimum-coverage schedule from the synthetic fixture |
| Every other current `POST`, `PUT`, `PATCH`, or `DELETE` route | `PUBLIC_DEMO_BLOCKED` | Private input, imports, evidence, calibration, preference, revision, or unneeded mutation |

The current state-changing route inventory includes calibration, survey/evidence review, provider preference, schedule creation/replan/revision, CSV/import row approval, demand structure/drafts/approval, minimum-coverage analysis, and plan approval. Tests enumerate FastAPI routes so new write routes default to blocked and an unintended safe route fails the expected allowlist assertion.

Contact retrieval (`GET /api/feedback/{feedback_id}/contact`), all feedback APIs, raw survey/evidence, audit events, pilot import/context/setup, arbitrary schedule revision, and unknown admin-like endpoints are blocked at the server boundary. Role query/body values do not grant access.

## Shared demo state and abuse limits

The demo uses one resettable synthetic SQLite sandbox per backend instance. Visitor state is **not isolated per visitor**: one visitor's demo decline, approval, or plan can be visible to another visitor until service restart/redeploy. Concurrent order is not guaranteed. This is the bounded fallback for this competition release; never use it for real residents or pilot operations. Render Free web services run one instance, and horizontal scaling is not configured.

The backend permits at most 20 requests per 60 seconds, shared across all visitors, for `/api/overview` and every allowlisted safe write. Excess requests receive 429 `DEMO_RATE_LIMITED` and `Retry-After`. This process-local throttle is a low-cost abuse guard, not a distributed DDoS control; a burst can temporarily exhaust the shared visitor budget.

## Network and response boundary

- CORS accepts only exact configured HTTPS origins in public mode. The deployment manifest configures only `https://villagecoverage-public-demo-web.onrender.com`; wildcard origins and local origins are rejected. Localhost is enabled only for explicitly opted-in E2E runs.
- FastAPI public mode adds `X-Content-Type-Options: nosniff`, `Referrer-Policy: strict-origin-when-cross-origin`, `Cache-Control: no-store`, and `Content-Security-Policy: frame-ancestors 'none'`. Next.js also sets `X-Frame-Options: DENY`.
- `/health` returns only `{"status":"ok"}`. Docs, ReDoc, and OpenAPI are disabled. Existing API error handlers sanitize errors; Uvicorn is started without debug mode.
- Provider/API secrets are not configured for the demo. The frontend uses a same-origin default API base, and the Render build injects only the public backend URL and demo-mode display flag. The frontend build is scanned for a non-secret marker before release.

## Hosting and limits

Render Free Node and Python web services in Singapore use managed HTTPS, one backend instance, ephemeral filesystems, and the demo startup reset. The Next.js service runs the generated standalone server with its static assets copied into the artifact. No disk, paid add-on, external key, or persistent pilot DB is configured. Free services sleep after 15 idle minutes; waking can take about one minute. The workspace has 750 free instance hours per calendar month shared across Free services. If that quota is exhausted, Render suspends its Free web services for the rest of the month. Outbound bandwidth beyond the included amount can incur supplementary charges when a payment method is on file; without one, Free services are suspended. Excess build-pipeline usage can also be billed unless the workspace spend limit is reached. The account's payment method, spend limit, and usage are not verified, so `$0/month` is an estimate only within included quotas; check those settings before creating the Blueprint.

Expected hosts in `render.yaml` are configuration values, **not verified public URLs**. Deployment and cold-start measurements remain pending the user's Render account session.

## Release acceptance

See [`../artifacts/public_demo_security_acceptance.json`](../artifacts/public_demo_security_acceptance.json) for machine-readable endpoint, PII, CORS, secret, test, deployment, and public URL status. `DEPLOYED_VERIFIED` requires a fresh unauthenticated browser check against the actual HTTPS URL; local tests cannot satisfy that condition.

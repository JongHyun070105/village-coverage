# Public Render data-loading incident — 2026-10-13

## Status

**Current report: `ROOT_CAUSE_UNKNOWN`.** The user-reported plan reload failure was not reproduced with an exact original request, response, or Render log. A low-volume smoke and a full synthetic browser journey show that the currently served public demo was reachable at test time, but do not establish that the reported intermittent failure is fixed. The candidate changes in this branch have not been deployed; `REMOTE_VERIFIED` is not claimed.

## Reported symptom

The report was that the public web UI loaded after a cold start, then plan data failed to reload with “계획 데이터를 불러오지 못했습니다”; retrying reportedly failed again. The original browser request, status, response body, timestamp, and deployed runtime SHA were not included. Render Dashboard deploy metadata and API/web logs were not available in this run, so the original failed endpoint and mechanism remain unknown.

## Current public smoke

On 2026-10-13 at approximately 00:53 UTC, using a new browser context and a low request rate:

| Request | Result | Elapsed |
| --- | --- | ---: |
| API `GET /health` (first request) | HTTP 200, JSON | 32.624 s |
| API `GET /health` after a 5 s wait | HTTP 200, JSON | 0.166 s |
| Web `GET /` | HTTP 200, HTML | 14.393 s |
| Web same-origin `GET /api/regions` | HTTP 200, JSON | 0.635 s |
| Web same-origin `GET /api/schedules?region_id=pilot:홍성군 장곡면` | HTTP 200, JSON | 0.355 s |

These observations are consistent with a slow first response, but do not prove cold start caused the reported plan reload failure. No Render service logs, restarts, or resource metrics were available to correlate.

## Browser reproduction attempts

The final public-demo Playwright journey ran at `2026-10-13T01:10:21.835Z` using a fresh browser A and a separate browser B. It completed 16 UI checkpoints and captured 45 same-origin API responses: 37 HTTP 200, six expected creation/replan HTTP 201, and two expected A/B ownership-denial HTTP 404 responses. It confirmed dashboard and region data, four-policy comparison, plan creation/detail/reload, provider page, the visible “데모 불참” click, saved state, replan/version history, Decision Memo, CSV/PDF downloads, and A/B session isolation. B had a distinct cookie, could not see A's owner-scoped provider round, received `NOT_FOUND` when requesting A's plan, and had no plan history. The browser artifact retains only redacted paths, test aliases A/B, statuses/timings, headings, and screenshots; it does not persist cookies or request payloads.

Two earlier attempts stopped on test-harness expectations: first a broad `v1` locator matched multiple controls; next the test incorrectly expected B to see A's owner-scoped provider round as available. The accessible locator and ownership assertion were corrected. Neither earlier failure was a service/API failure. The final run is an `EXEC PASS` for the **currently served public URL at that time**, not evidence for the un-deployed branch candidate; the deployed runtime SHA remains `NOT_VERIFIABLE`.

The journey is synthetic, single-user-at-a-time traffic. It is not a load test. A completed browser journey against the currently deployed code does not verify the un-deployed candidate or the original incident.

## Root-cause assessment

- **Reported plan reload failure:** `UNKNOWN`. There is no exact failed request/status or correlated Render log.
- **Render cold start:** observed slow first health/web requests, but not proven as the plan reload cause.
- **Next.js rewrite/proxy:** current browser calls used same-origin `/api` and returned JSON 200 in the observed smoke and journey steps; this does not rule out intermittent proxy failures.
- **Cookie/session:** observed browser session cookie attributes were `HttpOnly`, `Secure`, `SameSite=Lax`, and `Path=/api`; values were not saved. Final A/B isolation and owner-scoped provider round behavior passed.
- **Database:** production DB contents, restarts, SQLite errors, and reset history were not observable. In isolated tests, a database reset invalidates an old plan with `DEMO_SESSION_EXPIRED` and a newly issued session starts without that history; this does not establish production data loss.
- **API contract / frontend hydration:** the first live attempt's region selection exposed a test-side hydration/locator race and was corrected to wait for the actual region option. It did not reproduce the reported plan reload symptom.
- **Separate historical incident:** `docs/RENDER_502_INCIDENT_REPORT.md` records a prior health-probe HTTP 503 whose confirmed code mechanism was health checks allocating visitor sessions until the 256-session cap. That is a distinct incident; do not use it as the root cause of this plan reload report.

## Candidate recovery change

`frontend/lib/api.ts` now performs at most one 500 ms delayed retry for Public Demo GET transport failures or proxy 502/503/504 responses that have neither a machine-readable error code nor `Retry-After`. POST requests are never automatically retried. It classifies timeout, transient upstream, and malformed/non-JSON API responses separately and does not surface HTML error bodies. `frontend/components/api-error.tsx` provides distinct safe guidance for session expiry/capacity, rate limits, transient upstream failures, timeouts, and API contract errors. Existing session ownership and limits remain in place.

Injected frontend regression tests cover HTML 502 retry, 503 capacity plus `Retry-After` without retry, 504 timeout mapping, successful HTML as contract error, and no HTML-body disclosure. These tests establish client behavior for those constructed responses, not a real Render failure reproduction.

## Before/after and impact

There is no verified before/after production comparison: the candidate has not been deployed and the original failure did not have a captured request. The current smoke and live journey show the deployed site served the exercised requests successfully at test time. No production session or database state was reset or changed by this investigation.

## Release and remaining risk

- Local backend suite: `587 passed, 1 skipped`; Ruff and `compileall` passed. Frontend lint, typecheck, build, standard/public-demo E2E, two responsive UI E2E cases, and R1–R13 (112/112) passed. The live browser journey above passed on the public deployment. GitHub Actions on the new branch is recorded separately in the release gate after it completes.
- Remote runtime SHA and Render log timeline: `NOT_VERIFIABLE`.
- Original failure's request, status, root cause, recurrence rate, and production DB impact: `NOT_VERIFIABLE`.
- The candidate requires review and a separate human GO before updating the Render deployment branch or deploying.
- Do not describe the public demo as repaired until the candidate SHA is deployed and the full remote journey succeeds against that deployed SHA.

## Security release note checked on 2026-10-13

The [official Next.js advance notice](https://nextjs.org/blog/upcoming-nextjs-security-update-october-2026) says an out-of-band upstream-dependency update is planned for October 14, covering two Critical and one High severity vulnerabilities. The notice does not yet identify the CVEs, affected ranges, or fixed versions, so this branch did not guess an upgrade. The candidate carries Next.js 16.3.8; the inspected public-demo deployment branch contains 16.3.7. Actual Render runtime version remains unverified. Production `npm audit` reported zero vulnerabilities; the full development dependency audit reported five high findings in the lint dependency tree. No `npm audit fix --force` or unrelated framework upgrade was applied.

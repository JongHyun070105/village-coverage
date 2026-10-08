# Engineering quality audit

Baseline branch: `submission/public-demo-deploy`
Baseline SHA: `467c7381bed8066e5d9205bfa5097534923a6fd2`
Audit branch: `quality/public-demo-stability-study`

This inventory checks current code and tests, not earlier status claims alone.
The public deployment is synthetic and shared; no visitor test or load test in
this audit writes to Render.

## Inventory

| ID | Classification | Severity | Finding | Resolution |
|---|---|---:|---|---|
| Q-01 | CONFIRMED_DEFECT | MEDIUM | Independent anonymous visitors share plans, provider declines, and approvals in one process SQLite sandbox. Browser A's plan was visible to B/C, B replanned A's plan, and C's approval was visible to A. | Kept the shared sandbox; added an explicit visitor-sharing/restart notice and repeatable 3-context test. Per-visitor identity isolation is deferred. |
| Q-02 | CONFIRMED_DEFECT | MEDIUM | The shared 20 requests / 60 seconds limiter stops valid workflows as visitors arrive together. A client-supplied visitor header does not create a separate budget. | Kept the abuse ceiling. Added real local API load evidence and public 429/`Retry-After` guidance; no client-selected identity or bypass was introduced. |
| Q-03 | CONFIRMED_DEFECT | LOW | Public API errors could show local port 8000/uvicorn instructions; 429 lacked a friendly message and its `Retry-After` header was ignored. | Public-safe copy, machine code parsing, CORS exposure for the bounded wait hint, and mocked status/network E2E added. Development-mode diagnostic remains. |
| Q-04 | CONFIRMED_DEFECT | MEDIUM | Scenario comparison kept previous policy results visible while a new run was pending and after failure; controls also remained editable during the run. | Clear result state at run start and disable the comparison inputs while pending; E2E checks failed calculation state. |
| Q-05 | CONFIRMED_DEFECT | LOW | A public-demo provider decline had no UI action to restore that round to `AVAILABLE`, despite the safe write API allowing it. | Added a single-round “불참 되돌리기” action and E2E coverage. |
| Q-06 | CONFIRMED_DEFECT | LOW | Plan error retry only refreshed schedule history, not the selected plan/detail requests; that could leave a failed detail load stuck. | Retry now reloads history and selected detail, and is labeled “최신 상태 다시 불러오기” because failed writes are not blindly repeated. |
| Q-07 | TEST_GAP | MEDIUM | Existing tests did not cover public multi-visitor mutation, 429/network public copy, or restart invalidation of stale IDs. | Added browser/API regression tests against independent contexts, mocked failures, and isolated temporary SQLite. |
| Q-08 | DATA_LIMITATION | MEDIUM | The demo's shared process-local store and limiter reset on service restart; Render Free SQLite persistence is not promised. | Notice and security boundary documentation state the sharing and restart behavior; isolated persistence is deferred. |
| Q-09 | FIELD_VALIDATION_REQUIRED | HIGH | No current test establishes real service demand, resident benefit, provider participation/capacity, savings, or authenticated approval. | Remains explicitly out of scope for this synthetic demo; real pilot/production is not accepted by this audit. |
| Q-10 | DOCUMENTATION_DRIFT | MEDIUM | The security-boundary document still described the pre-deployment state although current release evidence records an external deployment. | Update current deployment fields after a low-frequency read-only smoke; preserve dated acceptance artifacts. |
| Q-11 | EXPERIMENTAL | LOW | The monthly aggregate policy comparator does not execute dated schedule planning or travel-cost sensitivity inputs. Provider removal may have no aggregate effect under nonbinding capacities. | Reported as constrained synthetic experiments; schedule-level/provider operations are not claimed. |
| Q-12 | CONFIRMED_DEFECT | MEDIUM | The request-boundary middleware short-circuited a 429 before outer CORS handling, so cross-origin browser code could not read the status or retry header. | CORS now wraps the boundary and exposes only `Retry-After` in public-demo mode; a middleware integration test asserts the actual cross-origin 429 headers. |

## Detailed evidence and reproduction

### Q-01 — Shared visitor state

- **Evidence:** `backend/public_demo.py` uses one process-local `PublicDemoRateLimiter`; `backend/database.py` resolves public-demo state to a shared temporary SQLite path. `docs/PUBLIC_DEMO_SECURITY_BOUNDARY.md` already documents one sandbox. New test `frontend/e2e/public-demo.spec.ts` creates three independent browser contexts.
- **Reproduction:** A creates a synthetic schedule; B reads it; A declines one assigned provider round; B loads and replans A's schedule; C creates a plan and approves the resulting child; A reloads and observes the approval. A stale random schedule ID returns 404.
- **Expected:** A public visitor is told the demo is shared and that changes are synthetic; stale IDs fail safely.
- **Actual:** State is shared until server restart and anonymous visitors can change each other's demo records. Restart resets the SQLite namespace and makes prior IDs return 404.
- **Affected files:** `backend/main.py`, `backend/database.py`, `frontend/app/layout.tsx`, `frontend/e2e/public-demo.spec.ts`.
- **Risk / priority:** MEDIUM. Cross-visitor confusion and demo integrity only; the test contains no real resident or provider records.
- **Resolution:** Shared-state warning plus automated reproduction. Per-visitor namespace design is deferred below.

### Q-02 — Shared rate limit

- **Evidence:** Default limiter is 20 limited requests in a 60-second sliding window. `GET /api/overview` and every public safe-write route share the same process bucket. `Retry-After` is emitted on 429. `X-Demo-Visitor` is not trusted.
- **Reproduction:** Run `uv run python scripts/measure_public_demo_rate_limit.py`; it uses actual local API endpoints and separately seeded temporary SQLite per visitor-count case. See `artifacts/research/public_demo_rate_limit_load.json`.
- **Expected:** Valid journeys complete under ordinary demo concurrency; abuse protections remain in force.
- **Actual:** Measured counts and phase of first 429 are recorded in the artifact. No remote load was run.
- **Affected files:** `backend/public_demo.py`, `scripts/measure_public_demo_rate_limit.py`, `frontend/components/api-error.tsx`.
- **Risk / priority:** MEDIUM usability / availability. The ceiling is retained pending operational policy review.
- **Resolution:** Public message and manual `Retry-After` wait guidance; no automatic retries.

### Q-03 to Q-06 — User-visible recovery

- **Evidence:** `frontend/lib/api.ts` now reads top-level `code` and `Retry-After`; `backend/main.py` places CORS outside the request boundary so the rate-limit response includes the configured origin and exposes only the retry hint; `frontend/components/api-error.tsx` maps public status and network failures without local server instructions; `frontend/app/scenarios/page.tsx` clears stale results and locks controls during calculation; provider and plan details have recovery controls.
- **Reproduction:** Run `npm run test:e2e:public-demo`; mocked 403/404/409/422/429/500/503 and timeout responses assert visible guidance, and one 503 verifies prior comparison results are cleared and no automatic retry occurred.
- **Expected:** Users see current results only, explicit retry/wait guidance, and can restore an accidental synthetic decline.
- **Actual:** Covered failures do not produce raw server details or development-only port instructions in public mode.
- **Affected files:** `frontend/lib/api.ts`, `frontend/components/api-error.tsx`, `frontend/app/page.tsx`, `frontend/app/scenarios/page.tsx`, `frontend/app/plans/page.tsx`, `frontend/app/providers/[id]/page.tsx`.
- **Risk / priority:** LOW to MEDIUM. A retry after a potentially completed write rereads server state instead of repeating the mutation.
- **Resolution:** Implemented and covered by UI tests.

## Shared-state design decision

| Option | Complexity / SQLite | Memory and Render Free | Security | Usability |
|---|---|---|---|---|
| A. Ephemeral context per visitor | High: per-session DB/transaction namespace and cleanup; SQLite connection ownership needed. | More DB files/handles and cleanup work; process restarts lose all contexts. | Unguessable session token is still not authentication; cookie/CSRF/abuse/lifetime and collision rules required. | Strong isolation while the process lives; links and reloads need session continuity. |
| B. Session plan namespace | Medium to high: add ownership namespace to every read/write/export/replan path and migration/index. | Small row overhead but cleanup and DB growth remain; Free instance restart still loses state. | Anonymous namespace IDs can be shared/guessed/leaked; not identity. CSRF and rate policy still required. | Plans become private only if all endpoints consistently enforce the namespace. |
| C. Read-only shared baseline + visitor results | High: separate baseline and user mutation store, route every stateful endpoint, and make exports/replan namespace-aware. | Additional schema/file and startup cleanup; memory can remain bounded but per-process state is fragile. | Better boundary if implemented fail-closed; still needs session lifecycle, CSRF and abuse controls. | Clear mental model, but session persistence and share-link behavior need design. |
| D. Shared sandbox + notice and conflict protection | Low: existing SQLite and route contracts remain. | Minimal memory/storage; matches current single-process demo. | Does not isolate visitors; must not be called authentication or privacy isolation. Keeps synthetic-only and route allowlist. | Visitors can see shared plans, but the notice makes this explicit. |

**Decision:** D for this release. Implementing A–C safely exceeds this bounded task: the application has no authenticated identity, cookie/session lifecycle, CSRF design, namespace checks across all plan endpoints, or multi-process persistent storage contract. A user-controlled header would be spoofable and is not used. Revisit isolation as a separately reviewed design before any real or private data is introduced.

## Verified, under-tested, and deferred areas

- **Verified locally:** public API allowlist and blocked private routes; synthetic-only test setup; CORS/security-header tests; shared state across three browser contexts; stale ID after temp-database restart; public 4-policy journey and export; status/network error copy; phone-width dashboard check.
- **Full regression completed:** `uv run pytest -q` (573 passed, 1 skipped); `uv run ruff check .`; `uv run python -m compileall -q backend scripts tests`; frontend lint, typecheck, and build; Playwright general workflow (12 passed) and public demo (5 passed); proposal R1–R13 acceptance (112 passed). See `artifacts/quality_longrun_acceptance.json` and `artifacts/research/proposal_acceptance_longrun.json`.
- **Accessibility checks:** keyboard/focus, labels, table captions, status/error semantics, and 390×844, 768×1024, 1280×800, 1440×900 responsive viewports passed automated checks. This is not manual screen-reader validation.
- **Independent review:** `NOT_VERIFIABLE`. Cross-provider review was attempted, but provider quota and worker checkout failures produced no usable independent review. This audit's findings are verified by the MAIN run only.
- **Not established here:** screen-reader usability, a cold-start distribution, authenticated approval, production readiness, field validation, or service outcomes. One read-only frontend GET and one API health GET returned 200 in about 32.68 seconds each; this is not a latency distribution or full remote journey.
- **Artifacts:** `artifacts/research/public_demo_rate_limit_load.json`, `artifacts/research/policy_robustness.json`, and `artifacts/quality_longrun_acceptance.json`.

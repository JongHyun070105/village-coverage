# Public demo admission and first-visit recovery (v18)

This policy applies only in public demo mode. It keeps the existing API allowlist,
opaque registered session cookie, ownership checks and isolated ephemeral database.
It changes no credentials, environment variables, service plans or submission materials.

## Request costs and admission

`backend/public_demo.py:operation_cost` classifies every allowed endpoint independently
of the security allowlist; blocked routes stay blocked.

| Class | Examples | Admission |
| --- | --- | --- |
| A: basic | health, regions, services, dictionary, policy metadata | No compute/read budget; health needs no session. Other reads still verify/issue a session. |
| B: general read | providers, stored plans, evidence, CSV, memo JSON/HTML | Separate 120 requests/session/60s; no compute budget. |
| C: expensive compute | overview, region/policy/reserve comparisons, village evaluation, fallback candidates, PDF rendering | Session 20/60s + shared compute/write 70/60s + bounded capacity. |
| D: writes | plan creation/replan, approval, participation, cost-model POST | Session 20/60s + shared compute/write 70/60s; solver-backed writes also use capacity. |

Main at baseline `48d131e` actually configured a shared **120/60s**, in addition to
20/session/60s. v18 sets the shared ceiling to **70/60s**; it does not give every
visitor 70 requests. New sessions remain bounded at 30/60s process-wide and 256
active sessions, with 30-minute idle expiry and 20 stored plans/session.

Admission first checks all applicable budgets without spending them, then reserves
capacity if required, then atomically checks and commits all budgets under ordered
locks. Concurrent consumers can invalidate a precheck, so the final check is required.
An initial budget rejection never enters the solver queue. Capacity rejection and
rate rejection spend neither budget. Application failures after admission (including
invalid inputs, ownership failures and unsuccessful writes) consume budget because
they cost work. Session issuance attempts at storage capacity still consume issuance
budget, preserving the existing abuse bound.

Capacity remains **4 active, 6 waiting, maximum 15 seconds waiting**. No extra CPU or
RAM is provisioned. The 70 ceiling is not a throughput promise. JSON/HTML memos
load bounded stored plans and explanations without solving; PDF rendering adds CPU
work and shares the capacity gate. Basic reads and existing sessions are independent
of compute and issuance ceilings respectively.

All limiter state is process-local and resets on restart. Each limiter stores at
most 1,024 keys, prunes expired events from inactive keys on admission, and rejects
new keys at capacity instead of evicting live budgets. Before increasing workers or
instances, replace in-memory counters and capacity state with a shared coordinator.
No Redis/database service is introduced by this change.

## Identity and remaining abuse limits

Only cookies whose opaque token hashes exist in the session store identify visitors.
Tabs sharing that cookie share a budget. Request IDs, forwarding headers and IPs do
not select budgets. The Render -> Next.js -> API proxy chain has not been verified
as a trusted source of end-user IP; no IP limiter or new pseudonymization secret is
introduced. IPv4/IPv6/NAT visitors therefore are not merged into one 20-request IP
bucket. Existing session isolation, HttpOnly/SameSite/Secure configuration, CORS,
input validation and idempotent write behavior are retained.

Cookie deletion can obtain a new registered session. Issuance/global/storage limits
bound resource use, but cannot establish one human per session. A determined client
can exhaust shared ceilings and affect other visitors. IP-aware anti-abuse requires
a verified proxy boundary; no claim of complete Sybil resistance is made here.

## Recovery and error provenance

The browser verifies health, then shares a single regions/session bootstrap before
parallel owner-scoped requests. Same-origin Web Locks serialize fresh tabs' bootstrap
where supported, with a bounded wait. Concurrent cheap reads share a promise and
abort only when their last consumer leaves. A storage-available cross-tab cooldown
is advisory UX only; the server remains authoritative.

Only explicitly cheap GETs retry: up to **4 total attempts / 120 seconds**, including
fetches and waits. Transient 429 and untyped 502/503/504 use bounded exponential
backoff and jitter; Retry-After seconds or HTTP dates are never shortened. A hint
beyond the deadline returns a clear error for manual recovery. Health probes are
bounded at 12 attempts / 120 seconds; total first-load health + data phases can take
up to roughly 240 seconds. Manual recovery appears after 15 seconds. A running
bootstrap lock also has a 120-second deadline. Page/request cancellation stops waits.

POSTs and expensive GETs are never repeated automatically, even after an ambiguous
network failure. Check stored plan state before resubmitting a mutation. A failed
session bootstrap can prevent a write from being sent; that is safe to recover by
reloading the connection, not by assuming a write occurred.

Known backend JSON codes retain their identity: DEMO_RATE_LIMITED,
DEMO_SESSION_RATE_LIMITED, DEMO_SOLVER_CAPACITY, session/storage errors. Generic
429 remains HTTP_429. Only an observed `x-render-routing: hibernate-rate-limited`
marker establishes UPSTREAM_RATE_LIMITED; absence of that header proves nothing.
502/503 map to TEMPORARY_UPSTREAM_FAILURE and 504 retains the existing
REQUEST_TIMEOUT contract. Real 500 errors are not hidden as server preparation.
HTML/plaintext upstream bodies are not displayed. Retry exhaustion exposes the last
structured error or SERVER_WAKE_TIMEOUT for the readiness/lock deadline.

## Confirmed live incident and platform boundary

During v18 inspection on 2026-10-31 KST, four low-volume reads observed:

| Request | Status/content | Safe evidence |
| --- | --- | --- |
| Web `/api/health` | 502 HTML | `x-render-routing: no-deploy` |
| Web `/api/regions` | 429 plaintext | `x-render-routing: hibernate-rate-limited` |
| API `/api/health` | 200 JSON after 42.52s | Backend X-Request-ID present |
| API `/api/regions` | 200 JSON in 0.31s | Backend X-Request-ID present |

This establishes a Render routing-layer 429 for the observed Web request. It does
not prove every historical 429 has that origin. Separately, a local test reproduces
regions returning backend DEMO_SESSION_RATE_LIMITED before compute admission.
Next config uses an external rewrite and a 60-second proxy timeout; it contains no
application-level proxy rate limiter.

Render can also reject the initial HTML before JavaScript is delivered. Browser
recovery code cannot run until HTML/JS loads. This residual platform failure cannot
be eliminated by client retry code or a larger backend limit. See [Render free
service lifecycle](https://render.com/docs/free); no keepalive traffic, paid upgrade
or environment change is used as a workaround.

## Verification

Use synthetic clocks for limiter windows and local injected responses for recovery.
Never send 70-request tests or attack traffic to the public service. Regression
coverage is in `tests/test_demo_admission.py`, the existing demo/session/concurrency
tests, `frontend/tests/api-recovery.test.mjs` and `frontend/e2e/public-demo.spec.ts`.
Local injected PASS does not establish Render Live SHA, production CPU/RAM or a
production cold-start guarantee. Those require separate authorized live acceptance.

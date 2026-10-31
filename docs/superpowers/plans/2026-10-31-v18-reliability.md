# v18 Reliability Implementation Plan

**Goal:** Independent visitor admission and bounded first-visit recovery on the single-instance public demo.
**Spec:** User's v18 task. No submission/media/email, secrets, environment, paid services or Gemini changes.
**Architecture:** Keep the registered opaque session and in-memory limiters. Centralize cost policy (A basic, B read, C compute, D write). Atomically check session and global budgets, then commit both; acquire bounded capacity before committing compute admission. Count admitted application failures to prevent invalid-request abuse. No IP policy until the Render -> Next -> API trust chain is verified.

**Evidence:** main and deployment branch 48d131e. Existing configured global budget is 120, session 20, issuance 30; gate 4 active + 6 waiting / 15 seconds. Live Web regions returned plain 429 with x-render-routing=hibernate-rate-limited; direct API regions 200. Existing recovery excludes all 429. Independent AGY/Claude Sonnet reviews collected in parallel-261031-220945-5446b3; recommendations independently rechecked. Baseline: backend demo 23 pass; frontend unit 11 pass.

**Approach decision:** User requests autonomous implementation of a detailed design. MAIN preserves existing architecture; no new infrastructure. Generic 429 remains HTTP_429; only the observed Render routing marker establishes UPSTREAM_RATE_LIMITED. No new IP secret. Unknown proxy trust means no IP restriction. Session issuance 30/60 and 256 active remain bounded defenses against cookie churn; they cannot prove one human per session.

## Global constraints
- Compute/write global 70/60; session 20/60. Basic lookup excluded. General reads separately 120/session/60.
- Solver concurrency stays 4 active, 6 queued, 15s bounded wait, with no speculative throughput claim.
- Retry only cheap GET 429 or untyped transient 502/503/504, max 4 attempts/120s including fetch and waits; Retry-After never shortened. Health bounded 120s and max 12 probes. POST and expensive GET never repeat automatically.
- Private scratch/caches outside repo. Existing dirty primary tree untouched. Push/merge impact checked; production requires broker GO.

## Review focus
- Global rejection must not burn session budget; solver saturation must not burn either.
- Fresh parallel page reads must establish one cookie before requesting owner-scoped data.
- Retry-After longer than deadline fails with manual recovery without early retry.
- Aborted shared waiters do not cancel surviving consumers or update abandoned UI.
- Upstream HTML/plaintext must not leak internals or masquerade as a backend limit.

## Task 1: Backend admission
- [x] Add tests for independent A/B 20, global 70, atomic rejection/concurrency, key expiry/bounds, endpoint inventory, session issuance 429, spoofed XFF invariance and capacity accounting. Observe RED.
- [x] Implement atomic multi-bucket admission in PublicDemoRateLimiter, bounded sweep, cost policy in public_demo.py; configure main global 70.
- [x] Run demo/session/concurrency regressions and full backend suite with external temporary storage.

## Task 2: Recovery
- [x] Add virtual-time tests for JSON/HTML/plain 429, Retry-After/date/backoff/deadline, 500, cancellation, no mutation/compute repeat and bootstrap serialization. Observe RED.
- [x] Update api.ts safe-read and health recovery, bootstrap sharing and verified upstream error classification; use requested Korean readiness copy with existing accessible spinner/manual retry.
- [x] Run unit/lint/type/build and local Playwright regression including 390x844, 768x1024, 1440x900.

## Task 3: Review and delivery
- [x] Fresh cross-provider patch review; verify findings mechanically, fix real defects with tests.
- [ ] Commit scoped changes, push non-production feature branch, create PR and verify CI.
- [ ] Confirm Render targets, previous recoverable deploy, PR review and CI; request exact broker deployment/merge grant. Stop at human GO if pending; deploy only approved plan, Auto Deploy once.
- [ ] Final evidence report distinguishes local injected PASS from actual live verification and records remaining platform constraints.

## Review resolutions
- Independent final review found queue occupancy by already-throttled sessions. Added a RED test, non-spending precheck, atomic final commit, and a simulated competing-admission test proving capacity release on 429.
- Retry-After now also receives positive jitter after the larger of hint/backoff.
- JSON/HTML memos remain B: they only inspect bounded stored plans; PDF rendering is C. Approval/cost-model POSTs do not invoke solvers and remain D without solver occupancy.
- General-read admission now has a middleware 120/60 separation regression test.
- A failing bootstrap intentionally blocks an unsent POST; the UI must not claim a mutation happened.

Final local verification: backend 638 passed/1 opt-in live smoke skipped; demo admission/session/concurrency 34 passed; frontend unit 19 passed; standard browser 14 passed/1 opt-in live journey skipped; public demo 14 passed; production responsive UI 5 passed. Ruff, ESLint, TypeScript and webpack production build passed. Default local Turbopack cannot resolve external cached node_modules; CI runs a regular npm ci and default production build.

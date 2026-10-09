# Public Demo Concurrency Audit

## Finding and remediation

The previous public demo wrote plans into shared SQLite and provider decline
state into shared provider participation records. Anonymous visitors could
therefore see each other's plans, and one visitor's decline could affect a
different plan. The public boundary also had a shared 20-request/minute ceiling
and did not bound all expensive read/solver paths.

The implementation adds server-registered session ownership and session-scoped
provider participation state. Ownership is checked before plan detail and
derived output, exports, approval, cost changes, revision, and replan. Lists
are owner-filtered. Expired/unknown session tokens cannot access prior plan IDs.
Public provider participation transitions compare expected state and write in a
transaction. Replan rechecks state after calculation and maps stale or already
approved plan state to 409.

## Route ownership coverage

| Surface | Enforcement |
|---|---|
| Plan list and create | Session-filtered list; creation records owner |
| Plan detail and explanations | Owner check |
| Replan and revision | Owner check, expected version/state checks |
| Approval | Owner check and transactional state/version validation |
| Provider decline/restore | Session-scoped state plus expected status |
| Minimum coverage | New plan records current session owner |
| Decision Memo HTML/PDF | Shared plan resolver checks owner |
| Schedule CSV, budget/unmet CSV, summary PDF | Owner-checked plan resolver |
| Cost model | Explicit owner check |
| Operations/latest plan views | Filtered to session-owned plans |

Private pilot/import write paths remain outside the explicit public-demo
allowlist. Public mode remains opt-in and synthetic-only.

## Browser and test evidence

- `tests/test_public_demo.py` and `tests/test_public_demo_sessions.py`: targeted
  session, ownership, expiry, resource-bound, and participation checks.
- `frontend/e2e/public-demo.spec.ts`: two independent browser contexts verify
  distinct HttpOnly cookies, cross-session read/write denial, decline/replan
  isolation, and approval isolation; the main demo flow and mobile-width layout
  are exercised locally.
- The Playwright API path uses the local Next.js same-origin rewrite; it does
  not exercise Render edge configuration.
- Android device exploration is `NOT_VERIFIABLE`: `adb devices -l` reported no
  attached or running device. Mobile evidence is responsive Playwright viewport
  emulation, not physical-device evidence.

## Security and reliability limits

Sessions are anonymous and do not authenticate a person or make demo approval
an administrative approval. HttpOnly, SameSite=Lax, Secure-on-HTTPS, strict
CORS, opaque random tokens, hashed-at-rest session identifiers, idle expiry,
and server-side ownership are implemented. XSS in the same origin can still
perform actions using the current visitor's cookie.

The active session, issuance, rate, solver, and database bounds are applied by
each API process. Rate/solver controls are not distributed across multiple
workers. The configured `/tmp` database is ephemeral; Render instance replacement
can invalidate visitor state. Those deployment properties require live
verification and are not represented as passed here.

## Status

Local isolation verification is tracked in `artifacts/concurrency/final_acceptance.json`.
Load measurements are tracked in `PUBLIC_DEMO_LOAD_TEST_REPORT.md` and its JSON
artifact. Render deployment and 10-visitor behavior must remain `NOT_VERIFIABLE`
or `PARTIAL` unless measured against the exact deployed SHA.

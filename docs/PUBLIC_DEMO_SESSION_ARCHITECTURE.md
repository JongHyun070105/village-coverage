# Public Demo Session Architecture

## Status

This document describes the local implementation on `fix/public-demo-concurrency`.
It does not claim a Render deployment or production verification.

## Trust boundary and storage

`PUBLIC_DEMO` remains disabled unless explicitly enabled. Public mode uses the
dedicated synthetic demo database and route database under the operating system
temporary directory; configured demo paths are accepted only when they resolve
inside that directory. The public mode never switches to the pilot database.

Reference population, facilities, policy definitions, and generated routes are
shared baseline data. A visitor's mutable state is separate:

- The API issues a 256-bit random opaque token. SQLite stores its SHA-256 hash,
  not the token, in `public_demo_sessions`.
- `public_demo_plan_owners` binds each created plan to that registered session.
- `public_demo_provider_participations` stores decline/restore state by session,
  provider, and round. It does not write public demo changes to the shared
  provider participation table.
- Plan list/detail, replan, revision, approval, cost model, explanations, memo,
  CSV, and PDF paths resolve the owner before returning or changing plan data.
  A plan owned by another visitor returns 404.

The frontend calls `/api` through the Next.js same-origin rewrite to the API
origin. This keeps the browser session cookie first-party even though the API
and frontend Render services use distinct hostnames.

## Cookie lifecycle

The API sets `vc_demo_session` with `Path=/api`, `HttpOnly`, `SameSite=Lax`, and
`Secure` on HTTPS (or when `PUBLIC_DEMO_COOKIE_SECURE=true`). The cookie is not
an authenticated identity. A 30-minute idle timeout refreshes on API activity.
Unknown, malformed, or expired tokens are replaced with a fresh server-issued
token. A known plan request after replacement returns `410 DEMO_SESSION_EXPIRED`
so an old direct link does not silently cross into another session.

SameSite and strict API CORS limit cross-site browser submission; JSON write
routes also require the application request shape. The cookie is HttpOnly, but
same-origin script injection could still issue actions as the current anonymous
visitor. This design is isolation for synthetic demo state, not login or CSRF
identity.

## Resource and fairness limits

Current per-process limits:

| Limit | Value |
|---|---:|
| Active sessions | 256 |
| Session issuance | 30 per minute |
| Idle session lifetime | 30 minutes |
| Plans per session | 20 |
| Demo SQLite size | 64 MiB |
| Ordinary requests per session | 20 per minute |
| Shared request ceiling | 120 per minute |
| Solver operations | 4 active, 6 queued, 15-second queue wait |

Rate-limit and solver counters are process-local. With multiple API workers or
instances, these limits multiply; a shared queue/counter service would be
needed for a strict deployment-wide ceiling. SQLite and the Render Free `/tmp`
filesystem are also ephemeral. Process restart can retain state only while that
container filesystem survives; a new instance or filesystem reset invalidates
old plans and the API asks the visitor to refresh. No durable cross-instance
session guarantee is claimed.

Expired cleanup deletes only rows linked to expired public demo sessions and
their demo plans, participations, and schedule audit rows. It does not sweep
pilot data, existing user files, or snapshots.

## Validation boundary

See `PUBLIC_DEMO_CONCURRENCY_AUDIT.md` for route coverage and test evidence. The
same-origin rewrite and cookie attributes are exercised by local Playwright
contexts. Real Render cookie behavior, deployment configuration, and service
restart behavior remain unverified until a verified deployment is available.

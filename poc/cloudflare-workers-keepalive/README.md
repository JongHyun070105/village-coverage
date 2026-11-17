# Cloudflare Workers Cron Trigger POC

Local-only proof of concept for pinging the **existing** Render Web and API health URLs. It does not proxy or migrate the website, write application data, restart Render, or deploy a Cloudflare Worker.

## Local test

Run from this directory:

```sh
node --test test/worker.test.mjs
```

The tests inject a fake `fetch`; they make no network requests. They cover the KST time gate, Web and API GET validation, parallel Web/API probing, the integrated `/api/health` GET at the 08:55 KST pre-warm and after recovery only, exact schedule-delay calculation, persistent 429, the observed 429 → 503 → 200 recovery flow, long 503 cold starts, strict `Retry-After` handling, the 18:00 cutoff, the Free-plan subrequest/concurrency limits, log allowlisting, and fail-closed cron validation. Time-dependent tests use a virtual clock, so they take milliseconds.

For Cloudflare's local scheduled-event runner, use Wrangler 4.139.0 or later with this directory's `wrangler.toml` (checked with Wrangler 4.158.0 in local `workerd`):

```sh
wrangler dev
curl "http://localhost:8787/cdn-cgi/local/scheduled?format=json&cron=5%2C15%2C25%2C35%2C45%2C55+0-7+*+*+*"
```

`/cdn-cgi/handler/scheduled` reaches the same handler; the legacy `/__scheduled` route needs `--test-scheduled`. Inside 08:55–17:59 KST this sends real GETs to the public Render URLs; outside it the handler logs `skipped_window` and sends none. The handler throws for every outcome other than `ok`, so a local `skipped_window` run returns HTTP 500 and a deployed one shows as an exception in Cron Events.

The built-in Node tests are the reproducible offline check. No Wrangler installation or Cloudflare account access was available or needed for this POC.

## Schedule and bounds

The three UTC triggers match the existing GitHub schedule. The handler checks `Asia/Seoul` time before each attempt and blocks new requests at or after 18:00 KST.

### Retry and budget policy

- **Parallel probes.** Web and API are probed independently with `Promise.allSettled`; at most two outbound requests are in flight. A failure or exception in one never delays the other.
- **Budgets.** Each of Web/API has a 150-second recovery budget and at most 12 attempts; the whole invocation stops after 180 seconds (well below the 10-minute Cron interval). Requests time out after 10 seconds (or the remaining budget, if shorter).
- **HTTP 429.** Wait a valid `Retry-After` (integer seconds or HTTP-date, never less than 5 s), otherwise 30 s. At most 5 consecutive 429 attempts per endpoint (`rate_limited_max_attempts`). The limit is 5 rather than 4 because the incident flow of 10:25 KST on 2026-11-17 had 429 responses for roughly 75–95 s before 503 and 200; a limit of 4 fails that recoverable flow (covered by tests).
- **HTTP 5xx, timeouts, network errors, invalid bodies.** Wait a valid `Retry-After` (min 5 s), otherwise a fixed 10 s (Render documents about one minute to spin up a Free service). A 429 → 5xx transition resets the 429 counter. A 200 after any retry is `recovered`.
- **Stop conditions, each recorded in `failure`.** `retry_after_exceeds_remaining_budget` / `retry_delay_exceeds_remaining_budget` (no sleep is started that would outlast the budget), `request_completed_after_budget`, `retry_would_cross_1800_kst`, `rate_limited_max_attempts`, `maximum_attempts_exhausted`. When a stop reason replaces the original failure, `endpoint_complete` also carries `last_cause`. Non-retryable statuses (for example 404) fail on the first attempt. Invalid `Retry-After` values (negative, fractional, exponent, free text) are ignored.
- **Integrated health.** `/api/health` is probed after Web and API: always on the 08:55 pre-warm, otherwise only after a recovery, and only if both Web and API are healthy (otherwise it is skipped and `integrated_health: "skipped_prior_failure"` is logged). It has its own 30 s / 4-attempt budget.
- **Request ceiling.** 12 + 12 + 4 = 28 GETs and about 180 s in the worst case; persistent 429 ends after 10 GETs and 120 s; persistent 503 after 24 GETs and about 110 s.

### Diagnostic logging

Logged per attempt: `service`, `status`, `attempt`, `elapsed_ms`, `failure`, `outcome`, and an allowlist of response headers (`Retry-After` as `retry_after_header`, `Server`, `CF-Ray` as `cf_ray`, `x-render-routing` as `render_routing`, `rndr-id` as `render_id`). Values are limited to 64 printable ASCII characters. No body, cookie, authorization header, URL credentials, or user data is logged. These headers are hints only: they do not by themselves prove which hop returned a 429. Render documents that it can return 429 for inbound rate limiting, but that the observed 429s came from Render is not established. `x-render-routing` and `rndr-id` were not confirmed against Render's documentation; they are logged as `null` when absent.

Cloudflare's documented Workers Free limits are 100,000 requests/day, 10 ms CPU per Cron invocation, 50 subrequests per invocation, and five Cron Triggers per account. This POC uses three triggers and 54 scheduled invocations per day. If every first attempt succeeds, the schedule sends 109 outbound GETs/day (53 normal invocations × 2 plus the 3-GET 08:55 pre-warm). The attempt caps allow at most 12 + 12 + 4 = 28 GETs in one invocation even with a frozen clock, below the 50-subrequest per-invocation limit, and at most 2 outbound requests are in flight (limit: 6 simultaneous connections); both bounds are covered by tests. Redirects are not followed, so they add no subrequests. The 180-second run bound is far below Cloudflare's 15-minute Cron wall-time limit. Account-wide existing trigger use and the account's current plan remain unchecked; those must be confirmed before deployment. Cloudflare's current Standard Workers pricing shows a $5 monthly subscription and usage charges above included limits. Do not deploy unless Workers Free is confirmed. Do not upgrade, add a payment method, or permit paid overage.

Permission scope also needs approval: creating a new Worker requires Workers product Admin; updating an already existing Worker can use per-Worker Editor. This Cron-only POC has no route or custom domain, so Routes permissions are unnecessary. No Cloudflare credential has been created or used. See [Workers roles and permissions](https://developers.cloudflare.com/workers/authorization/workers/).

Cloudflare Cron Triggers use UTC and expose `controller.scheduledTime`, allowing the handler to log actual delay. `wrangler.toml` enables Workers Logs (`[observability] enabled = true`, `head_sampling_rate = 1`) so structured JSON events (`scheduled_start`, `endpoint_attempt`, `endpoint_complete`, `scheduled_complete`) are collected once deployed with `scheduled_at`, `started_at`, `scheduled_delay_seconds`, `request_sent`, `method`, `status`, `attempts`, `retries`, `elapsed_ms`, `outcome`, and `failure` without logging response bodies, query strings, or PII. Workers Logs is not permanent storage: until 2026-11-30 the Workers Free plan keeps up to 200,000 log events/day for 3 days; from 2026-12-01 Workers Logs moves to Cloudflare Observability pricing (Free: 0.5 GB/day ingestion, 7-day retention). Workers Logpush requires Workers Paid. Enabling the setting is not evidence that logs were collected; and the Cron Events dashboard retains the 100 most recent invocations (~1.85 days at 54 invocations/day). The docs do not state a delivery SLA or an automatic catch-up guarantee. Treat Cloudflare as an unproven fallback until deployed under separate approval and observed in real Cron Events and Render request logs. Cron configuration changes may take up to 15 minutes to propagate.

## Cutover gate

Do not deploy this POC in parallel with GitHub Actions. First approve the scheduler switch; then disable GitHub's `schedule` trigger while retaining `workflow_dispatch` for diagnostics, deploy Cloudflare with only the three listed triggers, and verify its scheduled GETs against Render's request logs. If Cloudflare fails verification, disable its Cron Triggers before re-enabling GitHub's `schedule`. Keep the existing Render URLs, and keep SQLite/data-loss and Render deployment approval gates unchanged.

## Cutover without two schedulers

`wrangler.toml` declares Cron Triggers, so deploying it activates them (propagation can take up to 15 minutes). `wrangler.nocron.toml` is the same Worker with `crons = []`, which removes every deployed trigger; omitting or commenting out `[triggers]` would leave existing triggers in place. Use it to upload the Worker without schedules and as the rollback switch. Run the cutover outside 08:55–17:59 KST so that neither scheduler sends requests while one is being turned off and the other on: disable `.github/workflows/render-free-keepalive.yml`, confirm no scheduled run is queued or in progress, then deploy `wrangler.toml`. To roll back, deploy `wrangler.nocron.toml`, wait for propagation and for Cron Events to show no new invocation, then re-enable the GitHub workflow. Every deploy, trigger change, and workflow change needs separate user approval.

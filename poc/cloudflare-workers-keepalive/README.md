# Cloudflare Workers Cron Trigger POC

Local-only proof of concept for pinging the **existing** Render Web and API health URLs. It does not proxy or migrate the website, write application data, restart Render, or deploy a Cloudflare Worker.

## Local test

Run from this directory:

```sh
node --test test/worker.test.mjs
```

The tests inject a fake `fetch`; they make no network requests. They cover the KST time gate, Web and API GET validation, the integrated `/api/health` GET at the 08:55 KST pre-warm and after recovery, exact schedule-delay calculation, 40-second Web and 90-second API cold starts, bounded `Retry-After`, the 18:00 cutoff, and fail-closed cron validation.

For Cloudflare's local scheduled-event runner, use Wrangler 4.139.0 or later with this directory's `wrangler.toml` (checked with Wrangler 4.158.0 in local `workerd`):

```sh
wrangler dev
curl "http://localhost:8787/cdn-cgi/local/scheduled?format=json&cron=5%2C15%2C25%2C35%2C45%2C55+0-7+*+*+*"
```

`/cdn-cgi/handler/scheduled` reaches the same handler; the legacy `/__scheduled` route needs `--test-scheduled`. Inside 08:55–17:59 KST this sends real GETs to the public Render URLs; outside it the handler logs `skipped_window` and sends none. The handler throws for every outcome other than `ok`, so a local `skipped_window` run returns HTTP 500 and a deployed one shows as an exception in Cron Events.

The built-in Node tests are the reproducible offline check. No Wrangler installation or Cloudflare account access was available or needed for this POC.

## Schedule and bounds

The three UTC triggers match the existing GitHub schedule. The handler checks `Asia/Seoul` time before each attempt and blocks new requests at or after 18:00 KST. Each endpoint has at most 16 attempts and a four-minute wall-clock budget; the whole invocation stops after eight minutes. Requests time out after 10 seconds. Automatic backoff is 5, 10, then at most 20 seconds. A valid `Retry-After` is followed up to 180 seconds, and the retry is abandoned if it would cross 18:00 or exceed a hard budget. It logs Cloudflare's scheduled time, actual start, calculated delay, endpoint label, HTTP status, failure reason, elapsed milliseconds, retry delay, and outcome. It logs no response body, URL credentials, or user data. Redirects are not followed. Only GET requests to the existing public Render endpoints are made.

Cloudflare's documented Workers Free limits are 100,000 requests/day, 10 ms CPU per Cron invocation, 50 subrequests per invocation, and five Cron Triggers per account. This POC uses three triggers and 54 scheduled invocations per day. If every first attempt succeeds, the schedule sends 109 outbound GETs/day. Its retry cap allows at most 48 GETs in one 08:55 invocation (16 attempts for each of three endpoints) even with a frozen clock, below the 50-subrequest per-invocation limit. With real 5/10/20-second backoff inside the 4-minute endpoint and 8-minute run budgets, persistent instant 503s reach only 14 + 14 + 2 = 30 GETs; both bounds are covered by tests. Redirects are not followed, so they add no subrequests. The Cron handler's eight-minute bound is below Cloudflare's 15-minute Cron wall-time limit. Account-wide existing trigger use and the account's current plan remain unchecked; those must be confirmed before deployment. Cloudflare's current Standard Workers pricing shows a $5 monthly subscription and usage charges above included limits. Do not deploy unless Workers Free is confirmed. Do not upgrade, add a payment method, or permit paid overage.

Permission scope also needs approval: creating a new Worker requires Workers product Admin; updating an already existing Worker can use per-Worker Editor. This Cron-only POC has no route or custom domain, so Routes permissions are unnecessary. No Cloudflare credential has been created or used. See [Workers roles and permissions](https://developers.cloudflare.com/workers/authorization/workers/).

Cloudflare Cron Triggers use UTC and expose `controller.scheduledTime`, allowing the handler to log actual delay. `wrangler.toml` enables Workers Logs (`[observability] enabled = true`, `head_sampling_rate = 1`) so structured JSON events (`scheduled_start`, `endpoint_attempt`, `endpoint_complete`, `scheduled_complete`) are collected once deployed with `scheduled_at`, `started_at`, `scheduled_delay_seconds`, `request_sent`, `method`, `status`, `attempts`, `retries`, `elapsed_ms`, `outcome`, and `failure` without logging response bodies, query strings, or PII. Workers Logs is not permanent storage: until 2026-11-30 the Workers Free plan keeps up to 200,000 log events/day for 3 days; from 2026-12-01 Workers Logs moves to Cloudflare Observability pricing (Free: 0.5 GB/day ingestion, 7-day retention). Workers Logpush requires Workers Paid. Enabling the setting is not evidence that logs were collected; and the Cron Events dashboard retains the 100 most recent invocations (~1.85 days at 54 invocations/day). The docs do not state a delivery SLA or an automatic catch-up guarantee. Treat Cloudflare as an unproven fallback until deployed under separate approval and observed in real Cron Events and Render request logs. Cron configuration changes may take up to 15 minutes to propagate.

## Cutover gate

Do not deploy this POC in parallel with GitHub Actions. First approve the scheduler switch; then disable GitHub's `schedule` trigger while retaining `workflow_dispatch` for diagnostics, deploy Cloudflare with only the three listed triggers, and verify its scheduled GETs against Render's request logs. If Cloudflare fails verification, disable its Cron Triggers before re-enabling GitHub's `schedule`. Keep the existing Render URLs, and keep SQLite/data-loss and Render deployment approval gates unchanged.

## Cutover without two schedulers

`wrangler.toml` declares Cron Triggers, so deploying it activates them (propagation can take up to 15 minutes). `wrangler.nocron.toml` is the same Worker with `crons = []`, which removes every deployed trigger; omitting or commenting out `[triggers]` would leave existing triggers in place. Use it to upload the Worker without schedules and as the rollback switch. Run the cutover outside 08:55–17:59 KST so that neither scheduler sends requests while one is being turned off and the other on: disable `.github/workflows/render-free-keepalive.yml`, confirm no scheduled run is queued or in progress, then deploy `wrangler.toml`. To roll back, deploy `wrangler.nocron.toml`, wait for propagation and for Cron Events to show no new invocation, then re-enable the GitHub workflow. Every deploy, trigger change, and workflow change needs separate user approval.

# Render Free keep-alive

The workflow in `.github/workflows/render-free-keepalive.yml` sends sequential, unauthenticated `GET` requests to the existing Web and API services. It does not write to the database and does not trigger deploys or restarts. The integrated Web `/api/health` route is checked at the 08:55 KST pre-warm and after an endpoint needs recovery.

## Schedule and time gate

GitHub Actions cron uses UTC. The schedule runs every day, including weekends:

| UTC cron | Korea time |
| --- | --- |
| `55 23 * * *` | 08:55 pre-warm |
| `5,15,25,35,45,55 0-7 * * *` | 09:05 through 16:55, every ten minutes |
| `5,15,25,35,45 8 * * *` | 17:05 through 17:45, every ten minutes |

The script independently checks `Asia/Seoul` before each request and retry. It allows 08:55 through 17:59 KST and skips at or after 18:00. Scheduled events include the cron expression, but GitHub does not provide the original occurrence timestamp. With repeated ten-minute cron slots, the actual delay cannot be inferred from the cron expression and job start time, so the workflow validates known expressions but does not claim an exact delay or apply a misleading late-event threshold. Unknown schedule expressions fail closed. GitHub may delay or omit scheduled events, so the workflow is best-effort; events starting outside the KST window are skipped. GitHub does not automatically replay missed cron events. A later scheduled run can wake the services again. Manual dispatch follows the same KST time gate. GitHub also disables scheduled workflows in public repositories after 60 days without repository activity; re-enable it from the Actions page if that happens.

The single concurrency group avoids overlapping runs. If a workflow is already running, a newer event may wait; pending events can be replaced by later events. Calls are sequential with a 75-second timeout and at most three attempts per endpoint. `429`, `5xx`, network failures, and temporary non-JSON health wake responses receive bounded retries. A service failure is logged without preventing the other service from being checked. Responses are capped at 4 KiB and never printed. Redirects are not followed. Logs contain only endpoint labels, status, elapsed time, attempt count, and failure type.

## Free instance-hour estimate

Render documents 750 Free instance-hours per workspace per calendar month, shared across Free services. An idle Free web service normally spins down after 15 minutes. If the 08:55 request starts each service and the 17:45 request is the last visit, a nominal day uses about 9 hours 5 minutes per service:

| Month length | Web estimate | API estimate | Combined estimate |
| ---: | ---: | ---: | ---: |
| 30 days | 272.5 h | 272.5 h | 545 h |
| 31 days | 281.6 h | 281.6 h | 563.2 h |

These are schedule-based estimates, **not measured usage or a cap**. Because a delayed repeating schedule event cannot be tied to its original occurrence, the 17:45 ping may arrive later than planned while still inside the 08:55–17:59 KST request window. If the final ping arrives just before 18:00, the 15-minute idle timer may keep a service active until about 18:15; schedule-only usage could then reach about 559 h combined in a 30-day month or 579 h in a 31-day month. Visitors outside business hours, restarts, other Free services in the workspace, and Render accounting can increase actual usage further. This workflow cannot determine the workspace's complete included usage. Check Render Dashboard → Billing → Monthly Included Usage; do not treat its request log or this estimate as billing data. Review the workspace total at 600 h, reassess at 650 h, and require an operator decision at 700 h. Do not change service plans or add paid resources based on this workflow.

Render may restart services at any time, and a Free service's local filesystem is ephemeral. Keep-alive does not make SQLite durable. The demo database and its generated plans, approvals, and history must be treated as disposable demonstration data. Do not use this setup for records that must survive a restart or deploy. Persistent storage or database migration requires separate approval.

## Activation and verification

The workflow file is inert until merged into the repository's default branch. Merging it activates scheduled public requests to:

- `https://villagecoverage-public-demo-web.onrender.com/`
- `https://villagecoverage-public-demo-api.onrender.com/health`
- `https://villagecoverage-public-demo-web.onrender.com/api/health` at pre-warm or recovery

Review the scheduled times, destinations, and workspace-level usage before activating it. GitHub run history shows scheduled attempts and outcomes; it does not prove all events ran on time or that either service stayed awake continuously.

# Public Demo Load Test Report

## Scope and method

Run locally with `scripts/measure_public_demo_concurrency.py`. Each case used a
fresh temporary app SQLite database and temporary route SQLite database. No
request was sent to Render. The common workload used region
`pilot:홍성군 장곡면`, a ₩4,000,000 budget, the same seeded straight-line demo
routes, and the API's existing solver defaults (3 seconds, one solver worker).

Each visitor requested the dashboard, four policy plans and explanations,
minimum-coverage analysis, a plan, provider decline, replan, and plan detail.
Total request count also includes session issuance and one ownership-list check
per visitor. Latency samples cover core workflow API calls only. The “legacy”
case runs the current API while sharing one server-issued session across all
visitors and applying the former 20/minute ceiling; it is a policy simulation,
not a rerun of the old Git commit.

## Results

| Mode | Visitors | Requests (workflow) | Completed | 429 | Other failures | Elapsed | API avg / p50 / p95 ms | Solver avg / p95 ms | SQLite KiB |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Shared session, global 20/min | 1 | 16 (14) | 1/1 | 0 | 0 | 33.944 s | 2424 / 669 / 5229 | 4235 / 5229 | 2344 |
| Shared session, global 20/min | 3 | 39 (35) | 0/3 | 3 | 0 | 32.922 s | 2647 / 713 / 6451 | 4402 / 6451 | 2952 |
| Shared session, global 20/min | 5 | 46 (40) | 0/5 | 5 | 0 | 23.389 s | 2585 / 74 / 6724 | 4122 / 10400 | 2808 |
| Shared session, global 20/min | 10 | 51 (40) | 0/10 | 10 | 0 | 16.745 s | 2975 / 55 / 11728 | 3961 / 13651 | 2496 |
| Isolated, 20/session + 120 global | 1 | 16 (14) | 1/1 | 0 | 0 | 34.066 s | 2432 / 655 / 5251 | 4251 / 5251 | 2344 |
| Isolated, 20/session + 120 global | 3 | 48 (42) | 3/3 | 0 | 0 | 40.087 s | 2848 / 745 / 6391 | 4975 / 6417 | 3236 |
| Isolated, 20/session + 120 global | 5 | 80 (70) | 5/5 | 0 | 0 | 53.940 s | 3663 / 4054 / 11123 | 6397 / 11294 | 4108 |
| Isolated, 20/session + 120 global | 10 | 140 (120) | 8/10 | 0 | 2 | 88.350 s | 5848 / 4179 / 18308 | 10002 / 19087 | 5480 |

At 10 isolated visitors, two workflows stopped with `503 DEMO_SOLVER_CAPACITY`.
The bounded gate rejected excess work as designed; those two visitors did not
complete. The 5-visitor target completed without 429 or other failures. In the
shared-session runs, 3, 5, and 10 visitors encountered global throttling and
their shared plan list exposed other visitors' plan IDs. Isolated-session cases
reported zero cross-session plan IDs.

The process peak RSS high-water mark at the end of the suite was 363.14 MiB.
It is cumulative across cases and is not a per-visitor or per-case memory
measurement. The suite did not age sessions during the load run, so load-time
cleanup is `NOT_MEASURED`; the targeted expiry test verified expired demo plan
and participation cleanup. SQLite sizes above include app DB, route DB, and
present WAL/SHM files at the end of each case.

## Interpretation and limits

- Five local visitors completed the requested core flow under the new limits.
- Ten visitors exposed the bounded solver capacity: 8 completed, 2 received a
  retryable 503. The system did not lift or bypass the solver limit to improve
  the count.
- Duplicate replan requests return one child plan, but solver computations are
  not fully coalesced before work starts.
- Rate and solver counters are process-local. Multi-worker or multi-instance
  Render behavior can differ and needs live deployment measurement.
- This is in-process ASGI timing. It excludes browser, network, Render, and
  cold-start latency. It does not establish public-site capacity.
- Physical mobile-device evidence is `NOT_VERIFIABLE`; no Android device was
  attached. Responsive browser viewport tests passed.

Machine-readable request and latency records: `artifacts/concurrency/public_demo_load_test.json`.
